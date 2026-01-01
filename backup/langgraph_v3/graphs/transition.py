"""
Transition Graph - Plan transition type and timing.

This subgraph handles:
1. Analyze audio features of both tracks
2. Extract audio snippets for LLM context
3. LLM generates transition plan with timing
4. Normalize and validate plan
"""
import logging
import os
from typing import Any, Dict, Optional

from langgraph.graph import StateGraph, END

from backend_v2.langgraph_v3.state import DJStateV3
from backend_v2.langgraph_v3.types import TransitionType

logger = logging.getLogger("ai-dj.graph.transition")


# =============================================================================
# Nodes
# =============================================================================

async def analyze_tracks_node(state: DJStateV3) -> Dict[str, Any]:
    """
    Analyze audio features of Song A and Song B.
    """
    from backend_v2.db.session import get_db_session
    from backend_v2.models.existing import Song, SongFeatures
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    
    last_song = state.get("last_song") or {}
    current_song = state.get("selected_track") or {}
    
    song_a_uuid = last_song.get("uuid", last_song.get("song_uuid"))
    song_b_uuid = current_song.get("uuid", current_song.get("song_uuid"))
    
    song_a_features = {}
    song_b_features = {}
    
    async with get_db_session() as db:
        # Get Song A features
        if song_a_uuid:
            result = await db.execute(
                select(Song).options(selectinload(Song.features))
                .where(Song.uuid == song_a_uuid)
            )
            song = result.scalar_one_or_none()
            if song and song.features:
                song_a_features = {
                    "tempo": song.features.tempo,
                    "energy": song.features.energy,
                    "valence": song.features.valence,
                    "danceability": song.features.danceability,
                    "duration_sec": song.duration_sec,
                }
        
        # Get Song B features
        if song_b_uuid:
            result = await db.execute(
                select(Song).options(selectinload(Song.features))
                .where(Song.uuid == song_b_uuid)
            )
            song = result.scalar_one_or_none()
            if song and song.features:
                song_b_features = {
                    "tempo": song.features.tempo,
                    "energy": song.features.energy,
                    "valence": song.features.valence,
                    "danceability": song.features.danceability,
                    "duration_sec": song.duration_sec,
                }
    
    # Update state with features for transition planning
    updated_last = {**last_song, **song_a_features} if last_song else None
    updated_current = {**current_song, **song_b_features}
    
    return {
        "last_song": updated_last,
        "selected_track": updated_current,
    }


async def extract_snippets_node(state: DJStateV3) -> Dict[str, Any]:
    """
    Extract audio snippets for LLM context.
    
    Only runs if DISABLE_AUDIO_SNIPPETS is not set.
    """
    import os
    
    if os.environ.get("DISABLE_AUDIO_SNIPPETS", "false").lower() == "true":
        logger.debug("Audio snippets disabled")
        return {}
    
    from backend_v2.integrations.openrouter import get_track_duration_sec, build_audio_snippet
    
    last_song = state.get("last_song") or {}
    current_song = state.get("selected_track") or {}
    
    snippet_a = None
    snippet_b = None
    
    # Get Song A snippet (last 30 seconds)
    path_a = last_song.get("local_path")
    if path_a and os.path.exists(path_a):
        try:
            duration_a = get_track_duration_sec(path_a)
            if duration_a and duration_a > 30:
                start_time = max(0, duration_a - 30)
                snippet_a = build_audio_snippet(path_a, start_time, duration_sec=20)
                logger.debug(f"Extracted Song A snippet: {len(snippet_a) if snippet_a else 0} bytes")
        except Exception as e:
            logger.warning(f"Failed to extract Song A snippet: {e}")
    
    # Get Song B snippet (first 30 seconds)
    path_b = current_song.get("local_path")
    if path_b and os.path.exists(path_b):
        try:
            snippet_b = build_audio_snippet(path_b, 0, duration_sec=20)
            logger.debug(f"Extracted Song B snippet: {len(snippet_b) if snippet_b else 0} bytes")
        except Exception as e:
            logger.warning(f"Failed to extract Song B snippet: {e}")
    
    return {
        "transition_audio_snippet_a": snippet_a,
        "transition_audio_snippet_b": snippet_b,
    }


async def plan_transition_node(state: DJStateV3) -> Dict[str, Any]:
    """
    Use LLM to generate transition plan.
    """
    from backend_v2.integrations.openrouter import get_openrouter_client
    
    last_song = state.get("last_song") or {}
    current_song = state.get("selected_track") or {}
    
    # Skip if no Song A (initial segment)
    if not last_song:
        logger.debug("No Song A, using default transition")
        return {
            "transition_plan": {
                "transition_type": TransitionType.CROSSFADE.value,
                "start_position_a_seconds": 0,
                "start_position_b_seconds": 5,
                "transition_duration_seconds": 8,
                "mix_length_bars": 16,
                "rationale": "Initial segment - no transition needed",
            }
        }
    
    # Get recent transition types for variety
    recent_types = []  # TODO: Get from session history
    
    try:
        client = get_openrouter_client()
        
        # Build song dicts for API
        song_a = {
            "artist": last_song.get("artist"),
            "title": last_song.get("title"),
            "bpm": last_song.get("tempo", last_song.get("bpm")),
            "energy": last_song.get("energy"),
            "valence": last_song.get("valence"),
            "duration_sec": last_song.get("duration_sec"),
            "local_path": last_song.get("local_path"),
        }
        
        song_b = {
            "artist": current_song.get("artist"),
            "title": current_song.get("title"),
            "bpm": current_song.get("tempo", current_song.get("bpm")),
            "energy": current_song.get("energy"),
            "valence": current_song.get("valence"),
            "duration_sec": current_song.get("duration_sec"),
            "local_path": current_song.get("local_path"),
        }
        
        # Build preference bundle
        from backend_v2.services.preference_bundle import build_preference_bundle
        from backend_v2.db.session import get_db_session
        
        bundle = None
        async with get_db_session() as db:
            bundle = await build_preference_bundle(
                db=db,
                user_id=state.get("user_id"),
                session_id=state.get("session_id"),
                mood_id=state.get("mood_id"),
            )

        # Call transition planner
        plan = await client.generate_transition_plan(
            song_a=song_a,
            song_b=song_b,
            recent_transition_types=recent_types,
            bundle=bundle,
        )
        
        if plan:
            logger.info(f"Transition plan: {plan.get('transition_type')} "
                       f"({plan.get('transition_duration_seconds', 8)}s)")
            return {"transition_plan": plan}
            
    except Exception as e:
        logger.error(f"Transition planning failed: {e}")
    
    # Fallback to default
    return {
        "transition_plan": {
            "transition_type": TransitionType.CROSSFADE.value,
            "start_position_a_seconds": 0,
            "start_position_b_seconds": 5,
            "transition_duration_seconds": 8,
            "mix_length_bars": 16,
            "rationale": "Fallback default transition",
        }
    }


async def normalize_plan_node(state: DJStateV3) -> Dict[str, Any]:
    """
    Normalize and validate transition plan values.
    """
    from backend_v2.integrations.openrouter import normalize_transition_plan
    
    plan = state.get("transition_plan")
    if not plan:
        return {}
    
    last_song = state.get("last_song") or {}
    current_song = state.get("selected_track") or {}
    
    duration_a = last_song.get("duration_sec", 180)
    duration_b = current_song.get("duration_sec", 180)
    
    # Normalize using existing helper
    try:
        normalized = normalize_transition_plan(
            plan=plan,
            song_a=last_song,
            song_b=current_song,
        )
        return {"transition_plan": normalized}
    except Exception as e:
        logger.warning(f"Plan normalization failed: {e}")
    
    # Manual safety clamping
    plan = dict(plan)
    
    # Clamp start_position_a
    start_a = plan.get("start_position_a_seconds", 0)
    if start_a < 0:
        start_a = 0
    if duration_a and start_a > duration_a - 30:
        start_a = max(0, duration_a - 30)
    plan["start_position_a_seconds"] = start_a
    
    # Clamp start_position_b
    start_b = plan.get("start_position_b_seconds", 5)
    if start_b < 0:
        start_b = 0
    if start_b > 60:
        start_b = 5
    plan["start_position_b_seconds"] = start_b
    
    # Clamp transition duration
    duration = plan.get("transition_duration_seconds", 8)
    if duration < 2:
        duration = 8
    if duration > 30:
        duration = 16
    plan["transition_duration_seconds"] = duration
    
    return {"transition_plan": plan}


# =============================================================================
# Graph Builder
# =============================================================================

def build_transition_graph() -> StateGraph:
    """
    Build the TransitionGraph subgraph.
    
    Flow:
    1. analyze_tracks - Get audio features
    2. extract_snippets - Get audio snippets for LLM
    3. plan_transition - LLM generates plan
    4. normalize_plan - Validate and clamp values
    """
    graph = StateGraph(DJStateV3)
    
    # Add nodes
    graph.add_node("analyze_tracks", analyze_tracks_node)
    graph.add_node("extract_snippets", extract_snippets_node)
    graph.add_node("plan_transition", plan_transition_node)
    graph.add_node("normalize_plan", normalize_plan_node)
    
    # Entry point
    graph.set_entry_point("analyze_tracks")
    
    # Sequential flow
    graph.add_edge("analyze_tracks", "extract_snippets")
    graph.add_edge("extract_snippets", "plan_transition")
    graph.add_edge("plan_transition", "normalize_plan")
    graph.add_edge("normalize_plan", END)
    
    return graph


def get_transition_subgraph():
    """Get compiled transition subgraph."""
    return build_transition_graph().compile()
