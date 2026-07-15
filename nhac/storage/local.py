"""Local-filesystem storage backend (MVP default)."""

from __future__ import annotations

import shutil
from pathlib import Path

from nhac.config import settings


class LocalStorage:
    def __init__(self, root: Path | None = None, base_url: str | None = None) -> None:
        self.root = Path(root or settings.local_storage_dir).resolve()
        self.base_url = (base_url or settings.media_base_url).rstrip("/")
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        # Prevent path traversal; keys are app-generated but be defensive.
        safe = Path(key.replace("\\", "/"))
        if safe.is_absolute() or ".." in safe.parts:
            raise ValueError(f"Unsafe storage key: {key!r}")
        target = (self.root / safe).resolve()
        if not str(target).startswith(str(self.root)):
            raise ValueError(f"Unsafe storage key: {key!r}")
        return target

    def save_bytes(self, key: str, data: bytes, content_type: str | None = None) -> str:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    def save_file(self, key: str, src_path: Path, content_type: str | None = None) -> str:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src_path, path)
        return key

    def open_local_path(self, key: str) -> Path:
        path = self._path(key)
        if not path.exists():
            raise FileNotFoundError(key)
        return path

    def exists(self, key: str) -> bool:
        return self._path(key).exists()

    def delete(self, key: str) -> None:
        path = self._path(key)
        if path.exists():
            path.unlink()

    def url_for(self, key: str) -> str:
        return f"{self.base_url}/{key.replace(chr(92), '/')}"
