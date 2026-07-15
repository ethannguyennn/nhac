# Nhạc 🎵

> _Relive the moment._

Nhạc (Vietnamese for "music") turns the scattered concert videos on your phone
into a clean, replayable "greatest hits" experience. Upload your clips — Nhạc
extracts the audio, **identifies the song** via audio fingerprinting
(Shazam-style, not AI), and **auto-organizes** everything into playlists by
concert and song. Later: relive shows collaboratively with friends who were
there too.

This repo is an early-stage MVP scaffold. It's structured like a real product
but built to stay **cheap and simple** — free tiers first, ~90% detection
accuracy with a manual-tag fallback, ship-fun-first.

---

## Monorepo layout

```
nhac/
├── apps/
│   ├── mobile/        # Expo / React Native — the primary experience
│   └── web/           # Vite + React — upload/playback companion
├── services/
│   └── api/           # Node + Express — upload orchestration, ffmpeg, fingerprinting
├── packages/
│   └── shared/        # Shared TS domain types, enums, constants, DTOs
├── infra/
│   └── supabase/      # Postgres schema, RLS, seed (metadata DB + auth)
└── docs/              # Architecture, workflows, roadmap, decisions, setup, legal
```

**Storage split:** Supabase (Postgres) holds metadata; **Cloudflare R2** holds
video files. Video never sits in Supabase (1 GB free cap). See
[docs/DECISIONS.md](docs/DECISIONS.md).

## The core flow

```
record  →  upload  →  extract audio (ffmpeg)  →  fingerprint (AudD/ACRCloud/AcoustID)
        →  identify song (or manual tag)  →  auto-group into concert + playlist  →  play
```

Full diagrams in [docs/WORKFLOWS.md](docs/WORKFLOWS.md).

## Quick start

Prereqs: Node ≥ 20, npm, `ffmpeg` on PATH, a Supabase project, a Cloudflare R2
bucket, and a fingerprint API key. Full walkthrough in
[docs/SETUP.md](docs/SETUP.md).

```bash
npm install                       # install all workspaces
cp .env.example .env              # + per-app .env files (see SETUP)
npm run shared:build              # build shared types once

npm run api:dev                   # API on :4000
npm run web:dev                   # web on :5173
npm run mobile:start              # Expo dev server
```

## Where to look next

| I want to…                        | Read                                         |
| --------------------------------- | -------------------------------------------- |
| Understand the system            | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| See the build plan / open todos  | [docs/ROADMAP.md](docs/ROADMAP.md)           |
| Trace a pipeline end-to-end      | [docs/WORKFLOWS.md](docs/WORKFLOWS.md)       |
| Know why we picked X over Y      | [docs/DECISIONS.md](docs/DECISIONS.md)       |
| Set up my own environment        | [docs/SETUP.md](docs/SETUP.md)               |
| Understand the copyright stance  | [docs/LEGAL.md](docs/LEGAL.md)               |

## Status

🚧 **Scaffold.** Structure, types, schema, and the pipeline skeleton are in
place; handlers marked `TODO` are the next implementation steps (tracked in
[docs/ROADMAP.md](docs/ROADMAP.md)). Not production-ready.

## License

UNLICENSED / private while in early development.
