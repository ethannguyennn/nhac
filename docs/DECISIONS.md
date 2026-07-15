# Decisions (lightweight ADRs)

Choices made and why, with things to re-verify. ⚠️ **Provider pricing/limits
change often — confirm current terms before you commit or launch.**

---

## ADR-001 — Python, FastAPI, server-rendered UI

**Decision:** Python everywhere. **FastAPI** for the API + a **server-rendered
Jinja2** web UI (vanilla JS, no build step), mobile-first responsive.

**Why:** You prefer Python above all. A native mobile app can't be Python;
a responsive web app you open in your phone browser is the pragmatic MVP surface
and keeps the whole stack in one language with no npm/build toolchain. FastAPI
gives typed request/response models and an easy JSON API for a future native
client. **Revisit:** a real native app is a Phase-2 option (see NOTES.md).

---

## ADR-002 — SQLite now, Postgres-ready

**Decision:** SQLAlchemy 2.0 ORM on SQLite for the MVP; switch to Postgres by
changing `NHAC_DATABASE_URL`.

**Why:** zero-setup, no account, runs on your laptop. The ORM keeps the code
DB-agnostic. Dev creates tables with `create_all`; add Alembic before you rely
on migrations in production.

---

## ADR-003 — Local storage now, R2/S3-ready

**Decision:** `Storage` protocol with a local-filesystem default and a
`boto3`-based S3/R2 adapter behind the `s3` extra.

**Why:** video on the Supabase free tier is a non-starter (~1 GB). Local disk
needs no account for the MVP; Cloudflare **R2** (no egress fees, S3-compatible)
is the intended cloud target — flip `NHAC_STORAGE_BACKEND=s3` and fill the
`NHAC_S3_*` vars. **Verify:** R2 free-tier storage + operation limits.

---

## ADR-004 — Fingerprinting, not AI; mock default

**Decision:** Pluggable `Fingerprinter`. Default **`mock`** (offline,
deterministic). Real adapters: **AudD** (simple REST, artwork) and **AcoustID**
(free/open, MusicBrainz, needs `fpcalc`).

**Why:** fingerprinting is the right, cheap, deterministic tool for the
"~90% is fine" bar; LLM audio models are out of scope. The mock lets the entire
app work end-to-end **with no API key or signup**, so the MVP is demoable today.
Switching is one env var + a key.

| Provider     | Model                | Notes                                             |
| ------------ | -------------------- | ------------------------------------------------- |
| **mock**     | free, offline        | Deterministic demo matches; default. Not real ID. |
| **AudD**     | paid, small trial    | Easiest real option; returns artwork/metadata.    |
| **AcoustID** | free / donation      | Open; sparser metadata; needs `fpcalc` binary.    |

**Cost control (when real):** send a ~15s sample, cache repeat matches,
rate-limit.

---

## ADR-005 — Single-user auth for the MVP

**Decision:** one seeded local user, injected via `get_current_user`.

**Why:** avoids building/gambling on an auth system before the core loop is
proven. It's isolated behind one dependency, so real auth (session or JWT) drops
in without touching routers. **Your call** whether/when to go multi-user
(NOTES.md).

---

## ADR-006 — No Spotify integration

**Decision:** standalone player; no Spotify upload/library sync. Spotify's API
can't ingest user audio/video and it adds copyright exposure for zero MVP
benefit. Public metadata/artwork lookups only, if ever.

---

## ADR-007 — Inline processing now, queue later

**Decision:** the pipeline runs inline (in a threadpool) on upload. Simple and
fine at low volume; migrate to a queue + worker when uploads back up
(see ARCHITECTURE "Concurrency").

---

## Open questions

Collected for you in **[NOTES.md](NOTES.md)** — provider choice, storage/DB
target, auth model, native app — all things I deliberately did **not** sign you
up for or spend money on.
