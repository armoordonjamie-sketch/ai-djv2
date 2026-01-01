"""Session API router for session persistence and resume functionality.

Provides endpoints for:
- GET /resumable - Check if user has a resumable session
- POST /heartbeat - Update playback position for session persistence
"""
import logging
import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from backend_v2.db.session import get_async_session
from backend_v2.models.user import User
from backend_v2.models.existing import Session
from backend_v2.models.mood import Mood
from backend_v2.auth.dependencies import get_current_user_http
from backend_v2.utils.time import utc_isoformat, utc_now

logger = logging.getLogger("ai-dj.session")

router = APIRouter()


class TrackInfo(BaseModel):
    """Track information for resume session."""
    title: str
    artist: str
    artwork_url: Optional[str] = None


class ResumableSessionResponse(BaseModel):
    """Response for resumable session check."""
    resumable: bool
    session_id: Optional[str] = None
    position_sec: Optional[float] = None
    mood_name: Optional[str] = None
    track_info: Optional[TrackInfo] = None


class HeartbeatRequest(BaseModel):
    """Request body for heartbeat updates."""
    position_sec: float


class HeartbeatResponse(BaseModel):
    """Response for heartbeat updates."""
    success: bool


@router.get("/resumable", response_model=ResumableSessionResponse)
async def check_resumable_session(
    current_user: User = Depends(get_current_user_http),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Check if the user has an active session that can be resumed.
    
    Returns session details if resumable, otherwise indicates no resumable session.
    """
    # Find the most recent active session for this user
    result = await db.execute(
        select(Session)
        .where(
            Session.user_id == current_user.id,
            Session.is_active == 1,
        )
        .order_by(Session.started_at.desc())
        .limit(1)
    )
    session = result.scalar_one_or_none()
    
    if not session:
        return ResumableSessionResponse(resumable=False)
    
    # Get mood name if available
    mood_name = None
    if session.mood_id:
        mood_result = await db.execute(
            select(Mood).where(Mood.id == session.mood_id)
        )
        mood = mood_result.scalar_one_or_none()
        if mood:
            mood_name = mood.name
    
    # Build track info if available
    track_info = None
    if session.current_song_title and session.current_song_artist:
        track_info = TrackInfo(
            title=session.current_song_title,
            artist=session.current_song_artist,
            artwork_url=session.current_song_artwork,
        )
    
    logger.info(
        f"Resumable session found for user {current_user.id}: "
        f"session={session.session_id}, position={session.playback_position_sec}s"
    )
    
    return ResumableSessionResponse(
        resumable=True,
        session_id=session.session_id,
        position_sec=session.playback_position_sec,
        mood_name=mood_name,
        track_info=track_info,
    )


@router.post("/heartbeat", response_model=HeartbeatResponse)
async def update_session_heartbeat(
    data: HeartbeatRequest,
    current_user: User = Depends(get_current_user_http),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Update the playback position and heartbeat timestamp for the user's active session.
    
    Called periodically by the frontend to enable session resumption.
    """
    # Find the user's active session
    result = await db.execute(
        select(Session)
        .where(
            Session.user_id == current_user.id,
            Session.is_active == 1,
        )
        .order_by(Session.started_at.desc())
        .limit(1)
    )
    session = result.scalar_one_or_none()
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active session found",
        )
    
    # Update position and heartbeat
    session.playback_position_sec = data.position_sec
    session.last_heartbeat_at = utc_isoformat(utc_now())
    
    # Capture ID before commit expires the current_user object
    user_id = current_user.id

    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        try:
            await db.commit()
            logger.debug(f"Heartbeat: user={user_id}, position={data.position_sec}s")
            return HeartbeatResponse(success=True)
        except OperationalError as e:
            error_str = str(e).lower()
            if "database is locked" not in error_str:
                await db.rollback()
                raise
            await db.rollback()
            if attempt < max_attempts:
                await asyncio.sleep(0.2 * (2 ** (attempt - 1)))
                continue
            logger.warning(f"Heartbeat commit failed due to database lock after {max_attempts} attempts")
            return HeartbeatResponse(success=False)

