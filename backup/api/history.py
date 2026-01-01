import json
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend_v2.db.session import get_async_session
from backend_v2.auth.dependencies import get_current_user_http
from backend_v2.models.user import User
from backend_v2.models.status_event_log import StatusEventLog
from backend_v2.schemas.status_events import StatusCategory

router = APIRouter()

@router.get("/training")
async def get_training_history(
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user_http),
):
    """Get recent training history logs (insights, likes, dislikes)."""
    result = await db.execute(
        select(StatusEventLog)
        .where(
            StatusEventLog.user_id == current_user.id,
            StatusEventLog.category == StatusCategory.TRAINING.value
        )
        .order_by(StatusEventLog.created_at.desc())
        .limit(limit)
    )
    logs = result.scalars().all()
    
    # Format response
    history = []
    for log in logs:
        payload = {}
        if log.payload_json:
            try:
                payload = json.loads(log.payload_json)
            except:
                pass
        
        history.append({
            "id": log.id,
            "timestamp": log.created_at,
            "message": log.user_message,
            "payload": payload
        })
        
    return history


@router.get("/plays")
async def get_play_history(
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user_http),
):
    """Get user's listening history (songs played)."""
    from backend_v2.models.existing import PlayHistory, Song
    from sqlalchemy.orm import selectinload
    
    result = await db.execute(
        select(PlayHistory, Song)
        .outerjoin(Song, PlayHistory.song_uuid == Song.uuid)
        .where(PlayHistory.user_id == current_user.id)
        .order_by(PlayHistory.started_at.desc())
        .limit(limit)
    )
    rows = result.all()
    
    plays = []
    for play, song in rows:
        plays.append({
            "id": play.id,
            "song_uuid": play.song_uuid,
            "track_title": song.title if song else "Unknown Track",
            "track_artist": song.artist if song else "Unknown Artist",
            "started_at": play.started_at,
            "ended_at": play.ended_at,
            "skipped": bool(play.skipped),
            "mood_id": play.mood_id,
        })
    
    return plays
