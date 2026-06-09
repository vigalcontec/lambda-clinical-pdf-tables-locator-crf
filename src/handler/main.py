"""AWS Lambda Handler - Clinical PDF Tables Locator.

This Lambda function analyzes PDF documents to identify pages containing tables
and generates events for downstream Textract processing.
"""

from typing import Any
from urllib.parse import unquote_plus

from aws_lambda_powertools import Logger, Tracer
from aws_lambda_powertools.utilities.typing import LambdaContext

from handler.config import get_settings
from handler.utils import (
    analyze_pdf_pages,
    create_job_record,
    download_pdf_from_s3,
    filter_pending_events,
    generate_file_hash,
    generate_textract_events,
    get_job_status,
    get_total_pages,
    update_job_status,
    upload_json_to_s3,
)

logger = Logger()
tracer = Tracer()


@logger.inject_lambda_context(log_event=True)
@tracer.capture_lambda_handler
def handler(event: dict[str, Any], _context: LambdaContext) -> None:
    """Lambda handler for PDF table locator.

    Expected event payload:
        {
            "s3_bucket": "bucket-name",
            "s3_key": "path/product_name/yyyymmddhhmmss/document.pdf"
        }

    The product_name is extracted from the s3_key path (second-to-last directory).

    Output:
        - S3: Uploads textract events JSON to {s3_key}_events.json
        - DynamoDB: Creates job record with metadata

    No return value - results stored in S3/DynamoDB to avoid 6MB Lambda response limit.
    On error, raises exception and updates DynamoDB job status to FAILED.
    """
    settings = get_settings()
    logger.info("Starting PDF table locator", extra={"environment": settings.environment})

    try:
        # Extract bucket and key from event
        # Support both S3 trigger format and direct invocation format
        if "Records" in event:
            # S3 trigger format
            record = event["Records"][0]
            bucket = record["s3"]["bucket"]["name"]
            key = record["s3"]["object"]["key"]
            # URL decode the key (S3 encodes special characters)
            key = unquote_plus(key)
        else:
            # Direct invocation format
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

        # Use file_hash as job_id for idempotency
        job_id = file_hash

        # Check for force_reprocess flag (bypasses idempotency)
        force_reprocess = event.get("force_reprocess", False)

        # Generate Textract events (self-contained for Distributed Map)
        all_textract_events = generate_textract_events(page_info, bucket, key, product_name, job_id)

        # Count unique tables (before filtering)
        unique_tables = len({e["table_number"] for e in all_textract_events})

        # Check if job already exists and filter to only pending tables
        # Skip this check if force_reprocess is True
        existing_job = None if force_reprocess else get_job_status(settings.dynamodb_table_name, job_id)
        is_reprocessing = existing_job is not None

        if force_reprocess:
            logger.info(
                "Force reprocess enabled - processing all tables",
                extra={"job_id": job_id, "total_events": len(all_textract_events)},
            )

        if is_reprocessing:
            # Filter to only include tables that need processing
            # (not yet processed or previously failed)
            textract_events = filter_pending_events(
                table_name=settings.dynamodb_table_name,
                job_id=job_id,
                textract_events=all_textract_events,
                reprocess_failed=True,  # Reprocess failed tables
            )
            logger.info(
                "Reprocessing job - filtered to pending tables",
                extra={
                    "job_id": job_id,
                    "original_status": existing_job.get("status"),
                    "total_events": len(all_textract_events),
                    "pending_events": len(textract_events),
                    "skipped_events": len(all_textract_events) - len(textract_events),
                },
            )

            # If all tables already processed successfully, skip
            if not textract_events:
                logger.info(
                    "All tables already processed successfully, skipping",
                    extra={"job_id": job_id},
                )
                return

            # Update job status to REPROCESSING
            update_job_status(
                table_name=settings.dynamodb_table_name,
                job_id=job_id,
                status="REPROCESSING",
            )
        else:
            # New job or force reprocess - process all events
            textract_events = all_textract_events

            if force_reprocess:
                # Force reprocess: update existing job status
                update_job_status(
                    table_name=settings.dynamodb_table_name,
                    job_id=job_id,
                    status="REPROCESSING",
                )
            else:
                # New job: create job record in DynamoDB
                create_job_record(
                    table_name=settings.dynamodb_table_name,
                    job_id=job_id,
                    s3_bucket=bucket,
                    s3_key=key,
                    product_name=product_name,
                    file_hash=file_hash,
                    total_pages=total_pages,
                    total_tables=unique_tables,
                    textract_events_count=len(textract_events),
                )

        logger.info(
            "Analysis completed",
            extra={
                "total_pages": total_pages,
                "total_tables": unique_tables,
                "textract_events_count": len(textract_events),
                "file_hash": file_hash,
                "is_reprocessing": is_reprocessing,
                "force_reprocess": force_reprocess,
            },
        )

        # Upload textract events to S3 for Step Functions Distributed Map
        # Path: same as PDF but with _events.json suffix
        events_key = key.rsplit(".", 1)[0] + "_events.json"
        output_bucket = settings.output_s3_bucket or bucket
        events_s3_uri = upload_json_to_s3(
            bucket=output_bucket,
            key=events_key,
            data=textract_events,
        )

        logger.info(
            "Job completed successfully",
            extra={
                "job_id": job_id,
                "events_s3_uri": events_s3_uri,
                "dynamodb_table": settings.dynamodb_table_name,
                "textract_events_count": len(textract_events),
                "is_reprocessing": is_reprocessing,
            },
        )

        # No return - events are stored in S3, metadata in DynamoDB
        # This avoids Lambda response size limits (6MB)

    except Exception as e:
        logger.exception("Error processing PDF")

        # Try to update job status to FAILED if we have a job_id
        try:
            if "file_hash" in dir() and file_hash:
                update_job_status(
                    table_name=settings.dynamodb_table_name,
                    job_id=file_hash,
                    status="FAILED",
                    error_message=str(e),
                )
        except Exception:
            logger.warning("Could not update job status to FAILED")

        # Re-raise to mark Lambda invocation as failed
        raise


# if __name__ == "__main__":
#     import json
#     import os

#     os.environ.setdefault("POWERTOOLS_TRACE_DISABLED", "true")
#     os.environ.setdefault("ENVIRONMENT", "dev")
#     os.environ.setdefault("DYNAMODB_TABLE_NAME", "dynamodb-clinical-pdf-jobs-crf-dev")
#     os.environ.setdefault("OUTPUT_S3_BUCKET", "datalake-raw-vigalcontec-dev-002332700133")

#     # Clear settings cache to pick up new env vars
#     from handler.config import get_settings
#     get_settings.cache_clear()

#     # Local test mode - just analyze PDF without DynamoDB/S3 writes
#     LOCAL_TEST_MODE = True

#     if LOCAL_TEST_MODE:
#         # Direct PDF analysis test (no DynamoDB/S3)
#         from handler.utils import (
#             download_pdf_from_s3,
#             generate_file_hash,
#             get_total_pages,
#             analyze_pdf_pages,
#             generate_textract_events,
#         )

#         bucket = "datalake-raw-vigalcontec-dev-002332700133"
#         key = "crf/clinical_pdfs/tecentriq/20260603164300/tecentriq-epar-product-information_en.pdf"
#         product_name = "tecentriq"

#         print(f"\n{'='*60}")
#         print(f"LOCAL TEST: Analyzing PDF")
#         print(f"{'='*60}\n")

#         # Download and analyze
#         pdf_bytes = download_pdf_from_s3(bucket, key)
#         file_hash = generate_file_hash(pdf_bytes)
#         total_pages = get_total_pages(pdf_bytes)
#         page_info = analyze_pdf_pages(pdf_bytes)

#         # Generate events
#         textract_events = generate_textract_events(page_info, bucket, key, product_name, file_hash)

#         # Summary
#         pages_with_tables = [p for p in page_info if p["has_table_structure"]]
#         structural = [p for p in page_info if p.get("detection_method") == "structural"]
#         fallback = [p for p in page_info if p.get("detection_method") == "text_pattern"]

#         print(f"PDF Analysis Results:")
#         print(f"  - Total pages: {total_pages}")
#         print(f"  - Pages with tables: {len(pages_with_tables)}")
#         print(f"    - Structural detection: {len(structural)}")
#         print(f"    - Text pattern fallback: {len(fallback)}")
#         print(f"  - Textract events generated: {len(textract_events)}")
#         print(f"  - Unique tables: {len({e['table_number'] for e in textract_events})}")
#         print(f"  - File hash (job_id): {file_hash[:16]}...")

#         print(f"\n{'='*60}")
#         print(f"Sample Events (first 70):")
#         print(f"{'='*60}")
#         for event in textract_events[:70]:
#             print(json.dumps(event, indent=2))

#         print(f"\n{'='*60}")
#         print(f"Pages detected via text pattern fallback:")
#         print(f"{'='*60}")
#         for p in fallback[:10]:
#             identifiers = [f"Table {t['table_number']}" for t in p.get("table_identifiers", [])]
#             print(f"  Page {p['page']}: {', '.join(identifiers) if identifiers else 'continuation'}")

#     else:
#         # Full handler test
#         class MockContext:
#             function_name = "local-test"
#             memory_limit_in_mb = 256
#             invoked_function_arn = "arn:aws:lambda:eu-west-1:123456789012:function:local-test"
#             aws_request_id = "local-request-id"

#         test_event = {
#             "s3_bucket": "datalake-raw-vigalcontec-dev-002332700133",
#             "s3_key": "crf/clinical_pdfs/tecentriq/20260603164300/tecentriq-epar-product-information_en.pdf",
#         }

#         result = handler(test_event, MockContext())

#         logger.info(
#             "Handler result",
#             extra={
#                 "status": result["status"] if result else "N/A",
#                 "product_name": result.get("product_name") if result else "N/A",
#                 "total_tables": result.get("total_tables") if result else "N/A",
#                 "events_count": len(result.get("textract_events", [])) if result else 0,
#             }
#         )

#         # Pretty print the result
#         if result:
#             print(json.dumps(result, indent=2, ensure_ascii=False))
