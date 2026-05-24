"""Pytest fixtures and configuration."""

import os

# Disable X-Ray tracing before importing any modules
os.environ["POWERTOOLS_TRACE_DISABLED"] = "true"

from collections.abc import Generator  # noqa: E402
from typing import Any  # noqa: E402
from unittest.mock import patch  # noqa: E402

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def env_vars() -> Generator[None, None, None]:
    """Set environment variables for tests."""
    with patch.dict(
        os.environ,
        {
            "ENVIRONMENT": "dev",
            "AWS_REGION": "eu-west-1",
            "LOG_LEVEL": "INFO",
            "DYNAMODB_TABLE_NAME": "clinical-pdf-jobs-dev",
            "OUTPUT_S3_BUCKET": "datalake-raw-dev",
            "RAW_BUCKET_NAME": "datalake-raw-dev",
        },
    ):
        yield


@pytest.fixture
def pdf_event() -> dict[str, Any]:
    """Sample PDF processing event from Step Function.
    
    Format: s3_key = path/product_name/yyyymmddhhmmss/document.pdf
    Product name is extracted from the path (second-to-last directory).
    """
    return {
        "s3_bucket": "datalake-raw-dev",
        "s3_key": "crf/clinical_pdfs/Keytruda/20260520173800/report.pdf",
    }


@pytest.fixture
def lambda_context() -> Any:
    """Mock Lambda context."""

    class MockContext:
        function_name = "test-function"
        memory_limit_in_mb = 256
        invoked_function_arn = "arn:aws:lambda:eu-west-1:123456789012:function:test"
        aws_request_id = "test-request-id"

    return MockContext()


@pytest.fixture
def sample_page_info() -> list[dict[str, Any]]:
    """Sample page analysis info for testing textract event generation."""
    return [
        {
            "page": 7,
            "table_identifiers": [{"table_number": 1, "description": "Recommended dose"}],
            "tables_count": 1,
            "has_table_structure": True,
        },
        {
            "page": 8,
            "table_identifiers": [],
            "tables_count": 1,
            "has_table_structure": True,
        },
        {
            "page": 9,
            "table_identifiers": [],
            "tables_count": 0,
            "has_table_structure": False,
        },
        {
            "page": 32,
            "table_identifiers": [
                {"table_number": 6, "description": "Efficacy results KEYNOTE-002"},
                {"table_number": 7, "description": "Efficacy results KEYNOTE-006"},
            ],
            "tables_count": 2,
            "has_table_structure": True,
        },
    ]
