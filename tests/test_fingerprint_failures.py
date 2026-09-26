"""Regression tests: a fingerprint provider outage must not cost a clip.

Why this file exists: ``audd`` and ``acoustid`` are HTTP calls to someone
else's server. Every exception out of ``identify()`` used to fall into
``process_clip``'s catch-all handler, which meant a single timeout or 502:

1. marked the clip ``failed`` — a dead end, with no route to the manual-tag
   page that the "we didn't recognize it" path offers,
2. rolled the session back, so the orphan cleanup deleted the thumbnail AND
   the audio sample it had just made (see test_upload_failure_cleanup.py),
   destroying the very sample a retry would need, and
3. left no record that a provider was ever involved, so the clip was
   indistinguishable from a genuine miss and nothing could sweep it up later.

The clip was fine. The network blipped. Four guarantees are pinned here:

1. Retry-worthy provider errors (timeout, connection, 5xx, 429) are retried
   with bounded exponential backoff; answers and permanent errors are not.
2. A provider that stays unreachable degrades the clip to ``unidentified``
   (the manual-tag path), never ``failed`` and never a 5xx to the uploader.
3. The attempt survives as a dead-letter ``Recognition`` row, so an outage is
   a queryable backlog instead of a silent pile of "unidentified".
4. ``retry_fingerprint`` replays that backlog off the PRESERVED audio sample,
   without re-running ffmpeg or the excitement analysis.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from nhac.analysis import excitement
from nhac.audio import ffmpeg
from nhac.constants import (
    FINGERPRINT_MAX_ATTEMPTS,
    STORAGE_PREFIX_AUDIO,
    STORAGE_PREFIX_THUMBNAIL,
)
from nhac.db import SessionLocal
from nhac.enums import ClipStatus, MatchSource
from nhac.fingerprint import retry as retry_mod
from nhac.fingerprint.base import (
    Fingerprinter,
    FingerprintMatch,
    FingerprintUnavailable,
)
from nhac.fingerprint.retry import RetryingFingerprinter, is_transient
from nhac.models import Clip, Recognition
from nhac.pipeline.process_clip import retry_fingerprint
from nhac.services.clips import list_provider_failures
from nhac.storage import get_storage

_MATCH = FingerprintMatch(
    matched=True, title="1901", artist="Phoenix", album="Wolfgang", confidence=0.9
)


def _http_error(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://api.audd.io/")
    return httpx.HTTPStatusError(
        f"server said {status}",
        request=request,
        response=httpx.Response(status, request=request),
    )


class _Scripted(Fingerprinter):
    """Provider that replays a script of outcomes, counting the calls.

    An entry that is an exception is raised; anything else is returned. The
    last entry repeats, so a one-item script is a permanent condition.
    """

    name = "audd"  # pose as a real provider: name transparency is tested below

    def __init__(self, *outcomes: object) -> None:
        self.outcomes = list(outcomes)
        self.calls = 0

    def identify(self, audio_path: Path) -> FingerprintMatch:
        self.calls += 1
        outcome = self.outcomes[min(self.calls - 1, len(self.outcomes) - 1)]
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome  # type: ignore[return-value]


@pytest.fixture()
def no_sleep(monkeypatch):
    """Record backoff delays instead of actually waiting them out."""
    slept: list[float] = []
    monkeypatch.setattr(retry_mod.time, "sleep", slept.append)
    return slept


@pytest.fixture()
def provider(monkeypatch):
    """Install a scripted provider, wrapped exactly as the registry wraps a
    real one. Covers both the upload pipeline and the retry path."""

    def _install(*outcomes: object, wrap: bool = True) -> _Scripted:
        inner = _Scripted(*outcomes)
        served: Fingerprinter = RetryingFingerprinter(inner) if wrap else inner
        monkeypatch.setattr(
            "nhac.pipeline.process_clip.get_fingerprinter", lambda: served
        )
        return inner

    return _install


# ── Guarantee 1: retry only what a retry could fix ──


def test_an_answer_is_never_retried(no_sleep):
    """A clean "no match" is an ANSWER. Retrying it would burn paid API calls
    to be told the same thing three times."""
    inner = _Scripted(FingerprintMatch.no_match(raw={"reason": "unknown song"}))
    result = RetryingFingerprinter(inner).identify(Path("x.mp3"))

    assert result.matched is False
    assert inner.calls == 1
    assert no_sleep == []


def test_a_match_passes_straight_through(no_sleep):
    inner = _Scripted(_MATCH)
    result = RetryingFingerprinter(inner).identify(Path("x.mp3"))

    assert result.title == "1901"
    assert inner.calls == 1
    assert no_sleep == []


def test_transient_error_is_retried_then_succeeds(no_sleep):
    """The case the whole feature exists for: one blip, then a normal answer."""
    inner = _Scripted(httpx.ConnectTimeout("handshake timed out"), _MATCH)
    result = RetryingFingerprinter(inner).identify(Path("x.mp3"))

    assert result.title == "1901"
    assert inner.calls == 2
    assert len(no_sleep) == 1


def test_exhausted_budget_raises_fingerprint_unavailable(no_sleep):
    inner = _Scripted(httpx.ReadTimeout("still nothing"))
    with pytest.raises(FingerprintUnavailable) as caught:
        RetryingFingerprinter(inner).identify(Path("x.mp3"))

    exc = caught.value
    assert inner.calls == FINGERPRINT_MAX_ATTEMPTS
    assert exc.attempts == FINGERPRINT_MAX_ATTEMPTS
    assert exc.transient is True
    assert exc.provider == "audd"
    assert isinstance(exc.__cause__, httpx.ReadTimeout), "original cause lost"


@pytest.mark.parametrize("status", [500, 502, 503, 504, 429])
def test_server_side_and_rate_limit_statuses_are_retried(status, no_sleep):
    inner = _Scripted(_http_error(status), _MATCH)
    result = RetryingFingerprinter(inner).identify(Path("x.mp3"))

    assert inner.calls == 2, f"HTTP {status} should have been retried"
    assert result.title == "1901"


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
def test_client_side_statuses_are_not_retried(status, no_sleep):
    """A rejected key or a malformed request rejects the retry too. Failing
    fast keeps a misconfiguration from tripling every upload's latency."""
    inner = _Scripted(_http_error(status))
    with pytest.raises(FingerprintUnavailable) as caught:
        RetryingFingerprinter(inner).identify(Path("x.mp3"))

    assert inner.calls == 1
    assert caught.value.attempts == 1
    assert caught.value.transient is False
    assert no_sleep == []


def test_non_http_exceptions_are_not_retried(no_sleep):
    """A malformed payload or a missing fpcalc binary is a bug, not weather."""
    inner = _Scripted(ValueError("unexpected JSON shape"))
    with pytest.raises(FingerprintUnavailable) as caught:
        RetryingFingerprinter(inner).identify(Path("x.mp3"))

    assert inner.calls == 1
    assert caught.value.transient is False


def test_backoff_grows_exponentially_and_is_capped(no_sleep):
    inner = _Scripted(httpx.ConnectError("down"))
    wrapper = RetryingFingerprinter(inner, max_attempts=6, base_delay=1.0, max_delay=4.0)
    with pytest.raises(FingerprintUnavailable):
        wrapper.identify(Path("x.mp3"))

    # 5 waits between 6 attempts; doubling until the cap bites.
    assert no_sleep == [1.0, 2.0, 4.0, 4.0, 4.0]


def test_wrapper_keeps_the_real_provider_name(no_sleep):
    """Recognitions record ``provider``; a wrapper name would make every audit
    row read "retrying" instead of who was actually asked."""
    assert RetryingFingerprinter(_Scripted(_MATCH)).name == "audd"


def test_is_transient_classification():
    assert is_transient(httpx.ConnectTimeout("x")) is True
    assert is_transient(httpx.PoolTimeout("x")) is True
    assert is_transient(_http_error(503)) is True
    assert is_transient(_http_error(401)) is False
    assert is_transient(RuntimeError("x")) is False
    assert (
        is_transient(FingerprintUnavailable("x", provider="audd", transient=False))
        is False
    )


def test_registry_wraps_network_providers_but_not_mock(monkeypatch):
    """Policy lives in the registry, so a new provider inherits it for free."""
    from nhac.config import FingerprintProviderName
    from nhac.fingerprint import get_fingerprinter
    from nhac.fingerprint.mock import MockFingerprinter

    get_fingerprinter.cache_clear()
    assert isinstance(get_fingerprinter(), MockFingerprinter)

    monkeypatch.setattr(
        "nhac.fingerprint.settings.fingerprint_provider", FingerprintProviderName.AUDD
    )
    monkeypatch.setattr("nhac.config.settings.audd_api_token", "test-token")
    get_fingerprinter.cache_clear()
    served = get_fingerprinter()
    get_fingerprinter.cache_clear()  # don't leak the fake provider to other tests

    assert isinstance(served, RetryingFingerprinter)
    assert served.name == "audd"


# ── Guarantee 2: an outage degrades, it does not fail ──


def _upload(client, video, name="clip.mp4"):
    resp = client.post("/api/clips", files={"file": (name, video, "video/mp4")})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _db_clip(clip_id: str) -> Clip:
    with SessionLocal() as session:
        clip = session.get(Clip, clip_id)
        assert clip is not None
        session.expunge(clip)
        return clip


def _recognitions(clip_id: str) -> list[Recognition]:
    from sqlalchemy import select

    with SessionLocal() as session:
        rows = list(
            session.scalars(
                select(Recognition)
                .where(Recognition.clip_id == clip_id)
                .order_by(Recognition.created_at)
            )
        )
        for row in rows:
            session.expunge(row)
        return rows


def test_outage_ends_unidentified_not_failed(client, sample_video, provider, no_sleep):
    """``failed`` is a dead end; ``unidentified`` routes to manual tagging.
    The clip is fine — only the provider was unreachable."""
    provider(httpx.ConnectError("api.audd.io unreachable"))

    body = _upload(client, sample_video)

    assert body["clip"]["status"] == ClipStatus.UNIDENTIFIED.value
    assert body["identified"] is False
    assert _db_clip(body["clip"]["id"]).status is ClipStatus.UNIDENTIFIED


def test_outage_does_not_surface_a_500(client, sample_video, provider, no_sleep):
    """The uploader's request must succeed: their clip WAS stored."""
    provider(_http_error(503))
    resp = client.post(
        "/api/clips", files={"file": ("c.mp4", sample_video, "video/mp4")}
    )
    assert resp.status_code == 201, resp.text


def test_web_upload_redirects_to_the_tag_page(client, sample_video, provider, no_sleep):
    """Browser path: the user lands on "tell us what song this is", not on the
    home page with "Processing failed"."""
    provider(httpx.ReadTimeout("no answer"))

    resp = client.post(
        "/upload",
        files={"file": ("c.mp4", sample_video, "video/mp4")},
        follow_redirects=False,
    )

    assert resp.status_code == 303
    assert resp.headers["location"].endswith("/tag")


def test_outage_keeps_the_thumbnail_and_audio_sample(
    client, sample_video, provider, no_sleep
):
    """The subtle one. The old path rolled back, so the orphan sweep deleted
    both derived artifacts — including the audio sample a retry needs. The
    degraded path COMMITS, so both stay referenced and on disk."""
    provider(httpx.ConnectError("down"))

    clip_id = _upload(client, sample_video)["clip"]["id"]
    row = _db_clip(clip_id)
    storage = get_storage()

    assert row.thumbnail_key == f"{STORAGE_PREFIX_THUMBNAIL}/{clip_id}.jpg"
    assert row.audio_key == f"{STORAGE_PREFIX_AUDIO}/{clip_id}.mp3"
    assert storage.exists(row.thumbnail_key), "poster frame lost to a network blip"
    assert storage.exists(row.audio_key), "retry has no sample left to re-send"


def test_manual_tagging_still_works_after_an_outage(
    client, sample_video, provider, no_sleep
):
    """The fallback has to actually work end to end, not just be reachable."""
    provider(httpx.ConnectError("down"))
    clip_id = _upload(client, sample_video)["clip"]["id"]

    resp = client.post(
        f"/api/clips/{clip_id}/tag", json={"artist": "Phoenix", "title": "1901"}
    )

    assert resp.status_code == 200, resp.text
    row = _db_clip(clip_id)
    assert row.status is ClipStatus.MANUALLY_TAGGED
    assert row.match_source is MatchSource.MANUAL
    assert row.concert_id, "manual tag should still group the clip"


# ── Guarantee 3: the attempt is kept as a dead letter ──


def test_outage_writes_a_dead_letter_recognition(
    client, sample_video, provider, no_sleep
):
    provider(_http_error(502))

    clip_id = _upload(client, sample_video)["clip"]["id"]
    rows = _recognitions(clip_id)

    assert len(rows) == 1
    row = rows[0]
    assert row.provider == "audd", "must record who was asked, not the wrapper"
    assert row.matched_song_id is None
    assert row.confidence is None
    assert row.error and "502" in row.error
    assert row.raw_response["transient"] is True
    assert row.raw_response["attempts"] == FINGERPRINT_MAX_ATTEMPTS
    assert row.raw_response["failed_at"]


def test_permanent_failure_is_recorded_as_non_transient(
    client, sample_video, provider, no_sleep
):
    """A bad API key needs a human, not a retry loop — the sweep must be able
    to tell the two apart."""
    provider(_http_error(401))

    clip_id = _upload(client, sample_video)["clip"]["id"]
    row = _recognitions(clip_id)[0]

    assert row.raw_response["transient"] is False
    assert row.raw_response["attempts"] == 1


def test_dead_letter_queue_excludes_genuine_misses(
    client, sample_video, flashy_video, provider, no_sleep
):
    """A real "I don't know that song" is NOT a dead letter. Mixing the two
    would make the sweep re-ask the provider about songs it already answered."""
    provider(FingerprintMatch.no_match(raw={"reason": "unknown"}))
    missed_id = _upload(client, sample_video)["clip"]["id"]

    provider(httpx.ConnectError("down"))
    failed_id = _upload(client, flashy_video, name="flashy.mp4")["clip"]["id"]

    with SessionLocal() as session:
        queued = [c.id for c in list_provider_failures(session)]

    assert failed_id in queued
    assert missed_id not in queued


def test_a_miss_followed_by_an_outage_rejoins_the_queue(
    client, sample_video, provider, no_sleep
):
    """The mirror of the test above, pinning "the latest attempt decides" from
    the other side: a clip the provider once answered but couldn't be reached
    for on a later retry is waiting on the provider again."""
    provider(FingerprintMatch.no_match(raw={"reason": "unknown"}))
    clip_id = _upload(client, sample_video)["clip"]["id"]

    with SessionLocal() as session:
        assert clip_id not in [c.id for c in list_provider_failures(session)]

    provider(httpx.ConnectError("down"))
    retry_fingerprint(clip_id)

    with SessionLocal() as session:
        assert clip_id in [c.id for c in list_provider_failures(session)]


def test_transient_only_filter_reads_the_latest_attempt(
    client, sample_video, provider, no_sleep
):
    """An outage that turns out to be a dead API key must drop out of the
    automated sweep, or every run burns a call to be rejected again."""
    provider(httpx.ConnectError("down"))
    clip_id = _upload(client, sample_video)["clip"]["id"]

    with SessionLocal() as session:
        assert clip_id in [c.id for c in list_provider_failures(session, transient_only=True)]

    provider(_http_error(401))
    retry_fingerprint(clip_id)

    with SessionLocal() as session:
        auto = [c.id for c in list_provider_failures(session, transient_only=True)]
        everything = [c.id for c in list_provider_failures(session)]

    assert clip_id not in auto, "kept retrying a failure a retry cannot fix"
    assert clip_id in everything, "dropped off the backlog entirely"


def test_transient_only_filter_skips_what_a_retry_cannot_fix(
    client, sample_video, flashy_video, provider, no_sleep
):
    provider(_http_error(401))
    permanent_id = _upload(client, sample_video)["clip"]["id"]

    provider(_http_error(503))
    transient_id = _upload(client, flashy_video, name="flashy.mp4")["clip"]["id"]

    with SessionLocal() as session:
        auto = [c.id for c in list_provider_failures(session, transient_only=True)]
        everything = [c.id for c in list_provider_failures(session)]

    assert transient_id in auto
    assert permanent_id not in auto
    assert {transient_id, permanent_id} <= set(everything)


# ── Guarantee 4: the backlog can actually be replayed ──


def test_retry_identifies_from_the_stored_sample(
    client, sample_video, provider, no_sleep
):
    """The provider is back. The clip identifies, groups, and the outage
    breadcrumb is cleared."""
    provider(httpx.ConnectError("down"))
    clip_id = _upload(client, sample_video)["clip"]["id"]

    provider(_MATCH)
    result = retry_fingerprint(clip_id)

    assert result.status is ClipStatus.IDENTIFIED
    row = _db_clip(clip_id)
    assert row.status is ClipStatus.IDENTIFIED
    assert row.match_source is MatchSource.FINGERPRINT
    assert row.concert_id, "a retried clip must still get grouped"
    assert row.error_message is None, "stale outage breadcrumb left on the clip"


def test_retry_does_not_redo_ffmpeg_or_analysis(
    client, sample_video, provider, monkeypatch, no_sleep
):
    """Why the sample is preserved: the retry is an HTTP call, not a rerun of
    the pipeline. Re-analyzing every backlogged clip would make recovering
    from an outage cost more than the original ingest did."""
    provider(httpx.ConnectError("down"))
    clip_id = _upload(client, sample_video)["clip"]["id"]

    def _explode(*args, **kwargs):
        raise AssertionError("retry re-ran the expensive path")

    monkeypatch.setattr(ffmpeg, "extract_audio_sample", _explode)
    monkeypatch.setattr(ffmpeg, "extract_thumbnail", _explode)
    monkeypatch.setattr(excitement, "analyze_and_store", _explode)

    provider(_MATCH)
    assert retry_fingerprint(clip_id).status is ClipStatus.IDENTIFIED


def test_identified_clip_leaves_the_dead_letter_queue(
    client, sample_video, provider, no_sleep
):
    provider(httpx.ConnectError("down"))
    clip_id = _upload(client, sample_video)["clip"]["id"]

    provider(_MATCH)
    retry_fingerprint(clip_id)

    with SessionLocal() as session:
        assert clip_id not in [c.id for c in list_provider_failures(session)]


def test_retry_during_a_continuing_outage_stays_queued(
    client, sample_video, provider, no_sleep
):
    """Still down. The clip must not degrade any further, and the new attempt
    must be recorded too — a retry loop that silently drops evidence is worse
    than no retry at all."""
    provider(httpx.ConnectError("down"))
    clip_id = _upload(client, sample_video)["clip"]["id"]

    provider(_http_error(503))
    result = retry_fingerprint(clip_id)

    assert result.status is ClipStatus.UNIDENTIFIED
    assert _db_clip(clip_id).status is ClipStatus.UNIDENTIFIED
    assert len(_recognitions(clip_id)) == 2, "second attempt not recorded"
    with SessionLocal() as session:
        assert clip_id in [c.id for c in list_provider_failures(session)]


def test_retry_that_answers_with_a_miss_clears_the_error(
    client, sample_video, provider, no_sleep
):
    """The provider answered this time and doesn't know the song. That is a
    real miss, not an outage — it must leave the dead-letter queue so the
    sweep stops asking about it forever."""
    provider(httpx.ConnectError("down"))
    clip_id = _upload(client, sample_video)["clip"]["id"]

    provider(FingerprintMatch.no_match(raw={"reason": "unknown"}))
    result = retry_fingerprint(clip_id)

    assert result.status is ClipStatus.UNIDENTIFIED
    assert _db_clip(clip_id).error_message is None
    with SessionLocal() as session:
        assert clip_id not in [c.id for c in list_provider_failures(session)]


def test_retry_refuses_to_overwrite_a_manual_tag(
    client, sample_video, provider, no_sleep
):
    """The user already answered. A machine guess must never quietly replace a
    human's, however confident it is."""
    provider(httpx.ConnectError("down"))
    clip_id = _upload(client, sample_video)["clip"]["id"]
    client.post(
        f"/api/clips/{clip_id}/tag", json={"artist": "Beabadoobee", "title": "Coffee"}
    )

    provider(_MATCH)
    result = retry_fingerprint(clip_id)

    assert result.status is ClipStatus.MANUALLY_TAGGED
    row = _db_clip(clip_id)
    assert row.match_source is MatchSource.MANUAL
    assert row.manual_title == "Coffee"


def test_retry_without_a_sample_falls_back_to_the_full_pipeline(
    client, sample_video, provider, no_sleep
):
    """Older clips (and any whose sample was swept) still have their raw
    video — the retry must fall back to re-deriving rather than give up."""
    provider(httpx.ConnectError("down"))
    clip_id = _upload(client, sample_video)["clip"]["id"]

    storage = get_storage()
    with SessionLocal() as session:
        clip = session.get(Clip, clip_id)
        storage.delete(clip.audio_key)
        clip.audio_key = None
        session.commit()

    provider(_MATCH)
    result = retry_fingerprint(clip_id)

    assert result.status is ClipStatus.IDENTIFIED
    row = _db_clip(clip_id)
    assert row.audio_key and storage.exists(row.audio_key), "sample not re-derived"
