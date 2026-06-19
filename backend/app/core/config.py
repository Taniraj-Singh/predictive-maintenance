from functools import lru_cache
from pathlib import Path
from typing import List, Optional, Union
import os

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    project_name: str = "Predictive Maintenance Platform"
    environment: str = "local"
    debug: bool = True

    # Database
    postgres_user: str = "pm_user"
    postgres_password: str = "pm_pass"
    postgres_db: str = "pm_db"
    postgres_host: str = "postgres"
    postgres_port: int = 5432

    # MQTT
    mqtt_broker_host: str = "mqtt"
    mqtt_broker_port: int = 1883
    mqtt_topics: Union[List[str], str] = ["factory/#", "edge/#", "sensors/+/telemetry"]
    
    @field_validator("mqtt_topics", mode="before")
    @classmethod
    def parse_mqtt_topics(cls, v):
        """Parse MQTT topics from environment variable (comma-separated string) or list"""
        # Check environment variable first
        env_topics = os.getenv("MQTT_TOPICS")
        if env_topics:
            # Environment variable takes precedence
            return [topic.strip() for topic in env_topics.split(",") if topic.strip()]
        
        if isinstance(v, str):
            # Split by comma and strip whitespace
            return [topic.strip() for topic in v.split(",") if topic.strip()]
        return v

    # OPC UA (defaults are safe placeholders; real endpoints are configured via UI)
    opcua_default_endpoint_url: str = "opc.tcp://localhost:4840"
    opcua_default_namespace_index: int = 2
    opcua_default_sampling_interval_ms: int = 1000
    opcua_default_session_timeout_ms: int = 60000

    # AI service
    ai_service_url: str = "http://ai-service:8000"

    # Auth / Security
    # NOTE: jwt_secret MUST be overridden via the JWT_SECRET env var in any
    # non-local environment. A startup guard (see validate_production_secrets)
    # refuses to boot with the insecure default when environment != "local".
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_exp_minutes: int = 60

    # Notifications — all credentials come from the environment only.
    # No secrets are hardcoded here; email features stay disabled until
    # EMAIL_SMTP_USER / EMAIL_SMTP_PASS are provided via env / .env.
    email_smtp_host: str = "smtp.gmail.com"
    email_smtp_port: int = 587
    email_smtp_user: Optional[str] = None
    email_smtp_pass: Optional[str] = None
    slack_webhook_url: Optional[str] = None
    notification_email: Optional[str] = None

    # Alarms — flood protection / offline detection
    # Suppress duplicate alarms for the same sensor+severity within this window.
    alarm_flood_window_seconds: int = 300
    # A sensor with no reading for longer than this is considered offline.
    sensor_offline_after_seconds: int = 300
    # How often the offline-sensor scan runs.
    sensor_offline_scan_interval_seconds: int = 120

    # Reporting
    reports_dir: Path = Path("./reports")
    
    # Refresh token
    refresh_token_exp_days: int = 30

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        # Environment variables take precedence over env_file
        env_file_ignore_empty = True


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    # Clear cache if MQTT_TOPICS env var changed
    settings = Settings()
    return settings


def validate_production_secrets(settings: "Settings") -> None:
    """Refuse to run with insecure defaults outside local/dev.

    Called from application startup. Raises RuntimeError when the environment
    is production-like but secrets were left at their insecure defaults.
    """
    if settings.environment.lower() in {"local", "dev", "development", "test"}:
        return
    problems = []
    if settings.jwt_secret in {"change-me", "change-me-in-production", ""}:
        problems.append("JWT_SECRET is using an insecure default")
    if settings.postgres_password in {"pm_pass", "postgres", ""}:
        problems.append("POSTGRES_PASSWORD is using an insecure default")
    if problems:
        raise RuntimeError(
            "Refusing to start in environment '%s' with insecure secrets: %s. "
            "Set strong values via environment variables."
            % (settings.environment, "; ".join(problems))
        )

def clear_settings_cache():
    """Clear settings cache - useful for testing or env var changes"""
    get_settings.cache_clear()

