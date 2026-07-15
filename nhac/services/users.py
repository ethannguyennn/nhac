"""User service. The MVP is single-user: one seeded local account.

Real multi-user auth is a post-MVP decision (see docs/NOTES.md).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from nhac.config import settings
from nhac.models import User


def get_or_create_default_user(session: Session) -> User:
    email = settings.default_user_email
    user = session.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(email=email, display_name=email.split("@")[0])
        session.add(user)
        session.commit()
        session.refresh(user)
    return user
