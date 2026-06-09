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

# Patterns that indicate table content (for fallback detection)
TABLE_CONTENT_PATTERNS = [
    re.compile(r"\b(n\s*=\s*\d+)", re.IGNORECASE),  # Sample size: n = 467
    re.compile(r"\b\d+\s*\(\d+\.?\d*%\)"),  # Percentage format: 324 (69.4%)
    re.compile(r"\b\d+\.\d+\s*,\s*\d+\.\d+"),  # CI format: 7.8, 9.6
    re.compile(r"\b95%\s*CI\b", re.IGNORECASE),  # Confidence interval
    re.compile(r"\bhazard\s+ratio\b", re.IGNORECASE),  # Hazard ratio
    re.compile(r"\bmedian\b.*\b(months?|years?|days?)\b", re.IGNORECASE),  # Median time
]


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


def has_table_content_patterns(text: str) -> bool:
    """Check if text contains patterns typical of clinical table data.

    This is a fallback detection method for tables that PyMuPDF
    cannot detect structurally but contain obvious tabular data.

    Args:
        text: Page text content

    Returns:
        True if text contains table-like content patterns
    """
    matches = sum(1 for pattern in TABLE_CONTENT_PATTERNS if pattern.search(text))
    # Require at least 2 different patterns to reduce false positives
    return matches >= 2


def count_tables_on_page(page: fitz.Page) -> int:
    """Count the number of tables on a page using PyMuPDF.

    Uses improved detection parameters for complex tables.

    Args:
        page: PyMuPDF page object

    Returns:
        Number of tables found
    """
    try:
        # Try with default settings first
        found_tables = page.find_tables()
        if found_tables and len(found_tables.tables) > 0:
            return len(found_tables.tables)

        # Try with more lenient settings for complex tables
        found_tables = page.find_tables(
            snap_tolerance=5,      # More tolerance for alignment
            min_words_vertical=2,  # Fewer words needed to detect vertical structure
            min_words_horizontal=2,
        )
        return len(found_tables.tables) if found_tables else 0
    except Exception:
        return 0


def detect_tables_hybrid(page: fitz.Page, text: str, table_identifiers: list[dict]) -> tuple[int, bool]:
    """Hybrid table detection combining structural and text-based methods.

    Args:
        page: PyMuPDF page object
        text: Page text content
        table_identifiers: List of table identifiers found on page

    Returns:
        Tuple of (tables_count, has_table_structure)
    """
    # Method 1: PyMuPDF structural detection
    structural_count = count_tables_on_page(page)

    if structural_count > 0:
        return structural_count, True

    # Method 2: Fallback - if table identifier found, check for table content patterns
    if table_identifiers and has_table_content_patterns(text):
        logger.debug(
            "Table detected via text patterns (fallback)",
            extra={"identifiers": [t["table_number"] for t in table_identifiers]}
        )
        # Assume one table per identifier when using fallback
        return len(table_identifiers), True

    # Method 3: Check for table content patterns even without explicit identifier
    # (for continuation pages of multi-page tables)
    if has_table_content_patterns(text):
        # Check if this looks like a continuation (no identifier but has data)
        # This will be handled by the event generator's continuation logic
        return 1, True

    return 0, False


@tracer.capture_method
def analyze_pdf_pages(pdf_bytes: bytes) -> list[dict[str, Any]]:
    """Analyze all pages in a PDF for table content.

    Uses hybrid detection: PyMuPDF structural detection + text-based fallback
    for complex tables that may not be detected structurally.

    Args:
        pdf_bytes: PDF file content as bytes

    Returns:
        List of page analysis dictionaries with:
        - page: Page number (1-indexed)
        - table_identifiers: List of table identifiers found
        - tables_count: Number of tables on the page
        - has_table_structure: Whether page has any table
        - detection_method: How the table was detected (structural/text_pattern/none)
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page_info: list[dict[str, Any]] = []

    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        text = page.get_text("text")

        table_identifiers = extract_table_identifiers(text)

        # Use hybrid detection
        tables_count, has_table_structure = detect_tables_hybrid(
            page, text, table_identifiers
        )

        # Determine detection method for logging/debugging
        if has_table_structure:
            structural_count = count_tables_on_page(page)
            detection_method = "structural" if structural_count > 0 else "text_pattern"
        else:
            detection_method = "none"

        page_info.append({
            "page": page_num + 1,  # 1-indexed
            "table_identifiers": table_identifiers,
            "tables_count": tables_count,
            "has_table_structure": has_table_structure,
            "detection_method": detection_method,
        })

    doc.close()

    # Log summary with detection methods
    structural_pages = sum(1 for p in page_info if p["detection_method"] == "structural")
    fallback_pages = sum(1 for p in page_info if p["detection_method"] == "text_pattern")

    logger.info(
        "PDF pages analyzed",
        extra={
            "total_pages": len(page_info),
            "pages_with_tables": sum(1 for p in page_info if p["has_table_structure"]),
            "structural_detection": structural_pages,
            "text_pattern_fallback": fallback_pages,
        }
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
