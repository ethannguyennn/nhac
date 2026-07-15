"""Storage backend selection.

The rest of the app depends only on the ``Storage`` protocol, so switching from
local disk to Cloudflare R2 / S3 is a config change, not a code change.
"""

from __future__ import annotations

from functools import lru_cache

from nhac.config import StorageBackend, settings
from nhac.storage.base import Storage
from nhac.storage.local import LocalStorage


@lru_cache
def get_storage() -> Storage:
    if settings.storage_backend is StorageBackend.S3:
        from nhac.storage.s3 import S3Storage  # lazy: boto3 only needed for S3

        return S3Storage()
    return LocalStorage()


__all__ = ["Storage", "get_storage"]
