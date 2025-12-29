"""Feedback training service for mood profile updates."""
import json
import logging
from typing import Dict, Any, Optional, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend_v2.models.mood import MoodProfile
from backend_v2.models.feedback import FeedbackEvent
from backend_v2.models.existing import SongFeatures

logger = logging.getLogger("ai-dj.training")


async def update_mood_profile_weights(
    db: AsyncSession,
    mood_id: str,
    feedback: FeedbackEvent,
) -> Optional[MoodProfile]:
    """
    Update mood profile weights based on feedback.
    
    Uses simple online learning:
    - Like: nudge weights toward track features
    - Dislike: nudge weights away from track features
    
    Learning rate is small to avoid overcorrection.
    """
    learning_rate = 0.05
    
    # Get the mood profile
    result = await db.execute(
        select(MoodProfile).where(MoodProfile.mood_id == mood_id)
    )
    profile = result.scalar_one_or_none()
    
    if not profile:
        logger.warning(f"No profile found for mood {mood_id}")
        return None
    
    # Get song features if available
    if not feedback.song_uuid:
        logger.debug("No song_uuid in feedback, skipping weight update")
        return profile
    
    result = await db.execute(
        select(SongFeatures).where(SongFeatures.song_uuid == feedback.song_uuid)
    )
    features = result.scalar_one_or_none()
    
    if not features:
        logger.debug(f"No features found for song {feedback.song_uuid}")
        return profile
    
    # Parse current weights or initialize
    try:
        weights = json.loads(profile.weights_json) if profile.weights_json else {}
    except json.JSONDecodeError:
        weights = {}
    
    # Direction: +1 for like, -1 for dislike
    direction = 1.0 if feedback.value == "like" else -1.0
    
    # Update weights based on song features
    feature_names = ["energy", "valence", "tempo", "danceability", "acousticness"]
    
    for feature_name in feature_names:
        feature_value = getattr(features, feature_name, None)
        if feature_value is not None:
            current_weight = weights.get(feature_name, 0.0)
            # Nudge weight toward/away from this feature value
            # Normalize tempo to 0-1 range for weight calculation
            if feature_name == "tempo":
                normalized_value = min(feature_value / 200.0, 1.0)
            else:
                normalized_value = feature_value
            
            adjustment = direction * learning_rate * (normalized_value - 0.5)
            weights[feature_name] = max(-1.0, min(1.0, current_weight + adjustment))
    
    # Save updated weights
    profile.weights_json = json.dumps(weights)
    profile.version += 1
    
    await db.commit()
    await db.refresh(profile)
    
    logger.info(f"Updated mood profile {mood_id} weights: {weights}")
    return profile


async def regenerate_summary_text(
    db: AsyncSession,
    mood_id: str,
    limit: int = 20,
) -> Optional[str]:
    """
    Regenerate mood profile summary from recent feedback.
    
    This is a deterministic summary - no LLM needed.
    For LLM-enhanced summaries, this could be extended later.
    """
    # Get recent feedback for this mood
    result = await db.execute(
        select(FeedbackEvent)
        .where(FeedbackEvent.mood_id == mood_id)
        .order_by(FeedbackEvent.created_at.desc())
        .limit(limit)
    )
    feedback_events = result.scalars().all()
    
    if not feedback_events:
        return None
    
    # Count likes and dislikes
    likes = [f for f in feedback_events if f.value == "like"]
    dislikes = [f for f in feedback_events if f.value == "dislike"]
    
    # Build summary
    summary_parts = []
    
    if likes:
        liked_tracks = [
            f"{f.track_title} by {f.track_artist}" 
            for f in likes[:5] 
            if f.track_title and f.track_artist
        ]
        if liked_tracks:
            summary_parts.append(f"Likes: {', '.join(liked_tracks)}")
    
    if dislikes:
        disliked_tracks = [
            f"{f.track_title} by {f.track_artist}" 
            for f in dislikes[:3] 
            if f.track_title and f.track_artist
        ]
        if disliked_tracks:
            summary_parts.append(f"Dislikes: {', '.join(disliked_tracks)}")
    
    # Add reasons if provided
    reasons = [f.reason_text for f in feedback_events if f.reason_text]
    if reasons:
        summary_parts.append(f"Notes: {'; '.join(reasons[:3])}")
    
    summary = " | ".join(summary_parts) if summary_parts else None
    
    # Update profile
    result = await db.execute(
        select(MoodProfile).where(MoodProfile.mood_id == mood_id)
    )
    profile = result.scalar_one_or_none()
    
    if profile and summary:
        profile.summary_text = summary[:500]  # Limit length
        await db.commit()
    
    return summary


def build_user_preference_context(
    user_context_raw: Optional[str],
    user_context_parsed: Optional[Dict[str, Any]],
    mood_targets: Optional[Dict[str, float]],
    profile_weights: Optional[Dict[str, float]],
    profile_summary: Optional[str],
    liked_examples: Optional[List[str]],
    disliked_examples: Optional[List[str]],
) -> Dict[str, Any]:
    """
    Build a structured preference context for prompt injection.
    
    This object is passed to TrackSelectorAgent and SpeechWriterAgent
    to personalize their outputs.
    """
    return {
        "user_context": {
            "raw": user_context_raw,
            "parsed": user_context_parsed,
        },
        "mood": {
            "targets": mood_targets or {},
            "weights": profile_weights or {},
            "summary": profile_summary,
        },
        "examples": {
            "liked": liked_examples or [],
            "disliked": disliked_examples or [],
        },
    }
