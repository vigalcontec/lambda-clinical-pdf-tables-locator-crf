"""Textract event generation utilities."""

from typing import Any

from aws_lambda_powertools import Logger

from handler.utils.pdf import extract_product_type

logger = Logger()


def generate_textract_events(
    page_info: list[dict[str, Any]],
    s3_bucket: str,
    s3_key: str,
    product_name: str,
    job_id: str,
) -> list[dict[str, Any]]:
    """Generate Textract events for each page containing a table.

    Creates one event per page, handling multi-page tables where continuation
    pages don't have "Table X:" headers. Continuation pages inherit the
    table name from the previous table.

    For multi-product PDFs (e.g., different formulations of the same drug),
    tables are associated with their specific formulation using formulation_key.
    This allows "Table 1" to exist multiple times in the same PDF, once per
    formulation section.

    Each event is self-contained with all info needed for Textract lambda,
    ready for Step Functions Distributed Map processing.

    Args:
        page_info: List of page analysis dictionaries from analyze_pdf_pages
        s3_bucket: S3 bucket containing the PDF
        s3_key: S3 key of the PDF
        product_name: Product name to include in events
        job_id: Unique job identifier (file hash) for tracking

    Returns:
        List of events ready for Textract lambda (one per page):
        [
            {
                "job_id": "abc123...",
                "s3_bucket": "bucket-name",
                "s3_key": "path/to/document.pdf",
                "product_name": "Keytruda",
                "table_name": "Table 1: ...",
                "table_number": 1,
                "page": 7,
                "table_index_on_page": 0,
                "formulation_key": "840_1200mg",  # For multi-product PDFs
                "formulations": ["Tecentriq 840 mg ...", "Tecentriq 1200 mg ..."],
                "product_type": "film-coated tablets"  # Dosage form
            },
            ...
        ]
    """
    textract_events: list[dict[str, Any]] = []

    # Track current table info for continuation pages (per formulation)
    current_table_number: int | None = None
    current_table_name: str = ""
    current_formulation_key: str | None = None

    # Check if this is a multi-product PDF
    formulation_keys = {p.get("formulation_key") for p in page_info if p.get("formulation_key")}
    is_multi_product = len(formulation_keys) > 1

    for info in page_info:
        page_num = info["page"]
        table_identifiers = info["table_identifiers"]
        tables_count = info["tables_count"]
        has_table_structure = info["has_table_structure"]
        formulation_key = info.get("formulation_key")
        formulations = info.get("formulations", [])

        # Reset tracking when formulation changes (new product section)
        if formulation_key and formulation_key != current_formulation_key:
            current_table_number = None
            current_table_name = ""
            current_formulation_key = formulation_key

        if not has_table_structure:
            # No table on this page, reset current table tracking
            current_table_number = None
            current_table_name = ""
            continue

        if table_identifiers:
            # This page has table identifier(s) - new table(s) start here
            for idx, identifier in enumerate(table_identifiers):
                table_number = identifier["table_number"]
                table_name = f"Table {table_number}: {identifier['description']}"

                # Determine table_index_on_page for this table
                table_index = idx if idx < tables_count else 0

                event = {
                    "job_id": job_id,
                    "s3_bucket": s3_bucket,
                    "s3_key": s3_key,
                    "product_name": product_name,
                    "table_name": table_name,
                    "table_number": table_number,
                    "page": page_num,
                    "table_index_on_page": table_index,
                }

                # Add formulation info and product type
                if formulation_key:
                    event["formulation_key"] = formulation_key
                if formulations:
                    event["formulations"] = formulations
                    event["product_type"] = extract_product_type(formulations)

                textract_events.append(event)

                # Track the last table on this page for continuation detection
                current_table_number = table_number
                current_table_name = table_name

        elif current_table_number is not None:
            # This page has table structure but NO identifier
            # It's a continuation of the previous table
            event = {
                "job_id": job_id,
                "s3_bucket": s3_bucket,
                "s3_key": s3_key,
                "product_name": product_name,
                "table_name": current_table_name,
                "table_number": current_table_number,
                "page": page_num,
                "table_index_on_page": 0,  # Continuation pages have single table
            }

            # Add formulation info and product type
            if formulation_key:
                event["formulation_key"] = formulation_key
            if formulations:
                event["formulations"] = formulations
                event["product_type"] = extract_product_type(formulations)

            textract_events.append(event)

    # Sort by formulation_key (if present), then table number, then page
    if is_multi_product:
        textract_events.sort(key=lambda x: (
            x.get("formulation_key", ""),
            x["table_number"],
            x["page"]
        ))
    else:
        textract_events.sort(key=lambda x: (x["table_number"], x["page"]))

    logger.info(
        "Textract events generated",
        extra={
            "events_count": len(textract_events),
            "product_name": product_name,
            "is_multi_product": is_multi_product,
            "formulation_keys": list(formulation_keys) if is_multi_product else None,
        }
    )

    return textract_events
