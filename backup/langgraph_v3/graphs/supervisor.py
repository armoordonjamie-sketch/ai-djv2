"""
Supervisor Graph - Main orchestration graph for AI DJ v3.

This is the top-level graph that coordinates all subgraphs:
1. MoodGraph - Load mood and preferences
2. TrackSelectionGraph - Select next track
3. AcquisitionGraph - Ensure track is available
4. TransitionGraph - Plan transition
5. SpeechGraph - Generate DJ speech
6. RenderGraph - Create final audio

The supervisor handles routing based on session state (initial/resume/mix).
"""
import logging
from typing import Any, Dict

from langgraph.graph import StateGraph, END

from backend_v2.langgraph_v3.state import (
    DJStateV3,
    add_debug_event,
    advance_segment,
)

logger = logging.getLogger("ai-dj.graph.supervisor")


# =============================================================================
# Routing Functions
# =============================================================================

def route_initial(state: DJStateV3) -> str:
    """
    Route initial execution based on state.
    
    Returns: "resume", "initial", or "continue".
    """
    if state.get("is_resuming"):
        return "resume"
    
    if state.get("is_initial_segment", True):
        return "initial"
    
    return "continue"


def route_after_acquisition(state: DJStateV3) -> str:
    """
    Route after acquisition based on success/failure.
    
    Returns: "success" or "error".
    """
    if state.get("last_error"):
        return "error"
    
    if state.get("local_path") or (state.get("selected_track") or {}).get("local_path"):
        return "success"
    
    return "error"


def route_after_render(state: DJStateV3) -> str:
    """
    Route after render based on output.
    
    Returns: "success" or "error".
    """
    if state.get("next_segment_meta"):
        return "success"
    
    return "error"


# =============================================================================
# Nodes
# =============================================================================

async def load_context_node(state: DJStateV3) -> Dict[str, Any]:
    """
    Initial context loading - runs MoodGraph subgraph.
    """
    logger.info(f"Loading context for session {state.get('session_id')}")
    
    try:
        from backend_v2.langgraph_v3.graphs.mood import get_mood_subgraph
        
        subgraph = get_mood_subgraph()
        result = await subgraph.ainvoke(state)
        
        # Extract relevant state updates
        return {
            "mood_id": result.get("mood_id", state.get("mood_id")),
            "mood_targets": result.get("mood_targets"),
            "bundle_snapshot": result.get("bundle_snapshot"),
            "disliked_uuids": result.get("disliked_uuids", []),
            "blocked_artists": result.get("blocked_artists", []),
            "explicit_allowed": result.get("explicit_allowed", True),
            "spotify_top_artists": result.get("spotify_top_artists", []),
            "spotify_top_tracks": result.get("spotify_top_tracks", []),
            "spotify_genres": result.get("spotify_genres", []),
            "songs_played": result.get("songs_played", []),
            "recent_artists": result.get("recent_artists", []),
        }
        
    except Exception as e:
        logger.error(f"Context loading failed: {e}")
        return {"last_error": f"Context loading failed: {e}"}


async def resume_track_node(state: DJStateV3) -> Dict[str, Any]:
    """
    Handle resume - load existing track instead of selecting new one.
    """
    from backend_v2.db.session import get_db_session
    from backend_v2.models.existing import Song
    from sqlalchemy import select
    
    resume_uuid = state.get("resume_song_uuid")
    resume_position = state.get("resume_position_sec", 0)
    
    logger.info(f"Resuming from track {resume_uuid} at {resume_position}s")
    
    if not resume_uuid:
        # No resume track, fall back to normal selection
        return {"is_resuming": False}
    
    try:
        async with get_db_session() as db:
            result = await db.execute(
                select(Song).where(Song.uuid == resume_uuid)
            )
            song = result.scalar_one_or_none()
            
            if song and song.local_path:
                return {
                    "selected_track": {
                        "uuid": song.uuid,
                        "title": song.title,
                        "artist": song.artist,
                        "duration_sec": song.duration_sec,
                        "local_path": song.local_path,
                        "artwork_url": song.artwork_url,
                    },
                    "local_path": song.local_path,
                    "selection_source": "resume",
                    "is_initial_segment": True,  # No transition for resume
                }
                
    except Exception as e:
        logger.error(f"Resume failed: {e}")
    
    # Fallback to normal flow
    return {"is_resuming": False}


async def select_track_node(state: DJStateV3) -> Dict[str, Any]:
    """
    Run TrackSelectionGraph subgraph.
    """
    logger.info("Selecting next track")
    
    try:
        from backend_v2.langgraph_v3.graphs.track_selection import get_track_selection_subgraph
        
        subgraph = get_track_selection_subgraph()
        result = await subgraph.ainvoke(state)
        
        return {
            "selected_track": result.get("selected_track"),
            "selection_rationale": result.get("selection_rationale"),
            "selection_source": result.get("selection_source"),
            "candidate_tracks": result.get("candidate_tracks", []),
            "retrieved_docs": result.get("retrieved_docs", []),
            "artist_cooldowns": result.get("artist_cooldowns", state.get("artist_cooldowns", {})),
        }
        
    except Exception as e:
        logger.error(f"Track selection failed: {e}")
        return {"last_error": f"Track selection failed: {e}"}


async def acquire_track_node(state: DJStateV3) -> Dict[str, Any]:
    """
    Run AcquisitionGraph subgraph.
    """
    track = state.get("selected_track") or {}
    logger.info(f"Acquiring track: {track.get('artist')} - {track.get('title')}")
    
    try:
        from backend_v2.langgraph_v3.graphs.acquisition import get_acquisition_subgraph
        
        subgraph = get_acquisition_subgraph()
        result = await subgraph.ainvoke(state)
        
        return {
            "selected_track": result.get("selected_track", state.get("selected_track")),
            "acquisition_status": result.get("acquisition_status"),
            "local_path": result.get("local_path"),
            "acquisition_attempts": result.get("acquisition_attempts", 0),
            "fallback_track": result.get("fallback_track"),
            "last_error": result.get("last_error"),
        }
        
    except Exception as e:
        logger.error(f"Acquisition failed: {e}")
        return {"last_error": f"Acquisition failed: {e}"}


async def plan_transition_node(state: DJStateV3) -> Dict[str, Any]:
    """
    Run TransitionGraph subgraph.
    """
    logger.info("Planning transition")
    
    try:
        from backend_v2.langgraph_v3.graphs.transition import get_transition_subgraph
        
        subgraph = get_transition_subgraph()
        result = await subgraph.ainvoke(state)
        
        return {
            "transition_plan": result.get("transition_plan"),
            "last_song": result.get("last_song", state.get("last_song")),
            "selected_track": result.get("selected_track", state.get("selected_track")),
        }
        
    except Exception as e:
        logger.error(f"Transition planning failed: {e}")
        # Use default transition on failure
        return {
            "transition_plan": {
                "transition_type": "crossfade",
                "start_position_a_seconds": 0,
                "start_position_b_seconds": 5,
                "transition_duration_seconds": 8,
                "rationale": "Default transition (planning failed)",
            }
        }


async def generate_speech_node(state: DJStateV3) -> Dict[str, Any]:
    """
    Run SpeechGraph subgraph.
    """
    logger.info("Generating speech")
    
    try:
        from backend_v2.langgraph_v3.graphs.speech import get_speech_subgraph
        
        subgraph = get_speech_subgraph()
        result = await subgraph.ainvoke(state)
        
        return {
            "speech_script": result.get("speech_script"),
            "speech_topics_used": result.get("speech_topics_used", []),
            "tts_path": result.get("tts_path"),
            "persona_addendum": result.get("persona_addendum"),
        }
        
    except Exception as e:
        logger.warning(f"Speech generation failed: {e}")
        # Speech is optional, don't fail the whole flow
        return {}


async def render_segment_node(state: DJStateV3) -> Dict[str, Any]:
    """
    Run RenderGraph subgraph.
    """
    logger.info("Rendering segment")
    
    try:
        from backend_v2.langgraph_v3.graphs.render import get_render_subgraph
        
        subgraph = get_render_subgraph()
        result = await subgraph.ainvoke(state)
        
        return {
            "rendered_path": result.get("rendered_path"),
            "render_metadata": result.get("render_metadata"),
            "next_segment_meta": result.get("next_segment_meta"),
        }
        
    except Exception as e:
        logger.error(f"Rendering failed: {e}")
        return {"last_error": f"Rendering failed: {e}"}


async def output_segment_node(state: DJStateV3) -> Dict[str, Any]:
    """
    Finalize and prepare segment for output.
    """
    segment = state.get("next_segment_meta")
    
    if segment:
        logger.info(f"Segment ready: {segment.get('title')} by {segment.get('artist')}")
        
        # Advance state for next iteration
        advanced = advance_segment(state)
        
        return {
            "current_song": state.get("selected_track"),
            "last_song": advanced.get("last_song"),
            "songs_played": advanced.get("songs_played"),
            "recent_artists": advanced.get("recent_artists"),
            "segment_index": advanced.get("segment_index"),
            "is_initial_segment": False,
            "artist_cooldowns": advanced.get("artist_cooldowns", {}),
        }
    
    return {}


async def error_handler_node(state: DJStateV3) -> Dict[str, Any]:
    """
    Handle errors during execution.
    """
    error = state.get("last_error", "Unknown error")
    logger.error(f"Supervisor error: {error}")
    
    # Try to produce a fallback segment
    from backend_v2.langgraph_v3.state import build_segment_meta
    
    meta = build_segment_meta(state)
    if meta:
        logger.info("Produced fallback segment despite error")
        return {
            "next_segment_meta": meta.to_dict(),
            "last_error": None,  # Clear error since we recovered
        }
    
    return {}


# =============================================================================
# Graph Builder
# =============================================================================

def build_supervisor_graph() -> StateGraph:
    """
    Build the SupervisorGraph.
    
    This is the main orchestration graph that coordinates all subgraphs.
    
    Flow:
    1. load_context - Load mood and preferences
    2. Route: resume, initial, or continue
    3. select_track (for initial/continue) OR resume_track (for resume)
    4. acquire_track - Ensure track is available
    5. plan_transition - Plan mix (skipped for initial)
    6. generate_speech - Generate DJ speech
    7. render_segment - Create audio
    8. output_segment - Finalize
    """
    graph = StateGraph(DJStateV3)
    
    # Add nodes
    graph.add_node("load_context", load_context_node)
    graph.add_node("resume_track", resume_track_node)
    graph.add_node("select_track", select_track_node)
    graph.add_node("acquire_track", acquire_track_node)
    graph.add_node("plan_transition", plan_transition_node)
    graph.add_node("generate_speech", generate_speech_node)
    graph.add_node("render_segment", render_segment_node)
    graph.add_node("output_segment", output_segment_node)
    graph.add_node("error_handler", error_handler_node)
    
    # Entry point
    graph.set_entry_point("load_context")
    
    # Load context -> route
    graph.add_conditional_edges(
        "load_context",
        route_initial,
        {
            "resume": "resume_track",
            "initial": "select_track",
            "continue": "select_track",
        }
    )
    
    # Resume track -> acquire (skip selection)
    graph.add_edge("resume_track", "acquire_track")
    
    # Select track -> acquire
    graph.add_edge("select_track", "acquire_track")
    
    # Acquire -> route success/error
    graph.add_conditional_edges(
        "acquire_track",
        route_after_acquisition,
        {
            "success": "plan_transition",
            "error": "error_handler",
        }
    )
    
    # Transition -> speech
    graph.add_edge("plan_transition", "generate_speech")
    
    # Speech -> render
    graph.add_edge("generate_speech", "render_segment")
    
    # Render -> route success/error
    graph.add_conditional_edges(
        "render_segment",
        route_after_render,
        {
            "success": "output_segment",
            "error": "error_handler",
        }
    )
    
    # Output -> END
    graph.add_edge("output_segment", END)
    
    # Error handler -> END
    graph.add_edge("error_handler", END)
    
    return graph


def get_supervisor_graph():
    """Get compiled supervisor graph."""
    return build_supervisor_graph().compile()
