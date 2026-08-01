# Nhạc 🎵

> _Relive the moment._

Nhạc (Vietnamese for "music") turns the scattered concert videos on your phone
into a clean, replayable "greatest hits" experience. Upload a clip — Nhạc pulls
the audio, **identifies the song** by audio fingerprinting (Shazam-style, not
AI), and **auto-organizes** it into a playlist by concert and song. Then you
relive it with a video player and a warm audio-reactive visualizer.

**This is a working MVP**, written in **Python** and runnable on your laptop
with **zero external accounts** — SQLite, local file storage, and an offline
"mock" song-recognizer by default. Real cloud storage and fingerprinting
providers are wired and one config flag away.

---

## What works today

- 📤 **Upload** a concert video (web, mobile-first — open it on your phone browser)
- 🎧 **Audio extraction** from the video via ffmpeg
- 🔎 **Song identification** through a pluggable fingerprinter (offline mock by
  default; AudD / AcoustID adapters included)
- ✍️ **Manual tagging** fallback when detection misses
- 🗂️ **Auto-organization** into concerts + playlists by artist/date
- 🎬 **Theater mode** — pick a playlist and it just plays: shuffle on by
  default, video-only fullscreen stage, controls (pause/next/back/shuffle/…)
  fade in on mouse move and melt away when you go still
- 🔥 **Excitement detection** — every clip is scanned for its most hype
  moments (flashing stage lights via luma deltas + crowd loudness via RMS)
- ⚡ **Hype cut** — one tap renders a montage of those moments while the
  music keeps playing (visuals jump, audio never stops)
- ▶️ **Single-clip playback** with an audio-reactive visualizer
- 🌱 **Demo mode** — seeded sample concerts (with real generated clips) so a
  fresh install feels alive
- ✅ **Tested** — pytest covers the pipeline, excitement analysis, montage
  rendering, and the queue API end-to-end

## Tech stack

| Layer          | Choice                                             |
| -------------- | -------------------------------------------------- |
| Web framework  | **FastAPI** (+ Uvicorn)                            |
| UI             | Server-rendered **Jinja2** templates, vanilla JS   |
| Database       | **SQLAlchemy 2.0** ORM · SQLite (→ Postgres later) |
| Storage        | Local filesystem (→ Cloudflare R2 / S3 adapter)    |
| Audio          | **ffmpeg / ffprobe**                               |
| Fingerprinting | Pluggable: `mock` (default) · AudD · AcoustID      |
| Config         | pydantic-settings                                  |
| Tests / lint   | pytest · ruff                                      |

## Quick start

Prereqs: **Python ≥ 3.11** and **ffmpeg** on your PATH.

```bash
python -m venv .venv
# Windows:  .venv\Scripts\activate      macOS/Linux:  source .venv/bin/activate
pip install -r requirements-dev.txt

python scripts/seed_demo.py            # optional: demo concerts
python run.py                          # → http://127.0.0.1:8000
```

Open <http://127.0.0.1:8000>, hit **＋ Upload**, pick a video, watch it get
identified and filed under a concert. Full guide: [docs/SETUP.md](docs/SETUP.md).

```bash
pytest        # run the tests
ruff check .  # lint
```

## Project layout

```
nhac/
├── nhac/
│   ├── main.py            # FastAPI app factory
│   ├── config.py          # pydantic-settings
│   ├── db.py  models.py   # SQLAlchemy engine + ORM (incl. clip_highlights)
│   ├── schemas.py         # Pydantic API contracts (incl. play queue)
│   ├── storage/           # local + s3/r2 backends
│   ├── audio/ffmpeg.py    # extract / probe / quality
│   ├── analysis/          # excitement detection (flash + loudness)
│   ├── fingerprint/       # base · mock · audd · acoustid
│   ├── pipeline/          # process_clip · organize · montage (hype cut)
│   ├── services/          # clips · songs · concerts · playlists · playback · users
│   ├── routers/           # api.py (JSON) · web.py (HTML + /play theater)
│   ├── templates/  static/# Jinja2 UI + CSS/JS (incl. theater player)
│   └── uploads.py         # upload orchestration
├── scripts/               # seed_demo.py · build_highlights.py (backfill)
├── tests/                 # pytest
└── docs/                  # architecture, roadmap, workflows, decisions, setup, legal, notes
```

## Where to look next

| I want to…                       | Read                                         |
| -------------------------------- | -------------------------------------------- |
| Understand the system            | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| See the build plan / open todos  | [docs/ROADMAP.md](docs/ROADMAP.md)           |
| Trace a pipeline end-to-end      | [docs/WORKFLOWS.md](docs/WORKFLOWS.md)       |
| Know why we picked X over Y      | [docs/DECISIONS.md](docs/DECISIONS.md)       |
| Set up / configure providers     | [docs/SETUP.md](docs/SETUP.md)               |
| Decisions I left for you         | [docs/NOTES.md](docs/NOTES.md)               |
| Copyright stance                 | [docs/LEGAL.md](docs/LEGAL.md)               |

## Status

🟢 **Working MVP** (local, single-user). Phase-2 features (collaboration,
cleanest-audio selection, multi-angle edits, social export) are designed but not
built — see the roadmap. Not yet production-hardened.

## License

UNLICENSED / private while in early development.
