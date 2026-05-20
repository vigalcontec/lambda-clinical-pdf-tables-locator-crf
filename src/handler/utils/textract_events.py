"""Textract event generation utilities."""

from typing import Any

from aws_lambda_powertools import Logger

logger = Logger()


def generate_textract_events(
    page_info: list[dict[str, Any]],
    s3_bucket: str,
    s3_key: str,
    product_name: str,
) -> list[dict[str, Any]]:
    """Generate Textract events for each page containing a table.
    
    Creates one event per page, handling multi-page tables where continuation
    pages don't have "Table X:" headers. Continuation pages inherit the
    table name from the previous table.
    
    Each event is self-contained with all info needed for Textract lambda,
    ready for Step Functions Distributed Map processing.
    
    Args:
        page_info: List of page analysis dictionaries from analyze_pdf_pages
        s3_bucket: S3 bucket containing the PDF
        s3_key: S3 key of the PDF
        product_name: Product name to include in events
        
    Returns:
        List of events ready for Textract lambda (one per page):
        [
            {
                "s3_bucket": "bucket-name",
                "s3_key": "path/to/document.pdf",
                "product_name": "Keytruda",
                "table_name": "Table 1: ...",
                "table_number": 1,
                "page": 7,
                "table_index_on_page": 0
            },
            ...
        ]
    """
    textract_events: list[dict[str, Any]] = []
    
    # Track current table info for continuation pages
    current_table_number: int | None = None
    current_table_name: str = ""
    
    for info in page_info:
        page_num = info["page"]
        table_identifiers = info["table_identifiers"]
        tables_count = info["tables_count"]
        has_table_structure = info["has_table_structure"]
        
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
                
                textract_events.append({
                    "s3_bucket": s3_bucket,
                    "s3_key": s3_key,
                    "product_name": product_name,
                    "table_name": table_name,
                    "table_number": table_number,
                    "page": page_num,
                    "table_index_on_page": table_index,
                })
                
                # Track the last table on this page for continuation detection
                current_table_number = table_number
                current_table_name = table_name
        
        elif current_table_number is not None:
            # This page has table structure but NO identifier
            # It's a continuation of the previous table
            textract_events.append({
                "s3_bucket": s3_bucket,
                "s3_key": s3_key,
                "product_name": product_name,
                "table_name": current_table_name,
                "table_number": current_table_number,
                "page": page_num,
                "table_index_on_page": 0,  # Continuation pages have single table
            })
    
    # Sort by table number, then by page
    textract_events.sort(key=lambda x: (x["table_number"], x["page"]))
    
    logger.info(
        "Textract events generated",
        extra={"events_count": len(textract_events), "product_name": product_name}
    )
    
    return textract_events
