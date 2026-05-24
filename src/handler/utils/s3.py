"""S3 utility functions."""

import hashlib
import json
from typing import Any

import boto3
from aws_lambda_powertools import Logger, Tracer

logger = Logger()
tracer = Tracer()

s3_client = boto3.client("s3")


@tracer.capture_method
def download_pdf_from_s3(bucket: str, key: str) -> bytes:
    """Download PDF from S3 directly into memory.

    Args:
        bucket: S3 bucket name
        key: S3 object key

    Returns:
        PDF file content as bytes
    """
    logger.info("Downloading PDF from S3", extra={"bucket": bucket, "key": key})
    response = s3_client.get_object(Bucket=bucket, Key=key)
    content: bytes = response["Body"].read()
    return content


@tracer.capture_method
def generate_file_hash(pdf_bytes: bytes) -> str:
    """Generate SHA256 hash for idempotency checks.

    Args:
        pdf_bytes: PDF file content as bytes

    Returns:
        SHA256 hash string
    """
    return hashlib.sha256(pdf_bytes).hexdigest()


@tracer.capture_method
def upload_json_to_s3(
    bucket: str,
    key: str,
    data: dict[str, Any] | list[Any],
) -> str:
    """Upload JSON data to S3.

    Args:
        bucket: S3 bucket name
        key: S3 object key
        data: Dictionary or list to serialize as JSON

    Returns:
        S3 URI of the uploaded object
    """
    logger.info("Uploading JSON to S3", extra={"bucket": bucket, "key": key})

    json_bytes = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")

    s3_client.put_object(
        Bucket=bucket,
        Key=key,
        Body=json_bytes,
        ContentType="application/json",
    )

    s3_uri = f"s3://{bucket}/{key}"
    logger.info("JSON uploaded", extra={"s3_uri": s3_uri, "size_bytes": len(json_bytes)})

    return s3_uri
