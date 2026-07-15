# Setup

## Prerequisites

| Tool         | Notes                                              |
| ------------ | -------------------------------------------------- |
| Python ≥ 3.11| `python --version`                                 |
| ffmpeg + ffprobe | on PATH (`ffmpeg -version`), or set `NHAC_FFMPEG_PATH` / `NHAC_FFPROBE_PATH` |

That's it for the local MVP — no database server, no cloud account, no API key.

## Install & run

```bash
python -m venv .venv
# Windows:  .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate
pip install -r requirements-dev.txt   # or: pip install -r requirements.txt (no test/lint tools)

python scripts/seed_demo.py           # optional: seed demo concerts (generates real clips)
python run.py                         # http://127.0.0.1:8000  (auto-reload)
```

Prefer uvicorn directly:

```bash
uvicorn nhac.main:app --reload --port 8000
```

Data lives under `./var` (SQLite DB + uploaded/derived media) and is gitignored.
Delete `./var` to reset everything.

## Configuration

Copy the template and edit as needed (the app runs fine with none of it):

```bash
cp .env.example .env
```

All settings are `NHAC_`-prefixed (see `nhac/config.py`). Highlights:

| Setting                      | Default          | Purpose                              |
| ---------------------------- | ---------------- | ------------------------------------ |
| `NHAC_DATABASE_URL`          | SQLite in ./var  | Swap for Postgres later              |
| `NHAC_STORAGE_BACKEND`       | `local`          | `local` or `s3`                      |
| `NHAC_FINGERPRINT_PROVIDER`  | `mock`           | `mock`, `audd`, or `acoustid`        |
| `NHAC_DEFAULT_USER_EMAIL`    | you@example.com  | The seeded single MVP user           |

### Use a real fingerprinter

**AudD:**

```bash
# .env
NHAC_FINGERPRINT_PROVIDER=audd
NHAC_AUDD_API_TOKEN=your-token
```

**AcoustID** (needs the `fpcalc`/Chromaprint binary on PATH):

```bash
pip install -e ".[acoustid]"
# .env
NHAC_FINGERPRINT_PROVIDER=acoustid
NHAC_ACOUSTID_API_KEY=your-key
```

### Use Cloudflare R2 / S3 storage

```bash
pip install -e ".[s3]"
# .env
NHAC_STORAGE_BACKEND=s3
NHAC_S3_BUCKET=nhac-media
NHAC_S3_ENDPOINT_URL=https://<account>.r2.cloudflarestorage.com
NHAC_S3_ACCESS_KEY_ID=...
NHAC_S3_SECRET_ACCESS_KEY=...
NHAC_S3_PUBLIC_BASE_URL=https://media.yourdomain.com   # or leave blank for presigned URLs
```

## Testing your phone

Run the server, find your machine's LAN IP, and open
`http://<LAN-IP>:8000` on your phone (same Wi-Fi). Uploading from the phone's
camera roll is the intended flow. Bind all interfaces if needed:
`uvicorn nhac.main:app --host 0.0.0.0 --port 8000`.

## Dev commands

```bash
pytest                 # tests
ruff check .           # lint
ruff check . --fix     # autofix
```

## Troubleshooting

- **`ffmpeg not found`** → install it / set `NHAC_FFMPEG_PATH` and `NHAC_FFPROBE_PATH`.
- **App won't start with a config error** → `config.py` validation lists the bad var.
- **Everything got identified as random songs** → that's the `mock` provider
  (deterministic fake matches). Set a real provider to identify actual songs.
- **Reset all data** → stop the server, delete `./var`.
