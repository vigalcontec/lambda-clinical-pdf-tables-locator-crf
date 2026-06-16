"""Tests for Lambda handler - Clinical PDF Tables Locator."""

from typing import Any
from unittest.mock import MagicMock, patch

from handler.config import Settings, get_settings


class TestHandler:
    """Tests for main handler function."""

    @patch("handler.main.upload_json_to_s3")
    @patch("handler.main.create_job_record")
    @patch("handler.main.get_job_status")
    @patch("handler.main.generate_textract_events")
    @patch("handler.main.analyze_pdf_pages")
    @patch("handler.main.get_total_pages")
    @patch("handler.main.generate_file_hash")
    @patch("handler.main.download_pdf_from_s3")
    def test_handler_success(
        self,
        mock_download: MagicMock,
        mock_hash: MagicMock,
        mock_total_pages: MagicMock,
        mock_analyze: MagicMock,
        mock_generate_events: MagicMock,
        mock_get_job_status: MagicMock,
        mock_create_job: MagicMock,
        mock_upload_json: MagicMock,
        pdf_event: dict[str, Any],
        lambda_context: Any,
    ) -> None:
        """Test successful handler execution - no return value."""
        get_settings.cache_clear()

        # Setup mocks
        mock_download.return_value = b"fake pdf content"
        mock_hash.return_value = "abc123hash"
        mock_total_pages.return_value = 100
        # analyze_pdf_pages now returns (page_info, product_sections)
        mock_analyze.return_value = ([{"page": 7, "has_table_structure": True}], [])
        mock_get_job_status.return_value = None  # New job
        mock_generate_events.return_value = [
            {
                "s3_bucket": "datalake-raw-dev",
                "s3_key": "crf/clinical_pdfs/Keytruda/20260520173800/report.pdf",
                "product_name": "Keytruda",
                "table_name": "Table 1: Test",
                "table_number": 1,
                "page": 7,
                "table_index_on_page": 0,
            }
        ]
        mock_upload_json.return_value = "s3://datalake-raw-dev/crf/clinical_pdfs/Keytruda/20260520173800/report_events.json"

        from handler.main import handler

        # Handler completes without raising - no return value
        result = handler(pdf_event, lambda_context)
        assert result is None

        # Verify DynamoDB was called with correct job_id
        mock_create_job.assert_called_once()
        call_kwargs = mock_create_job.call_args.kwargs
        assert call_kwargs["job_id"] == "abc123hash"
        assert call_kwargs["product_name"] == "Keytruda"

        # Verify S3 upload was called
        mock_upload_json.assert_called_once()

    def test_handler_extracts_product_name_from_path(
        self, lambda_context: Any
    ) -> None:
        """Test product_name is extracted from s3_key path."""
        get_settings.cache_clear()

        with patch("handler.main.download_pdf_from_s3") as mock_download, \
             patch("handler.main.generate_file_hash") as mock_hash, \
             patch("handler.main.get_total_pages") as mock_pages, \
             patch("handler.main.analyze_pdf_pages") as mock_analyze, \
             patch("handler.main.generate_textract_events") as mock_events, \
             patch("handler.main.get_job_status") as mock_get_job_status, \
             patch("handler.main.create_job_record") as mock_create_job, \
             patch("handler.main.upload_json_to_s3") as mock_upload:

            mock_download.return_value = b"pdf"
            mock_hash.return_value = "hash"
            mock_pages.return_value = 10
            # analyze_pdf_pages now returns (page_info, product_sections)
            mock_analyze.return_value = ([], [])
            mock_events.return_value = []
            mock_get_job_status.return_value = None  # New job
            mock_upload.return_value = "s3://bucket/path/MyProduct/20260520/doc_events.json"

            from handler.main import handler

            event = {
                "s3_bucket": "bucket",
                "s3_key": "path/MyProduct/20260520/doc.pdf",
            }
            handler(event, lambda_context)

            # Verify product_name was passed to DynamoDB
            call_kwargs = mock_create_job.call_args.kwargs
            assert call_kwargs["product_name"] == "MyProduct"

    def test_handler_raises_on_missing_bucket(
        self, lambda_context: Any
    ) -> None:
        """Test handler raises exception when s3_bucket is missing."""
        import pytest

        get_settings.cache_clear()

        from handler.main import handler

        with pytest.raises(ValueError, match="Missing 's3_bucket' or 's3_key'"):
            handler({"s3_key": "test.pdf"}, lambda_context)

    def test_handler_raises_on_missing_key(
        self, lambda_context: Any
    ) -> None:
        """Test handler raises exception when s3_key is missing."""
        import pytest

        get_settings.cache_clear()

        from handler.main import handler

        with pytest.raises(ValueError, match="Missing 's3_bucket' or 's3_key'"):
            handler({"s3_bucket": "my-bucket"}, lambda_context)

    @patch("handler.main.upload_json_to_s3")
    @patch("handler.main.create_job_record")
    @patch("handler.main.get_job_status")
    @patch("handler.main.generate_textract_events")
    @patch("handler.main.analyze_pdf_pages")
    @patch("handler.main.get_total_pages")
    @patch("handler.main.generate_file_hash")
    @patch("handler.main.download_pdf_from_s3")
    def test_handler_s3_trigger_format(
        self,
        mock_download: MagicMock,
        mock_hash: MagicMock,
        mock_total_pages: MagicMock,
        mock_analyze: MagicMock,
        mock_generate_events: MagicMock,
        mock_get_job_status: MagicMock,
        mock_create_job: MagicMock,
        mock_upload_json: MagicMock,
        lambda_context: Any,
    ) -> None:
        """Test handler with S3 trigger event format."""
        get_settings.cache_clear()

        mock_download.return_value = b"fake pdf content"
        mock_hash.return_value = "abc123hash"
        mock_total_pages.return_value = 50
        # analyze_pdf_pages now returns (page_info, product_sections)
        mock_analyze.return_value = ([], [])
        mock_generate_events.return_value = []
        mock_get_job_status.return_value = None  # New job
        mock_upload_json.return_value = "s3://datalake-raw-dev/crf/clinical_pdfs/Keytruda/20260520/doc_events.json"

        from handler.main import handler

        # S3 trigger event format
        s3_event = {
            "Records": [
                {
                    "s3": {
                        "bucket": {"name": "datalake-raw-dev"},
                        "object": {"key": "crf/clinical_pdfs/Keytruda/20260520/doc.pdf"}
                    }
                }
            ]
        }

        # Handler completes without raising
        result = handler(s3_event, lambda_context)
        assert result is None

        mock_download.assert_called_once_with(
            "datalake-raw-dev",
            "crf/clinical_pdfs/Keytruda/20260520/doc.pdf"
        )

    @patch("handler.main.upload_json_to_s3")
    @patch("handler.main.create_job_record")
    @patch("handler.main.get_job_status")
    @patch("handler.main.generate_textract_events")
    @patch("handler.main.analyze_pdf_pages")
    @patch("handler.main.get_total_pages")
    @patch("handler.main.generate_file_hash")
    @patch("handler.main.download_pdf_from_s3")
    def test_handler_s3_trigger_url_encoded_key(
        self,
        mock_download: MagicMock,
        mock_hash: MagicMock,
        mock_total_pages: MagicMock,
        mock_analyze: MagicMock,
        mock_generate_events: MagicMock,
        mock_get_job_status: MagicMock,
        mock_create_job: MagicMock,
        mock_upload_json: MagicMock,
        lambda_context: Any,
    ) -> None:
        """Test handler decodes URL-encoded S3 keys from trigger."""
        get_settings.cache_clear()

        mock_download.return_value = b"fake pdf content"
        mock_hash.return_value = "hash"
        mock_total_pages.return_value = 10
        # analyze_pdf_pages now returns (page_info, product_sections)
        mock_analyze.return_value = ([], [])
        mock_generate_events.return_value = []
        mock_get_job_status.return_value = None  # New job
        mock_upload_json.return_value = "s3://bucket/path/My Product/2026/file name_events.json"

        from handler.main import handler

        # S3 encodes spaces as + and special chars as %XX
        s3_event = {
            "Records": [
                {
                    "s3": {
                        "bucket": {"name": "bucket"},
                        "object": {"key": "path/My+Product/2026/file+name.pdf"}
                    }
                }
            ]
        }

        # Handler completes without raising
        result = handler(s3_event, lambda_context)
        assert result is None

        # Key should be decoded
        mock_download.assert_called_once_with(
            "bucket",
            "path/My Product/2026/file name.pdf"
        )

    @patch("handler.main.upload_json_to_s3")
    @patch("handler.main.update_job_status")
    @patch("handler.main.create_job_record")
    @patch("handler.main.get_job_status")
    @patch("handler.main.filter_pending_events")
    @patch("handler.main.generate_textract_events")
    @patch("handler.main.analyze_pdf_pages")
    @patch("handler.main.get_total_pages")
    @patch("handler.main.generate_file_hash")
    @patch("handler.main.download_pdf_from_s3")
    def test_handler_reprocessing_existing_job(
        self,
        mock_download: MagicMock,
        mock_hash: MagicMock,
        mock_total_pages: MagicMock,
        mock_analyze: MagicMock,
        mock_generate_events: MagicMock,
        mock_filter_events: MagicMock,
        mock_get_job_status: MagicMock,
        mock_create_job: MagicMock,
        mock_update_job_status: MagicMock,
        mock_upload_json: MagicMock,
        pdf_event: dict[str, Any],
        lambda_context: Any,
    ) -> None:
        """Test handler reprocessing an existing job."""
        get_settings.cache_clear()

        mock_download.return_value = b"fake pdf content"
        mock_hash.return_value = "abc123hash"
        mock_total_pages.return_value = 100
        mock_analyze.return_value = ([{"page": 7, "has_table_structure": True}], [])
        mock_generate_events.return_value = [{"table_number": 1, "page": 7}]
        # Existing job found
        mock_get_job_status.return_value = {"status": "FAILED", "PK": "JOB#abc123hash"}
        mock_filter_events.return_value = [{"table_number": 1, "page": 7}]
        mock_upload_json.return_value = "s3://bucket/path_events.json"

        from handler.main import handler

        result = handler(pdf_event, lambda_context)
        assert result is None

        # Should have called filter_pending_events
        mock_filter_events.assert_called_once()
        # Should have updated job status to REPROCESSING
        mock_update_job_status.assert_called()

    @patch("handler.main.upload_json_to_s3")
    @patch("handler.main.create_job_record")
    @patch("handler.main.get_job_status")
    @patch("handler.main.filter_pending_events")
    @patch("handler.main.generate_textract_events")
    @patch("handler.main.analyze_pdf_pages")
    @patch("handler.main.get_total_pages")
    @patch("handler.main.generate_file_hash")
    @patch("handler.main.download_pdf_from_s3")
    def test_handler_all_tables_already_processed(
        self,
        mock_download: MagicMock,
        mock_hash: MagicMock,
        mock_total_pages: MagicMock,
        mock_analyze: MagicMock,
        mock_generate_events: MagicMock,
        mock_filter_events: MagicMock,
        mock_get_job_status: MagicMock,
        mock_create_job: MagicMock,
        mock_upload_json: MagicMock,
        pdf_event: dict[str, Any],
        lambda_context: Any,
    ) -> None:
        """Test handler when all tables already processed successfully."""
        get_settings.cache_clear()

        mock_download.return_value = b"fake pdf content"
        mock_hash.return_value = "abc123hash"
        mock_total_pages.return_value = 100
        mock_analyze.return_value = ([{"page": 7, "has_table_structure": True}], [])
        mock_generate_events.return_value = [{"table_number": 1, "page": 7}]
        mock_get_job_status.return_value = {"status": "SUCCESS", "PK": "JOB#abc123hash"}
        # All tables already processed - empty list returned
        mock_filter_events.return_value = []

        from handler.main import handler

        result = handler(pdf_event, lambda_context)
        assert result is None

        # Should NOT have called create_job_record or upload_json (skipped)
        mock_create_job.assert_not_called()
        mock_upload_json.assert_not_called()

    @patch("handler.main.update_job_status")
    @patch("handler.main.download_pdf_from_s3")
    def test_handler_empty_pdf_raises_error(
        self,
        mock_download: MagicMock,
        mock_update_status: MagicMock,
        pdf_event: dict[str, Any],
        lambda_context: Any,
    ) -> None:
        """Test handler raises error for empty PDF."""
        import pytest

        get_settings.cache_clear()

        mock_download.return_value = b""  # Empty PDF

        from handler.main import handler

        with pytest.raises(ValueError, match="Downloaded PDF is empty"):
            handler(pdf_event, lambda_context)

    @patch("handler.main.upload_json_to_s3")
    @patch("handler.main.create_job_record")
    @patch("handler.main.get_job_status")
    @patch("handler.main.generate_textract_events")
    @patch("handler.main.analyze_pdf_pages")
    @patch("handler.main.get_total_pages")
    @patch("handler.main.generate_file_hash")
    @patch("handler.main.download_pdf_from_s3")
    def test_handler_multi_product_pdf(
        self,
        mock_download: MagicMock,
        mock_hash: MagicMock,
        mock_total_pages: MagicMock,
        mock_analyze: MagicMock,
        mock_generate_events: MagicMock,
        mock_get_job_status: MagicMock,
        mock_create_job: MagicMock,
        mock_upload_json: MagicMock,
        pdf_event: dict[str, Any],
        lambda_context: Any,
    ) -> None:
        """Test handler with multi-product PDF."""
        get_settings.cache_clear()

        mock_download.return_value = b"fake pdf content"
        mock_hash.return_value = "abc123hash"
        mock_total_pages.return_value = 100
        # Multi-product PDF with 2 sections
        product_sections = [
            {"start_page": 1, "end_page": 50, "formulation_key": "840mg", "formulations": ["840 mg"]},
            {"start_page": 51, "end_page": 100, "formulation_key": "1200mg", "formulations": ["1200 mg"]},
        ]
        mock_analyze.return_value = ([{"page": 7, "has_table_structure": True}], product_sections)
        mock_generate_events.return_value = [{"table_number": 1, "page": 7}]
        mock_get_job_status.return_value = None
        mock_upload_json.return_value = "s3://bucket/path_events.json"

        from handler.main import handler

        result = handler(pdf_event, lambda_context)
        assert result is None


class TestS3Utils:
    """Tests for S3 utility functions."""

    @patch("handler.utils.s3.s3_client")
    def test_download_pdf_from_s3(self, mock_s3: MagicMock) -> None:
        """Test downloading PDF from S3."""
        from handler.utils.s3 import download_pdf_from_s3

        mock_body = MagicMock()
        mock_body.read.return_value = b"pdf content"
        mock_s3.get_object.return_value = {"Body": mock_body}

        result = download_pdf_from_s3("my-bucket", "path/to/file.pdf")

        assert result == b"pdf content"
        mock_s3.get_object.assert_called_once_with(
            Bucket="my-bucket", Key="path/to/file.pdf"
        )

    def test_generate_file_hash(self) -> None:
        """Test SHA256 hash generation."""
        from handler.utils.s3 import generate_file_hash

        content = b"test content"
        result = generate_file_hash(content)

        assert len(result) == 64
        assert result == "6ae8a75555209fd6c44157c0aed8016e763ff435a19cf186f76863140143ff72"

    def test_generate_file_hash_deterministic(self) -> None:
        """Test same content produces same hash."""
        from handler.utils.s3 import generate_file_hash

        content = b"same content"
        assert generate_file_hash(content) == generate_file_hash(content)


class TestPdfUtils:
    """Tests for PDF utility functions."""

    def test_extract_table_identifiers(self) -> None:
        """Test extracting table identifiers from text."""
        from handler.utils.pdf import extract_table_identifiers

        text = "Table 1: Recommended dose modifications\nSome text\nTable 2: Adverse events"
        result = extract_table_identifiers(text)

        assert len(result) == 2
        assert result[0]["table_number"] == 1
        assert result[0]["description"] == "Recommended dose modifications"
        assert result[1]["table_number"] == 2

    def test_extract_table_identifiers_case_insensitive(self) -> None:
        """Test table identifier extraction is case insensitive."""
        from handler.utils.pdf import extract_table_identifiers

        text = "TABLE 5: Efficacy Results"
        result = extract_table_identifiers(text)

        assert len(result) == 1
        assert result[0]["table_number"] == 5

    def test_extract_table_identifiers_no_match(self) -> None:
        """Test when no table identifiers found."""
        from handler.utils.pdf import extract_table_identifiers

        text = "This is just regular text without tables"
        result = extract_table_identifiers(text)

        assert result == []

    def test_has_table_content_patterns_clinical_data(self) -> None:
        """Test detection of clinical table content patterns."""
        from handler.utils.pdf import has_table_content_patterns

        # Text with clinical table patterns
        text = """
        Atezolizumab (n = 467) vs Chemotherapy (n = 464)
        No. of deaths (%): 324 (69.4%) vs 350 (75.4%)
        Median time to events (months): 8.6 vs 8.0
        95% CI: 7.8, 9.6 vs 7.2, 8.6
        Stratified hazard ratio (95% CI): 0.85 (0.73, 0.99)
        """

        assert has_table_content_patterns(text) is True

    def test_has_table_content_patterns_no_match(self) -> None:
        """Test no detection when clinical patterns are absent."""
        from handler.utils.pdf import has_table_content_patterns

        text = "This is regular paragraph text without any clinical data patterns."

        assert has_table_content_patterns(text) is False

    def test_has_table_content_patterns_single_pattern_not_enough(self) -> None:
        """Test that a single pattern is not enough (requires 2+)."""
        from handler.utils.pdf import has_table_content_patterns

        # Only one pattern (n = X)
        text = "The study included n = 467 patients."

        assert has_table_content_patterns(text) is False


class TestProductFormulationDetection:
    """Tests for multi-product PDF formulation detection."""

    def test_extract_product_formulations(self) -> None:
        """Test extracting product formulation names from text."""
        from handler.utils.pdf import extract_product_formulations

        # Use text format similar to actual PDF (each on separate line)
        text = """1. NAME OF THE MEDICINAL PRODUCT
Tecentriq 840 mg concentrate for solution for infusion
Tecentriq 1200 mg concentrate for solution for infusion
2. QUALITATIVE AND QUANTITATIVE COMPOSITION"""

        formulations = extract_product_formulations(text)

        # Should find at least one formulation with 840 or 1200
        assert len(formulations) >= 1
        assert any("840" in f or "1200" in f for f in formulations)

    def test_extract_product_formulations_single(self) -> None:
        """Test extracting single product formulation."""
        from handler.utils.pdf import extract_product_formulations

        text = """1. NAME OF THE MEDICINAL PRODUCT
        Tecentriq 1 875 mg solution for injection
        2. QUALITATIVE AND QUANTITATIVE COMPOSITION"""

        formulations = extract_product_formulations(text)

        assert len(formulations) >= 1
        assert any("1875" in f or "1 875" in f for f in formulations)

    def test_extract_product_formulations_no_match(self) -> None:
        """Test when no product formulations found."""
        from handler.utils.pdf import extract_product_formulations

        text = "This is just regular text without product names"
        formulations = extract_product_formulations(text)

        assert formulations == []

    def test_get_formulation_for_page(self) -> None:
        """Test getting formulation info for a specific page."""
        from handler.utils.pdf import get_formulation_for_page

        product_sections = [
            {"start_page": 1, "end_page": 67, "formulation_key": "840_1200mg", "formulations": ["Tecentriq 840 mg"]},
            {"start_page": 68, "end_page": 175, "formulation_key": "1875mg", "formulations": ["Tecentriq 1875 mg"]},
        ]

        # Page in first section
        result = get_formulation_for_page(30, product_sections)
        assert result is not None
        assert result["formulation_key"] == "840_1200mg"

        # Page in second section
        result = get_formulation_for_page(100, product_sections)
        assert result is not None
        assert result["formulation_key"] == "1875mg"

        # Page at boundary
        result = get_formulation_for_page(68, product_sections)
        assert result is not None
        assert result["formulation_key"] == "1875mg"

    def test_get_formulation_for_page_not_found(self) -> None:
        """Test when page is not in any section."""
        from handler.utils.pdf import get_formulation_for_page

        product_sections = [
            {"start_page": 10, "end_page": 50, "formulation_key": "test", "formulations": []},
        ]

        result = get_formulation_for_page(5, product_sections)
        assert result is None

    def test_create_formulation_key(self) -> None:
        """Test creating formulation key from formulation names."""
        from handler.utils.pdf import _create_formulation_key

        # Multiple doses
        formulations = ["Tecentriq 840 mg concentrate", "Tecentriq 1200 mg concentrate"]
        key = _create_formulation_key(formulations)
        assert "840" in key
        assert "1200" in key
        assert key.endswith("mg")

        # Single dose
        formulations = ["Tecentriq 1875 mg solution"]
        key = _create_formulation_key(formulations)
        assert "1875" in key
        assert key.endswith("mg")

    def test_create_formulation_key_no_dose(self) -> None:
        """Test formulation key when no dose found."""
        from handler.utils.pdf import _create_formulation_key

        formulations = ["Some product without dose"]
        key = _create_formulation_key(formulations)
        assert key == "unknown"

    def test_create_formulation_key_empty(self) -> None:
        """Test formulation key with empty list."""
        from handler.utils.pdf import _create_formulation_key

        key = _create_formulation_key([])
        assert key == "unknown"

    @patch("handler.utils.pdf.fitz")
    def test_count_tables_on_page_with_tables(self, mock_fitz: MagicMock) -> None:
        """Test counting tables on a page with tables found."""
        from handler.utils.pdf import count_tables_on_page

        mock_page = MagicMock()
        mock_tables_result = MagicMock()
        mock_tables_result.tables = [MagicMock(), MagicMock()]  # 2 tables
        mock_page.find_tables.return_value = mock_tables_result

        result = count_tables_on_page(mock_page)
        assert result == 2

    @patch("handler.utils.pdf.fitz")
    def test_count_tables_on_page_no_tables(self, mock_fitz: MagicMock) -> None:
        """Test counting tables on a page with no tables."""
        from handler.utils.pdf import count_tables_on_page

        mock_page = MagicMock()
        mock_tables_result = MagicMock()
        mock_tables_result.tables = []
        mock_page.find_tables.return_value = mock_tables_result

        result = count_tables_on_page(mock_page)
        assert result == 0

    @patch("handler.utils.pdf.fitz")
    def test_count_tables_on_page_exception(self, mock_fitz: MagicMock) -> None:
        """Test counting tables handles exceptions gracefully."""
        from handler.utils.pdf import count_tables_on_page

        mock_page = MagicMock()
        mock_page.find_tables.side_effect = Exception("PDF error")

        result = count_tables_on_page(mock_page)
        assert result == 0

    @patch("handler.utils.pdf.count_tables_on_page")
    def test_detect_tables_hybrid_structural(self, mock_count: MagicMock) -> None:
        """Test hybrid detection with structural tables found."""
        from handler.utils.pdf import detect_tables_hybrid

        mock_count.return_value = 2
        mock_page = MagicMock()

        count, has_table = detect_tables_hybrid(mock_page, "some text", [])
        assert count == 2
        assert has_table is True

    @patch("handler.utils.pdf.count_tables_on_page")
    @patch("handler.utils.pdf.has_table_content_patterns")
    def test_detect_tables_hybrid_fallback_with_identifier(
        self, mock_patterns: MagicMock, mock_count: MagicMock
    ) -> None:
        """Test hybrid detection fallback with table identifier."""
        from handler.utils.pdf import detect_tables_hybrid

        mock_count.return_value = 0  # No structural tables
        mock_patterns.return_value = True  # Has table patterns
        mock_page = MagicMock()
        identifiers = [{"table_number": 1, "description": "Test"}]

        count, has_table = detect_tables_hybrid(mock_page, "text with patterns", identifiers)
        assert count == 1
        assert has_table is True

    @patch("handler.utils.pdf.count_tables_on_page")
    @patch("handler.utils.pdf.has_table_content_patterns")
    def test_detect_tables_hybrid_fallback_continuation(
        self, mock_patterns: MagicMock, mock_count: MagicMock
    ) -> None:
        """Test hybrid detection fallback for continuation page."""
        from handler.utils.pdf import detect_tables_hybrid

        mock_count.return_value = 0  # No structural tables
        mock_patterns.return_value = True  # Has table patterns
        mock_page = MagicMock()

        # No identifiers but has patterns (continuation page)
        count, has_table = detect_tables_hybrid(mock_page, "text with patterns", [])
        assert count == 1
        assert has_table is True

    @patch("handler.utils.pdf.count_tables_on_page")
    @patch("handler.utils.pdf.has_table_content_patterns")
    def test_detect_tables_hybrid_no_tables(
        self, mock_patterns: MagicMock, mock_count: MagicMock
    ) -> None:
        """Test hybrid detection with no tables found."""
        from handler.utils.pdf import detect_tables_hybrid

        mock_count.return_value = 0
        mock_patterns.return_value = False
        mock_page = MagicMock()

        count, has_table = detect_tables_hybrid(mock_page, "regular text", [])
        assert count == 0
        assert has_table is False

    @patch("handler.utils.pdf.fitz")
    def test_get_total_pages(self, mock_fitz: MagicMock) -> None:
        """Test getting total pages from PDF."""
        from handler.utils.pdf import get_total_pages

        mock_doc = MagicMock()
        mock_doc.__len__ = MagicMock(return_value=50)
        mock_fitz.open.return_value = mock_doc

        result = get_total_pages(b"fake pdf bytes")
        assert result == 50
        mock_doc.close.assert_called_once()


class TestTextractEvents:
    """Tests for Textract event generation."""

    def test_generate_textract_events_basic(
        self, sample_page_info: list[dict[str, Any]]
    ) -> None:
        """Test basic textract event generation."""
        from handler.utils.textract_events import generate_textract_events

        events = generate_textract_events(
            sample_page_info, "test-bucket", "path/Keytruda/20260520/doc.pdf", "Keytruda", "job123"
        )

        # Should have events for pages 7, 8, 32 (page 9 has no table)
        assert len(events) == 4
        
        # Check first event (Table 1, page 7)
        assert events[0]["job_id"] == "job123"
        assert events[0]["s3_bucket"] == "test-bucket"
        assert events[0]["product_name"] == "Keytruda"
        assert events[0]["table_number"] == 1
        assert events[0]["page"] == 7

    def test_generate_textract_events_continuation_page(
        self, sample_page_info: list[dict[str, Any]]
    ) -> None:
        """Test continuation pages inherit table info."""
        from handler.utils.textract_events import generate_textract_events

        events = generate_textract_events(
            sample_page_info, "bucket", "key", "Product", "job456"
        )

        # Page 8 is continuation of Table 1
        page_8_event = next(e for e in events if e["page"] == 8)
        assert page_8_event["job_id"] == "job456"
        assert page_8_event["table_number"] == 1
        assert page_8_event["table_name"] == "Table 1: Recommended dose"

    def test_generate_textract_events_multiple_tables_on_page(
        self, sample_page_info: list[dict[str, Any]]
    ) -> None:
        """Test multiple tables on same page."""
        from handler.utils.textract_events import generate_textract_events

        events = generate_textract_events(
            sample_page_info, "bucket", "key", "Product", "job789"
        )

        # Page 32 has Table 6 and Table 7
        page_32_events = [e for e in events if e["page"] == 32]
        assert len(page_32_events) == 2
        assert page_32_events[0]["table_number"] == 6
        assert page_32_events[0]["table_index_on_page"] == 0
        assert page_32_events[1]["table_number"] == 7
        assert page_32_events[1]["table_index_on_page"] == 1

    def test_generate_textract_events_sorted(
        self, sample_page_info: list[dict[str, Any]]
    ) -> None:
        """Test events are sorted by table_number then page."""
        from handler.utils.textract_events import generate_textract_events

        events = generate_textract_events(
            sample_page_info, "bucket", "key", "Product", "job_sorted"
        )

        # Should be sorted: Table 1 (p7, p8), Table 6 (p32), Table 7 (p32)
        table_numbers = [e["table_number"] for e in events]
        assert table_numbers == [1, 1, 6, 7]

    def test_generate_textract_events_multi_product(self) -> None:
        """Test textract events include formulation info for multi-product PDFs."""
        from handler.utils.textract_events import generate_textract_events

        # Simulate multi-product PDF with two formulations
        page_info = [
            {
                "page": 4,
                "table_identifiers": [{"table_number": 1, "description": "Dose for 840mg"}],
                "tables_count": 1,
                "has_table_structure": True,
                "formulation_key": "840_1200mg",
                "formulations": ["Tecentriq 840 mg", "Tecentriq 1200 mg"],
            },
            {
                "page": 70,
                "table_identifiers": [{"table_number": 1, "description": "Dose for 1875mg"}],
                "tables_count": 1,
                "has_table_structure": True,
                "formulation_key": "1875mg",
                "formulations": ["Tecentriq 1875 mg"],
            },
        ]

        events = generate_textract_events(
            page_info, "bucket", "key", "Tecentriq", "job_multi"
        )

        assert len(events) == 2

        # First event should have 840_1200mg formulation
        event_840 = next(e for e in events if e["page"] == 4)
        assert event_840["formulation_key"] == "840_1200mg"
        assert "Tecentriq 840 mg" in event_840["formulations"]

        # Second event should have 1875mg formulation
        event_1875 = next(e for e in events if e["page"] == 70)
        assert event_1875["formulation_key"] == "1875mg"
        assert "Tecentriq 1875 mg" in event_1875["formulations"]

    def test_generate_textract_events_multi_product_sorted(self) -> None:
        """Test multi-product events are sorted by formulation_key, then table_number."""
        from handler.utils.textract_events import generate_textract_events

        page_info = [
            {
                "page": 70,
                "table_identifiers": [{"table_number": 1, "description": "Table 1 for 1875mg"}],
                "tables_count": 1,
                "has_table_structure": True,
                "formulation_key": "1875mg",
                "formulations": ["Tecentriq 1875 mg"],
            },
            {
                "page": 4,
                "table_identifiers": [{"table_number": 1, "description": "Table 1 for 840mg"}],
                "tables_count": 1,
                "has_table_structure": True,
                "formulation_key": "840_1200mg",
                "formulations": ["Tecentriq 840 mg"],
            },
        ]

        events = generate_textract_events(
            page_info, "bucket", "key", "Tecentriq", "job_sorted_multi"
        )

        # Should be sorted by formulation_key: 1875mg comes before 840_1200mg alphabetically
        assert events[0]["formulation_key"] == "1875mg"
        assert events[1]["formulation_key"] == "840_1200mg"

    def test_generate_textract_events_single_product_no_formulation(
        self, sample_page_info: list[dict[str, Any]]
    ) -> None:
        """Test single-product PDFs don't include formulation info."""
        from handler.utils.textract_events import generate_textract_events

        events = generate_textract_events(
            sample_page_info, "bucket", "key", "Product", "job_single"
        )

        # Single product PDFs should not have formulation_key
        for event in events:
            assert "formulation_key" not in event
            assert "formulations" not in event


class TestConfig:
    """Tests for configuration."""

    def test_get_settings_returns_settings(self) -> None:
        """Test get_settings returns Settings instance."""
        get_settings.cache_clear()
        settings = get_settings()

        assert isinstance(settings, Settings)

    def test_get_settings_cached(self) -> None:
        """Test get_settings returns cached instance."""
        get_settings.cache_clear()
        settings1 = get_settings()
        settings2 = get_settings()

        assert settings1 is settings2

    def test_settings_default_values(self) -> None:
        """Test Settings has correct default values."""
        get_settings.cache_clear()
        settings = get_settings()

        assert settings.environment == "dev"
        assert settings.aws_region == "eu-west-1"
        assert settings.log_level == "INFO"

    def test_settings_from_env(self) -> None:
        """Test Settings reads from environment variables."""
        import os
        from unittest.mock import patch

        with patch.dict(os.environ, {"ENVIRONMENT": "prod", "LOG_LEVEL": "DEBUG"}):
            get_settings.cache_clear()
            settings = get_settings()

            assert settings.environment == "prod"
            assert settings.log_level == "DEBUG"


class TestSSMUtils:
    """Tests for SSM utilities."""

    @patch("handler.utils.ssm.boto3.client")
    def test_get_parameter(self, mock_boto_client: MagicMock) -> None:
        """Test get_parameter fetches from SSM."""
        from handler.utils.ssm import get_parameter

        # Clear cache
        get_parameter.cache_clear()

        # Setup mock
        mock_ssm = MagicMock()
        mock_boto_client.return_value = mock_ssm
        mock_ssm.get_parameter.return_value = {
            "Parameter": {"Value": "test-value"}
        }

        # Act
        result = get_parameter("/dev/my-app/secret")

        # Assert
        assert result == "test-value"
        mock_ssm.get_parameter.assert_called_once_with(
            Name="/dev/my-app/secret", WithDecryption=True
        )

    @patch("handler.utils.ssm.boto3.client")
    def test_get_parameter_no_decrypt(self, mock_boto_client: MagicMock) -> None:
        """Test get_parameter with decrypt=False."""
        from handler.utils.ssm import get_parameter

        get_parameter.cache_clear()

        mock_ssm = MagicMock()
        mock_boto_client.return_value = mock_ssm
        mock_ssm.get_parameter.return_value = {
            "Parameter": {"Value": "plain-value"}
        }

        result = get_parameter("/dev/my-app/config", decrypt=False)

        assert result == "plain-value"
        mock_ssm.get_parameter.assert_called_once_with(
            Name="/dev/my-app/config", WithDecryption=False
        )

    @patch("handler.utils.ssm.boto3.client")
    def test_get_parameters_by_path(self, mock_boto_client: MagicMock) -> None:
        """Test get_parameters_by_path fetches all parameters under path."""
        from handler.utils.ssm import get_parameters_by_path

        mock_ssm = MagicMock()
        mock_boto_client.return_value = mock_ssm

        # Setup paginator mock
        mock_paginator = MagicMock()
        mock_ssm.get_paginator.return_value = mock_paginator
        mock_paginator.paginate.return_value = [
            {
                "Parameters": [
                    {"Name": "/dev/my-app/db-host", "Value": "localhost"},
                    {"Name": "/dev/my-app/db-port", "Value": "5432"},
                ]
            }
        ]

        result = get_parameters_by_path("/dev/my-app/")

        assert result == {"db-host": "localhost", "db-port": "5432"}

    @patch("handler.utils.ssm.boto3.client")
    def test_get_parameters_by_path_empty(self, mock_boto_client: MagicMock) -> None:
        """Test get_parameters_by_path with no parameters."""
        from handler.utils.ssm import get_parameters_by_path

        mock_ssm = MagicMock()
        mock_boto_client.return_value = mock_ssm

        mock_paginator = MagicMock()
        mock_ssm.get_paginator.return_value = mock_paginator
        mock_paginator.paginate.return_value = [{"Parameters": []}]

        result = get_parameters_by_path("/dev/empty/")

        assert result == {}


class TestDynamoDBUtils:
    """Tests for DynamoDB utility functions."""

    @patch("handler.utils.dynamodb._get_dynamodb_resource")
    def test_create_job_record(self, mock_get_resource: MagicMock) -> None:
        """Test creating a job record in DynamoDB."""
        from handler.utils.dynamodb import create_job_record

        mock_table = MagicMock()
        mock_resource = MagicMock()
        mock_resource.Table.return_value = mock_table
        mock_get_resource.return_value = mock_resource

        result = create_job_record(
            table_name="clinical-pdf-jobs-dev",
            job_id="abc123",
            s3_bucket="bucket",
            s3_key="path/to/file.pdf",
            product_name="Keytruda",
            file_hash="abc123",
            total_pages=100,
            total_tables=10,
            textract_events_count=15,
        )

        assert result["PK"] == "JOB#abc123"
        assert result["SK"] == "METADATA"
        assert result["status"] == "PENDING"
        assert result["product_name"] == "Keytruda"
        assert result["GSI1PK"] == "PRODUCT#Keytruda"
        mock_table.put_item.assert_called_once()

    @patch("handler.utils.dynamodb._get_dynamodb_resource")
    def test_update_job_status(self, mock_get_resource: MagicMock) -> None:
        """Test updating job status in DynamoDB."""
        from handler.utils.dynamodb import update_job_status

        mock_table = MagicMock()
        mock_resource = MagicMock()
        mock_resource.Table.return_value = mock_table
        mock_get_resource.return_value = mock_resource

        update_job_status(
            table_name="clinical-pdf-jobs-dev",
            job_id="abc123",
            status="SUCCESS",
        )

        mock_table.update_item.assert_called_once()
        call_args = mock_table.update_item.call_args
        assert call_args.kwargs["Key"] == {"PK": "JOB#abc123", "SK": "METADATA"}

    @patch("handler.utils.dynamodb._get_dynamodb_resource")
    def test_update_job_status_failed_with_error(self, mock_get_resource: MagicMock) -> None:
        """Test updating job status to FAILED with error message."""
        from handler.utils.dynamodb import update_job_status

        mock_table = MagicMock()
        mock_resource = MagicMock()
        mock_resource.Table.return_value = mock_table
        mock_get_resource.return_value = mock_resource

        update_job_status(
            table_name="clinical-pdf-jobs-dev",
            job_id="abc123",
            status="FAILED",
            error_message="Something went wrong",
        )

        mock_table.update_item.assert_called_once()
        call_args = mock_table.update_item.call_args
        assert ":error" in call_args.kwargs["ExpressionAttributeValues"]

    @patch("handler.utils.dynamodb._get_dynamodb_resource")
    def test_get_job_status_found(self, mock_get_resource: MagicMock) -> None:
        """Test getting job status when job exists."""
        from handler.utils.dynamodb import get_job_status

        mock_table = MagicMock()
        mock_resource = MagicMock()
        mock_resource.Table.return_value = mock_table
        mock_get_resource.return_value = mock_resource
        mock_table.get_item.return_value = {
            "Item": {"PK": "JOB#abc123", "SK": "METADATA", "status": "SUCCESS"}
        }

        result = get_job_status("clinical-pdf-jobs-dev", "abc123")

        assert result is not None
        assert result["status"] == "SUCCESS"
        mock_table.get_item.assert_called_once_with(
            Key={"PK": "JOB#abc123", "SK": "METADATA"}
        )

    @patch("handler.utils.dynamodb._get_dynamodb_resource")
    def test_get_job_status_not_found(self, mock_get_resource: MagicMock) -> None:
        """Test getting job status when job does not exist."""
        from handler.utils.dynamodb import get_job_status

        mock_table = MagicMock()
        mock_resource = MagicMock()
        mock_resource.Table.return_value = mock_table
        mock_get_resource.return_value = mock_resource
        mock_table.get_item.return_value = {}

        result = get_job_status("clinical-pdf-jobs-dev", "nonexistent")

        assert result is None

    @patch("handler.utils.dynamodb._get_dynamodb_resource")
    def test_get_processed_tables(self, mock_get_resource: MagicMock) -> None:
        """Test getting processed tables for a job."""
        from handler.utils.dynamodb import get_processed_tables

        mock_table = MagicMock()
        mock_resource = MagicMock()
        mock_resource.Table.return_value = mock_table
        mock_get_resource.return_value = mock_resource
        mock_table.query.return_value = {
            "Items": [
                {"SK": "TABLE#1#PAGE#5", "status": "SUCCESS"},
                {"SK": "TABLE#2#PAGE#10", "status": "FAILED"},
                {"SK": "TABLE#3#PAGE#15", "status": "SUCCESS"},
            ]
        }

        result = get_processed_tables("clinical-pdf-jobs-dev", "abc123")

        assert result == {"1_5": "SUCCESS", "2_10": "FAILED", "3_15": "SUCCESS"}

    @patch("handler.utils.dynamodb._get_dynamodb_resource")
    def test_filter_pending_events_all_new(self, mock_get_resource: MagicMock) -> None:
        """Test filtering events when no tables have been processed."""
        from handler.utils.dynamodb import filter_pending_events

        mock_table = MagicMock()
        mock_resource = MagicMock()
        mock_resource.Table.return_value = mock_table
        mock_get_resource.return_value = mock_resource
        mock_table.query.return_value = {"Items": []}

        events = [
            {"table_number": 1, "page": 5},
            {"table_number": 2, "page": 10},
        ]

        result = filter_pending_events("table", "job123", events)

        assert len(result) == 2

    @patch("handler.utils.dynamodb._get_dynamodb_resource")
    def test_filter_pending_events_skip_success(self, mock_get_resource: MagicMock) -> None:
        """Test filtering events skips successfully processed tables."""
        from handler.utils.dynamodb import filter_pending_events

        mock_table = MagicMock()
        mock_resource = MagicMock()
        mock_resource.Table.return_value = mock_table
        mock_get_resource.return_value = mock_resource
        # SK format produces key "1__5" after parsing (TABLE#1#PAGE#5 -> 1__5)
        mock_table.query.return_value = {
            "Items": [
                {"SK": "TABLE#1#PAGE#5", "status": "SUCCESS"},
            ]
        }

        events = [
            {"table_number": 1, "page": 5},
            {"table_number": 2, "page": 10},
        ]

        # The filter uses key format "{table_number}_{page}" to match
        result = filter_pending_events("table", "job123", events)

        # Table 1 page 5 should be skipped (SUCCESS), only table 2 page 10 remains
        assert len(result) == 1
        assert result[0]["table_number"] == 2

    @patch("handler.utils.dynamodb._get_dynamodb_resource")
    def test_filter_pending_events_reprocess_failed(self, mock_get_resource: MagicMock) -> None:
        """Test filtering events includes failed tables for reprocessing."""
        from handler.utils.dynamodb import filter_pending_events

        mock_table = MagicMock()
        mock_resource = MagicMock()
        mock_resource.Table.return_value = mock_table
        mock_get_resource.return_value = mock_resource
        mock_table.query.return_value = {
            "Items": [
                {"SK": "TABLE#1#PAGE#5", "status": "FAILED"},
            ]
        }

        events = [
            {"table_number": 1, "page": 5},
            {"table_number": 2, "page": 10},
        ]

        result = filter_pending_events("table", "job123", events, reprocess_failed=True)

        assert len(result) == 2  # Both events included

    @patch("handler.utils.dynamodb._get_dynamodb_resource")
    def test_filter_pending_events_skip_failed(self, mock_get_resource: MagicMock) -> None:
        """Test filtering events skips failed tables when reprocess_failed=False."""
        from handler.utils.dynamodb import filter_pending_events

        mock_table = MagicMock()
        mock_resource = MagicMock()
        mock_resource.Table.return_value = mock_table
        mock_get_resource.return_value = mock_resource
        mock_table.query.return_value = {
            "Items": [
                {"SK": "TABLE#1#PAGE#5", "status": "FAILED"},
            ]
        }

        events = [
            {"table_number": 1, "page": 5},
            {"table_number": 2, "page": 10},
        ]

        result = filter_pending_events("table", "job123", events, reprocess_failed=False)

        assert len(result) == 1
        assert result[0]["table_number"] == 2


class TestS3UploadUtils:
    """Tests for S3 upload utility functions."""

    @patch("handler.utils.s3.s3_client")
    def test_upload_json_to_s3(self, mock_s3: MagicMock) -> None:
        """Test uploading JSON to S3."""
        from handler.utils.s3 import upload_json_to_s3

        data = {"key": "value", "list": [1, 2, 3]}
        result = upload_json_to_s3("my-bucket", "path/to/file.json", data)

        assert result == "s3://my-bucket/path/to/file.json"
        mock_s3.put_object.assert_called_once()
        call_args = mock_s3.put_object.call_args
        assert call_args.kwargs["Bucket"] == "my-bucket"
        assert call_args.kwargs["Key"] == "path/to/file.json"
        assert call_args.kwargs["ContentType"] == "application/json"

    @patch("handler.utils.s3.s3_client")
    def test_upload_json_to_s3_list(self, mock_s3: MagicMock) -> None:
        """Test uploading a list as JSON to S3."""
        from handler.utils.s3 import upload_json_to_s3

        data = [{"event": 1}, {"event": 2}]
        result = upload_json_to_s3("bucket", "events.json", data)

        assert result == "s3://bucket/events.json"
        mock_s3.put_object.assert_called_once()
