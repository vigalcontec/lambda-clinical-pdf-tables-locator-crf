# =============================================================================
# IAM Role and Policies for Lambda - Clinical PDF Tables Locator
# =============================================================================
# This Lambda only needs:
# - S3 GetObject on RAW bucket (to download PDFs)
# - KMS Decrypt on RAW bucket KMS key (to decrypt PDFs)
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
# S3 Read Access - RAW Bucket Only
# -----------------------------------------------------------------------------
resource "aws_iam_role_policy" "s3_read" {
  name = "${local.full_name}-s3-read"
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
      }
    ]
  })
}

# -----------------------------------------------------------------------------
# KMS Decrypt - RAW Bucket KMS Key Only
# -----------------------------------------------------------------------------
resource "aws_iam_role_policy" "kms_decrypt" {
  name = "${local.full_name}-kms-decrypt"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "KMSDecrypt"
        Effect = "Allow"
        Action = [
          "kms:Decrypt"
        ]
        Resource = [
          local.datalake.raw.kms_key_arn
        ]
      }
    ]
  })
}
