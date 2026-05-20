"""Utility modules."""

from handler.utils.pdf import (
    analyze_pdf_pages,
    count_tables_on_page,
    extract_table_identifiers,
    get_total_pages,
)
from handler.utils.s3 import download_pdf_from_s3, generate_file_hash
from handler.utils.ssm import get_parameter, get_parameters_by_path
from handler.utils.textract_events import generate_textract_events

__all__ = [
    # S3
    "download_pdf_from_s3",
    "generate_file_hash",
    # PDF
    "analyze_pdf_pages",
    "count_tables_on_page",
    "extract_table_identifiers",
    "get_total_pages",
    # Textract Events
    "generate_textract_events",
    # SSM
    "get_parameter",
    "get_parameters_by_path",
]
