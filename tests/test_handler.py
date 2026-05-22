"""Tests for Lambda handler - Clinical PDF Tables Locator."""

from typing import Any
from unittest.mock import MagicMock, patch

from handler.config import Settings, get_settings


class TestHandler:
    """Tests for main handler function."""

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
        pdf_event: dict[str, Any],
        lambda_context: Any,
    ) -> None:
        """Test successful handler execution."""
        get_settings.cache_clear()

        # Setup mocks
        mock_download.return_value = b"fake pdf content"
        mock_hash.return_value = "abc123hash"
        mock_total_pages.return_value = 100
        mock_analyze.return_value = [{"page": 7, "has_table_structure": True}]
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

        from handler.main import handler

        result = handler(pdf_event, lambda_context)

        assert result["status"] == "SUCCESS"
        assert result["file_hash"] == "abc123hash"
        assert result["total_pages"] == 100
        assert result["product_name"] == "Keytruda"
        assert len(result["textract_events"]) == 1
        assert result["textract_events"][0]["s3_bucket"] == "datalake-raw-dev"

    def test_handler_extracts_product_name_from_path(
        self, lambda_context: Any
    ) -> None:
        """Test product_name is extracted from s3_key path."""
        get_settings.cache_clear()

        with patch("handler.main.download_pdf_from_s3") as mock_download, \
             patch("handler.main.generate_file_hash") as mock_hash, \
             patch("handler.main.get_total_pages") as mock_pages, \
             patch("handler.main.analyze_pdf_pages") as mock_analyze, \
             patch("handler.main.generate_textract_events") as mock_events:
            
            mock_download.return_value = b"pdf"
            mock_hash.return_value = "hash"
            mock_pages.return_value = 10
            mock_analyze.return_value = []
            mock_events.return_value = []

            from handler.main import handler

            event = {
                "s3_bucket": "bucket",
                "s3_key": "path/MyProduct/20260520/doc.pdf",
            }
            result = handler(event, lambda_context)

            assert result["product_name"] == "MyProduct"

    def test_handler_returns_failed_on_missing_bucket(
        self, lambda_context: Any
    ) -> None:
        """Test handler returns FAILED when s3_bucket is missing."""
        get_settings.cache_clear()

        from handler.main import handler

        result = handler({"s3_key": "test.pdf"}, lambda_context)
        
        assert result["status"] == "FAILED"
        assert "Missing 's3_bucket' or 's3_key'" in result["error"]

    def test_handler_returns_failed_on_missing_key(
        self, lambda_context: Any
    ) -> None:
        """Test handler returns FAILED when s3_key is missing."""
        get_settings.cache_clear()

        from handler.main import handler

        result = handler({"s3_bucket": "my-bucket"}, lambda_context)
        
        assert result["status"] == "FAILED"
        assert "Missing 's3_bucket' or 's3_key'" in result["error"]

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
        lambda_context: Any,
    ) -> None:
        """Test handler with S3 trigger event format."""
        get_settings.cache_clear()

        mock_download.return_value = b"fake pdf content"
        mock_hash.return_value = "abc123hash"
        mock_total_pages.return_value = 50
        mock_analyze.return_value = []
        mock_generate_events.return_value = []

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

        result = handler(s3_event, lambda_context)

        assert result["status"] == "SUCCESS"
        assert result["s3_bucket"] == "datalake-raw-dev"
        assert result["s3_key"] == "crf/clinical_pdfs/Keytruda/20260520/doc.pdf"
        assert result["product_name"] == "Keytruda"
        mock_download.assert_called_once_with(
            "datalake-raw-dev",
            "crf/clinical_pdfs/Keytruda/20260520/doc.pdf"
        )

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
        lambda_context: Any,
    ) -> None:
        """Test handler decodes URL-encoded S3 keys from trigger."""
        get_settings.cache_clear()

        mock_download.return_value = b"fake pdf content"
        mock_hash.return_value = "hash"
        mock_total_pages.return_value = 10
        mock_analyze.return_value = []
        mock_generate_events.return_value = []

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

        result = handler(s3_event, lambda_context)

        assert result["status"] == "SUCCESS"
        # Key should be decoded
        assert result["s3_key"] == "path/My Product/2026/file name.pdf"
        mock_download.assert_called_once_with(
            "bucket",
            "path/My Product/2026/file name.pdf"
        )


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


class TestTextractEvents:
    """Tests for Textract event generation."""

    def test_generate_textract_events_basic(
        self, sample_page_info: list[dict[str, Any]]
    ) -> None:
        """Test basic textract event generation."""
        from handler.utils.textract_events import generate_textract_events

        events = generate_textract_events(
            sample_page_info, "test-bucket", "path/Keytruda/20260520/doc.pdf", "Keytruda"
        )

        # Should have events for pages 7, 8, 32 (page 9 has no table)
        assert len(events) == 4
        
        # Check first event (Table 1, page 7)
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
            sample_page_info, "bucket", "key", "Product"
        )

        # Page 8 is continuation of Table 1
        page_8_event = next(e for e in events if e["page"] == 8)
        assert page_8_event["table_number"] == 1
        assert page_8_event["table_name"] == "Table 1: Recommended dose"

    def test_generate_textract_events_multiple_tables_on_page(
        self, sample_page_info: list[dict[str, Any]]
    ) -> None:
        """Test multiple tables on same page."""
        from handler.utils.textract_events import generate_textract_events

        events = generate_textract_events(
            sample_page_info, "bucket", "key", "Product"
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
            sample_page_info, "bucket", "key", "Product"
        )

        # Should be sorted: Table 1 (p7, p8), Table 6 (p32), Table 7 (p32)
        table_numbers = [e["table_number"] for e in events]
        assert table_numbers == [1, 1, 6, 7]


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
