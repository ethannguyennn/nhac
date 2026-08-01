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


def make_flashy_video(path: Path) -> Path:
    """9s video: quiet+dark (3s) → LOUD+FLASHING (3s) → quiet+dark (3s).

    The middle third simulates the "crowd goes wild under strobes" moment the
    excitement analyzer is supposed to find.
    """
    from nhac.config import settings

    cmd = [
        settings.ffmpeg_bin, "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=black:s=320x240:d=3:r=15",
        "-f", "lavfi", "-i",
        "nullsrc=s=320x240:d=3:r=15,"
        "geq=lum='255*gt(mod(floor(T*8),2),0)':cb=128:cr=128",
        "-f", "lavfi", "-i", "color=black:s=320x240:d=3:r=15",
        "-f", "lavfi", "-i", "sine=frequency=220:d=3",
        "-f", "lavfi", "-i", "anoisesrc=d=3:amplitude=0.8:colour=pink",
        "-f", "lavfi", "-i", "sine=frequency=220:d=3",
        "-filter_complex",
        "[3:a]volume=0.03[a0];[5:a]volume=0.03[a2];"
        "[0:v][a0][1:v][4:a][2:v][a2]concat=n=3:v=1:a=1[v][a]",
        "-map", "[v]", "-map", "[a]",
        "-pix_fmt", "yuv420p", "-c:v", "libx264", "-c:a", "aac",
        "-y", str(path),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return path


@pytest.fixture()
def flashy_video_path(tmp_path) -> Path:
    return make_flashy_video(tmp_path / "flashy.mp4")


@pytest.fixture()
def flashy_video(flashy_video_path) -> bytes:
    return flashy_video_path.read_bytes()
