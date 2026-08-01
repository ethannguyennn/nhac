"""Server-rendered web pages (Jinja2 + vanilla JS)."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from nhac.deps import get_current_user, get_session
from nhac.enums import ClipStatus
from nhac.models import User
from nhac.services import clips as clip_service
from nhac.services import concerts as concert_service
from nhac.services import playback as playback_service
from nhac.services.playlists import ensure_concert_playlist
from nhac.templating import templates
from nhac.uploads import UploadError, ingest_upload

router = APIRouter(include_in_schema=False)


@router.get("/", response_class=HTMLResponse)
def index(
    request: Request,
    msg: str | None = None,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> HTMLResponse:
    concerts = concert_service.list_concerts(session, user.id)
    unidentified = concert_service.list_unidentified_clips(session, user.id)
    return templates.TemplateResponse(
        request,
        "index.html",
        {"concerts": concerts, "unidentified": unidentified, "msg": msg},
    )


@router.get("/upload", response_class=HTMLResponse)
def upload_form(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "upload.html", {})


@router.post("/upload")
async def upload_submit(
    request: Request,
    file: UploadFile,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
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
        return templates.TemplateResponse(
            request, "upload.html", {"error": str(exc)}, status_code=422
        )

    if result.status is ClipStatus.IDENTIFIED and clip.concert_id:
        return RedirectResponse(
            f"/concerts/{clip.concert_id}?msg=Added+{_q(clip.display_title)}", status_code=303
        )
    if result.status is ClipStatus.UNIDENTIFIED:
        return RedirectResponse(f"/clips/{clip.id}/tag", status_code=303)
    if result.status is ClipStatus.FAILED:
        return RedirectResponse(f"/?msg=Processing+failed:+{_q(result.message)}", status_code=303)
    return RedirectResponse(f"/clips/{clip.id}", status_code=303)


@router.get("/concerts/{concert_id}", response_class=HTMLResponse)
def concert_detail(
    concert_id: str,
    request: Request,
    msg: str | None = None,
    session: Session = Depends(get_session),
) -> HTMLResponse:
    concert = concert_service.get_concert(session, concert_id)
    if concert is None:
        return RedirectResponse("/?msg=Concert+not+found", status_code=303)
    clips = sorted(concert.clips, key=lambda c: c.created_at)
    playlist = ensure_concert_playlist(session, concert)
    session.commit()  # ensure_concert_playlist may have created it
    return templates.TemplateResponse(
        request,
        "concert.html",
        {"concert": concert, "clips": clips, "playlist_id": playlist.id, "msg": msg},
    )


@router.get("/concerts/{concert_id}/play")
def concert_play(
    concert_id: str,
    session: Session = Depends(get_session),
) -> RedirectResponse:
    """Jump straight into theater mode for a concert's auto-playlist."""
    concert = concert_service.get_concert(session, concert_id)
    if concert is None:
        return RedirectResponse("/?msg=Concert+not+found", status_code=303)
    playlist = ensure_concert_playlist(session, concert)
    session.commit()
    return RedirectResponse(f"/play/{playlist.id}", status_code=303)


@router.get("/play/{playlist_id}", response_class=HTMLResponse)
def theater(
    playlist_id: str,
    request: Request,
    track: str | None = None,
    session: Session = Depends(get_session),
) -> HTMLResponse:
    """Immersive playlist player: video only, controls on mouse move."""
    playlist = playback_service.get_playlist(session, playlist_id)
    if playlist is None:
        return RedirectResponse("/?msg=Playlist+not+found", status_code=303)
    queue = playback_service.build_queue(playlist)
    if not queue.items:
        return RedirectResponse(
            f"/concerts/{playlist.concert_id}?msg=Nothing+playable+yet"
            if playlist.concert_id
            else "/?msg=Nothing+playable+yet",
            status_code=303,
        )
    # </ escaped so titles can never break out of the inline <script> block.
    queue_json = json.dumps(queue.model_dump()).replace("</", "<\\/")
    return templates.TemplateResponse(
        request,
        "play.html",
        {
            "playlist": playlist,
            "queue_json": queue_json,
            "start_track": track,
            "back_url": (
                f"/concerts/{playlist.concert_id}" if playlist.concert_id else "/"
            ),
        },
    )


@router.get("/clips/{clip_id}", response_class=HTMLResponse)
def clip_player(
    clip_id: str,
    request: Request,
    session: Session = Depends(get_session),
) -> HTMLResponse:
    clip = clip_service.get_clip(session, clip_id)
    if clip is None:
        return RedirectResponse("/?msg=Clip+not+found", status_code=303)
    theater_url = None
    if clip.concert is not None:
        playlist = ensure_concert_playlist(session, clip.concert)
        session.commit()
        theater_url = f"/play/{playlist.id}?track={clip.id}"
    return templates.TemplateResponse(
        request, "player.html", {"clip": clip, "theater_url": theater_url}
    )


@router.get("/clips/{clip_id}/tag", response_class=HTMLResponse)
def tag_form(
    clip_id: str,
    request: Request,
    session: Session = Depends(get_session),
) -> HTMLResponse:
    clip = clip_service.get_clip(session, clip_id)
    if clip is None:
        return RedirectResponse("/?msg=Clip+not+found", status_code=303)
    return templates.TemplateResponse(request, "tag.html", {"clip": clip})


@router.post("/clips/{clip_id}/tag")
def tag_submit(
    clip_id: str,
    artist: str = Form(...),
    title: str = Form(...),
    album: str | None = Form(None),
    session: Session = Depends(get_session),
):
    clip = clip_service.get_clip(session, clip_id)
    if clip is None:
        return RedirectResponse("/?msg=Clip+not+found", status_code=303)
    clip = clip_service.apply_manual_tag(session, clip, artist=artist, title=title, album=album)
    target = f"/concerts/{clip.concert_id}" if clip.concert_id else "/"
    return RedirectResponse(f"{target}?msg=Tagged+{_q(title)}", status_code=303)


def _q(text: str) -> str:
    from urllib.parse import quote_plus

    return quote_plus(text or "")
