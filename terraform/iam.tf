# =============================================================================
# IAM Role and Policies for Lambda - Clinical PDF Tables Locator
# =============================================================================
# This Lambda needs:
# - S3 GetObject on RAW bucket (to download PDFs)
# - S3 PutObject on RAW bucket (to upload events JSON)
# - KMS Decrypt on RAW bucket KMS key (to decrypt PDFs)
# - DynamoDB PutItem/UpdateItem on clinical-pdf-jobs table (job tracking)
# - CloudWatch Logs (basic execution)
# - X-Ray tracing

# -----------------------------------------------------------------------------
# Lambda Execution Role
# -----------------------------------------------------------------------------
resource "aws_iam_role" "lambda" {
  name = "${local.full_name}-lambda"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = merge(local.common_tags, {
    Name = "${local.full_name}-lambda"
  })
}

# -----------------------------------------------------------------------------
# Basic Lambda Execution Policy (CloudWatch Logs)
# -----------------------------------------------------------------------------
resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# -----------------------------------------------------------------------------
# X-Ray Tracing Policy
# -----------------------------------------------------------------------------
resource "aws_iam_role_policy_attachment" "lambda_xray" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/AWSXRayDaemonWriteAccess"
}

# -----------------------------------------------------------------------------
# S3 Read/Write Access - RAW Bucket
# -----------------------------------------------------------------------------
resource "aws_iam_role_policy" "s3_access" {
  name = "${local.full_name}-s3-access"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "S3GetObject"
        Effect = "Allow"
        Action = [
          "s3:GetObject"
        ]
        Resource = [
          "${local.datalake.raw.bucket_arn}/*"
        ]
      },
      {
        Sid    = "S3PutObject"
        Effect = "Allow"
        Action = [
          "s3:PutObject"
        ]
        Resource = [
          "${local.datalake.raw.bucket_arn}/crf/clinical_pdfs/*"
        ]
      }
    ]
  })
}

# -----------------------------------------------------------------------------
# KMS Access - RAW Bucket KMS Key (Decrypt for read, GenerateDataKey for write)
# -----------------------------------------------------------------------------
resource "aws_iam_role_policy" "kms_access" {
  name = "${local.full_name}-kms-access"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "KMSReadWrite"
        Effect = "Allow"
        Action = [
          "kms:Decrypt",        # Required for s3:GetObject on encrypted bucket
          "kms:GenerateDataKey" # Required for s3:PutObject on encrypted bucket
        ]
        Resource = [
          local.datalake.raw.kms_key_arn
        ]
      }
    ]
  })
}

# -----------------------------------------------------------------------------
# DynamoDB Write Access - Clinical PDF Jobs Table
# -----------------------------------------------------------------------------
resource "aws_iam_role_policy" "dynamodb_write" {
  name = "${local.full_name}-dynamodb-write"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "DynamoDBWriteAccess"
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:GetItem"
        ]
        Resource = [
          local.dynamodb.clinical_pdf_jobs.table_arn
        ]
      }
    ]
  })
}
