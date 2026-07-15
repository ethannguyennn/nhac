from pathlib import Path

from nhac.fingerprint.mock import MockFingerprinter


def test_mock_is_deterministic(tmp_path: Path):
    f = MockFingerprinter()
    p = tmp_path / "a.mp3"
    p.write_bytes(b"hello world" * 100)
    first = f.identify(p)
    second = f.identify(p)
    assert first.matched == second.matched
    assert first.title == second.title
    assert first.artist == second.artist


def test_mock_returns_variety_and_misses(tmp_path: Path):
    f = MockFingerprinter()
    titles = set()
    saw_miss = False
    for i in range(60):
        p = tmp_path / f"c{i}.mp3"
        p.write_bytes(f"content-{i}".encode() * 50)
        m = f.identify(p)
        if m.matched:
            titles.add(m.title)
            assert 0.0 <= (m.confidence or 0) <= 1.0
        else:
            saw_miss = True
    assert len(titles) >= 3  # variety across inputs
    assert saw_miss  # exercises the manual-tag fallback
