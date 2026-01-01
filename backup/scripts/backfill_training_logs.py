"""Backfill training logs from historical feedback events.

This script generates StatusEventLog entries for existing FeedbackEvent records
that were created before the training logging system was implemented.

Usage:
    python -m backend_v2.scripts.backfill_training_logs
"""
import asyncio
import json
import logging
from sqlalchemy import select, func

from backend_v2.db.session import get_db_session
from backend_v2.models.feedback import FeedbackEvent
from backend_v2.models.status_event_log import StatusEventLog
from backend_v2.models.mood import Mood
from backend_v2.schemas.status_events import StatusCategory, StatusStep

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("backfill")


async def backfill_training_logs():
    """Generate StatusEventLog entries from historical FeedbackEvent records."""
    async with get_db_session() as db:
        # Get all feedback events
        result = await db.execute(
            select(FeedbackEvent).order_by(FeedbackEvent.created_at)
        )
        feedback_events = result.scalars().all()
        
        if not feedback_events:
            logger.info("No feedback events found to backfill.")
            return
        
        logger.info(f"Found {len(feedback_events)} feedback events to process.")
        
        backfilled = 0
        skipped = 0
        
        for event in feedback_events:
            track_name = f"{event.track_artist or 'Unknown'} - {event.track_title or 'Unknown'}"
            
            # Check if a log already exists for this user+track combo
            existing = await db.execute(
                select(StatusEventLog).where(
                    StatusEventLog.user_id == event.user_id,
                    StatusEventLog.category == StatusCategory.TRAINING,
                    StatusEventLog.payload_json.contains(track_name)
                ).limit(1)
            )
            if existing.scalar_one_or_none():
                skipped += 1
                continue
            
            # Get mood name if available
            mood_name = "General"
            if event.mood_id:
                mood_result = await db.execute(
                    select(Mood).where(Mood.id == event.mood_id)
                )
                mood = mood_result.scalar_one_or_none()
                if mood:
                    mood_name = mood.name
            
            # Generate synthetic message
            if event.value == "like":
                message = f"Learned from your history: You liked {track_name}"
                added_artists = [event.track_artist] if event.track_artist else []
                demoted_artist = None
            else:
                message = f"Learned from your history: You disliked {track_name}"
                added_artists = []
                demoted_artist = event.track_artist
            
            # Create the log entry
            payload = {
                "type": "training_update",
                "source": event.value,
                "track": track_name,
                "added_artists": added_artists,
                "demoted_artist": demoted_artist,
                "reasoning": "Backfilled from historical feedback.",
                "mood_name": mood_name,
            }
            
            log_entry = StatusEventLog(
                user_id=event.user_id,
                category=StatusCategory.TRAINING,
                step=StatusStep.TRAINING_COMPLETE,
                user_message=message,
                payload_json=json.dumps(payload),
                created_at=event.created_at,  # Preserve original timestamp
            )
            db.add(log_entry)
            backfilled += 1
        
        await db.commit()
        logger.info(f"Backfill complete: {backfilled} created, {skipped} skipped (already exist).")


if __name__ == "__main__":
    asyncio.run(backfill_training_logs())
