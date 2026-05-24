# Clinical PDF Tables Locator Lambda

[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python)](https://www.python.org/)
[![Poetry](https://img.shields.io/badge/Poetry-1.8%2B-60A5FA?logo=poetry)](https://python-poetry.org/)
[![Docker](https://img.shields.io/badge/Docker-ECR-2496ED?logo=docker)](https://aws.amazon.com/ecr/)
[![Terraform](https://img.shields.io/badge/Terraform-1.10%2B-7B42BC?logo=terraform)](https://www.terraform.io/)

AWS Lambda function that analyzes clinical PDF documents to identify pages containing tables and generates events for downstream AWS Textract processing via Step Functions Distributed Map.

---

## 📋 Table of Contents

- [Overview](#overview)
- [Input/Output Contract](#inputoutput-contract)
- [Features](#features)
- [Repository Structure](#repository-structure)
- [Prerequisites](#prerequisites)
- [Local Development](#local-development)
- [Testing](#testing)
- [Deployment](#deployment)

---

## Overview

This Lambda is the first step in a clinical document processing pipeline:

1. **Locator Lambda** (this) → Analyzes PDF, identifies tables, generates events
2. **Step Functions Distributed Map** → Iterates over `textract_events`
3. **Textract Lambda** → Extracts table data from each page

---

## Input/Output Contract

### Input Event

```json
{
    "s3_bucket": "datalake-raw-dev",
    "s3_key": "crf/clinical_pdfs/Keytruda/20260520173800/document.pdf"
}
```

**Note:** `product_name` is extracted from the S3 key path (second-to-last directory).

### Output

**No return value** - The Lambda writes results to S3 and DynamoDB instead of returning data (avoids 6MB Lambda response limit).

| Storage | Content |
|---------|---------|
| **S3** | `{s3_key}_events.json` - Textract events array for Step Functions Distributed Map |
| **DynamoDB** | Job metadata (job_id, status, product_name, total_pages, etc.) |

On error, the Lambda raises an exception (marks invocation as failed) and updates DynamoDB job status to `FAILED`.

---

## Features

- ✅ **PDF Table Detection** - Uses PyMuPDF to identify pages with tables
- ✅ **Multi-page Table Support** - Continuation pages inherit table info
- ✅ **Multiple Tables per Page** - Tracks `table_index_on_page`
- ✅ **Distributed Map Ready** - Events uploaded to S3 for parallel processing
- ✅ **DynamoDB Job Tracking** - Creates job records for monitoring and status
- ✅ **Product Name Extraction** - Parsed from S3 key path
- ✅ **File Hash** - SHA256 for idempotency checks
- ✅ **Structured Logging** - AWS Lambda Powertools
- ✅ **Modular Architecture** - Utils split into s3, pdf, textract_events, dynamodb

---

## Repository Structure

```
lambda-clinical-pdf-tables-locator-crf/
├── src/
│   └── handler/
│       ├── main.py                 # Lambda handler
│       ├── config.py               # Settings
│       └── utils/
│           ├── __init__.py         # Exports
│           ├── s3.py               # S3 download, upload, hash generation
│           ├── pdf.py              # PDF analysis with PyMuPDF
│           ├── textract_events.py  # Event generation for Distributed Map
│           ├── dynamodb.py         # DynamoDB job tracking
│           └── ssm.py              # SSM utilities
├── tests/
│   ├── conftest.py                 # Pytest fixtures
│   └── test_handler.py             # Unit tests
├── terraform/
│   ├── config.tf                   # Project configuration
│   ├── main.tf                     # Lambda + ECR
│   ├── iam.tf                      # IAM policies (S3, DynamoDB, KMS)
│   ├── ssm_imports.tf              # SSM parameter imports (datalake, DynamoDB)
│   └── ssm_exports.tf              # SSM parameter exports
├── Dockerfile
├── pyproject.toml
├── CHANGELOG.md
└── README.md
```

---

## Environment Variables

The Lambda requires the following environment variables, set by Terraform from SSM parameters:

| Variable | Required | Source | Description |
|----------|----------|--------|-------------|
| `ENVIRONMENT` | ✅ | Terraform | Environment name (dev, qa, prod) |
| `DYNAMODB_TABLE_NAME` | ✅ | SSM | DynamoDB table for job tracking |
| `OUTPUT_S3_BUCKET` | ✅ | SSM | S3 bucket for events JSON output |
| `LOG_LEVEL` | ❌ | Terraform | Log level (default: INFO) |
| `AWS_REGION` | ❌ | Lambda | AWS region (default: eu-west-1) |

---

## Prerequisites

- **Python 3.12+**
- **Poetry 1.8+**
- **Docker**
- **AWS CLI v2**

---

## Local Development

### Install Dependencies

```bash
poetry install --with dev
```

### Run Handler Locally

```bash
poetry run python -c "import sys; sys.path.insert(0,'src'); exec(open('src/handler/main.py').read())"
```

### Run Tests

```bash
make test
```

### Format & Lint

```bash
make format
make lint
```

---

## Testing

### Unit Tests

```bash
make test
```

### Coverage Report

```bash
make coverage
```

---

## Deployment

Deployment is handled via GitHub Actions CI/CD pipeline.

| Branch | Environment |
|--------|-------------|
| `main` | prod |
| `release/*` | qa |
| `develop`, `feature/*` | dev |

---

## License

MIT
