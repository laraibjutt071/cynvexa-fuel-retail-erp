from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Known placeholder values that must never reach a production deployment -
# shipped in .env.example / this repo's docs as "replace me" text, not real
# secrets. Checked case-insensitively so a copy-paste with different casing
# still gets caught.
_INSECURE_JWT_SECRET_PLACEHOLDERS = {
    "replace-with-a-generated-secret-never-commit-this",
    "changeme",
    "secret",
    "test-secret-key-not-for-production-use-only",
}
_MIN_PRODUCTION_JWT_SECRET_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    env: Literal["development", "test", "staging", "production"] = "development"

    database_url: str = "postgresql+asyncpg://cynvexa:cynvexa@localhost:5432/cynvexa"

    # A dedicated database for the automated test suite only - never read by
    # the running application itself (nothing in app/ references this field
    # except the test suite's own conftest.py). Kept here, not hardcoded in
    # conftest.py, so it goes through the same env-file/env-var loading path
    # as every other setting and is visible in one place. See
    # docs/TEST_DATABASE_ISOLATION_REPORT.md for why this exists.
    test_database_url: str | None = None

    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30

    cors_allowed_origins: str = "http://localhost:3000"

    @model_validator(mode="after")
    def _reject_weak_production_jwt_secret(self) -> "Settings":
        # jwt_secret_key being required (no default) already makes the app
        # refuse to start with no value at all, in any environment. This
        # adds the second half: in production specifically, also refuse a
        # *present but weak* secret - too short, or a known placeholder
        # copied from .env.example / test fixtures without being replaced.
        if self.env != "production":
            return self
        secret = self.jwt_secret_key
        if secret.lower() in _INSECURE_JWT_SECRET_PLACEHOLDERS:
            raise ValueError(
                "JWT_SECRET_KEY is set to a known placeholder/example value. "
                "Generate a real secret before starting in production: "
                'python -c "import secrets; print(secrets.token_urlsafe(48))"'
            )
        if len(secret) < _MIN_PRODUCTION_JWT_SECRET_LENGTH:
            raise ValueError(
                f"JWT_SECRET_KEY must be at least {_MIN_PRODUCTION_JWT_SECRET_LENGTH} characters "
                "in production. Generate a real secret: "
                'python -c "import secrets; print(secrets.token_urlsafe(48))"'
            )
        return self

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
