# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.3.0] - 2026-06-16

### Added

- **Multi-Product PDF Support** - Detects and associates tables with their correct product formulations
  - Detects "1. NAME OF THE MEDICINAL PRODUCT" sections in PDFs
  - Extracts product formulation names (e.g., "Tecentriq 840 mg concentrate for solution")
  - Associates each table with its formulation using `formulation_key`
  - Allows same table number (e.g., "Table 1") to exist in different formulation sections

- **Hybrid Table Detection** - Improved table detection combining structural and text-based methods
  - Primary: PyMuPDF structural detection with improved parameters
  - Fallback: Text pattern detection for complex tables (clinical data patterns)
  - Detects tables with: n=X, percentages, 95% CI, hazard ratios, median time

- **New PDF Utility Functions**
  - `detect_product_sections()` - Find all product formulation sections in PDF
  - `extract_product_formulations()` - Extract formulation names from text
  - `get_formulation_for_page()` - Get formulation info for a specific page
  - `has_table_content_patterns()` - Check for clinical table data patterns

### Changed

- **`analyze_pdf_pages()` Return Type** - Now returns tuple `(page_info, product_sections)`
- **Textract Events** - Include `formulation_key` and `formulations` for multi-product PDFs
- **Event Sorting** - Multi-product events sorted by formulation_key, then table_number, then page
- **Logging** - Added detection method tracking (structural vs text_pattern)

### Event Output (Multi-Product PDF)

```json
{
  "job_id": "abc123...",
  "table_number": 1,
  "page": 4,
  "formulation_key": "840_1200mg",
  "formulations": [
    "Tecentriq 840 mg concentrate for solution for infusion",
    "Tecentriq 1200 mg concentrate for solution for infusion"
  ]
}
```

---

## [2.2.0] - 2026-06-09

### Added

- **Incremental Reprocessing** - Table-level tracking in DynamoDB to avoid reprocessing successful tables
  - `get_job_status()` - Check if job already exists
  - `get_processed_tables()` - Get status of all tables for a job
  - `filter_pending_events()` - Filter events to only pending/failed tables
- **Force Reprocess Flag** - `force_reprocess: true` in event bypasses idempotency checks
- **Job ID in Events** - Each Textract event now includes `job_id` for tracking

### Changed

- **Idempotency** - Same PDF (by content hash) skips already successful tables
- **Job Status** - Updates to `REPROCESSING` when reprocessing existing job

---

## [2.1.0] - 2026-05-24

### Added

- **DynamoDB Job Tracking** - Creates job records in DynamoDB for monitoring and status tracking
- **S3 Events Upload** - Uploads textract events JSON to S3 for Step Functions Distributed Map
- **Job Status Updates** - Updates job status to FAILED on errors with error message
- **DynamoDB Utility Module** - New `utils/dynamodb.py` with `create_job_record` and `update_job_status`

### Changed

- **No Return Value** - Handler no longer returns data (avoids 6MB Lambda response limit)
- **Error Handling** - Raises exceptions on failure instead of returning error dict
- **Config** - `ENVIRONMENT`, `DYNAMODB_TABLE_NAME`, `OUTPUT_S3_BUCKET` now required from env vars (via SSM)
- **IAM Permissions** - Added DynamoDB write and S3 PutObject permissions

### New Environment Variables

| Variable | Source | Description |
|----------|--------|-------------|
| `ENVIRONMENT` | Terraform | Environment name (dev, qa, prod) |
| `DYNAMODB_TABLE_NAME` | SSM | DynamoDB table for job tracking |
| `OUTPUT_S3_BUCKET` | SSM | S3 bucket for events JSON output |

### Output Storage

| Storage | Content |
|---------|---------|
| S3 | `{s3_key}_events.json` - Textract events for Distributed Map |
| DynamoDB | Job metadata (job_id, status, product_name, etc.) |

---

## [2.0.0] - 2026-05-20

### Added

- **Textract Events Output** - Generates self-contained events for Step Functions Distributed Map
- **Product Name Extraction** - Automatically extracted from S3 key path
- **Multi-page Table Support** - Continuation pages inherit table info from previous page
- **Multiple Tables per Page** - Tracks `table_index_on_page` for pages with multiple tables
- **Modular Architecture** - Split code into utils modules (s3.py, pdf.py, textract_events.py)

### Changed

- **Output Format** - Now returns `textract_events` array instead of `page_groups`
- **Input Contract** - Removed `product_name` from input, extracted from `s3_key` path
- **Handler Returns FAILED** - Instead of raising exceptions, returns error status
- **Logging** - Replaced print statements with structured PowerTools logging

### Input/Output Contract

**Input:**
```json
{
    "s3_bucket": "bucket-name",
    "s3_key": "path/product_name/yyyymmddhhmmss/document.pdf"
}
```

**Output:**
```json
{
    "status": "SUCCESS",
    "s3_bucket": "bucket-name",
    "s3_key": "path/product_name/yyyymmddhhmmss/document.pdf",
    "product_name": "product_name",
    "file_hash": "sha256-hash",
    "total_pages": 100,
    "total_tables": 25,
    "textract_events": [
        {
            "s3_bucket": "bucket-name",
            "s3_key": "path/product_name/yyyymmddhhmmss/document.pdf",
            "product_name": "product_name",
            "table_name": "Table 1: ...",
            "table_number": 1,
            "page": 7,
            "table_index_on_page": 0
        }
    ]
}
```

---

## [1.0.0] - 2026-04-30

### Added

- **Lambda Function Template** - Production-ready Python 3.12 Lambda with Poetry
- **Docker Container Deployment** - Multi-stage Dockerfile for ECR
- **Terraform Infrastructure** - Lambda, IAM roles, CloudWatch Logs, SSM exports
- **GitHub Actions CI/CD** - OIDC authentication, multi-environment support
- **AWS Lambda Powertools** - Logger, Tracer, structured logging
- **SSM Integration** - Read datalake bucket/KMS ARNs from Parameter Store
- **Unit Tests** - pytest with 80% coverage requirement
- **Code Quality** - ruff linter, mypy type checking
- **Makefile** - Common development commands

### CI/CD Features

- **Manual Trigger** - `workflow_dispatch` for deploy/destroy actions
- **Environment Detection** - Automatic env based on branch (main→prod, release/*→qa, *→dev)
- **ECR Management** - Automatic repository creation via AWS CLI
- **Terraform Destroy** - Manual cleanup action to remove all infrastructure

### Template Mode

- Workflow triggers commented out by default
- Step-by-step setup instructions in README
- Configure GitHub secrets and uncomment triggers to enable

### Infrastructure Created

| Resource | Description |
|----------|-------------|
| Lambda Function | Container-based with X-Ray tracing |
| IAM Role | Execution role with S3, KMS, CloudWatch permissions |
| ECR Repository | Created by CI/CD, lifecycle policy managed by Terraform |
| CloudWatch Logs | Log group with 14-day retention |
| SSM Parameters | Function ARN, name, invoke ARN, role ARN exports |
