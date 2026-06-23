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
    size = 1024 # 1GB - needed for PyMuPDF temp files
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
# EventBridge Rule - Trigger Lambda on PDF upload
# -----------------------------------------------------------------------------
# Uses EventBridge instead of S3 bucket notification to avoid conflicts with
# the aws-datalake-layers module which manages the bucket notification.
resource "aws_cloudwatch_event_rule" "pdf_upload" {
  name        = "${local.full_name}-pdf-trigger"
  description = "Trigger Locator Lambda when PDF is uploaded to S3"

  event_pattern = jsonencode({
    source      = ["aws.s3"]
    detail-type = ["Object Created"]
    detail = {
      bucket = {
        name = [local.datalake.raw.bucket_name]
      }
      object = {
        key = [{
          wildcard = "crf/clinical_pdfs/*.pdf"
        }]
      }
    }
  })

  tags = local.common_tags
}

# -----------------------------------------------------------------------------
# EventBridge Target - Lambda Function
# -----------------------------------------------------------------------------
resource "aws_cloudwatch_event_target" "lambda" {
  rule      = aws_cloudwatch_event_rule.pdf_upload.name
  target_id = "TriggerLocatorLambda"
  arn       = aws_lambda_function.main.arn

  # Transform S3 event to Lambda input format
  input_transformer {
    input_paths = {
      bucket = "$.detail.bucket.name"
      key    = "$.detail.object.key"
      size   = "$.detail.object.size"
    }
    input_template = <<EOF
{
  "source": "eventbridge",
  "bucket": <bucket>,
  "key": <key>,
  "size": <size>
}
EOF
  }
}

# -----------------------------------------------------------------------------
# Lambda Permission - Allow EventBridge to invoke Lambda
# -----------------------------------------------------------------------------
resource "aws_lambda_permission" "eventbridge" {
  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.main.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.pdf_upload.arn
}
