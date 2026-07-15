"""Application settings, loaded from environment / .env (pydantic-settings).

Import the singleton ``settings`` everywhere; it is validated once at startup so
the app fails fast on misconfiguration.
"""

from __future__ import annotations

from enum import Enum
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class StorageBackend(str, Enum):
    LOCAL = "local"
    S3 = "s3"


class FingerprintProviderName(str, Enum):
    MOCK = "mock"
    AUDD = "audd"
    ACOUSTID = "acoustid"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="NHAC_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    env: str = "development"
    log_level: str = "INFO"
    secret_key: str = "dev-insecure-change-me"

    # Database
    database_url: str = "sqlite:///./var/nhac.sqlite3"

    # Storage
    storage_backend: StorageBackend = StorageBackend.LOCAL
    local_storage_dir: Path = Path("./var/media")
    media_base_url: str = "/media"

    # S3 / R2
    s3_bucket: str = "nhac-media"
    s3_endpoint_url: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_region: str = "auto"
    s3_public_base_url: str = ""

    # Fingerprinting
    fingerprint_provider: FingerprintProviderName = FingerprintProviderName.MOCK
    audd_api_token: str = ""
    acoustid_api_key: str = ""

    # Media processing
    ffmpeg_path: str = ""
    ffprobe_path: str = ""

    # Auth (MVP single-user)
    default_user_email: str = "you@example.com"

    # Derived paths
    data_dir: Path = Field(default=Path("./var"))

    @property
    def ffmpeg_bin(self) -> str:
        return self.ffmpeg_path or "ffmpeg"

    @property
    def ffprobe_bin(self) -> str:
        return self.ffprobe_path or "ffprobe"

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
