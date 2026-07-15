"""S3 / Cloudflare R2 storage backend.

Off by default. Requires the ``s3`` extra (``pip install -e ".[s3]"``) and the
NHAC_S3_* settings. boto3 is imported lazily so the local MVP has no dependency
on it.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from nhac.config import settings


class S3Storage:
    def __init__(self) -> None:
        import boto3  # lazy import

        self._bucket = settings.s3_bucket
        self._public_base = settings.s3_public_base_url.rstrip("/")
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url or None,
            aws_access_key_id=settings.s3_access_key_id or None,
            aws_secret_access_key=settings.s3_secret_access_key or None,
            region_name=settings.s3_region or None,
        )

    def save_bytes(self, key: str, data: bytes, content_type: str | None = None) -> str:
        extra = {"ContentType": content_type} if content_type else {}
        self._client.put_object(Bucket=self._bucket, Key=key, Body=data, **extra)
        return key

    def save_file(self, key: str, src_path: Path, content_type: str | None = None) -> str:
        extra = {"ContentType": content_type} if content_type else {}
        self._client.upload_file(str(src_path), self._bucket, key, ExtraArgs=extra or None)
        return key

    def open_local_path(self, key: str) -> Path:
        suffix = Path(key).suffix
        fd, tmp = tempfile.mkstemp(suffix=suffix)
        Path(tmp).unlink(missing_ok=True)
        self._client.download_file(self._bucket, key, tmp)
        return Path(tmp)

    def exists(self, key: str) -> bool:
        from botocore.exceptions import ClientError

        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
            return True
        except ClientError:
            return False

    def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=key)

    def url_for(self, key: str) -> str:
        if self._public_base:
            return f"{self._public_base}/{key}"
        # Fall back to a short-lived presigned GET.
        return self._client.generate_presigned_url(
            "get_object", Params={"Bucket": self._bucket, "Key": key}, ExpiresIn=3600
        )
