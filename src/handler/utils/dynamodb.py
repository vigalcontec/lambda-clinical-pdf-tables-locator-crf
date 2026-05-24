"""DynamoDB utility functions for job tracking."""

from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

import boto3
from aws_lambda_powertools import Logger, Tracer

logger = Logger()
tracer = Tracer()


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
    now = datetime.now(timezone.utc)
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
    now = datetime.now(timezone.utc).isoformat()

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
