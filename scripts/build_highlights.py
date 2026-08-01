"""Backfill excitement highlights (and optionally hype-cut montages) for
clips that predate the analyzer.

Usage, from the repo root:

    python scripts/build_highlights.py            # analyze clips missing highlights
    python scripts/build_highlights.py --montage  # ...and render missing montages
    python scripts/build_highlights.py --force    # re-analyze everything
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from nhac.analysis.excitement import analyze_and_store  # noqa: E402
from nhac.db import SessionLocal, init_db  # noqa: E402
from nhac.logging_config import get_logger  # noqa: E402
from nhac.models import Clip  # noqa: E402
from nhac.pipeline.montage import MontageError, build_montage  # noqa: E402
from nhac.storage import get_storage  # noqa: E402

log = get_logger("backfill")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--montage", action="store_true", help="also render missing montages")
    parser.add_argument("--force", action="store_true", help="re-analyze even if present")
    args = parser.parse_args()

    init_db()
    storage = get_storage()
    analyzed = skipped = failed = montaged = 0

    with SessionLocal() as session:
        clips = list(
            session.scalars(select(Clip).where(Clip.raw_video_key.is_not(None)))
        )
        log.info("found %d clip(s) with stored video", len(clips))

        for clip in clips:
            if clip.highlights and not args.force:
                skipped += 1
                continue
            try:
                raw_path = storage.open_local_path(clip.raw_video_key)
                analyze_and_store(session, clip, raw_path)
                session.commit()
                analyzed += 1
            except Exception as exc:  # noqa: BLE001 - keep going, report at the end
                session.rollback()
                log.warning("analysis failed for %s: %s", clip.id, exc)
                failed += 1

    if args.montage:
        with SessionLocal() as session:
            clip_ids = list(
                session.scalars(
                    select(Clip.id).where(
                        Clip.raw_video_key.is_not(None), Clip.montage_key.is_(None)
                    )
                )
            )
        for clip_id in clip_ids:
            try:
                result = build_montage(clip_id)
                montaged += 1
                log.info("montage %s → %s", clip_id, result.montage_key)
            except MontageError as exc:
                log.warning("montage failed for %s: %s", clip_id, exc)
                failed += 1

    log.info(
        "done: %d analyzed, %d skipped, %d montage(s) built, %d failed",
        analyzed, skipped, montaged, failed,
    )


if __name__ == "__main__":
    main()
