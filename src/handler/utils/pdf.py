"""PDF analysis utility functions using PyMuPDF."""

import re
from typing import Any

import fitz
from aws_lambda_powertools import Logger, Tracer

logger = Logger()
tracer = Tracer()

# Regex pattern to capture full table identifier: "Table X: description"
TABLE_IDENTIFIER_PATTERN = re.compile(
    r"\btable\s+(\d+)\s*:\s*([^\n]+)",
    re.IGNORECASE
)


def extract_table_identifiers(text: str) -> list[dict[str, Any]]:
    """Extract all table identifiers from text.

    Looks for pattern: "Table X: description"
    E.g., "Table 56: Efficacy results in KEYNOTE-B96..."

    Args:
        text: Page text content

    Returns:
        List of dicts with table_number and description
    """
    matches = TABLE_IDENTIFIER_PATTERN.findall(text)
    return [
        {
            "table_number": int(num),
            "description": desc.strip()
        }
        for num, desc in matches
    ]


def count_tables_on_page(page: fitz.Page) -> int:
    """Count the number of tables on a page.

    Args:
        page: PyMuPDF page object

    Returns:
        Number of tables found
    """
    try:
        found_tables = page.find_tables()
        return len(found_tables.tables) if found_tables else 0
    except Exception:
        return 0


@tracer.capture_method
def analyze_pdf_pages(pdf_bytes: bytes) -> list[dict[str, Any]]:
    """Analyze all pages in a PDF for table content.

    Args:
        pdf_bytes: PDF file content as bytes

    Returns:
        List of page analysis dictionaries with:
        - page: Page number (1-indexed)
        - table_identifiers: List of table identifiers found
        - tables_count: Number of tables on the page
        - has_table_structure: Whether page has any table
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page_info: list[dict[str, Any]] = []

    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        text = page.get_text("text")

        table_identifiers = extract_table_identifiers(text)
        tables_count = count_tables_on_page(page)

        page_info.append({
            "page": page_num + 1,  # 1-indexed
            "table_identifiers": table_identifiers,
            "tables_count": tables_count,
            "has_table_structure": tables_count > 0,
        })

    doc.close()

    logger.debug(
        "PDF pages analyzed",
        extra={"total_pages": len(page_info), "pages_with_tables": sum(1 for p in page_info if p["has_table_structure"])}
    )

    return page_info


def get_total_pages(pdf_bytes: bytes) -> int:
    """Get total number of pages in PDF.

    Args:
        pdf_bytes: PDF file content as bytes

    Returns:
        Total page count
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    total = len(doc)
    doc.close()
    return total
