"""DynamoDB utility functions for job tracking."""

from datetime import UTC, datetime
from functools import lru_cache
from typing import Any

import boto3
from aws_lambda_powertools import Logger, Tracer
from boto3.dynamodb.conditions import Key

logger = Logger()
tracer = Tracer()


# -----------------------------------------------------------------------------
# Job Status Queries
# -----------------------------------------------------------------------------


@tracer.capture_method
def get_job_status(table_name: str, job_id: str) -> dict[str, Any] | None:
    """Get job metadata from DynamoDB.

    Args:
        table_name: DynamoDB table name
        job_id: Job identifier (file hash)

    Returns:
        Job metadata dict or None if not found
    """
    table = _get_dynamodb_resource().Table(table_name)

    response = table.get_item(
        Key={"PK": f"JOB#{job_id}", "SK": "METADATA"}
    )

    item: dict[str, Any] | None = response.get("Item")
    if item:
        logger.info("Job found", extra={"job_id": job_id, "status": item.get("status")})
    else:
        logger.info("Job not found", extra={"job_id": job_id})

    return item


@tracer.capture_method(capture_response=False)
def get_processed_tables(table_name: str, job_id: str) -> dict[str, str]:
    """Get all processed table records for a job.

    Queries DynamoDB for all TABLE# records under a job to determine
    which tables have already been processed successfully.

    Args:
        table_name: DynamoDB table name
        job_id: Job identifier (file hash)

    Returns:
        Dict mapping table_key (e.g., "3_86") to status ("SUCCESS" or "FAILED")
        where table_key is "{table_number}_{page}"
    """
    table = _get_dynamodb_resource().Table(table_name)

    response = table.query(
        KeyConditionExpression=Key("PK").eq(f"JOB#{job_id}") & Key("SK").begins_with("TABLE#")
    )

    processed = {}
    for item in response.get("Items", []):
        # SK format: TABLE#{table_number}#PAGE#{page}
        sk = item.get("SK", "")
        status = item.get("status", "UNKNOWN")
        # Extract table_number and page from SK
        # Example: "TABLE#1#PAGE#5" -> table_number=1, page=5 -> key="1_5"
        parts = sk.split("#")
        # parts = ["TABLE", "1", "PAGE", "5"]
        if len(parts) >= 4:
            table_number = parts[1]
            page = parts[3]
            table_key = f"{table_number}_{page}"
            processed[table_key] = status

    logger.info(
        "Retrieved processed tables",
        extra={"job_id": job_id, "processed_count": len(processed)}
    )

    return processed


@tracer.capture_method(capture_response=False)
def filter_pending_events(
    table_name: str,
    job_id: str,
    textract_events: list[dict[str, Any]],
    reprocess_failed: bool = True,
) -> list[dict[str, Any]]:
    """Filter textract events to only include pending (not yet processed) tables.

    This enables incremental reprocessing - only tables that failed or were
    never processed will be included in the output.

    Args:
        table_name: DynamoDB table name
        job_id: Job identifier (file hash)
        textract_events: List of all textract events
        reprocess_failed: If True, include FAILED tables for reprocessing

    Returns:
        Filtered list of events for tables that need processing
    """
    processed = get_processed_tables(table_name, job_id)

    if not processed:
        logger.info("No processed tables found, returning all events")
        return textract_events

    pending_events = []
    skipped_count = 0

    for event in textract_events:
        table_key = f"{event['table_number']}_{event['page']}"
        status = processed.get(table_key)

        if status == "SUCCESS":
            # Already processed successfully, skip
            skipped_count += 1
            continue
        elif status == "FAILED" and not reprocess_failed:
            # Failed but not reprocessing failures
            skipped_count += 1
            continue
        else:
            # Not processed or failed (and reprocessing)
            pending_events.append(event)

    logger.info(
        "Filtered pending events",
        extra={
            "job_id": job_id,
            "total_events": len(textract_events),
            "pending_events": len(pending_events),
            "skipped_events": skipped_count,
            "reprocess_failed": reprocess_failed,
        }
    )

    return pending_events


@lru_cache
def _get_dynamodb_resource() -> Any:
    """Get cached DynamoDB resource."""
    return boto3.resource("dynamodb")


@tracer.capture_method
def create_job_record(
    table_name: str,
    job_id: str,
    s3_bucket: str,
    s3_key: str,
    product_name: str,
    file_hash: str,
    total_pages: int,
    total_tables: int,
    textract_events_count: int,
    ttl_days: int = 90,
) -> dict[str, Any]:
    """Create a job metadata record in DynamoDB.

    Args:
        table_name: DynamoDB table name
        job_id: Unique job identifier (typically file_hash or UUID)
        s3_bucket: Source S3 bucket
        s3_key: Source S3 key
        product_name: Product name extracted from path
        file_hash: SHA256 hash of the PDF
        total_pages: Total pages in PDF
        total_tables: Number of unique tables found
        textract_events_count: Number of Textract events generated
        ttl_days: Days until record expires (default 90)

    Returns:
        The created DynamoDB item
    """
    table = _get_dynamodb_resource().Table(table_name)
    now = datetime.now(UTC)
    ttl = int(now.timestamp()) + (ttl_days * 24 * 60 * 60)

    item = {
        "PK": f"JOB#{job_id}",
        "SK": "METADATA",
        "job_id": job_id,
        "status": "PENDING",
        "s3_bucket": s3_bucket,
        "s3_key": s3_key,
        "product_name": product_name,
        "file_hash": file_hash,
        "total_pages": total_pages,
        "total_tables": total_tables,
        "textract_events_count": textract_events_count,
        "tables_processed": 0,
        "tables_failed": 0,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "GSI1PK": f"PRODUCT#{product_name}",
        "GSI1SK": now.isoformat(),
        "ttl": ttl,
    }

    logger.info("Creating job record", extra={"job_id": job_id, "table": table_name})
    table.put_item(Item=item)

    return item


@tracer.capture_method
def update_job_status(
    table_name: str,
    job_id: str,
    status: str,
    error_message: str | None = None,
) -> None:
    """Update job status in DynamoDB.

    Args:
        table_name: DynamoDB table name
        job_id: Job identifier
        status: New status (PENDING, RUNNING, SUCCESS, FAILED)
        error_message: Optional error message for FAILED status
    """
    table = _get_dynamodb_resource().Table(table_name)
    now = datetime.now(UTC).isoformat()

    update_expr = "SET #status = :status, updated_at = :updated_at"
    expr_values: dict[str, Any] = {
        ":status": status,
        ":updated_at": now,
    }
    expr_names = {"#status": "status"}

    # Update GSI1PK for status-based queries
    if status in ("FAILED", "SUCCESS"):
        update_expr += ", GSI1PK = :gsi1pk, GSI1SK = :gsi1sk"
        expr_values[":gsi1pk"] = f"STATUS#{status}"
        expr_values[":gsi1sk"] = now

    if error_message:
        update_expr += ", error_message = :error"
        expr_values[":error"] = error_message

    logger.info("Updating job status", extra={"job_id": job_id, "status": status})
    table.update_item(
        Key={"PK": f"JOB#{job_id}", "SK": "METADATA"},
        UpdateExpression=update_expr,
        ExpressionAttributeNames=expr_names,
        ExpressionAttributeValues=expr_values,
    )
