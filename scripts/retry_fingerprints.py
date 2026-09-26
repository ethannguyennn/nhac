"""Retry clips that a fingerprint-provider outage left untagged.

When AudD/AcoustID is unreachable, ``process_clip`` degrades the clip to
``unidentified`` and records a dead-letter ``Recognition`` row rather than
failing it (see docs/WORKFLOWS.md). Once the provider is healthy again, this
replays those clips against it, re-sending the audio sample already in
storage — no ffmpeg, no re-analysis.

Usage, from the repo root:

    python scripts/retry_fingerprints.py            # list the backlog only
    python scripts/retry_fingerprints.py --run      # retry the transient ones
    python scripts/retry_fingerprints.py --run --all    # include non-transient
    python scripts/retry_fingerprints.py --run --limit 20
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nhac.db import SessionLocal, init_db  # noqa: E402
from nhac.enums import ClipStatus  # noqa: E402
from nhac.logging_config import get_logger  # noqa: E402
from nhac.pipeline.process_clip import retry_fingerprint  # noqa: E402
from nhac.services.clips import list_provider_failures  # noqa: E402

log = get_logger("retry-fingerprints")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="actually retry (default: list)")
    parser.add_argument(
        "--all", action="store_true", help="include failures a retry probably can't fix"
    )
    parser.add_argument("--limit", type=int, default=None, help="cap how many are retried")
    args = parser.parse_args()

    init_db()
    with SessionLocal() as session:
        clips = list_provider_failures(
            session, transient_only=not args.all, limit=args.limit
        )
        backlog = [(c.id, c.original_filename, c.error_message) for c in clips]

    if not backlog:
        log.info("no clips waiting on a provider retry")
        return

    log.info("%d clip(s) in the dead-letter queue:", len(backlog))
    for clip_id, filename, error in backlog:
        log.info("  %s  %-28s %s", clip_id, (filename or "?")[:28], (error or "")[:60])

    if not args.run:
        log.info("dry run - pass --run to retry them")
        return

    identified = still_waiting = errored = 0
    for clip_id, _filename, _error in backlog:
        result = retry_fingerprint(clip_id)
        if result.status is ClipStatus.IDENTIFIED:
            identified += 1
            log.info("%s -> %s - %s", clip_id, result.song_artist, result.song_title)
        elif result.status is ClipStatus.UNIDENTIFIED:
            still_waiting += 1
            log.info("%s -> still unidentified (%s)", clip_id, result.message)
        else:
            errored += 1
            log.warning("%s -> %s (%s)", clip_id, result.status.value, result.message)

    log.info(
        "done: %d identified, %d still unidentified, %d errored",
        identified, still_waiting, errored,
    )


if __name__ == "__main__":
    main()
