"""Pytest fixtures. Sets up an isolated temp DB + storage BEFORE importing the
app, so tests never touch your real ./var data.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

import pytest

# ── Isolate config before any nhac import (settings is a cached singleton) ──
_TMP = Path(tempfile.mkdtemp(prefix="nhac_test_"))
os.environ["NHAC_DATABASE_URL"] = f"sqlite:///{(_TMP / 'test.sqlite3').as_posix()}"
os.environ["NHAC_LOCAL_STORAGE_DIR"] = str(_TMP / "media")
os.environ["NHAC_FINGERPRINT_PROVIDER"] = "mock"
os.environ["NHAC_ENV"] = "test"


@pytest.fixture(scope="session")
def app_module():
    from nhac.main import app

    return app


@pytest.fixture()
def client(app_module):
    from fastapi.testclient import TestClient

    with TestClient(app_module) as c:
        yield c


def _make_video(path: Path, freq: int = 330, seconds: int = 3) -> Path:
    """Generate a tiny real video (with audio) via ffmpeg for upload tests."""
    from nhac.config import settings

    cmd = [
        settings.ffmpeg_bin, "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", f"testsrc2=size=320x240:rate=15:duration={seconds}",
        "-f", "lavfi", "-i", f"sine=frequency={freq}:duration={seconds}",
        "-shortest", "-pix_fmt", "yuv420p", "-c:v", "libx264", "-c:a", "aac",
        "-y", str(path),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return path


@pytest.fixture()
def sample_video(tmp_path) -> bytes:
    path = _make_video(tmp_path / "clip.mp4")
    return path.read_bytes()
