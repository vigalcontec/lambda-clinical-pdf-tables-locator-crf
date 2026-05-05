"""Tests for Lambda handler - Clinical PDF Tables Locator."""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from handler.config import Settings, get_settings


class TestHandler:
    """Tests for main handler function."""

    @patch("handler.main.find_pages_with_tables")
    @patch("handler.main.generate_file_hash")
    @patch("handler.main.download_pdf_from_s3")
    def test_handler_success(
        self,
        mock_download: MagicMock,
        mock_hash: MagicMock,
        mock_find_pages: MagicMock,
        pdf_event: dict[str, Any],
        lambda_context: Any,
    ) -> None:
        """Test successful handler execution."""
        get_settings.cache_clear()

        # Setup mocks
        mock_download.return_value = b"fake pdf content"
        mock_hash.return_value = "abc123hash"
        mock_find_pages.return_value = [1, 5, 10]

        with patch("handler.main.fitz") as mock_fitz:
            mock_doc = MagicMock()
            mock_doc.__len__ = MagicMock(return_value=20)
            mock_fitz.open.return_value = mock_doc

            from handler.main import handler

            result = handler(pdf_event, lambda_context)

        assert result["status"] == "SUCCESS"
        assert result["file_hash"] == "abc123hash"
        assert result["total_pages"] == 20
        assert result["pages_to_process"] == [1, 5, 10]

    def test_handler_missing_bucket(self, lambda_context: Any) -> None:
        """Test handler raises error when s3_bucket is missing."""
        get_settings.cache_clear()

        from handler.main import handler

        with pytest.raises(ValueError, match="Missing 's3_bucket' or 's3_key'"):
            handler({"s3_key": "test.pdf"}, lambda_context)

    def test_handler_missing_key(self, lambda_context: Any) -> None:
        """Test handler raises error when s3_key is missing."""
        get_settings.cache_clear()

        from handler.main import handler

        with pytest.raises(ValueError, match="Missing 's3_bucket' or 's3_key'"):
            handler({"s3_bucket": "my-bucket"}, lambda_context)

    def test_handler_empty_event(self, lambda_context: Any) -> None:
        """Test handler raises error with empty event."""
        get_settings.cache_clear()

        from handler.main import handler

        with pytest.raises(ValueError, match="Missing 's3_bucket' or 's3_key'"):
            handler({}, lambda_context)


class TestDownloadPdfFromS3:
    """Tests for S3 download function."""

    @patch("handler.main.s3_client")
    def test_download_pdf_from_s3(self, mock_s3: MagicMock) -> None:
        """Test downloading PDF from S3."""
        from handler.main import download_pdf_from_s3

        mock_body = MagicMock()
        mock_body.read.return_value = b"pdf content"
        mock_s3.get_object.return_value = {"Body": mock_body}

        result = download_pdf_from_s3("my-bucket", "path/to/file.pdf")

        assert result == b"pdf content"
        mock_s3.get_object.assert_called_once_with(Bucket="my-bucket", Key="path/to/file.pdf")


class TestGenerateFileHash:
    """Tests for file hash generation."""

    def test_generate_file_hash(self) -> None:
        """Test SHA256 hash generation."""
        from handler.main import generate_file_hash

        content = b"test content"
        result = generate_file_hash(content)

        # SHA256 of "test content"
        assert len(result) == 64  # SHA256 hex is 64 characters
        assert result == "6ae8a75555209fd6c44157c0aed8016e763ff435a19cf186f76863140143ff72"

    def test_generate_file_hash_same_content_same_hash(self) -> None:
        """Test same content produces same hash."""
        from handler.main import generate_file_hash

        content = b"same content"
        hash1 = generate_file_hash(content)
        hash2 = generate_file_hash(content)

        assert hash1 == hash2

    def test_generate_file_hash_different_content_different_hash(self) -> None:
        """Test different content produces different hash."""
        from handler.main import generate_file_hash

        hash1 = generate_file_hash(b"content 1")
        hash2 = generate_file_hash(b"content 2")

        assert hash1 != hash2


class TestFindPagesWithTables:
    """Tests for page scanning function."""

    @patch("handler.main.fitz")
    def test_find_pages_with_tables(self, mock_fitz: MagicMock) -> None:
        """Test finding pages containing 'table' keyword."""
        from handler.main import find_pages_with_tables

        # Setup mock document with 3 pages
        mock_doc = MagicMock()
        mock_doc.__len__ = MagicMock(return_value=3)

        mock_page1 = MagicMock()
        mock_page1.get_text.return_value = "This page has a table with data"

        mock_page2 = MagicMock()
        mock_page2.get_text.return_value = "This page has no relevant content"

        mock_page3 = MagicMock()
        mock_page3.get_text.return_value = "Another TABLE here"

        mock_doc.load_page.side_effect = [mock_page1, mock_page2, mock_page3]
        mock_fitz.open.return_value = mock_doc

        result = find_pages_with_tables(b"fake pdf")

        # Pages 1 and 3 contain "table" (1-indexed)
        assert result == [1, 3]
        mock_doc.close.assert_called_once()

    @patch("handler.main.fitz")
    def test_find_pages_with_tables_no_matches(self, mock_fitz: MagicMock) -> None:
        """Test when no pages contain keywords."""
        from handler.main import find_pages_with_tables

        mock_doc = MagicMock()
        mock_doc.__len__ = MagicMock(return_value=2)

        mock_page = MagicMock()
        mock_page.get_text.return_value = "Just regular text without keywords"

        mock_doc.load_page.return_value = mock_page
        mock_fitz.open.return_value = mock_doc

        result = find_pages_with_tables(b"fake pdf")

        assert result == []

    @patch("handler.main.fitz")
    def test_find_pages_with_tables_empty_document(self, mock_fitz: MagicMock) -> None:
        """Test with empty document."""
        from handler.main import find_pages_with_tables

        mock_doc = MagicMock()
        mock_doc.__len__ = MagicMock(return_value=0)
        mock_fitz.open.return_value = mock_doc

        result = find_pages_with_tables(b"fake pdf")

        assert result == []


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
