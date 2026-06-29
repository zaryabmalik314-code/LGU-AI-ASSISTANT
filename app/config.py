"""
Unified Configuration Manager (Phase 9).
"""
import os
from pydantic_settings import BaseSettings
from pydantic import Field

class Settings(BaseSettings):
    database_url: str = Field(
        "postgresql://postgres:postgres@localhost:5432/lgu_rec",
        validation_alias="DATABASE_URL"
    )
    redis_url: str | None = Field(
        None,
        validation_alias="REDIS_URL"
    )
    groq_api_key: str | None = Field(
        None,
        validation_alias="GROQ_API_KEY"
    )
    policy_scheduler_enabled: bool = Field(
        False,
        validation_alias="POLICY_SCHEDULER_ENABLED"
    )
    policy_schedule_hour: int = Field(
        3,
        validation_alias="POLICY_SCHEDULE_HOUR"
    )
    policy_schedule_minute: int = Field(
        0,
        validation_alias="POLICY_SCHEDULE_MINUTE"
    )
    environment: str = Field(
        "production",
        validation_alias="ENVIRONMENT"
    )
    log_level: str = Field(
        "INFO",
        validation_alias="LOG_LEVEL"
    )

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore"
    }

# Create a global instance
settings = Settings()
