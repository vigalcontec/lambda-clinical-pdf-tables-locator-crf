"""Utility modules."""

from handler.utils.dynamodb import (
    create_job_record,
    filter_pending_events,
    get_job_status,
    get_processed_tables,
    update_job_status,
)
from handler.utils.pdf import (
    analyze_pdf_pages,
    count_tables_on_page,
    detect_tables_hybrid,
    extract_table_identifiers,
    get_total_pages,
    has_table_content_patterns,
)
from handler.utils.s3 import download_pdf_from_s3, generate_file_hash, upload_json_to_s3
from handler.utils.ssm import get_parameter, get_parameters_by_path
from handler.utils.textract_events import generate_textract_events

__all__ = [
    # S3
    "download_pdf_from_s3",
    "generate_file_hash",
    "upload_json_to_s3",
    # PDF
    "analyze_pdf_pages",
    "count_tables_on_page",
    "detect_tables_hybrid",
    "extract_table_identifiers",
    "get_total_pages",
    "has_table_content_patterns",
    # Textract Events
    "generate_textract_events",
    # SSM
    "get_parameter",
    "get_parameters_by_path",
    # DynamoDB
    "create_job_record",
    "filter_pending_events",
    "get_job_status",
    "get_processed_tables",
    "update_job_status",
]
