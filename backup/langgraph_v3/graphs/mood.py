"""
Mood Graph - Load and enrich mood targets.

This subgraph handles:
1. Loading mood from database
2. Extracting energy/valence/genre targets
3. Optional LLM enrichment for similar artists
"""
import logging
from typing import Any, Dict, Optional

from langgraph.graph import StateGraph, END

from backend_v2.langgraph_v3.state import DJStateV3, add_debug_event

logger = logging.getLogger("ai-dj.graph.mood")


# =============================================================================
# Nodes
# =============================================================================

async def load_mood_node(state: DJStateV3) -> Dict[str, Any]:
    """
    Load mood from database and extract targets.
    
    Reads mood settings and populates mood_targets in state.
    """
    from backend_v2.db.session import get_db_session
    from backend_v2.models.mood import Mood
    from sqlalchemy import select
    
    mood_id = state.get("mood_id")
    user_id = state.get("user_id")
    
    logger.debug(f"Loading mood: mood_id={mood_id}, user_id={user_id}")
    
    mood_targets = None
    
    async with get_db_session() as db:
        if mood_id:
            # Load specific mood
            result = await db.execute(
                select(Mood).where(Mood.id == mood_id)
            )
            mood = result.scalar_one_or_none()
        else:
            # Load default mood for user
            result = await db.execute(
                select(Mood).where(
                    Mood.user_id == user_id,
                    Mood.is_default == True
                )
            )
            mood = result.scalar_one_or_none()
            
            if not mood:
                # Get any mood for user
                result = await db.execute(
                    select(Mood).where(Mood.user_id == user_id).limit(1)
                )
                mood = result.scalar_one_or_none()
        
        if mood:
            import json
            
            # Parse JSON fields safely
            def parse_json_list(val):
                if not val:
                    return []
                if isinstance(val, list):
                    return val
                try:
                    return json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    return []
            
            mood_targets = {
                "mood_id": mood.id,
                "mood_name": mood.name,
                "energy_target": mood.energy_target or 0.5,
                "valence_target": mood.valence_target or 0.5,
                "danceability_target": getattr(mood, "danceability_target", 0.5) or 0.5,
                "genres": parse_json_list(mood.genres_json),
                "example_artists": parse_json_list(getattr(mood, "example_artists_json", None)),
                "avoid_genres": parse_json_list(getattr(mood, "avoid_genres_json", None)),
                "vibe_keywords": parse_json_list(getattr(mood, "vibe_keywords_json", None)),
                "dj_personality": mood.dj_personality or "casual_funny",
            }
            
            logger.info(f"Loaded mood '{mood.name}': energy={mood_targets['energy_target']}, "
                       f"valence={mood_targets['valence_target']}, genres={mood_targets['genres'][:3]}")
    
    if not mood_targets:
        # Default fallback
        logger.warning(f"No mood found for user {user_id}, using defaults")
        mood_targets = {
            "mood_id": None,
            "mood_name": "Default",
            "energy_target": 0.5,
            "valence_target": 0.5,
            "danceability_target": 0.5,
            "genres": [],
            "example_artists": [],
            "avoid_genres": [],
            "vibe_keywords": [],
            "dj_personality": "casual_funny",
        }
    
    return {
        "mood_id": mood_targets.get("mood_id") or state.get("mood_id"),
        "mood_targets": mood_targets,
    }


async def load_preferences_node(state: DJStateV3) -> Dict[str, Any]:
    """
    Load user preferences and build preference bundle snapshot.
    """
    from backend_v2.db.session import get_db_session
    from backend_v2.services.preference_bundle import build_preference_bundle
    
    user_id = state.get("user_id")
    mood_id = state.get("mood_id")
    context_name = state.get("context_name")
    
    logger.debug(f"Loading preferences for user {user_id}")
    
    bundle_snapshot = None
    disliked_uuids = []
    blocked_artists = []
    explicit_allowed = True
    spotify_top_artists = []
    spotify_top_tracks = []
    spotify_genres = []
    
    try:
        async with get_db_session() as db:
            bundle = await build_preference_bundle(
                db=db,
                user_id=user_id,
                session_id=state.get("session_id"),
                mood_id=mood_id,
                context_name=context_name,
            )
            
            if bundle:
                # Extract key fields for state
                disliked_uuids = bundle.get_disliked_song_uuids()
                explicit_allowed = bundle.allows_explicit()
                
                # Get blocked artists from feedback
                if bundle.feedback:
                    blocked_artists = [
                        item.artist for item in bundle.feedback.recent_dislikes
                        if item.artist
                    ]
                
                # Get Spotify context
                if bundle.profile and bundle.profile.spotify_connected:
                    spotify_top_artists = [
                        {"name": a.get("name"), "id": a.get("id")}
                        for a in bundle.profile.top_artists_medium_term[:20]
                    ]
                    spotify_top_tracks = [
                        {"title": t.get("title"), "artist": t.get("artist")}
                        for t in bundle.profile.top_tracks_with_stats[:20]
                    ]
                    if bundle.profile.spotify_genre_analysis:
                        spotify_genres = bundle.profile.spotify_genre_analysis.get("primary_genres", [])[:20]
                
                # Serialize bundle (simplified)
                bundle_snapshot = {
                    "user_id": user_id,
                    "mood_name": bundle.mood.name if bundle.mood else None,
                    "context_name": bundle.context.name if bundle.context else None,
                    "profile": {
                        "display_name": bundle.profile.display_name if bundle.profile else None,
                        "dj_personality": bundle.profile.dj_personality if bundle.profile else None,
                        "favorite_genres": bundle.profile.favorite_genres if bundle.profile else [],
                        "favorite_artists": bundle.profile.favorite_artists if bundle.profile else [],
                    } if bundle.profile else None,
                }
                
                logger.debug(f"Loaded preferences: {len(disliked_uuids)} disliked, "
                           f"{len(spotify_top_artists)} Spotify artists")
                
    except Exception as e:
        logger.warning(f"Error loading preferences: {e}")
    
    return {
        "bundle_snapshot": bundle_snapshot,
        "disliked_uuids": disliked_uuids,
        "blocked_artists": blocked_artists,
        "explicit_allowed": explicit_allowed,
        "spotify_top_artists": spotify_top_artists,
        "spotify_top_tracks": spotify_top_tracks,
        "spotify_genres": spotify_genres,
    }


async def load_history_node(state: DJStateV3) -> Dict[str, Any]:
    """
    Load recent play history for the session.
    """
    from backend_v2.db.session import get_db_session
    from backend_v2.integrations.db_tools import get_play_history
    
    user_id = state.get("user_id")
    mood_id = state.get("mood_id")
    
    songs_played = []
    recent_artists = []
    
    try:
        async with get_db_session() as db:
            history = await get_play_history(
                db=db,
                user_id=user_id,
                mood_id=mood_id,
                limit=20,
            )
            
            for item in history:
                if item.get("song_uuid"):
                    songs_played.append(item["song_uuid"])
                if item.get("artist"):
                    recent_artists.append(item["artist"])
        
        logger.debug(f"Loaded history: {len(songs_played)} songs, {len(recent_artists)} artists")
        
    except Exception as e:
        logger.warning(f"Error loading history: {e}")
    
    return {
        "songs_played": songs_played[:50],
        "recent_artists": recent_artists[:20],
    }


async def enrich_mood_node(state: DJStateV3) -> Dict[str, Any]:
    """
    Optionally enrich mood with LLM-generated similar artists.
    
    Only runs if mood has few example artists.
    """
    mood_targets = state.get("mood_targets") or {}
    example_artists = mood_targets.get("example_artists", [])
    
    # Skip enrichment if we have enough artists
    if len(example_artists) >= 5:
        logger.debug("Mood has sufficient example artists, skipping enrichment")
        return {}
    
    # Check if enrichment is enabled
    import os
    if os.environ.get("LANGGRAPH_MOOD_ENRICHMENT", "true").lower() != "true":
        return {}
    
    try:
        from backend_v2.services.mood_enrichment import enrich_mood_with_llm
        from backend_v2.db.session import get_db_session
        from backend_v2.models.mood import Mood
        from sqlalchemy import select
        
        mood_id = mood_targets.get("mood_id")
        if not mood_id:
            return {}
        
        async with get_db_session() as db:
            result = await db.execute(
                select(Mood).where(Mood.id == mood_id)
            )
            mood = result.scalar_one_or_none()
            
            if mood:
                await enrich_mood_with_llm(db, mood)
                
                # Reload updated mood targets
                import json
                def parse_json_list(val):
                    if not val:
                        return []
                    if isinstance(val, list):
                        return val
                    try:
                        return json.loads(val)
                    except:
                        return []
                
                updated_targets = {
                    **mood_targets,
                    "example_artists": parse_json_list(getattr(mood, "example_artists_json", None)),
                }
                
                logger.info(f"Enriched mood with {len(updated_targets.get('example_artists', []))} artists")
                return {"mood_targets": updated_targets}
        
    except Exception as e:
        logger.warning(f"Mood enrichment failed: {e}")
    
    return {}


# =============================================================================
# Graph Builder
# =============================================================================

def build_mood_graph() -> StateGraph:
    """
    Build the MoodGraph subgraph.
    
    Flow:
    1. load_mood - Load mood settings from DB
    2. load_preferences - Load user preferences
    3. load_history - Load recent play history
    4. enrich_mood - Optional LLM enrichment
    """
    graph = StateGraph(DJStateV3)
    
    # Add nodes
    graph.add_node("load_mood", load_mood_node)
    graph.add_node("load_preferences", load_preferences_node)
    graph.add_node("load_history", load_history_node)
    graph.add_node("enrich_mood", enrich_mood_node)
    
    # Set entry point
    graph.set_entry_point("load_mood")
    
    # Add edges - sequential flow
    graph.add_edge("load_mood", "load_preferences")
    graph.add_edge("load_preferences", "load_history")
    graph.add_edge("load_history", "enrich_mood")
    graph.add_edge("enrich_mood", END)
    
    return graph


# Export compiled subgraph
def get_mood_subgraph():
    """Get compiled mood subgraph."""
    return build_mood_graph().compile()
