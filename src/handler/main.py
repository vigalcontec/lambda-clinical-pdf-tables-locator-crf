"""AWS Lambda Handler - Clinical PDF Tables Locator.

This Lambda function performs triage on PDF documents to identify pages
containing tables with clinical data (efficacy, adverse events, etc.).
It's designed to be called from a Step Function workflow.
"""

import hashlib
from typing import Any

import boto3
import fitz  # PyMuPDF
from aws_lambda_powertools import Logger, Tracer
from aws_lambda_powertools.utilities.typing import LambdaContext

from handler.config import get_settings

logger = Logger()
tracer = Tracer()

s3_client = boto3.client("s3")

# Keywords indicating relevant clinical data (EMA reports in English)
KEYWORDS = ["table", "efficacy", "adverse events", "safety", "clinical trial"]


@tracer.capture_method
def download_pdf_from_s3(bucket: str, key: str) -> bytes:
    """Download PDF from S3 directly into memory."""
    logger.info("Downloading PDF from S3", extra={"bucket": bucket, "key": key})
    response = s3_client.get_object(Bucket=bucket, Key=key)
    return response["Body"].read()


@tracer.capture_method
def generate_file_hash(pdf_bytes: bytes) -> str:
    """Generate SHA256 hash for idempotency checks."""
    return hashlib.sha256(pdf_bytes).hexdigest()


@tracer.capture_method
def find_pages_with_tables(pdf_bytes: bytes) -> list[int]:
    """Scan PDF pages and identify those containing relevant tables.

    Args:
        pdf_bytes: PDF file content as bytes

    Returns:
        List of 1-indexed page numbers containing tables
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages_with_tables = []

    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        text = page.get_text("text").lower()

        if any(keyword in text for keyword in KEYWORDS):
            # Add 1 because PyMuPDF is 0-indexed, but Textract and humans use 1-indexed
            pages_with_tables.append(page_num + 1)

    doc.close()
    return pages_with_tables


@logger.inject_lambda_context(log_event=True)
@tracer.capture_lambda_handler
def handler(event: dict[str, Any], _context: LambdaContext) -> dict[str, Any]:
    """Lambda handler for PDF table triage.

    Expected event payload from Step Function:
        {
            "s3_bucket": "bucket-name",
            "s3_key": "path/to/document.pdf"
        }

    Returns:
        {
            "status": "SUCCESS",
            "file_hash": "sha256-hash",
            "total_pages": 100,
            "pages_to_process": [1, 5, 12, ...]
        }
    """
    settings = get_settings()
    logger.info("Starting PDF triage", extra={"environment": settings.environment})

    # Validate input contract
    bucket = event.get("s3_bucket")
    key = event.get("s3_key")

    if not bucket or not key:
        raise ValueError("Missing 's3_bucket' or 's3_key' in event payload.")

    logger.info(f"Processing document: s3://{bucket}/{key}")

    # Download PDF into memory
    pdf_bytes = download_pdf_from_s3(bucket, key)

    # Generate hash for idempotency (detect duplicate uploads with different names)
    file_hash = generate_file_hash(pdf_bytes)
    logger.info("File hash generated", extra={"file_hash": file_hash})

    # Scan pages for tables
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    total_pages = len(doc)
    doc.close()

    pages_with_tables = find_pages_with_tables(pdf_bytes)

    logger.info(
        "Triage completed",
        extra={
            "total_pages": total_pages,
            "pages_with_tables": len(pages_with_tables),
            "file_hash": file_hash,
        },
    )

    # Return structured payload for Step Function Distributed Map
    return {
        "status": "SUCCESS",
        "file_hash": file_hash,
        "total_pages": total_pages,
        "pages_to_process": pages_with_tables,
    }
