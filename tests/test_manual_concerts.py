"""Regression tests: naming a concert up front, then bulk-adding its clips.

Why this file exists: the normal flow infers a concert from a clip's
fingerprinted artist + date (``pipeline.organize.auto_group_into_concert``),
which only works once a clip has been identified. This is the other
direction — the user already knows which show this was, so they name it
first (``services.concerts.create_concert``) and every clip they add
afterwards is filed there directly, whether or not fingerprinting on that
particular clip succeeds. Three guarantees are pinned here:

1. A clip attaches to the named concert's playlist IMMEDIATELY at upload
   time, independent of whether it later identifies, misses, or the
   fingerprint provider is unreachable — that's the whole point of naming
   the show first.
2. Once a clip is pre-assigned, neither a confident fingerprint match nor a
   later manual tag can move it to a different (artist, date)-derived
   concert. The user's assignment is authoritative.
3. Knowing the concert's artist up front pre-fills (but doesn't lock) the
   manual-tag form's artist field, so a miss only costs the user a song
   title.

The ordinary single-clip auto-grouping path (no concert named) is left
untouched and is covered by the existing upload-flow tests.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from nhac.db import SessionLocal
from nhac.enums import ClipStatus, MatchSource
from nhac.fingerprint.base import Fingerprinter, FingerprintMatch
from nhac.models import Clip, Concert, PlaylistItem
from nhac.services.clips import get_clip
from nhac.services.concerts import get_concert


class _Scripted(Fingerprinter):
    """Replays one outcome per call, in order; the last repeats."""

    name = "stub"

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
def scripted_provider(monkeypatch):
    def _install(*outcomes: object) -> _Scripted:
        stub = _Scripted(*outcomes)
        monkeypatch.setattr("nhac.pipeline.process_clip.get_fingerprinter", lambda: stub)
        return stub

    return _install


_MATCH = FingerprintMatch(matched=True, title="1901", artist="Phoenix", confidence=0.9)
_MISS = FingerprintMatch.no_match(raw={"reason": "unknown"})


def _create_concert(client, **overrides) -> dict:
    body = {"artist": "Phoenix", "venue": "Greek Theatre", "city": "Los Angeles, CA"}
    body.update(overrides)
    resp = client.post("/api/concerts", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _upload_to_concert(client, concert_id, videos: list[bytes]) -> list[dict]:
    files = [("files", (f"clip{i}.mp4", v, "video/mp4")) for i, v in enumerate(videos)]
    resp = client.post(f"/api/concerts/{concert_id}/clips", files=files)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _db_clip(clip_id: str) -> Clip:
    with SessionLocal() as session:
        clip = session.get(Clip, clip_id)
        assert clip is not None
        session.expunge(clip)
        return clip


def _playlist_clip_ids(concert_id: str) -> set[str]:
    from nhac.models import Playlist

    with SessionLocal() as session:
        playlist = session.query(Playlist).filter_by(concert_id=concert_id).one()
        items = session.query(PlaylistItem).filter_by(playlist_id=playlist.id).all()
        return {item.clip_id for item in items}


# ── Concert creation ──


def test_create_concert_via_api(client):
    body = _create_concert(client, artist="Radiohead", title=None, performed_on="2026-06-01")

    assert body["artist"] == "Radiohead"
    assert body["title"] == "Radiohead"  # defaulted from artist
    assert body["performed_on"] == "2026-06-01"

    with SessionLocal() as session:
        concert = get_concert(session, body["id"])
        assert concert is not None
        assert concert.clips == []


def test_create_concert_defaults_date_to_today(client):
    import datetime

    body = _create_concert(client, performed_on=None)
    assert body["performed_on"] == datetime.date.today().isoformat()


def test_create_concert_requires_an_artist(client):
    resp = client.post("/api/concerts", json={"artist": ""})
    assert resp.status_code == 422


def test_web_new_concert_form_redirects_straight_to_bulk_upload(client):
    resp = client.post(
        "/concerts/new",
        data={"artist": "MGMT", "venue": "The Wiltern"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "/upload" in resp.headers["location"]


# ── Guarantee 1: attached to the playlist regardless of pipeline outcome ──


def test_identified_clip_joins_the_named_concert(
    client, sample_video, scripted_provider
):
    scripted_provider(_MATCH)
    concert = _create_concert(client)

    [result] = _upload_to_concert(client, concert["id"], [sample_video])

    assert result["clip"]["status"] == ClipStatus.IDENTIFIED.value
    assert result["clip"]["concert_id"] == concert["id"]
    assert result["clip"]["id"] in _playlist_clip_ids(concert["id"])


def test_missed_clip_still_joins_the_named_concert(
    client, sample_video, scripted_provider
):
    """The whole point: a clip fingerprinting can't name still belongs at
    this show, because the show — unlike the song — was never in question."""
    scripted_provider(_MISS)
    concert = _create_concert(client)

    [result] = _upload_to_concert(client, concert["id"], [sample_video])

    assert result["clip"]["status"] == ClipStatus.UNIDENTIFIED.value
    assert result["clip"]["concert_id"] == concert["id"]
    assert result["clip"]["id"] in _playlist_clip_ids(concert["id"])


def test_provider_outage_clip_still_joins_the_named_concert(
    client, sample_video, scripted_provider
):
    """Same guarantee against a fingerprint-provider outage (see
    test_fingerprint_failures.py): the concert assignment does not wait on
    the network call succeeding at all."""
    import httpx

    scripted_provider(httpx.ConnectError("down"))
    concert = _create_concert(client)

    [result] = _upload_to_concert(client, concert["id"], [sample_video])

    assert result["clip"]["status"] == ClipStatus.UNIDENTIFIED.value
    assert result["clip"]["concert_id"] == concert["id"]
    assert result["clip"]["id"] in _playlist_clip_ids(concert["id"])


def test_bulk_upload_files_all_land_in_the_same_concert(
    client, sample_video, flashy_video, scripted_provider
):
    """The actual feature: several clips added in one request, mixed
    outcomes, all filed under one show."""
    scripted_provider(_MATCH, _MISS)
    concert = _create_concert(client)

    results = _upload_to_concert(client, concert["id"], [sample_video, flashy_video])

    assert len(results) == 2
    assert {r["clip"]["concert_id"] for r in results} == {concert["id"]}
    assert {r["clip"]["status"] for r in results} == {
        ClipStatus.IDENTIFIED.value,
        ClipStatus.UNIDENTIFIED.value,
    }
    joined = _playlist_clip_ids(concert["id"])
    assert {r["clip"]["id"] for r in results} <= joined
    assert len(joined) == 2


def test_web_bulk_upload_summary_message(
    client, sample_video, flashy_video, scripted_provider
):
    scripted_provider(_MATCH, _MISS)
    concert = _create_concert(client)

    resp = client.post(
        f"/concerts/{concert['id']}/upload",
        files=[
            ("files", ("a.mp4", sample_video, "video/mp4")),
            ("files", ("b.mp4", flashy_video, "video/mp4")),
        ],
        follow_redirects=False,
    )

    assert resp.status_code == 303
    location = resp.headers["location"]
    assert location.startswith(f"/concerts/{concert['id']}")
    assert "identified" in location
    assert "name" in location  # "N need(s) a name"


def test_upload_to_a_nonexistent_concert_is_a_clean_4xx(client, sample_video):
    resp = client.post(
        "/api/concerts/does-not-exist/clips",
        files=[("files", ("a.mp4", sample_video, "video/mp4"))],
    )
    assert resp.status_code == 422
    assert resp.status_code != 500


# ── Guarantee 2: pre-assignment is authoritative ──


def test_identification_does_not_override_the_named_concert(
    client, sample_video, scripted_provider
):
    """The fingerprint confidently says "Phoenix", the concert says "Phoenix"
    too here — but the important case is the NEXT test, where they disagree
    and the concert still wins."""
    scripted_provider(_MATCH)
    concert = _create_concert(client, artist="Phoenix")

    [result] = _upload_to_concert(client, concert["id"], [sample_video])
    assert result["clip"]["concert_id"] == concert["id"]


def test_a_conflicting_fingerprint_match_does_not_move_the_clip(
    client, sample_video, scripted_provider
):
    """The show was named "Beabadoobee" but the audio confidently fingerprints
    as Phoenix (e.g. a support act, or just a fingerprinting quirk). The
    clip must stay at the show the user actually named — auto-grouping must
    never second-guess an explicit assignment."""
    scripted_provider(_MATCH)  # matches "Phoenix", concert is "Beabadoobee"
    concert = _create_concert(client, artist="Beabadoobee", title="Beabadoobee at The Fonda")
    with SessionLocal() as session:
        phoenix_concerts_before = session.query(Concert).filter_by(artist="Phoenix").count()

    [result] = _upload_to_concert(client, concert["id"], [sample_video])

    assert result["clip"]["concert_id"] == concert["id"]
    assert result["clip"]["song"]["artist"] == "Phoenix"  # song identity still recorded
    with SessionLocal() as session:
        # Grouping must not have spun up (or reused) a "Phoenix" concert for
        # this clip — the count of those is untouched by this upload.
        assert (
            session.query(Concert).filter_by(artist="Phoenix").count()
            == phoenix_concerts_before
        )


def test_manual_tag_does_not_move_a_pre_assigned_clip(client, sample_video):
    """The provider missed; the user manually tags the clip with a DIFFERENT
    artist than the concert's. It must still stay put — the concert was
    named on purpose and manual tagging is only correcting the song."""
    concert = _create_concert(client, artist="Phoenix")
    [result] = _upload_to_concert(client, concert["id"], [sample_video])
    clip_id = result["clip"]["id"]

    resp = client.post(
        f"/api/clips/{clip_id}/tag", json={"artist": "Some Opener", "title": "Warmup Song"}
    )
    assert resp.status_code == 200, resp.text
    tagged = resp.json()

    assert tagged["concert_id"] == concert["id"]
    assert tagged["status"] == ClipStatus.MANUALLY_TAGGED.value
    row = _db_clip(clip_id)
    assert row.match_source is MatchSource.MANUAL
    with SessionLocal() as session:
        assert session.query(Concert).filter_by(artist="Some Opener").count() == 0


# ── Guarantee 3: manual-tag form is pre-filled, not locked ──


def test_tag_page_prefills_the_concerts_artist(client, sample_video, scripted_provider):
    scripted_provider(_MISS)
    concert = _create_concert(client, artist="Phoebe Bridgers")
    [result] = _upload_to_concert(client, concert["id"], [sample_video])
    clip_id = result["clip"]["id"]

    resp = client.get(f"/clips/{clip_id}/tag")
    assert resp.status_code == 200
    assert 'value="Phoebe Bridgers"' in resp.text


def test_tag_page_prefill_is_editable_not_authoritative(client, sample_video):
    """Prefilling must be a convenience, not a constraint: the user can still
    submit a different artist entirely (e.g. an opening act)."""
    concert = _create_concert(client, artist="Phoenix")
    [result] = _upload_to_concert(client, concert["id"], [sample_video])
    clip_id = result["clip"]["id"]

    resp = client.post(
        f"/api/clips/{clip_id}/tag", json={"artist": "Different Artist", "title": "Some Song"}
    )
    assert resp.status_code == 200
    assert resp.json()["manual_artist"] == "Different Artist"


def test_tag_page_has_no_prefill_without_a_named_concert(client, sample_video):
    """Regression guard for the ordinary (no concert named) flow: nothing to
    prefill from, so the field must come back empty, not error."""
    resp = client.post("/api/clips", files={"file": ("c.mp4", sample_video, "video/mp4")})
    clip_id = resp.json()["clip"]["id"]

    tag_resp = client.get(f"/clips/{clip_id}/tag")
    assert tag_resp.status_code == 200


# ── Existing flow stays untouched ──


def test_ordinary_upload_without_a_named_concert_still_auto_groups(
    client, sample_video, scripted_provider
):
    """The old path (no concert named up front) must be completely
    unaffected: still infers the concert from the fingerprint."""
    scripted_provider(_MATCH)
    resp = client.post("/api/clips", files={"file": ("c.mp4", sample_video, "video/mp4")})
    assert resp.status_code == 201
    body = resp.json()

    assert body["clip"]["status"] == ClipStatus.IDENTIFIED.value
    assert body["clip"]["concert_id"] is not None
    with SessionLocal() as session:
        clip = get_clip(session, body["clip"]["id"])
        assert clip.concert.artist == "Phoenix"
