"""Batch training mode for learning from multiple feedback events.

Instead of training on each individual feedback event, batch training:
1. Collects multiple feedback events over a time window (e.g., session)
2. Analyzes patterns across all events
3. Makes holistic mood adjustments based on aggregate insights
4. More stable than reactive single-event training
"""
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import timedelta
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from backend_v2.models.mood import Mood
from backend_v2.models.feedback import FeedbackEvent
from backend_v2.models.existing import PlayHistory
from backend_v2.integrations.openrouter import get_openrouter_client
from backend_v2.utils.time import utc_now

logger = logging.getLogger("ai-dj.batch-trainer")


async def train_in_batch(
    db: AsyncSession,
    mood_id: str,
    user_id: str,
    session_id: Optional[str] = None,
    lookback_hours: int = 24,
) -> Dict[str, Any]:
    """Train mood from multiple feedback events in batch.
    
    Args:
        db: Database session
        mood_id: Mood to train
        user_id: User ID
        session_id: Optional session to limit to
        lookback_hours: Hours of history to analyze
        
    Returns:
        Dict with batch training results
    """
    # Get mood
    mood_result = await db.execute(select(Mood).where(Mood.id == mood_id))
    mood = mood_result.scalar_one_or_none()
    if not mood:
        return {"success": False, "error": "Mood not found"}
    
    # Collect feedback events
    cutoff_time = utc_now() - timedelta(hours=lookback_hours)
    
    feedback_query = select(FeedbackEvent).where(
        and_(
            FeedbackEvent.user_id == user_id,
            FeedbackEvent.mood_id == mood_id,
            FeedbackEvent.created_at >= cutoff_time,
        )
    ).order_by(FeedbackEvent.created_at.desc())
    
    feedback_result = await db.execute(feedback_query)
    feedback_events = list(feedback_result.scalars().all())
    
    if len(feedback_events) < 3:
        logger.info(f"Not enough feedback for batch training ({len(feedback_events)} events)")
        return {"success": False, "error": "Insufficient feedback"}
    
    # Organize feedback by type
    likes = [f for f in feedback_events if f.value == "like"]
    dislikes = [f for f in feedback_events if f.value == "dislike"]
    
    # Get play history for additional context
    if session_id:
        plays_query = select(PlayHistory).where(
            and_(
                PlayHistory.session_id == session_id,
                PlayHistory.user_id == user_id,
            )
        ).order_by(PlayHistory.created_at.desc())
    else:
        plays_query = select(PlayHistory).where(
            and_(
                PlayHistory.user_id == user_id,
                PlayHistory.created_at >= cutoff_time,
            )
        ).order_by(PlayHistory.created_at.desc()).limit(50)
    
    plays_result = await db.execute(plays_query)
    plays = list(plays_result.scalars().all())
    
    # Build batch analysis prompt
    system_prompt = f"""You are analyzing multiple feedback events to train a mood profile.

**Mood**: {mood.name} (Energy: {mood.energy_target}, Valence: {mood.valence_target})

**Your Task**: 
Analyze the collective feedback to identify clear patterns and make holistic mood improvements.

**Batch Analysis Approach**:
1. Look for PATTERNS, not individual events
   - Which artists are consistently liked/disliked?
   - Are there genre preferences emerging?
   - Any timing patterns (skips at certain times)?

2. Focus on STRONG SIGNALS
   - Multiple likes for similar artists = add more
   - Multiple dislikes for an artist = remove
   - Mixed signals = be conservative

3. Make BALANCED adjustments
   - Don't overreact to outliers
   - Prefer gradual shifts over radical changes
   - Keep mood coherent

**Output Format**:
```json
{{
  "patterns_identified": [
    "User consistently likes indie pop artists",
    "Electronic music gets skipped frequently"
  ],
  "artists_to_add": ["Artist 1", "Artist 2"],
  "artists_to_remove": ["Artist X"],
  "genres_to_emphasize": ["genre1"],
  "genres_to_avoid": ["genre2"],
  "confidence": 0.8,
  "reasoning": "Detailed explanation of batch insights"
}}
```"""
    
    # Build feedback summary
    liked_tracks = [f"{f.track_artist} - {f.track_title}" for f in likes[:10]]
    disliked_tracks = [f"{f.track_artist} - {f.track_title}" for f in dislikes[:10]]
    
    user_prompt = f"""Batch Training Data:

**Likes** ({len(likes)} total):
{chr(10).join(f'- {t}' for t in liked_tracks)}

**Dislikes** ({len(dislikes)} total):
{chr(10).join(f'- {t}' for t in disliked_tracks)}

**Plays**: {len(plays)} tracks played
**Time Period**: Last {lookback_hours} hours

Analyze these patterns and recommend mood adjustments."""
    
    # Call LLM for batch analysis
    client = get_openrouter_client()
    result = await client.chat_completion(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.5,  # Lower temp for more consistent batch analysis
        json_mode=True,
        use_lite_model=False,  # Use full model for complex analysis
        session_id=None,
        db=db,
        user_id=user_id,
        mood_id=mood_id,
        agent_name="batch_trainer",
    )
    
    if not result or not result.get('parsed'):
        return {"success": False, "error": "LLM analysis failed"}
    
    decision = result['parsed']
    
    # Apply batch decision to mood
    await _apply_batch_decision(db, mood, decision)
    
    logger.info(f"🎓 Batch training complete: {len(likes)} likes, {len(dislikes)} dislikes analyzed")
    
    return {
        "success": True,
        "feedback_analyzed": len(feedback_events),
        "patterns": decision.get("patterns_identified", []),
        "confidence": decision.get("confidence", 0),
        "decision": decision,
    }


async def _apply_batch_decision(
    db: AsyncSession,
    mood: Mood,
    decision: Dict[str, Any],
) -> None:
    """Apply batch training decision to mood."""
    # Get existing artists
    existing_artists = []
    if mood.example_artists_json:
        try:
            existing_artists = json.loads(mood.example_artists_json) or []
        except:
            pass
    
    # Add artists
    artists_to_add = decision.get("artists_to_add", [])
    for artist in artists_to_add:
        if artist and artist not in existing_artists:
            existing_artists.insert(0, artist)
    
    # Remove artists
    artists_to_remove = decision.get("artists_to_remove", [])
    for artist in artists_to_remove:
        existing_artists = [a for a in existing_artists if a.lower() != artist.lower()]
    
    # Update mood
    mood.example_artists_json = json.dumps(existing_artists[:25])
    
    # Update genres
    genres_to_emphasize = decision.get("genres_to_emphasize", [])
    if genres_to_emphasize and mood.genre_seeds_json:
        try:
            existing_genres = json.loads(mood.genre_seeds_json) or []
            for genre in genres_to_emphasize:
                if genre and genre not in existing_genres:
                    existing_genres.insert(0, genre)
            mood.genre_seeds_json = json.dumps(existing_genres[:10])
        except:
            pass
    
    await db.commit()
    
    # Invalidate cache
    from backend_v2.services.preference_bundle import get_bundle_cache
    cache = get_bundle_cache()
    cache.invalidate(mood.user_id)

