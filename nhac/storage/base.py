"""Storage protocol shared by every backend."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class Storage(Protocol):
    """Object storage abstraction keyed by string keys (e.g. ``raw/<id>.mp4``)."""

    def save_bytes(self, key: str, data: bytes, content_type: str | None = None) -> str:
        """Store ``data`` under ``key``; return the key."""

    def save_file(self, key: str, src_path: Path, content_type: str | None = None) -> str:
        """Store the file at ``src_path`` under ``key``; return the key."""

    def open_local_path(self, key: str) -> Path:
        """Return a local filesystem path to the object's bytes.

        Local backend returns the real path; remote backends download to a temp
        file. Used by ffmpeg which needs a real path to read.
        """

    def exists(self, key: str) -> bool: ...

    def delete(self, key: str) -> None: ...

    def url_for(self, key: str) -> str:
        """Public/served URL a client can use to fetch the object."""
