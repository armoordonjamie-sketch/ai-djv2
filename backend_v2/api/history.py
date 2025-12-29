"""History API router."""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend_v2.db.session import get_async_session
from backend_v2.models.user import User
from backend_v2.models.existing import PlayHistory, Song
from backend_v2.auth.dependencies import get_current_user_http

logger = logging.getLogger("ai-dj.history")

router = APIRouter()


class HistoryItem(BaseModel):
    """A single play history item."""
    id: int
    song_uuid: str
    title: Optional[str] = None
    artist: Optional[str] = None
    artwork_url: Optional[str] = None
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    skipped: bool = False
    mood_id: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)


@router.get("", response_model=List[HistoryItem])
async def get_history(
    limit: int = Query(50, ge=1, le=200),
    mood_id: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user_http),
    db: AsyncSession = Depends(get_async_session),
):
    """Get listening history for the current user.
    
    Returns most recently played tracks first.
    """
    query = select(PlayHistory).where(
        PlayHistory.user_id == current_user.id
    )
    
    if mood_id:
        query = query.where(PlayHistory.mood_id == mood_id)
    
    query = query.order_by(PlayHistory.started_at.desc()).limit(limit)
    
    result = await db.execute(query)
    history_items = result.scalars().all()
    
    # Enrich with song metadata
    response = []
    for item in history_items:
        # Try to get song metadata
        song_data = None
        if item.song_uuid:
            song_result = await db.execute(
                select(Song).where(Song.uuid == item.song_uuid)
            )
            song_data = song_result.scalar_one_or_none()
        
        response.append(HistoryItem(
            id=item.id,
            song_uuid=item.song_uuid or "",
            title=song_data.title if song_data else item.song_uuid,
            artist=song_data.artist if song_data else None,
            artwork_url=song_data.artwork_url if song_data else None,
            started_at=item.started_at,
            ended_at=item.ended_at,
            skipped=bool(item.skipped),
            mood_id=item.mood_id,
        ))
    
    return response
