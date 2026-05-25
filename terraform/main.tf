# =============================================================================
# AWS Lambda with ECR Container Image
# =============================================================================

terraform {
  required_version = ">= 1.10.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = local.aws_region

  default_tags {
    tags = local.common_tags
  }
}

# -----------------------------------------------------------------------------
# Data Sources
# -----------------------------------------------------------------------------
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# -----------------------------------------------------------------------------
# ECR Repository (created by CI/CD via AWS CLI, referenced here)
# -----------------------------------------------------------------------------
data "aws_ecr_repository" "lambda" {
  name = local.full_name
}

# Lifecycle policy for the ECR repository
resource "aws_ecr_lifecycle_policy" "lambda" {
  repository = data.aws_ecr_repository.lambda.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep last 10 images"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 10
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}

# -----------------------------------------------------------------------------
# Lambda Function
# -----------------------------------------------------------------------------
resource "aws_lambda_function" "main" {
  function_name = local.full_name
  role          = aws_iam_role.lambda.arn
  package_type  = "Image"
  image_uri     = "${data.aws_ecr_repository.lambda.repository_url}:${var.image_tag}"

  timeout     = local.timeout
  memory_size = local.memory_size

  memory = 1024

  environment {
    variables = {
      ENVIRONMENT                  = var.environment
      LOG_LEVEL                    = local.log_level
      POWERTOOLS_SERVICE_NAME      = local.function_name
      POWERTOOLS_METRICS_NAMESPACE = local.project_name

      # Datalake RAW bucket (source PDFs and output events)
      OUTPUT_S3_BUCKET = local.datalake.raw.bucket_name

      # DynamoDB table for job tracking
      DYNAMODB_TABLE_NAME = local.dynamodb.clinical_pdf_jobs.table_name
    }
  }

  tracing_config {
    mode = "Active"
  }

  # Ephemeral storage for large PDF processing (default 512MB)
  ephemeral_storage {
    size = 1024  # 1GB - needed for PyMuPDF temp files
  }

  tags = {
    Name = local.full_name
  }

  depends_on = [
    aws_cloudwatch_log_group.lambda
  ]
}

# -----------------------------------------------------------------------------
# CloudWatch Log Group
# -----------------------------------------------------------------------------
resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${local.full_name}"
  retention_in_days = local.log_retention_days

  tags = {
    Name = local.full_name
  }
}

# -----------------------------------------------------------------------------
# Lambda Permission - Allow S3 to invoke Lambda
# -----------------------------------------------------------------------------
resource "aws_lambda_permission" "s3" {
  statement_id  = "AllowS3Invoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.main.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = local.datalake.raw.bucket_arn
}

# -----------------------------------------------------------------------------
# S3 Bucket Notification - Trigger Lambda on object creation
# -----------------------------------------------------------------------------
resource "aws_s3_bucket_notification" "lambda_trigger" {
  bucket = local.datalake.raw.bucket_name

  lambda_function {
    lambda_function_arn = aws_lambda_function.main.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "crf/clinical_pdfs/"
    filter_suffix       = ".pdf"
  }

  depends_on = [aws_lambda_permission.s3]
}
