"""AWS Lambda Handler - Clinical PDF Tables Locator.

This Lambda function analyzes PDF documents to identify pages containing tables
and generates events for downstream Textract processing.
"""

from typing import Any

from aws_lambda_powertools import Logger, Tracer
from aws_lambda_powertools.utilities.typing import LambdaContext

from handler.config import get_settings
from handler.utils import (
    analyze_pdf_pages,
    download_pdf_from_s3,
    generate_file_hash,
    generate_textract_events,
    get_total_pages,
)

logger = Logger()
tracer = Tracer()


@logger.inject_lambda_context(log_event=True)
@tracer.capture_lambda_handler
def handler(event: dict[str, Any], _context: LambdaContext) -> dict[str, Any]:
    """Lambda handler for PDF table locator.

    Expected event payload:
        {
            "s3_bucket": "bucket-name",
            "s3_key": "path/product_name/yyyymmddhhmmss/document.pdf"
        }

    The product_name is extracted from the s3_key path (second-to-last directory).

    Returns:
        {
            "status": "SUCCESS",
            "s3_bucket": "bucket-name",
            "s3_key": "path/to/document.pdf",
            "product_name": "Keytruda",
            "file_hash": "sha256-hash",
            "total_pages": 100,
            "total_tables": 25,
            "textract_events": [
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
        }

    Step Functions Distributed Map uses $.textract_events as ItemsPath,
    and each event is self-contained for the Textract lambda.
    """
    settings = get_settings()
    logger.info("Starting PDF table locator", extra={"environment": settings.environment})

    try:
        # Validate input
        bucket = event.get("s3_bucket")
        key = event.get("s3_key")

        if not bucket or not key:
            raise ValueError("Missing 's3_bucket' or 's3_key' in event payload.")

        # Extract product_name from s3_key path
        # Expected format: path/product_name/yyyymmddhhmmss/document.pdf
        key_parts = key.split("/")
        if len(key_parts) >= 3:
            product_name = key_parts[-3]  # Second-to-last directory
        else:
            product_name = ""
            logger.warning("Could not extract product_name from s3_key", extra={"key": key})

        logger.info(
            "Processing document",
            extra={"bucket": bucket, "key": key, "product_name": product_name}
        )

        # Download PDF
        pdf_bytes = download_pdf_from_s3(bucket, key)

        if len(pdf_bytes) == 0:
            raise ValueError(f"Downloaded PDF is empty: s3://{bucket}/{key}")

        logger.info("PDF downloaded", extra={"size_bytes": len(pdf_bytes)})

        # Generate hash for idempotency
        file_hash = generate_file_hash(pdf_bytes)

        # Analyze PDF pages
        total_pages = get_total_pages(pdf_bytes)
        page_info = analyze_pdf_pages(pdf_bytes)

        # Generate Textract events (self-contained for Distributed Map)
        textract_events = generate_textract_events(page_info, bucket, key, product_name)

        # Count unique tables
        unique_tables = len({e["table_number"] for e in textract_events})

        logger.info(
            "Analysis completed",
            extra={
                "total_pages": total_pages,
                "total_tables": unique_tables,
                "textract_events_count": len(textract_events),
                "file_hash": file_hash,
            },
        )

        return {
            "status": "SUCCESS",
            "s3_bucket": bucket,
            "s3_key": key,
            "product_name": product_name,
            "file_hash": file_hash,
            "total_pages": total_pages,
            "total_tables": unique_tables,
            "textract_events": textract_events,
        }

    except Exception as e:
        logger.exception("Error processing PDF")
        return {
            "status": "FAILED",
            "error": str(e),
            "s3_bucket": event.get("s3_bucket"),
            "s3_key": event.get("s3_key"),
        }


# if __name__ == "__main__":
#     import json
#     import os

#     os.environ.setdefault("POWERTOOLS_TRACE_DISABLED", "true")

#     # Lambda simulation with S3 event
#     class MockContext:
#         function_name = "local-test"
#         memory_limit_in_mb = 256
#         invoked_function_arn = "arn:aws:lambda:eu-west-1:123456789012:function:local-test"
#         aws_request_id = "local-request-id"

#     # Test event with product_name extracted from s3_key path
#     # Format: path/product_name/yyyymmddhhmmss/document.pdf
#     test_event = {
#         "s3_bucket": "datalake-raw-vigalcontec-dev-002332700133",
#         "s3_key": "crf/clinical_pdfs/Keytruda/20260520173800/keytruda-epar-product-information_en.pdf",
#     }

#     result = handler(test_event, MockContext())

#     logger.info(
#         "Handler result",
#         extra={
#             "status": result["status"],
#             "product_name": result.get("product_name"),
#             "total_tables": result.get("total_tables"),
#             "events_count": len(result.get("textract_events", [])),
#         }
#     )

#     # Pretty print the result
#     print(json.dumps(result, indent=2, ensure_ascii=False))
