from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    env: Literal["development", "test", "staging", "production"] = "development"

    database_url: str = "postgresql+asyncpg://cynvexa:cynvexa@localhost:5432/cynvexa"

    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30

    cors_allowed_origins: str = "http://localhost:3000"

    # Local-disk evidence storage. NOT durable across container restarts or
    # safe with more than one backend instance - a real deployment must swap
    # this for object storage (S3 or equivalent) before going live with more
    # than a single-instance pilot. See Attachment model + docs/ASSUMPTIONS.md.
    upload_dir: str = "uploads"
    max_upload_size_bytes: int = 10 * 1024 * 1024

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
