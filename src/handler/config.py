"""Configuration management using Pydantic Settings."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    These are set by Terraform in the Lambda function configuration.
    See terraform/main.tf for the environment variables.
    """

    model_config = SettingsConfigDict(case_sensitive=False)

    # Required - from Terraform environment variables (via SSM)
    environment: str  # ENVIRONMENT - "dev", "qa", "prod"
    dynamodb_table_name: str  # DYNAMODB_TABLE_NAME - from SSM
    output_s3_bucket: str  # OUTPUT_S3_BUCKET - from SSM (RAW bucket)
    
    # Optional - with sensible defaults
    aws_region: str = "eu-west-1"
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
