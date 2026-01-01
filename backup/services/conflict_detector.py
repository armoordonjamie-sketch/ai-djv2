"""Detect and resolve conflicting feedback signals.

Handles patterns like:
- Like then skip (within 30 seconds)
- Skip then like (testing/changed mind)
- Multiple conflicting signals in short time
"""
import logging
from typing import Dict, Any, Optional, List
from datetime import timedelta
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from backend_v2.models.feedback import FeedbackEvent
from backend_v2.models.existing import PlayHistory
from backend_v2.utils.time import utc_now

logger = logging.getLogger("ai-dj.conflict-detector")


class ConflictType:
    LIKE_THEN_SKIP = "like_then_skip"
    SKIP_THEN_LIKE = "skip_then_like"
    RAPID_CHANGES = "rapid_changes"
    LIKE_AND_DISLIKE = "like_and_dislike"


async def detect_conflicts(
    db: AsyncSession,
    user_id: str,
    track_artist: str,
    track_title: str,
    current_feedback: str,  # "like", "dislike", "skip"
    lookback_minutes: int = 5,
) -> Optional[Dict[str, Any]]:
    """Detect conflicting feedback for this track.
    
    Returns:
        Dict with conflict info if detected:
        {
            "conflict_type": "like_then_skip",
            "previous_feedback": "like",
            "time_delta_seconds": 23,
            "resolution": "treat_as_testing" | "treat_as_neutral" | "prioritize_latest"
        }
        
        None if no conflict detected
    """
    cutoff_time = utc_now() - timedelta(minutes=lookback_minutes)
    
    # Get recent feedback for this track
    result = await db.execute(
        select(FeedbackEvent).where(
            and_(
                FeedbackEvent.user_id == user_id,
                FeedbackEvent.track_artist == track_artist,
                FeedbackEvent.track_title == track_title,
                FeedbackEvent.created_at >= cutoff_time,
            )
        ).order_by(FeedbackEvent.created_at.desc())
    )
    recent_feedback = list(result.scalars().all())
    
    if len(recent_feedback) < 1:
        return None  # No previous feedback to conflict with
    
    # Check if there's actually a previous feedback (current one might not be in DB yet)
    if len(recent_feedback) < 2:
        # Only one event found - this might be the current one
        return None
    
    # Get most recent previous feedback (second item, since first might be current)
    previous = recent_feedback[0] if len(recent_feedback) > 0 else None
    if not previous:
        return None
    
    time_delta = (utc_now() - previous.created_at).total_seconds()
    
    # Detect conflict patterns
    conflict = None
    
    # Like then skip (within 30 seconds)
    if previous.value == "like" and current_feedback == "skip" and time_delta < 30:
        conflict = {
            "conflict_type": ConflictType.LIKE_THEN_SKIP,
            "previous_feedback": "like",
            "time_delta_seconds": time_delta,
            "resolution": "treat_as_testing",  # User was testing feedback
            "explanation": "User liked then immediately skipped - likely testing UI",
        }
    
    # Skip then like (changed mind)
    elif previous.value == "skip" and current_feedback == "like" and time_delta < 60:
        conflict = {
            "conflict_type": ConflictType.SKIP_THEN_LIKE,
            "previous_feedback": "skip",
            "time_delta_seconds": time_delta,
            "resolution": "prioritize_latest",  # Latest is true preference
            "explanation": "User skipped then liked - they changed their mind",
        }
    
    # Like and dislike (strong conflict)
    elif (previous.value == "like" and current_feedback == "dislike") or \
         (previous.value == "dislike" and current_feedback == "like"):
        conflict = {
            "conflict_type": ConflictType.LIKE_AND_DISLIKE,
            "previous_feedback": previous.value,
            "time_delta_seconds": time_delta,
            "resolution": "prioritize_latest",  # Latest is true preference
            "explanation": f"User changed from {previous.value} to {current_feedback}",
        }
    
    # Rapid changes (3+ feedback events in 2 minutes)
    elif len(recent_feedback) >= 3 and time_delta < 120:
        conflict = {
            "conflict_type": ConflictType.RAPID_CHANGES,
            "previous_feedback": previous.value,
            "time_delta_seconds": time_delta,
            "resolution": "treat_as_neutral",  # Ignore unstable signals
            "explanation": f"Multiple rapid changes detected ({len(recent_feedback)} events)",
        }
    
    if conflict:
        logger.info(f"🔍 Conflict detected: {conflict['conflict_type']} for {track_artist} - {track_title}")
    
    return conflict


async def resolve_conflict(
    db: AsyncSession,
    conflict: Dict[str, Any],
    current_feedback_event: FeedbackEvent,
) -> str:
    """Resolve conflict and return effective feedback to use for training.
    
    Returns:
        "like" | "dislike" | "skip" | "neutral" (don't train)
    """
    resolution = conflict.get("resolution")
    
    if resolution == "treat_as_testing":
        # Don't train on testing behavior
        logger.info("Treating as testing behavior - skipping training")
        return "neutral"
    
    elif resolution == "treat_as_neutral":
        # Too unstable - don't train
        logger.info("Too many rapid changes - treating as neutral")
        return "neutral"
    
    elif resolution == "prioritize_latest":
        # Use the latest feedback
        logger.info(f"Using latest feedback: {current_feedback_event.value}")
        return current_feedback_event.value
    
    else:
        # Default: use current
        return current_feedback_event.value


async def get_conflict_statistics(
    db: AsyncSession,
    user_id: str,
    days: int = 7,
) -> Dict[str, int]:
    """Get conflict statistics for debugging/metrics.
    
    Returns:
        Dict with counts of each conflict type
    """
    cutoff_time = utc_now() - timedelta(days=days)
    
    # Get all feedback for user in time window
    result = await db.execute(
        select(FeedbackEvent).where(
            and_(
                FeedbackEvent.user_id == user_id,
                FeedbackEvent.created_at >= cutoff_time,
            )
        ).order_by(FeedbackEvent.created_at)
    )
    all_feedback = list(result.scalars().all())
    
    # Detect conflicts
    conflict_counts = {
        ConflictType.LIKE_THEN_SKIP: 0,
        ConflictType.SKIP_THEN_LIKE: 0,
        ConflictType.RAPID_CHANGES: 0,
        ConflictType.LIKE_AND_DISLIKE: 0,
    }
    
    # Group by track
    track_feedback = {}
    for feedback in all_feedback:
        key = f"{feedback.track_artist}|{feedback.track_title}"
        if key not in track_feedback:
            track_feedback[key] = []
        track_feedback[key].append(feedback)
    
    # Check each track for conflicts
    for track_key, feedback_list in track_feedback.items():
        for i in range(len(feedback_list) - 1):
            current = feedback_list[i]
            next_feedback = feedback_list[i + 1]
            
            time_delta = (next_feedback.created_at - current.created_at).total_seconds()
            
            # Like then skip
            if current.value == "like" and next_feedback.value == "skip" and time_delta < 30:
                conflict_counts[ConflictType.LIKE_THEN_SKIP] += 1
            
            # Skip then like
            elif current.value == "skip" and next_feedback.value == "like" and time_delta < 60:
                conflict_counts[ConflictType.SKIP_THEN_LIKE] += 1
            
            # Like and dislike
            elif (current.value == "like" and next_feedback.value == "dislike") or \
                 (current.value == "dislike" and next_feedback.value == "like"):
                conflict_counts[ConflictType.LIKE_AND_DISLIKE] += 1
        
        # Check for rapid changes
        if len(feedback_list) >= 3:
            first = feedback_list[0]
            last = feedback_list[-1]
            time_span = (last.created_at - first.created_at).total_seconds()
            if time_span < 120:
                conflict_counts[ConflictType.RAPID_CHANGES] += 1
    
    return conflict_counts

