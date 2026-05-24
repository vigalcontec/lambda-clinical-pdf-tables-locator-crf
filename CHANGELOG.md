# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.1.0] - 2026-05-24

### Added

- **DynamoDB Job Tracking** - Creates job records in DynamoDB for monitoring and status tracking
- **S3 Events Upload** - Uploads textract events JSON to S3 for Step Functions Distributed Map
- **Job Status Updates** - Updates job status to FAILED on errors with error message
- **DynamoDB Utility Module** - New `utils/dynamodb.py` with `create_job_record` and `update_job_status`

### Changed

- **Output Format** - Now includes `job_id`, `events_s3_uri`, and `dynamodb_table` in response
- **Config** - `ENVIRONMENT`, `DYNAMODB_TABLE_NAME`, `OUTPUT_S3_BUCKET` now required from env vars (via SSM)
- **IAM Permissions** - Added DynamoDB write and S3 PutObject permissions

### New Environment Variables

| Variable | Source | Description |
|----------|--------|-------------|
| `ENVIRONMENT` | Terraform | Environment name (dev, qa, prod) |
| `DYNAMODB_TABLE_NAME` | SSM | DynamoDB table for job tracking |
| `OUTPUT_S3_BUCKET` | SSM | S3 bucket for events JSON output |

### New Output Fields

| Field | Description |
|-------|-------------|
| `job_id` | Unique job identifier (file_hash) |
| `events_s3_uri` | S3 URI of uploaded events JSON |
| `dynamodb_table` | DynamoDB table name used |
| `textract_events_count` | Number of events generated |

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
