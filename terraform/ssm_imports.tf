# =============================================================================
# SSM Parameter Imports - Datalake Configuration
# =============================================================================
# This Lambda only reads from RAW bucket (downloads PDFs for analysis)

# -----------------------------------------------------------------------------
# Raw Layer Only
# -----------------------------------------------------------------------------
data "aws_ssm_parameter" "raw_bucket_name" {
  name            = "/${var.environment}/datalake/raw/bucket_name"
  with_decryption = true
}

data "aws_ssm_parameter" "raw_bucket_arn" {
  name            = "/${var.environment}/datalake/raw/bucket_arn"
  with_decryption = true
}

data "aws_ssm_parameter" "raw_kms_key_arn" {
  name            = "/${var.environment}/datalake/raw/kms_key_arn"
  with_decryption = true
}

# -----------------------------------------------------------------------------
# Local Variables for Easy Access
# -----------------------------------------------------------------------------
locals {
  datalake = {
    raw = {
      bucket_name = data.aws_ssm_parameter.raw_bucket_name.value
      bucket_arn  = data.aws_ssm_parameter.raw_bucket_arn.value
      kms_key_arn = data.aws_ssm_parameter.raw_kms_key_arn.value
    }
  }
}
