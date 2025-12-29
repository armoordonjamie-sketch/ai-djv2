"""Generation service for off-loop audio production.

Encapsulates logic for generating segments (intros, etc.) without a running DJLoop.
Used by mood_generator to pre-generate intros.
"""
import logging
import os
import asyncio
from typing import Optional, Dict, Any, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from backend_v2.services.preference_bundle import build_preference_bundle, PreferenceBundle
from backend_v2.orchestration.state import create_initial_state, add_decision_step, DJState
from backend_v2.orchestration.agents import (
    select_track,
    select_track_via_catalog,
    write_intro_speech,
    synthesize_speech,
)
from backend_v2.audio.mix import create_intro_mix

logger = logging.getLogger("ai-dj.generation")


async def generate_mood_intro(
    db: AsyncSession,
    user_id: str,
    mood_id: str,
) -> Optional[Dict[str, Any]]:
    """Generate an intro segment for a specific mood.
    
    Returns dict with:
    - path: str (absolute path to segment)
    - song_uuid: str
    - duration: float
    - song_info: dict (title, artist)
    """
    logger.info(f"Pre-generating intro for user {user_id}, mood {mood_id}")
    
    # 1. Build Bundle (Mock session ID since we are not in a stream)
    # We use a static session ID for pre-generation context if needed, or just "pre-gen"
    bundle = await build_preference_bundle(
        db=db,
        user_id=user_id,
        session_id=f"pre-gen-{mood_id}",
        mood_id=mood_id,
        use_cache=False
    )
    
    # 2. Select Track
    # We use an empty state primarily
    state = create_initial_state(user_id, f"pre-gen-{mood_id}", mood_id)
    
    # Get already-used intro song UUIDs for this user to prevent duplicates
    from backend_v2.models.mood import Mood as MoodModel
    from sqlalchemy import select as sql_select
    
    result = await db.execute(
        sql_select(MoodModel.intro_song_uuid).where(
            MoodModel.user_id == user_id,
            MoodModel.intro_song_uuid.isnot(None)
        )
    )
    used_intro_uuids = [uuid for (uuid,) in result if uuid]
    
    logger.info(f"Selecting track for intro (mood {mood_id}), excluding {len(used_intro_uuids)} already-used intro songs")
    
    # Use new catalog-based selection with intent flow
    selected = await select_track_via_catalog(
        db, bundle, state,
        prev_song=None,
        history_ids=used_intro_uuids,  # Exclude songs already used in other intros
        use_intent_flow=True  # Enable new catalog-based flow
    )
    
    if not selected:
        logger.warning(f"Failed to select track for intro (user {user_id}, mood {mood_id})")
        return None
        
    song_uuid = selected.get("uuid")
    song_path = selected.get("local_path")
    
    if not song_path or not os.path.exists(song_path):
        logger.warning(f"Selected song file missing: {song_path}")
        return None
        
    # 3. Generate Speech
    # Always speak for intro
    song_info = {
        "title": selected.get("title"),
        "artist": selected.get("artist"),
        "uuid": song_uuid,
    }
    
    script = await write_intro_speech(db, bundle, song_info, banter_history=[])
    
    tts_path = None
    if script:
        tts_path = await synthesize_speech(bundle, script)
        
    # 4. Render Mix
    # Run in thread
    try:
        result = await asyncio.to_thread(
            create_intro_mix,
            song_path=song_path,
            tts_path=tts_path,
            user_id=user_id,
        )
        
        if result:
            segment_path = result["output_path"]
            duration = result["metadata"]["render"]["actual_duration"]
            
            logger.info(f"Generated intro segment: {segment_path}")
            
            return {
                "path": segment_path,
                "song_uuid": song_uuid,
                "duration": duration,
                "song_info": song_info
            }
            
    except Exception as e:
        logger.error(f"Render failed for intro: {e}")
        import traceback
        traceback.print_exc()
        
    return None
