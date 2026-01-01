"""
Feedback Training Graph - Process feedback and update long-term memory.

This subgraph handles:
1. Load feedback event
2. Use agentic training with tool calling
3. Apply training decisions to mood
4. Update long-term memory
5. Calculate effectiveness metrics
"""
import logging
from typing import Any, Dict, List

from langgraph.graph import StateGraph, END

from backend_v2.langgraph_v3.state import DJStateV3
from backend_v2.langgraph_v3.types import FeedbackType

logger = logging.getLogger("ai-dj.graph.feedback-training")


# =============================================================================
# Routing Functions
# =============================================================================

def route_feedback_type(state: DJStateV3) -> str:
    """
    Route based on feedback type.
    
    Returns "like", "dislike", "skip", or "invalid".
    """
    feedback = state.get("pending_feedback") or {}
    feedback_type = feedback.get("feedback_type", "").lower()
    
    if feedback_type == "like":
        return "like"
    elif feedback_type == "dislike":
        return "dislike"
    elif feedback_type == "skip":
        return "skip"
    
    return "invalid"


# =============================================================================
# Nodes
# =============================================================================

async def load_feedback_node(state: DJStateV3) -> Dict[str, Any]:
    """
    Load and validate feedback event.
    """
    feedback = state.get("pending_feedback")
    
    if not feedback:
        return {"last_error": "No feedback to process"}
    
    feedback_type = feedback.get("feedback_type", "").lower()
    track_artist = feedback.get("track_artist", "")
    track_title = feedback.get("track_title", "")
    
    if not feedback_type:
        return {"last_error": "Invalid feedback type"}
    
    if not track_artist and not track_title:
        return {"last_error": "Missing track information"}
    
    logger.info(f"Processing {feedback_type} feedback for: {track_artist} - {track_title}")
    
    return {}


async def train_like_node(state: DJStateV3) -> Dict[str, Any]:
    """
    Process LIKE feedback using agentic training.
    
    Attempts to find similar artists and add them to the mood.
    """
    from backend_v2.db.session import get_db_session
    
    feedback = state.get("pending_feedback") or {}
    mood_id = state.get("mood_id")
    user_id = state.get("user_id")
    track_artist = feedback.get("track_artist", "")
    track_title = feedback.get("track_title", "")
    
    logger.info(f"Training from LIKE: {track_artist} - {track_title}")
    
    training_decision = {
        "artists_to_add": [],
        "artists_to_remove": [],
        "genres_to_boost": [],
        "genres_to_demote": [],
        "feature_adjustments": {},
        "rationale": "",
    }
    
    try:
        # Try agentic training first
        from backend_v2.orchestration.agentic_trainer import train_with_tools
        
        async with get_db_session() as db:
            result = await train_with_tools(
                db=db,
                mood_id=mood_id,
                user_id=user_id,
                feedback_type="like",
                track_artist=track_artist,
                track_title=track_title,
            )
            
            if result and isinstance(result, dict):
                training_decision.update(result)
                logger.info(f"Agentic training result: +{len(result.get('artists_to_add', []))} artists")
                
    except ImportError:
        logger.debug("Agentic trainer not available, using fallback")
    except Exception as e:
        logger.warning(f"Agentic training failed: {e}")
    
    # Fallback: use mood_enrichment training
    if not training_decision["artists_to_add"]:
        try:
            from backend_v2.services.mood_enrichment import train_from_like
            
            await train_from_like(
                mood_id=mood_id,
                track_artist=track_artist,
                track_title=track_title,
            )
            
            training_decision["rationale"] = f"Added similar artists to '{track_artist}' via enrichment"
            
        except Exception as e:
            logger.warning(f"Fallback like training failed: {e}")
            training_decision["rationale"] = f"Training failed: {e}"
    
    return {
        "training_decision": training_decision,
    }


async def train_dislike_node(state: DJStateV3) -> Dict[str, Any]:
    """
    Process DISLIKE feedback.
    
    Removes/demotes artist and potentially related artists.
    """
    from backend_v2.db.session import get_db_session
    
    feedback = state.get("pending_feedback") or {}
    mood_id = state.get("mood_id")
    user_id = state.get("user_id")
    track_artist = feedback.get("track_artist", "")
    track_title = feedback.get("track_title", "")
    
    logger.info(f"Training from DISLIKE: {track_artist} - {track_title}")
    
    training_decision = {
        "artists_to_add": [],
        "artists_to_remove": [track_artist] if track_artist else [],
        "genres_to_boost": [],
        "genres_to_demote": [],
        "feature_adjustments": {},
        "rationale": f"Removed '{track_artist}' due to dislike",
    }
    
    try:
        # Try agentic training
        from backend_v2.orchestration.agentic_trainer import train_with_tools
        
        async with get_db_session() as db:
            result = await train_with_tools(
                db=db,
                mood_id=mood_id,
                user_id=user_id,
                feedback_type="dislike",
                track_artist=track_artist,
                track_title=track_title,
            )
            
            if result and isinstance(result, dict):
                training_decision.update(result)
                logger.info(f"Agentic training result: -{len(result.get('artists_to_remove', []))} artists")
                
    except ImportError:
        logger.debug("Agentic trainer not available")
    except Exception as e:
        logger.warning(f"Agentic training failed: {e}")
    
    # Fallback training
    try:
        from backend_v2.services.mood_enrichment import train_from_dislike
        
        await train_from_dislike(
            mood_id=mood_id,
            track_artist=track_artist,
            track_title=track_title,
        )
        
    except Exception as e:
        logger.warning(f"Fallback dislike training failed: {e}")
    
    return {"training_decision": training_decision}


async def train_skip_node(state: DJStateV3) -> Dict[str, Any]:
    """
    Process SKIP feedback.
    
    Investigates why skip occurred (overplayed, wrong timing, etc).
    """
    from backend_v2.db.session import get_db_session
    
    feedback = state.get("pending_feedback") or {}
    mood_id = state.get("mood_id")
    user_id = state.get("user_id")
    track_artist = feedback.get("track_artist", "")
    track_title = feedback.get("track_title", "")
    
    logger.info(f"Training from SKIP: {track_artist} - {track_title}")
    
    training_decision = {
        "artists_to_add": [],
        "artists_to_remove": [],
        "genres_to_boost": [],
        "genres_to_demote": [],
        "feature_adjustments": {},
        "rationale": f"Skip analyzed for '{track_artist}'",
    }
    
    try:
        # Try agentic training
        from backend_v2.orchestration.agentic_trainer import train_with_tools
        
        async with get_db_session() as db:
            result = await train_with_tools(
                db=db,
                mood_id=mood_id,
                user_id=user_id,
                feedback_type="skip",
                track_artist=track_artist,
                track_title=track_title,
            )
            
            if result and isinstance(result, dict):
                training_decision.update(result)
                
    except ImportError:
        logger.debug("Agentic trainer not available")
    except Exception as e:
        logger.warning(f"Agentic training failed: {e}")
    
    # Fallback training
    try:
        from backend_v2.services.mood_enrichment import train_from_skip
        
        await train_from_skip(
            mood_id=mood_id,
            track_artist=track_artist,
            track_title=track_title,
        )
        
    except Exception as e:
        logger.warning(f"Fallback skip training failed: {e}")
    
    return {"training_decision": training_decision}


async def apply_decision_node(state: DJStateV3) -> Dict[str, Any]:
    """
    Apply training decision to mood.
    """
    from backend_v2.db.session import get_db_session
    from backend_v2.models.mood import Mood
    from sqlalchemy import select
    import json
    
    training_decision = state.get("training_decision") or {}
    mood_id = state.get("mood_id")
    
    if not mood_id:
        return {}
    
    artists_to_add = training_decision.get("artists_to_add", [])
    artists_to_remove = training_decision.get("artists_to_remove", [])
    
    if not artists_to_add and not artists_to_remove:
        return {}
    
    try:
        async with get_db_session() as db:
            result = await db.execute(
                select(Mood).where(Mood.id == mood_id)
            )
            mood = result.scalar_one_or_none()
            
            if mood:
                # Parse current example artists
                current_artists = []
                if mood.example_artists:
                    if isinstance(mood.example_artists, list):
                        current_artists = mood.example_artists
                    else:
                        try:
                            current_artists = json.loads(mood.example_artists)
                        except:
                            pass
                
                # Apply changes
                updated_artists = list(current_artists)
                
                # Add new artists
                for artist in artists_to_add:
                    if artist and artist.lower() not in [a.lower() for a in updated_artists]:
                        updated_artists.append(artist)
                
                # Remove artists
                for artist in artists_to_remove:
                    updated_artists = [
                        a for a in updated_artists
                        if a.lower() != artist.lower()
                    ]
                
                # Save
                mood.example_artists = json.dumps(updated_artists)
                await db.commit()
                
                logger.info(f"Applied training: +{len(artists_to_add)}, -{len(artists_to_remove)} artists")
                
    except Exception as e:
        logger.error(f"Failed to apply training decision: {e}")
    
    return {}


async def write_memory_node(state: DJStateV3) -> Dict[str, Any]:
    """
    Write training insights to long-term memory.
    """
    from backend_v2.langgraph_v3.memory.store import (
        record_feedback_to_memory,
        record_training_outcome,
    )
    
    user_id = state.get("user_id")
    mood_id = state.get("mood_id")
    feedback = state.get("pending_feedback") or {}
    training_decision = state.get("training_decision") or {}
    
    feedback_type = feedback.get("feedback_type", "")
    track_artist = feedback.get("track_artist", "")
    track_title = feedback.get("track_title", "")
    track_uuid = feedback.get("track_uuid", "")
    
    try:
        # Record feedback to taste preferences
        await record_feedback_to_memory(
            user_id=user_id,
            feedback_type=feedback_type,
            track_artist=track_artist,
            track_title=track_title,
            track_genres=[],  # TODO: Get from track data
        )
        
        # Record training outcome
        if training_decision and mood_id:
            await record_training_outcome(
                user_id=user_id,
                mood_id=mood_id,
                training_decision=training_decision,
            )
        
        logger.debug("Updated long-term memory with training outcome")
        
    except Exception as e:
        logger.warning(f"Failed to write to memory: {e}")
    
    return {}


async def update_metrics_node(state: DJStateV3) -> Dict[str, Any]:
    """
    Log training metrics for effectiveness tracking.
    """
    from backend_v2.db.session import get_db_session
    from backend_v2.models.training_metrics import TrainingMetrics
    
    user_id = state.get("user_id")
    mood_id = state.get("mood_id")
    feedback = state.get("pending_feedback") or {}
    training_decision = state.get("training_decision") or {}
    
    try:
        async with get_db_session() as db:
            metric = TrainingMetrics(
                user_id=user_id,
                mood_id=mood_id,
                agent_name="langgraph_v3",
                feedback_type=feedback.get("feedback_type", ""),
                track_artist=feedback.get("track_artist", ""),
                track_title=feedback.get("track_title", ""),
                artists_added=len(training_decision.get("artists_to_add", [])),
                artists_removed=len(training_decision.get("artists_to_remove", [])),
            )
            db.add(metric)
            await db.commit()
            
            logger.debug(f"Recorded training metric: {metric.id}")
            
    except Exception as e:
        logger.warning(f"Failed to record training metric: {e}")
    
    return {}


async def emit_events_node(state: DJStateV3) -> Dict[str, Any]:
    """
    Emit training events for frontend.
    """
    from backend_v2.orchestration.events import get_event_emitter
    from backend_v2.schemas.status_events import StatusCategory, StatusStep
    
    user_id = state.get("user_id")
    session_id = state.get("session_id")
    feedback = state.get("pending_feedback") or {}
    training_decision = state.get("training_decision") or {}
    
    try:
        emitter = get_event_emitter()
        await emitter.emit_status(
            user_id=user_id,
            session_id=session_id,
            category=StatusCategory.TRAINING.value,
            step=StatusStep.TRAINING_APPLIED.value,
            message=training_decision.get("rationale", "Training applied"),
            details={
                "feedback_type": feedback.get("feedback_type"),
                "track_artist": feedback.get("track_artist"),
                "artists_added": training_decision.get("artists_to_add", []),
                "artists_removed": training_decision.get("artists_to_remove", []),
            },
        )
    except Exception as e:
        logger.debug(f"Event emission failed: {e}")
    
    return {}


async def invalid_feedback_node(state: DJStateV3) -> Dict[str, Any]:
    """
    Handle invalid feedback.
    """
    logger.warning("Invalid feedback received")
    return {"last_error": "Invalid feedback type"}


# =============================================================================
# Graph Builder
# =============================================================================

def build_feedback_training_graph() -> StateGraph:
    """
    Build the FeedbackTrainingGraph subgraph.
    
    Flow:
    1. load_feedback - Validate feedback
    2. Route by type: like, dislike, skip
    3. train_* - Type-specific training
    4. apply_decision - Apply to mood
    5. write_memory - Update long-term memory
    6. update_metrics - Log metrics
    7. emit_events - Notify frontend
    """
    graph = StateGraph(DJStateV3)
    
    # Add nodes
    graph.add_node("load_feedback", load_feedback_node)
    graph.add_node("train_like", train_like_node)
    graph.add_node("train_dislike", train_dislike_node)
    graph.add_node("train_skip", train_skip_node)
    graph.add_node("apply_decision", apply_decision_node)
    graph.add_node("write_memory", write_memory_node)
    graph.add_node("update_metrics", update_metrics_node)
    graph.add_node("emit_events", emit_events_node)
    graph.add_node("invalid_feedback", invalid_feedback_node)
    
    # Entry point
    graph.set_entry_point("load_feedback")
    
    # Route by feedback type
    graph.add_conditional_edges(
        "load_feedback",
        route_feedback_type,
        {
            "like": "train_like",
            "dislike": "train_dislike",
            "skip": "train_skip",
            "invalid": "invalid_feedback",
        }
    )
    
    # All training types -> apply_decision
    graph.add_edge("train_like", "apply_decision")
    graph.add_edge("train_dislike", "apply_decision")
    graph.add_edge("train_skip", "apply_decision")
    
    # Sequential flow
    graph.add_edge("apply_decision", "write_memory")
    graph.add_edge("write_memory", "update_metrics")
    graph.add_edge("update_metrics", "emit_events")
    graph.add_edge("emit_events", END)
    
    # Invalid -> END
    graph.add_edge("invalid_feedback", END)
    
    return graph


def get_feedback_training_subgraph():
    """Get compiled feedback training subgraph."""
    return build_feedback_training_graph().compile()
