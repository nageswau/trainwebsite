from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "EduSphere"
    environment: str = "development"
    log_level: str = "INFO"
    secret_key: str = "change-me"
    access_token_minutes: int = 60
    refresh_token_days: int = 14
    database_url: str = "postgresql+asyncpg://edusphere:edusphere@localhost:5432/edusphere"
    redis_url: str = "redis://localhost:6379/0"
    frontend_url: str = "http://localhost:3000"
    cookie_secure: bool = False
    auto_create_schema: bool = True
    aws_region: str = "eu-west-2"
    aws_s3_bucket: str | None = None
    local_upload_dir: str = "/data/uploads"
    crm_webhook_url: str | None = None
    whatsapp_webhook_url: str | None = None
    sms_webhook_url: str | None = None
    email_webhook_url: str | None = None
    inbound_email_webhook_secret: str | None = None
    google_client_id: str | None = None
    google_client_secret: str | None = None
    google_refresh_token: str | None = None
    google_calendar_id: str = "primary"
    zoho_client_id: str | None = None
    zoho_client_secret: str | None = None
    zoho_refresh_token: str | None = None
    zoho_organization_id: str | None = None
    zoho_presenter_id: str | None = None
    zoho_accounts_url: str = "https://accounts.zoho.com"
    zoho_meeting_base_url: str = "https://meeting.zoho.com"
    max_upload_bytes: int = 20 * 1024 * 1024
    allowed_upload_types: str = "application/pdf,image/jpeg,image/png,text/plain,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    razorpay_key_id: str | None = None
    razorpay_key_secret: str | None = None
    razorpay_webhook_secret: str | None = None
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
