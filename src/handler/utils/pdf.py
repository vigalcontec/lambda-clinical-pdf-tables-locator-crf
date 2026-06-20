"""PDF analysis utility functions using PyMuPDF."""

import re
from typing import Any

import fitz
from aws_lambda_powertools import Logger, Tracer

logger = Logger()
tracer = Tracer()

# Regex pattern to capture table identifier start: "Table X: " or "Table X. "
# We capture the table number and then extract the full title separately
TABLE_IDENTIFIER_PATTERN = re.compile(
    r"\btable\s+(\d+)\s*[.:]\s*",
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

# Pattern to detect "1. NAME OF THE MEDICINAL PRODUCT" section header
SECTION_1_PATTERN = re.compile(
    r"1\.\s*\n?\s*NAME OF THE MEDICINAL PRODUCT",
    re.IGNORECASE
)

# Pattern to detect "2. QUALITATIVE AND QUANTITATIVE COMPOSITION" section header
SECTION_2_PATTERN = re.compile(
    r"2\.\s*\n?\s*QUALITATIVE AND QUANTITATIVE COMPOSITION",
    re.IGNORECASE
)


def extract_table_identifiers(text: str) -> list[dict[str, Any]]:
    """Extract all table identifiers from text.

    Looks for pattern: "Table X: description" or "Table X. description"
    Extracts only the first line/sentence as the title - the actual complete
    title will be extracted by Textract using LAYOUT_TITLE blocks.

    Args:
        text: Page text content

    Returns:
        List of dicts with table_number and description
    """
    results = []

    # Find all table identifier positions
    for match in TABLE_IDENTIFIER_PATTERN.finditer(text):
        table_num = int(match.group(1))
        start_pos = match.end()

        # Get text after "Table X: " or "Table X. "
        remaining_text = text[start_pos:]

        # Stop at first newline - just get the first line as a basic identifier
        # The actual title will be extracted by Textract using LAYOUT_TITLE blocks
        newline_pos = remaining_text.find("\n")
        description = remaining_text[:newline_pos] if newline_pos != -1 else remaining_text[:200]

        # Clean up whitespace
        description = " ".join(description.split()).strip()

        # Limit length for safety
        if len(description) > 150:
            description = description[:150].rsplit(" ", 1)[0] + "..."

        results.append({
            "table_number": table_num,
            "description": description
        })

    # Deduplicate by table_number, keeping the last occurrence (most likely the actual table header)
    seen_tables: dict[int, dict[str, Any]] = {}
    for item in results:
        tbl_num = item["table_number"]
        if isinstance(tbl_num, int):
            seen_tables[tbl_num] = item

    return list(seen_tables.values())


def extract_product_formulations(text: str) -> list[str]:
    """Extract product formulation names from text.

    Extracts only the lines between "1. NAME OF THE MEDICINAL PRODUCT" and
    "2. QUALITATIVE AND QUANTITATIVE COMPOSITION" section headers.

    Args:
        text: Page text content

    Returns:
        List of product formulation names found
    """
    formulations: list[str] = []

    # Find section 1 header
    section1_match = SECTION_1_PATTERN.search(text)
    if not section1_match:
        return formulations

    # Find section 2 header (marks the end of formulation list)
    section2_match = SECTION_2_PATTERN.search(text)

    # Extract text between section 1 and section 2 (or end of text)
    start_pos = section1_match.end()
    end_pos = section2_match.start() if section2_match else len(text)

    section_text = text[start_pos:end_pos]

    # Extract each non-empty line as a formulation
    for line in section_text.split("\n"):
        line = line.strip()
        # Skip empty lines and lines that look like headers/numbers
        if line and len(line) > 5 and not line.isdigit():
            # Clean up the formulation name
            formulation = " ".join(line.split())  # Normalize whitespace
            if formulation not in formulations:
                formulations.append(formulation)

    return formulations


def detect_product_sections(pdf_bytes: bytes) -> list[dict[str, Any]]:
    """Detect product formulation sections in a multi-product PDF.

    Scans the PDF for "1. NAME OF THE MEDICINAL PRODUCT" sections
    and extracts the product formulations associated with each section.

    Args:
        pdf_bytes: PDF file content as bytes

    Returns:
        List of product sections with:
        - start_page: First page of this product section (1-indexed)
        - end_page: Last page of this product section (1-indexed)
        - formulations: List of product formulation names
        - formulation_key: Normalized key for this formulation group
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    sections: list[dict[str, Any]] = []

    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        text = page.get_text("text")

        # Check if this page has a "1. NAME OF THE MEDICINAL PRODUCT" section
        if SECTION_1_PATTERN.search(text):
            formulations = extract_product_formulations(text)
            if formulations:
                sections.append({
                    "start_page": page_num + 1,  # 1-indexed
                    "end_page": None,  # Will be set later
                    "formulations": formulations,
                    "formulation_key": _create_formulation_key(formulations),
                })

    # Set end_page for each section (page before next section starts, or last page)
    total_pages = len(doc)
    for i, section in enumerate(sections):
        if i + 1 < len(sections):
            section["end_page"] = sections[i + 1]["start_page"] - 1
        else:
            section["end_page"] = total_pages

    doc.close()

    logger.info(
        "Product sections detected",
        extra={
            "sections_count": len(sections),
            "sections": [
                {
                    "pages": f"{s['start_page']}-{s['end_page']}",
                    "formulation_key": s["formulation_key"],
                }
                for s in sections
            ],
        }
    )

    return sections


def _create_formulation_key(formulations: list[str]) -> str:
    """Create a normalized key from formulation names.

    Args:
        formulations: List of formulation names

    Returns:
        Normalized key string (e.g., "840_1200mg" or "1875mg")
    """
    # Extract doses from formulations (handles spaces in numbers like "1 200 mg")
    doses = []
    for f in formulations:
        # Match digits with optional spaces before "mg"
        match = re.search(r"([\d\s]+)\s*mg", f, re.IGNORECASE)
        if match:
            # Remove spaces from the dose number
            dose = match.group(1).replace(" ", "")
            if dose.isdigit():
                doses.append(dose)

    if doses:
        return "_".join(sorted(set(doses), key=int)) + "mg"
    return "unknown"


def get_formulation_for_page(page_num: int, product_sections: list[dict]) -> dict[str, Any] | None:
    """Get the product formulation info for a given page.

    Args:
        page_num: Page number (1-indexed)
        product_sections: List of product sections from detect_product_sections

    Returns:
        Product section dict if found, None otherwise
    """
    for section in product_sections:
        if section["start_page"] <= page_num <= section["end_page"]:
            return section
    return None


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


@tracer.capture_method(capture_response=False)
def analyze_pdf_pages(pdf_bytes: bytes) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Analyze all pages in a PDF for table content and product formulations.

    Uses hybrid detection: PyMuPDF structural detection + text-based fallback
    for complex tables that may not be detected structurally.

    Also detects product formulation sections for multi-product PDFs.

    Args:
        pdf_bytes: PDF file content as bytes

    Returns:
        Tuple of:
        - List of page analysis dictionaries with:
          - page: Page number (1-indexed)
          - table_identifiers: List of table identifiers found
          - tables_count: Number of tables on the page
          - has_table_structure: Whether page has any table
          - detection_method: How the table was detected (structural/text_pattern/none)
          - formulation_key: Product formulation key for this page (if multi-product PDF)
          - formulations: List of product formulation names for this page
        - List of product sections (from detect_product_sections)
    """
    # First, detect product sections
    product_sections = detect_product_sections(pdf_bytes)

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

        # Get product formulation for this page
        formulation_info = get_formulation_for_page(page_num + 1, product_sections)

        page_data = {
            "page": page_num + 1,  # 1-indexed
            "table_identifiers": table_identifiers,
            "tables_count": tables_count,
            "has_table_structure": has_table_structure,
            "detection_method": detection_method,
        }

        # Add formulation info if this is a multi-product PDF
        if formulation_info:
            page_data["formulation_key"] = formulation_info["formulation_key"]
            page_data["formulations"] = formulation_info["formulations"]

        page_info.append(page_data)

    doc.close()

    # Log summary with detection methods
    structural_pages = sum(1 for p in page_info if p["detection_method"] == "structural")
    fallback_pages = sum(1 for p in page_info if p["detection_method"] == "text_pattern")
    formulation_keys = list({p.get("formulation_key", "single") for p in page_info})

    logger.info(
        "PDF pages analyzed",
        extra={
            "total_pages": len(page_info),
            "pages_with_tables": sum(1 for p in page_info if p["has_table_structure"]),
            "structural_detection": structural_pages,
            "text_pattern_fallback": fallback_pages,
            "product_formulations": formulation_keys,
            "is_multi_product": len(product_sections) > 1,
        }
    )

    return page_info, product_sections


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
