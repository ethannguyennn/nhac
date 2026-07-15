"""Shared FastAPI dependencies."""

from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from nhac.db import get_session
from nhac.models import User
from nhac.services.users import get_or_create_default_user

__all__ = ["get_session", "get_current_user"]


def get_current_user(session: Session = Depends(get_session)) -> User:
    """MVP: always the seeded single local user.

    FastAPI caches ``get_session`` per request, so this shares the route's
    session. Swap for real session/JWT auth post-MVP without touching routers
    (see docs/NOTES.md).
    """
    return get_or_create_default_user(session)
