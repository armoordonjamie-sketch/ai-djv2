"""Feedback API router."""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend_v2.db.session import get_async_session
from backend_v2.models.user import User
from backend_v2.models.feedback import FeedbackEvent
from backend_v2.models.mood import Mood
from backend_v2.models.existing import Song
from backend_v2.services.preference_bundle import get_bundle_cache
from backend_v2.schemas.feedback import FeedbackCreate, FeedbackResponse
from backend_v2.auth.dependencies import get_current_user_http

logger = logging.getLogger("ai-dj.feedback")

router = APIRouter()


@router.post("", response_model=FeedbackResponse, status_code=status.HTTP_201_CREATED)
async def submit_feedback(
    data: FeedbackCreate,
    current_user: User = Depends(get_current_user_http),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Submit feedback on a song.
    
    This will:
    1. Store the feedback event
    2. Update the mood profile weights (if mood_id provided and song has features)
    """
    # Validate mood_id if provided
    if data.mood_id:
        result = await db.execute(
            select(Mood).where(
                Mood.id == data.mood_id,
                Mood.user_id == current_user.id,
            )
        )
        mood = result.scalar_one_or_none()
        if not mood:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Mood not found",
            )
    
    # Validate song_uuid if provided
    song_uuid = data.song_uuid
    if song_uuid:
        # Verify song exists to prevent FK violation
        result = await db.execute(select(Song).where(Song.uuid == song_uuid))
        if not result.scalar_one_or_none():
            logger.warning(f"Song {song_uuid} not found for feedback, unlinking")
            song_uuid = None

    # Create feedback event
    feedback = FeedbackEvent(
        user_id=current_user.id,
        mood_id=data.mood_id,
        song_uuid=song_uuid,
        track_title=data.track_title,
        track_artist=data.track_artist,
        value=data.value,
        reason_text=data.reason_text,
    )
    db.add(feedback)
    await db.commit()
    await db.refresh(feedback)
    
    logger.info(f"Feedback submitted: user={current_user.id}, value={data.value}")

    # Emit feedback received status
    from backend_v2.orchestration.events import get_event_emitter
    from backend_v2.schemas.status_events import StatusCategory, StatusStep
    
    emitter = get_event_emitter()
    await emitter.emit_status(
        user_id=current_user.id,
        category=StatusCategory.TRAINING,
        step=StatusStep.FEEDBACK_RECEIVED,
        user_message="Thanks for the feedback!",
        payload={
            "feedback_value": data.value,
            "track_title": data.track_title,
            "track_artist": data.track_artist,
        },
    )

    # Invalidate cached preference bundle so feedback takes effect immediately
    get_bundle_cache().invalidate(current_user.id)
    
    # Trigger training and summary update
    # We do this in the request loop for simplicity, but could be background task
    if data.mood_id:
        from backend_v2.services.training import update_mood_profile_weights, regenerate_summary_text
        
        try:
            await update_mood_profile_weights(db, data.mood_id, feedback)
            if data.value == "like" or data.value == "dislike":
                await regenerate_summary_text(db, data.mood_id)
            
            # Emit training complete status
            await emitter.emit_status(
                user_id=current_user.id,
                category=StatusCategory.TRAINING,
                step=StatusStep.TRAINING_COMPLETE,
                user_message="Updated your DJ's preferences",
            )
        except Exception as e:
            logger.error(f"Training failed: {e}")
    
    return feedback


@router.get("", response_model=List[FeedbackResponse])
async def list_feedback(
    mood_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user_http),
    db: AsyncSession = Depends(get_async_session),
):
    """List feedback events for the current user."""
    query = select(FeedbackEvent).where(
        FeedbackEvent.user_id == current_user.id
    )
    
    if mood_id:
        query = query.where(FeedbackEvent.mood_id == mood_id)
    
    query = query.order_by(FeedbackEvent.created_at.desc()).limit(limit)
    
    result = await db.execute(query)
    return result.scalars().all()


@router.delete("/all", status_code=status.HTTP_204_NO_CONTENT)
async def delete_all_feedback(
    current_user: User = Depends(get_current_user_http),
    db: AsyncSession = Depends(get_async_session),
):
    """Delete all feedback for the current user (reset training)."""
    from sqlalchemy import delete
    from backend_v2.models.mood import Mood, MoodProfile
    
    # Delete all feedback events
    await db.execute(
        delete(FeedbackEvent).where(FeedbackEvent.user_id == current_user.id)
    )
    
    # Reset mood profile weights
    result = await db.execute(
        select(Mood).where(Mood.user_id == current_user.id)
    )
    for mood in result.scalars():
        profile_result = await db.execute(
            select(MoodProfile).where(MoodProfile.mood_id == mood.id)
        )
        profile = profile_result.scalar_one_or_none()
        if profile:
            profile.weights_json = None
            profile.summary_text = None
            profile.version = 1
    
    await db.commit()
    get_bundle_cache().invalidate(current_user.id)
    logger.info(f"Training reset for user {current_user.id}")
