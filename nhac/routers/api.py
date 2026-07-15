"""JSON API under /api. Mirrors the web flow for programmatic clients / tests."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from nhac.deps import get_current_user, get_session
from nhac.models import User
from nhac.schemas import (
    ClipDetailOut,
    ClipOut,
    ConcertOut,
    ConcertWithClipsOut,
    TagClipIn,
    UploadResultOut,
)
from nhac.services import clips as clip_service
from nhac.services import concerts as concert_service
from nhac.storage import get_storage
from nhac.uploads import UploadError, ingest_upload

router = APIRouter(prefix="/api", tags=["api"])


@router.get("/health")
def health() -> dict:
    return {"ok": True, "service": "nhac"}


@router.post("/clips", response_model=UploadResultOut, status_code=201)
async def upload_clip(
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> UploadResultOut:
    data = await file.read()
    try:
        clip, result = await ingest_upload(
            session,
            uploader_id=user.id,
            filename=file.filename or "clip.mp4",
            content_type=file.content_type,
            data=data,
        )
    except UploadError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return UploadResultOut(
        clip=ClipOut.model_validate(clip),
        identified=result.identified,
        message=result.message,
    )


@router.get("/clips/{clip_id}", response_model=ClipDetailOut)
def get_clip(
    clip_id: str,
    session: Session = Depends(get_session),
) -> ClipDetailOut:
    clip = clip_service.get_clip(session, clip_id)
    if clip is None:
        raise HTTPException(status_code=404, detail="clip not found")
    out = ClipDetailOut.model_validate(clip)
    if clip.raw_video_key:
        out.media_url = get_storage().url_for(clip.raw_video_key)
    return out


@router.post("/clips/{clip_id}/tag", response_model=ClipOut)
def tag_clip(
    clip_id: str,
    body: TagClipIn,
    session: Session = Depends(get_session),
) -> ClipOut:
    clip = clip_service.get_clip(session, clip_id)
    if clip is None:
        raise HTTPException(status_code=404, detail="clip not found")
    clip = clip_service.apply_manual_tag(
        session, clip, artist=body.artist, title=body.title, album=body.album
    )
    return ClipOut.model_validate(clip)


@router.get("/concerts", response_model=list[ConcertOut])
def list_concerts(
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[ConcertOut]:
    concerts = concert_service.list_concerts(session, user.id)
    return [ConcertOut.model_validate(c) for c in concerts]


@router.get("/concerts/{concert_id}", response_model=ConcertWithClipsOut)
def get_concert(
    concert_id: str,
    session: Session = Depends(get_session),
) -> ConcertWithClipsOut:
    concert = concert_service.get_concert(session, concert_id)
    if concert is None:
        raise HTTPException(status_code=404, detail="concert not found")
    return ConcertWithClipsOut.model_validate(concert)
