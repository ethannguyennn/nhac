"""FastAPI application factory."""

from __future__ import annotations

import mimetypes
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from nhac import __version__
from nhac.config import StorageBackend, settings
from nhac.db import init_db
from nhac.logging_config import configure_logging, get_logger
from nhac.routers.api import router as api_router
from nhac.routers.web import router as web_router

log = get_logger(__name__)

STATIC_DIR = Path(__file__).parent / "static"

# Some OS mimetypes databases (notably Windows) don't know modern font/web
# types, so StaticFiles falls back to application/octet-stream for them.
mimetypes.add_type("font/woff2", ".woff2")
mimetypes.add_type("font/woff", ".woff")


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    init_db()
    # Seed the single MVP user so the first request has an owner.
    from nhac.db import SessionLocal
    from nhac.services.users import get_or_create_default_user

    with SessionLocal() as session:
        get_or_create_default_user(session)
    log.info("Nhạc %s ready (env=%s, storage=%s, fingerprint=%s)",
             __version__, settings.env, settings.storage_backend.value,
             settings.fingerprint_provider.value)
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Nhạc", version=__version__, lifespan=lifespan)

    app.include_router(api_router)
    app.include_router(web_router)

    # Static assets.
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # Serve local media directly (StaticFiles supports HTTP Range for <video>).
    if settings.storage_backend is StorageBackend.LOCAL:
        media_dir = Path(settings.local_storage_dir)
        media_dir.mkdir(parents=True, exist_ok=True)
        app.mount("/media", StaticFiles(directory=str(media_dir)), name="media")

    return app


app = create_app()
