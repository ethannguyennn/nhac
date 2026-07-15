"""Jinja2 templates instance + shared template helpers."""

from __future__ import annotations

from pathlib import Path

from fastapi.templating import Jinja2Templates

from nhac.storage import get_storage

TEMPLATES_DIR = Path(__file__).parent / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _media_url(key: str | None) -> str | None:
    return get_storage().url_for(key) if key else None


# Helpers available in every template.
templates.env.globals["media_url"] = _media_url
templates.env.globals["app_name"] = "Nhạc"
