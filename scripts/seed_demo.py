"""Seed demo-mode content so a brand-new install feels alive.

Generates a few short synthetic concert clips with ffmpeg (color pattern + tone),
stores them, and wires up real Song/Clip/Concert/Playlist rows — so demo
concerts actually play. Idempotent: re-running won't duplicate.

Run from the repo root:  python scripts/seed_demo.py
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

# Make the repo root importable when run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nhac.audio import ffmpeg  # noqa: E402
from nhac.config import settings  # noqa: E402
from nhac.constants import (  # noqa: E402
    STORAGE_PREFIX_RAW,
    STORAGE_PREFIX_THUMBNAIL,
)
from nhac.db import SessionLocal, init_db  # noqa: E402
from nhac.enums import ClipStatus, MatchSource  # noqa: E402
from nhac.logging_config import get_logger  # noqa: E402
from nhac.models import Clip, Concert  # noqa: E402
from nhac.services.playlists import add_clip_to_playlist, ensure_concert_playlist  # noqa: E402
from nhac.services.songs import upsert_song  # noqa: E402
from nhac.services.users import get_or_create_default_user  # noqa: E402
from nhac.storage import get_storage  # noqa: E402

log = get_logger("seed")

DEMO = [
    {
        "concert": "Phoenix — Greek Theatre",
        "artist": "Phoenix",
        "venue": "Greek Theatre",
        "city": "Los Angeles",
        "performed_on": date(2024, 8, 17),
        "songs": [
            ("Lisztomania", "Wolfgang Amadeus Phoenix", 300),
            ("1901", "Wolfgang Amadeus Phoenix", 440),
        ],
    },
    {
        "concert": "Beabadoobee — The Fonda",
        "artist": "Beabadoobee",
        "venue": "The Fonda Theatre",
        "city": "Los Angeles",
        "performed_on": date(2024, 10, 12),
        "songs": [
            ("Coffee", "Loveworm", 520),
            ("The Perfect Pair", "Beatopia", 620),
        ],
    },
]


def _generate_clip_video(out_path: Path, freq: int, seconds: int = 6) -> None:
    """Synthesize a short portrait video + tone with ffmpeg (lavfi)."""
    cmd = [
        settings.ffmpeg_bin,
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        f"testsrc2=size=720x1280:rate=30:duration={seconds}",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency={freq}:duration={seconds}",
        "-shortest",
        "-pix_fmt",
        "yuv420p",
        "-c:v",
        "libx264",
        "-c:a",
        "aac",
        "-y",
        str(out_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)


def main() -> None:
    init_db()
    storage = get_storage()
    tmp_dir = Path(tempfile.mkdtemp(prefix="nhac_seed_"))
    session = SessionLocal()
    try:
        user = get_or_create_default_user(session)

        for demo in DEMO:
            existing = (
                session.query(Concert)
                .filter(Concert.owner_id == user.id, Concert.title == demo["concert"])
                .first()
            )
            if existing:
                log.info("demo concert already present: %s", demo["concert"])
                continue

            concert = Concert(
                owner_id=user.id,
                title=demo["concert"],
                artist=demo["artist"],
                venue=demo["venue"],
                city=demo["city"],
                performed_on=demo["performed_on"],
                is_demo=True,
            )
            session.add(concert)
            session.flush()
            playlist = ensure_concert_playlist(session, concert)

            for title, album, freq in demo["songs"]:
                video_tmp = tmp_dir / f"{freq}.mp4"
                _generate_clip_video(video_tmp, freq)
                info = ffmpeg.probe(video_tmp)

                song = upsert_song(session, title=title, artist=demo["artist"], album=album)
                clip = Clip(
                    uploader_id=user.id,
                    concert_id=concert.id,
                    status=ClipStatus.IDENTIFIED,
                    song_id=song.id,
                    match_source=MatchSource.FINGERPRINT,
                    match_confidence=0.9,
                    original_filename=f"{title}.mp4",
                    content_type="video/mp4",
                    duration_seconds=info.duration_seconds,
                    width=info.width,
                    height=info.height,
                    size_bytes=video_tmp.stat().st_size,
                )
                session.add(clip)
                session.flush()

                raw_key = f"{STORAGE_PREFIX_RAW}/{clip.id}.mp4"
                storage.save_file(raw_key, video_tmp, content_type="video/mp4")
                clip.raw_video_key = raw_key

                thumb_tmp = tmp_dir / f"{freq}.jpg"
                if ffmpeg.extract_thumbnail(video_tmp, thumb_tmp):
                    thumb_key = f"{STORAGE_PREFIX_THUMBNAIL}/{clip.id}.jpg"
                    storage.save_file(thumb_key, thumb_tmp, content_type="image/jpeg")
                    clip.thumbnail_key = thumb_key

                add_clip_to_playlist(session, playlist, clip.id)
                log.info("seeded clip: %s — %s", demo["artist"], title)

            session.commit()

        log.info("✅ demo seed complete")
    finally:
        session.close()
        import shutil

        shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
