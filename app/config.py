from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "CyArt DarkTrace Health Monitoring Service"
    app_version: str = "1.0.0"

    aes_secret_key: str

    redis_url: str = "redis://localhost:6379/0"
    database_url: str = "postgresql://localhost:5432/darktrace"

    crawler_heartbeat_interval: int = 30
    crawler_heartbeat_ttl: int = 60
    crawler_heartbeat_max_age: int = 300

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


settings = Settings()
