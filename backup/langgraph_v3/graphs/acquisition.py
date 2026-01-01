"""
Acquisition Graph - Ensure track exists locally; download if missing.

This subgraph handles:
1. Check local cache for track
2. Download via providers (YouTube, etc.) if missing
3. Fallback track selection if download fails
"""
import logging
import os
from typing import Any, Dict

from langgraph.graph import StateGraph, END

from backend_v2.langgraph_v3.state import DJStateV3
from backend_v2.langgraph_v3.types import AcquisitionStatus

logger = logging.getLogger("ai-dj.graph.acquisition")


# =============================================================================
# Routing Functions
# =============================================================================

def check_acquisition_needed(state: DJStateV3) -> str:
    """
    Check if acquisition is needed.
    
    Returns "already_local", "acquire", or "no_track".
    """
    track = state.get("selected_track")
    if not track:
        return "no_track"
    
    # Check if already has local path
    local_path = track.get("local_path")
    if local_path and os.path.exists(local_path):
        return "already_local"
    
    return "acquire"


def check_acquisition_result(state: DJStateV3) -> str:
    """
    Check acquisition result.
    
    Returns "success", "retry", or "fallback".
    """
    status = state.get("acquisition_status")
    
    if status == AcquisitionStatus.ACQUIRED.value:
        return "success"
    
    if status == AcquisitionStatus.FAILED.value:
        attempts = state.get("acquisition_attempts", 0)
        if attempts < 2:  # Max 2 retries
            return "retry"
        return "fallback"
    
    return "fallback"


# =============================================================================
# Nodes
# =============================================================================

async def check_local_node(state: DJStateV3) -> Dict[str, Any]:
    """
    Check if track exists in local cache.
    """
    track = state.get("selected_track")
    if not track:
        return {"last_error": "No track selected"}
    
    from backend_v2.db.session import get_db_session
    from backend_v2.models.existing import Song
    from sqlalchemy import select, or_
    
    artist = track.get("artist", "")
    title = track.get("title", "")
    uuid = track.get("uuid")
    
    logger.debug(f"Checking local cache: {artist} - {title}")
    
    async with get_db_session() as db:
        # Build query
        conditions = []
        if uuid:
            conditions.append(Song.uuid == uuid)
        if artist and title:
            conditions.append(
                (Song.artist.ilike(f"%{artist}%")) &
                (Song.title.ilike(f"%{title}%"))
            )
        
        if not conditions:
            return {"acquisition_status": AcquisitionStatus.PENDING.value}
        
        result = await db.execute(
            select(Song).where(
                or_(*conditions),
                Song.local_path.isnot(None)
            ).limit(1)
        )
        song = result.scalar_one_or_none()
        
        if song and song.local_path and os.path.exists(song.local_path):
            logger.info(f"Found in local cache: {song.local_path}")
            return {
                "acquisition_status": AcquisitionStatus.ACQUIRED.value,
                "local_path": song.local_path,
                "selected_track": {
                    **track,
                    "uuid": song.uuid,
                    "local_path": song.local_path,
                    "duration_sec": song.duration_sec,
                    "artwork_url": song.artwork_url,
                },
            }
    
    return {"acquisition_status": AcquisitionStatus.PENDING.value}


async def mark_local_node(state: DJStateV3) -> Dict[str, Any]:
    """
    Mark track as already local (no acquisition needed).
    """
    track = state.get("selected_track")
    if not track:
        return {}
    
    local_path = track.get("local_path")
    
    logger.debug(f"Track already local: {local_path}")
    
    return {
        "acquisition_status": AcquisitionStatus.ACQUIRED.value,
        "local_path": local_path,
    }


async def acquire_node(state: DJStateV3) -> Dict[str, Any]:
    """
    Download track using acquisition service.
    """
    from backend_v2.db.session import get_db_session
    from backend_v2.services.acquisition import get_acquisition_service
    from backend_v2.models.track_intent import TrackIntent
    
    track = state.get("selected_track")
    if not track:
        return {"acquisition_status": AcquisitionStatus.FAILED.value}
    
    user_id = state.get("user_id")
    session_id = state.get("session_id")
    mood_id = state.get("mood_id")
    
    artist = track.get("artist", "")
    title = track.get("title", "")
    
    logger.info(f"Acquiring track: {artist} - {title}")
    
    attempts = state.get("acquisition_attempts", 0) + 1
    
    try:
        service = get_acquisition_service()
        
        async with get_db_session() as db:
            # Create track intent
            intent = TrackIntent(
                user_id=user_id,
                session_id=session_id,
                mood_id=mood_id,
                artist=artist,
                title=title,
                status="PENDING",
                selection_method="langgraph_v3",
            )
            db.add(intent)
            await db.commit()
            await db.refresh(intent)
            
            # Attempt acquisition
            success = await service.acquire(
                db=db,
                intent=intent,
                timeout_per_provider=90,
            )
            
            if success and intent.acquired_song_uuid:
                # Get the song record
                from backend_v2.models.existing import Song
                from sqlalchemy import select
                
                song_result = await db.execute(
                    select(Song).where(Song.uuid == intent.acquired_song_uuid)
                )
                song = song_result.scalar_one_or_none()
                
                if song and song.local_path and os.path.exists(song.local_path):
                    logger.info(f"Acquisition successful: {song.local_path}")
                    return {
                        "acquisition_status": AcquisitionStatus.ACQUIRED.value,
                        "local_path": song.local_path,
                        "acquisition_attempts": attempts,
                        "selected_track": {
                            **track,
                            "uuid": song.uuid,
                            "local_path": song.local_path,
                            "duration_sec": song.duration_sec,
                            "artwork_url": song.artwork_url,
                        },
                    }
            
            logger.warning(f"Acquisition failed for {artist} - {title}")
            return {
                "acquisition_status": AcquisitionStatus.FAILED.value,
                "acquisition_attempts": attempts,
            }
            
    except Exception as e:
        logger.error(f"Acquisition error: {e}")
        return {
            "acquisition_status": AcquisitionStatus.FAILED.value,
            "acquisition_attempts": attempts,
            "last_error": str(e),
        }


async def fallback_selection_node(state: DJStateV3) -> Dict[str, Any]:
    """
    Select a fallback track from local library.
    """
    from backend_v2.db.session import get_db_session
    from backend_v2.integrations.db_tools import search_songs_in_library
    
    logger.info("Selecting fallback track from local library")
    
    songs_played = state.get("songs_played", [])
    disliked_uuids = state.get("disliked_uuids", [])
    mood_targets = state.get("mood_targets") or {}
    
    try:
        async with get_db_session() as db:
            # Search for available local tracks
            genres = mood_targets.get("genres", [])
            genre = genres[0] if genres else None
            
            songs = await search_songs_in_library(
                db=db,
                genre=genre,
                limit=20,
            )
            
            # Filter to available tracks
            available = [
                s for s in songs
                if s.get("uuid") not in songs_played
                and s.get("uuid") not in disliked_uuids
                and s.get("local_path")
                and os.path.exists(s.get("local_path", ""))
            ]
            
            if available:
                track = available[0]
                logger.info(f"Fallback track: {track.get('artist')} - {track.get('title')}")
                return {
                    "selected_track": {
                        "uuid": track.get("uuid"),
                        "title": track.get("title"),
                        "artist": track.get("artist"),
                        "duration_sec": track.get("duration_sec"),
                        "local_path": track.get("local_path"),
                        "artwork_url": track.get("artwork_url"),
                    },
                    "fallback_track": track,
                    "acquisition_status": AcquisitionStatus.FALLBACK.value,
                    "local_path": track.get("local_path"),
                    "selection_source": "fallback_local",
                }
                
    except Exception as e:
        logger.error(f"Fallback selection failed: {e}")
    
    return {"last_error": "No fallback tracks available"}


# =============================================================================
# Graph Builder
# =============================================================================

def build_acquisition_graph() -> StateGraph:
    """
    Build the AcquisitionGraph subgraph.
    
    Flow:
    1. check_local - Check if already cached
    2. Route: already_local, acquire, or no_track
    3. acquire - Download track
    4. Route: success, retry, or fallback
    5. fallback_selection - Get local alternative
    """
    graph = StateGraph(DJStateV3)
    
    # Add nodes
    graph.add_node("check_local", check_local_node)
    graph.add_node("mark_local", mark_local_node)
    graph.add_node("acquire", acquire_node)
    graph.add_node("fallback_selection", fallback_selection_node)
    
    # Entry with conditional routing
    graph.set_conditional_entry_point(
        check_acquisition_needed,
        {
            "already_local": "mark_local",
            "acquire": "check_local",
            "no_track": "fallback_selection",
        }
    )
    
    # Mark local -> END
    graph.add_edge("mark_local", END)
    
    # Check local result routing
    def route_check_local(state: DJStateV3) -> str:
        if state.get("acquisition_status") == AcquisitionStatus.ACQUIRED.value:
            return "done"
        return "acquire"
    
    graph.add_conditional_edges(
        "check_local",
        route_check_local,
        {
            "done": END,
            "acquire": "acquire",
        }
    )
    
    # Acquire result routing
    graph.add_conditional_edges(
        "acquire",
        check_acquisition_result,
        {
            "success": END,
            "retry": "acquire",
            "fallback": "fallback_selection",
        }
    )
    
    # Fallback -> END
    graph.add_edge("fallback_selection", END)
    
    return graph


def get_acquisition_subgraph():
    """Get compiled acquisition subgraph."""
    return build_acquisition_graph().compile()
