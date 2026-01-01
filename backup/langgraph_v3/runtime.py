"""
LangGraph v3 Runtime - Graph compilation and execution APIs.

This module provides:
- Graph compilation with checkpointer and store
- High-level APIs for invoking the DJ graphs
- Thread state management
- Configuration helpers
"""
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph

from backend_v2.langgraph_v3.state import (
    DJStateV3,
    create_initial_state,
    build_segment_meta,
    advance_segment,
)
from backend_v2.langgraph_v3.memory.store import get_store

logger = logging.getLogger("ai-dj.langgraph-runtime")


# =============================================================================
# Globals
# =============================================================================

_checkpointer: Optional[MemorySaver] = None
_compiled_supervisor: Optional[Any] = None


def get_checkpointer() -> MemorySaver:
    """
    Get or create the checkpointer for state persistence.
    
    Uses MemorySaver for dev/test. For production, this can be
    swapped to SQLite or Postgres via environment variable.
    """
    global _checkpointer
    
    if _checkpointer is None:
        checkpointer_type = os.environ.get("LANGGRAPH_CHECKPOINTER", "memory")
        
        if checkpointer_type == "memory":
            _checkpointer = MemorySaver()
            logger.info("Initialized MemorySaver checkpointer")
        elif checkpointer_type == "sqlite":
            try:
                from langgraph.checkpoint.sqlite import SqliteSaver
                db_path = os.environ.get("LANGGRAPH_SQLITE_PATH", "data/checkpoints.db")
                # Ensure directory exists
                os.makedirs(os.path.dirname(db_path), exist_ok=True)
                _checkpointer = SqliteSaver.from_conn_string(db_path)
                logger.info(f"Initialized SqliteSaver checkpointer at {db_path}")
            except ImportError:
                logger.warning("langgraph-checkpoint-sqlite not installed, falling back to MemorySaver")
                _checkpointer = MemorySaver()
        else:
            logger.warning(f"Unknown checkpointer type '{checkpointer_type}', using MemorySaver")
            _checkpointer = MemorySaver()
    
    return _checkpointer


def get_compiled_supervisor() -> Any:
    """
    Get or compile the SupervisorGraph.
    
    Lazy-loads and compiles the graph with checkpointer and store.
    """
    global _compiled_supervisor
    
    if _compiled_supervisor is None:
        try:
            from backend_v2.langgraph_v3.graphs.supervisor import build_supervisor_graph
            
            graph = build_supervisor_graph()
            checkpointer = get_checkpointer()
            store = get_store()
            
            _compiled_supervisor = graph.compile(
                checkpointer=checkpointer,
                store=store,
            )
            logger.info("Compiled SupervisorGraph with checkpointer and store")
            
        except Exception as e:
            logger.error(f"Failed to compile SupervisorGraph: {e}")
            raise
    
    return _compiled_supervisor


def reset_runtime() -> None:
    """
    Reset runtime state (for testing).
    
    Clears compiled graphs and checkpointer.
    """
    global _checkpointer, _compiled_supervisor
    _checkpointer = None
    _compiled_supervisor = None
    logger.info("Reset LangGraph runtime")


# =============================================================================
# Execution APIs
# =============================================================================

async def invoke_segment(
    user_id: str,
    session_id: str,
    mood_id: Optional[str] = None,
    context_name: Optional[str] = None,
    resume_song_uuid: Optional[str] = None,
    resume_position_sec: Optional[float] = None,
    # Additional parameters from DJLoop
    last_song: Optional[Dict[str, Any]] = None,
    songs_played: Optional[List[str]] = None,
    is_initial: bool = False,
) -> Optional[Dict[str, Any]]:
    """
    Invoke the SupervisorGraph to generate one segment.
    
    This is the main entry point for segment generation.
    Uses session_id as thread_id for checkpointing.
    
    Args:
        user_id: User ID
        session_id: Session ID (used as thread_id)
        mood_id: Optional mood ID
        context_name: Optional context name
        resume_song_uuid: Optional song UUID to resume from
        resume_position_sec: Optional position to resume from
        last_song: Optional dict with info about the last played song (for transitions)
        songs_played: Optional list of UUIDs of previously played songs
        is_initial: Whether this is the initial segment of the session
        
    Returns:
        Segment metadata dict matching pipeline contract, or None on failure
    """
    logger.info(f"invoke_segment: user={user_id}, session={session_id}, mood={mood_id}, is_initial={is_initial}")
    
    try:
        graph = get_compiled_supervisor()
        
        # Build initial state
        initial_state = create_initial_state(
            user_id=user_id,
            session_id=session_id,
            mood_id=mood_id,
            context_name=context_name,
            resume_song_uuid=resume_song_uuid,
            resume_position_sec=resume_position_sec,
        )
        
        # Inject DJLoop state if provided
        if last_song:
            initial_state["last_song"] = last_song
        if songs_played:
            initial_state["songs_played"] = songs_played
        if is_initial:
            initial_state["is_initial_segment"] = True
        elif last_song:
            # If we have a last_song, it's not an initial segment
            initial_state["is_initial_segment"] = False
        
        # Set resuming flag if applicable
        if resume_song_uuid and resume_position_sec:
            initial_state["is_resuming"] = True
        
        # Configure with thread_id for checkpointing
        config = {
            "configurable": {
                "thread_id": session_id,
                "user_id": user_id,
            }
        }
        
        # Invoke graph
        result = await graph.ainvoke(initial_state, config=config)
        
        if not result:
            logger.error("Graph returned empty result")
            return None
        
        # Extract segment metadata
        segment_meta = result.get("next_segment_meta")
        if segment_meta:
            logger.info(f"Generated segment: {segment_meta.get('title', 'unknown')} by {segment_meta.get('artist', 'unknown')}")
            return segment_meta
        
        # Try to build from state if not explicitly set
        from backend_v2.langgraph_v3.state import build_segment_meta as build_meta
        meta = build_meta(result)
        if meta:
            return meta.to_dict()
        
        logger.error("Could not build segment metadata from result")
        return None
        
    except Exception as e:
        logger.exception(f"Error invoking segment: {e}")
        return None


async def get_thread_state(session_id: str) -> Optional[Dict[str, Any]]:
    """
    Get the current checkpointed state for a session.
    
    Args:
        session_id: Session ID (thread_id)
        
    Returns:
        Current state dict or None
    """
    try:
        graph = get_compiled_supervisor()
        config = {"configurable": {"thread_id": session_id}}
        
        state = await graph.aget_state(config)
        if state and state.values:
            return dict(state.values)
        return None
        
    except Exception as e:
        logger.error(f"Error getting thread state: {e}")
        return None


async def get_thread_history(
    session_id: str,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """
    Get checkpoint history for a session.
    
    Useful for debugging and time-travel.
    
    Args:
        session_id: Session ID (thread_id)
        limit: Maximum checkpoints to return
        
    Returns:
        List of checkpoint state dicts
    """
    try:
        graph = get_compiled_supervisor()
        config = {"configurable": {"thread_id": session_id}}
        
        history = []
        async for checkpoint in graph.aget_state_history(config):
            if len(history) >= limit:
                break
            history.append({
                "values": dict(checkpoint.values) if checkpoint.values else {},
                "checkpoint_id": checkpoint.config.get("configurable", {}).get("checkpoint_id"),
                "created_at": checkpoint.metadata.get("created_at") if checkpoint.metadata else None,
            })
        
        return history
        
    except Exception as e:
        logger.error(f"Error getting thread history: {e}")
        return []


async def update_thread_state(
    session_id: str,
    updates: Dict[str, Any],
) -> bool:
    """
    Update the current thread state.
    
    Useful for injecting feedback or corrections.
    
    Args:
        session_id: Session ID (thread_id)
        updates: Dict of state updates
        
    Returns:
        True if successful
    """
    try:
        graph = get_compiled_supervisor()
        config = {"configurable": {"thread_id": session_id}}
        
        await graph.aupdate_state(config, updates)
        return True
        
    except Exception as e:
        logger.error(f"Error updating thread state: {e}")
        return False


# =============================================================================
# Batch/Stream APIs
# =============================================================================

async def invoke_segment_stream(
    user_id: str,
    session_id: str,
    mood_id: Optional[str] = None,
    context_name: Optional[str] = None,
):
    """
    Stream segment generation events.
    
    Yields events as the graph executes each node.
    Useful for real-time progress updates.
    """
    try:
        graph = get_compiled_supervisor()
        
        initial_state = create_initial_state(
            user_id=user_id,
            session_id=session_id,
            mood_id=mood_id,
            context_name=context_name,
        )
        
        config = {
            "configurable": {
                "thread_id": session_id,
                "user_id": user_id,
            }
        }
        
        async for event in graph.astream_events(initial_state, config=config, version="v2"):
            yield event
            
    except Exception as e:
        logger.exception(f"Error in segment stream: {e}")
        yield {"event": "error", "error": str(e)}


# =============================================================================
# Training Integration
# =============================================================================

async def process_feedback(
    user_id: str,
    session_id: str,
    mood_id: str,
    feedback_type: str,
    track_artist: str,
    track_title: str,
    track_uuid: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Process user feedback and trigger training.
    
    This integrates with the FeedbackTrainingGraph.
    
    Args:
        user_id: User ID
        session_id: Session ID
        mood_id: Mood ID for training
        feedback_type: "like", "dislike", or "skip"
        track_artist: Artist name
        track_title: Track title
        track_uuid: Optional track UUID
        
    Returns:
        Training result dict
    """
    logger.info(f"Processing feedback: {feedback_type} for {track_artist} - {track_title}")
    
    try:
        # Update long-term memory
        from backend_v2.langgraph_v3.memory.store import record_feedback_to_memory
        await record_feedback_to_memory(
            user_id=user_id,
            feedback_type=feedback_type,
            track_artist=track_artist,
            track_title=track_title,
            track_genres=[],  # TODO: Get from track data
        )
        
        # Invoke training graph
        try:
            from backend_v2.langgraph_v3.graphs.feedback_training import build_feedback_training_graph
            
            training_graph = build_feedback_training_graph()
            checkpointer = get_checkpointer()
            store = get_store()
            
            compiled = training_graph.compile(
                checkpointer=checkpointer,
                store=store,
            )
            
            training_state = {
                "user_id": user_id,
                "session_id": session_id,
                "mood_id": mood_id,
                "pending_feedback": {
                    "feedback_type": feedback_type,
                    "track_uuid": track_uuid or "",
                    "track_artist": track_artist,
                    "track_title": track_title,
                },
            }
            
            config = {
                "configurable": {
                    "thread_id": f"training_{session_id}_{track_uuid or 'unknown'}",
                }
            }
            
            result = await compiled.ainvoke(training_state, config=config)
            
            return {
                "success": True,
                "training_decision": result.get("training_decision"),
            }
            
        except ImportError:
            # Training graph not yet implemented, use legacy
            logger.debug("FeedbackTrainingGraph not available, using legacy training")
            from backend_v2.services.mood_enrichment import (
                train_from_like,
                train_from_dislike,
                train_from_skip,
            )
            
            if feedback_type == "like":
                await train_from_like(mood_id, track_artist, track_title)
            elif feedback_type == "dislike":
                await train_from_dislike(mood_id, track_artist, track_title)
            elif feedback_type == "skip":
                await train_from_skip(mood_id, track_artist, track_title)
            
            return {"success": True, "training_decision": None, "legacy": True}
        
    except Exception as e:
        logger.exception(f"Error processing feedback: {e}")
        return {"success": False, "error": str(e)}


# =============================================================================
# Health Check
# =============================================================================

def check_runtime_health() -> Dict[str, Any]:
    """
    Check the health of the LangGraph runtime.
    
    Returns status of checkpointer, store, and graph compilation.
    """
    result = {
        "checkpointer": "unknown",
        "store": "unknown",
        "supervisor_graph": "unknown",
        "healthy": False,
    }
    
    try:
        # Check checkpointer
        cp = get_checkpointer()
        result["checkpointer"] = type(cp).__name__
        
        # Check store
        store = get_store()
        result["store"] = type(store).__name__
        
        # Check graph compilation
        try:
            graph = get_compiled_supervisor()
            result["supervisor_graph"] = "compiled"
        except Exception as e:
            result["supervisor_graph"] = f"error: {str(e)}"
            return result
        
        result["healthy"] = True
        
    except Exception as e:
        result["error"] = str(e)
    
    return result
