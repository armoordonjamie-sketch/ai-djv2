"""
Render Graph - Render final audio segment.

This subgraph handles:
1. Validate inputs (paths, parameters)
2. Render mix using FFmpeg
3. Build segment metadata for pipeline
"""
import logging
import os
from typing import Any, Dict

from langgraph.graph import StateGraph, END

from backend_v2.langgraph_v3.state import DJStateV3, build_segment_meta

logger = logging.getLogger("ai-dj.graph.render")


# =============================================================================
# Routing Functions
# =============================================================================

def check_render_type(state: DJStateV3) -> str:
    """
    Determine render type based on state.
    
    Returns "intro", "transition", or "single".
    """
    is_initial = state.get("is_initial_segment", False)
    last_song = state.get("last_song")
    
    if is_initial:
        return "single"  # Intro segment, just play Song B with optional TTS
    
    if last_song:
        return "transition"  # Mix Song A -> Song B
    
    return "single"


# =============================================================================
# Nodes
# =============================================================================

async def validate_inputs_node(state: DJStateV3) -> Dict[str, Any]:
    """
    Validate all required inputs for rendering.
    """
    track = state.get("selected_track") or {}
    local_path = state.get("local_path") or track.get("local_path")
    
    errors = []
    
    if not local_path:
        errors.append("No local audio path available")
    elif not os.path.exists(local_path):
        errors.append(f"Audio file not found: {local_path}")
    
    if errors:
        error_msg = "; ".join(errors)
        logger.error(f"Render validation failed: {error_msg}")
        return {"last_error": error_msg}
    
    return {}


async def render_single_node(state: DJStateV3) -> Dict[str, Any]:
    """
    Render a single track (intro segment).
    
    Optionally prepends TTS intro.
    """
    track = state.get("selected_track") or {}
    local_path = state.get("local_path") or track.get("local_path")
    tts_path = state.get("tts_path")
    session_id = state.get("session_id")
    segment_index = state.get("segment_index", 0)
    
    logger.info(f"Rendering single track: {track.get('artist')} - {track.get('title')}")
    
    # If no TTS, just use the track directly
    if not tts_path or not os.path.exists(tts_path):
        logger.debug("No TTS, using track directly")
        return {
            "rendered_path": local_path,
            "render_metadata": {
                "type": "single",
                "has_tts": False,
            },
        }
    
    # Prepend TTS to track
    try:
        from backend_v2.audio.mix import create_intro_mix
        
        output_dir = os.path.join("data", "rendered_segments")
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"intro_{session_id}_{segment_index}.wav")
        
        # Note: create_intro_mix is synchronous/blocking (like create_dj_mix)
        mix_result = create_intro_mix(
            song_path=local_path,
            tts_path=tts_path,
            output_path=output_path,
        )
        
        if mix_result and os.path.exists(output_path):
            logger.info(f"Rendered intro segment: {output_path}")
            return {
                "rendered_path": output_path,
                "render_metadata": {
                    "type": "intro",
                    "has_tts": True,
                    "tts_path": tts_path,
                    "mix_result": mix_result,
                },
            }
            
    except ImportError:
        logger.error("create_intro_mix not found in backend_v2.audio.mix")
    except Exception as e:
        logger.error(f"Intro render failed: {e}")
    
    # Fallback: just use track
    return {
        "rendered_path": local_path,
        "render_metadata": {
            "type": "single",
            "has_tts": False,
            "error": "TTS prepend failed",
        },
    }


async def render_transition_node(state: DJStateV3) -> Dict[str, Any]:
    """
    Render transition mix between two tracks.
    """
    from backend_v2.audio.mix import create_dj_mix
    
    last_song = state.get("last_song") or {}
    current_song = state.get("selected_track") or {}
    transition_plan = state.get("transition_plan") or {}
    tts_path = state.get("tts_path")
    session_id = state.get("session_id")
    segment_index = state.get("segment_index", 0)
    
    path_a = last_song.get("local_path")
    path_b = state.get("local_path") or current_song.get("local_path")
    
    logger.info(f"Rendering transition: {last_song.get('artist')} -> {current_song.get('artist')}")
    
    if not path_a or not os.path.exists(path_a):
        logger.warning("Song A path missing, rendering as single")
        return await render_single_node(state)
    
    if not path_b or not os.path.exists(path_b):
        logger.error("Song B path missing")
        return {"last_error": "Song B audio not found"}
    
    try:
        output_dir = os.path.join("data", "rendered_segments")
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"mix_{session_id}_{segment_index}.wav")
        
        # Extract transition parameters
        transition_type = transition_plan.get("transition_type", "crossfade")
        start_a = transition_plan.get("start_position_a_seconds", 0)
        start_b = transition_plan.get("start_position_b_seconds", 5)
        duration = transition_plan.get("transition_duration_seconds", 8)
        
        # Create mix
        mix_result = create_dj_mix(
            song1_path=path_a,
            song2_path=path_b,
            transition_type=transition_type,
            transition_start_a_sec=start_a,
            song2_start_sec=start_b,
            xfade_dur=duration,
            tts_path=tts_path,
            output_path=output_path,
        )
        
        if mix_result and os.path.exists(output_path):
            logger.info(f"Rendered mix: {output_path}")
            return {
                "rendered_path": output_path,
                "render_metadata": {
                    "type": "transition",
                    "transition_type": transition_type,
                    "has_tts": bool(tts_path),
                    "mix_result": mix_result,
                },
            }
            
    except Exception as e:
        logger.error(f"Mix render failed: {e}")
        return {"last_error": f"Mix render failed: {e}"}
    
    return {"last_error": "Mix render produced no output"}


async def build_output_node(state: DJStateV3) -> Dict[str, Any]:
    """
    Build final segment metadata for pipeline output.
    """
    meta = build_segment_meta(state)
    
    if meta:
        logger.info(f"Segment ready: {meta.title} by {meta.artist}")
        return {"next_segment_meta": meta.to_dict()}
    
    # Try to build minimal metadata
    track = state.get("selected_track") or {}
    rendered_path = state.get("rendered_path") or state.get("local_path")
    
    if rendered_path:
        minimal_meta = {
            "path": rendered_path,
            "song_uuid": track.get("uuid", ""),
            "title": track.get("title", "Unknown"),
            "artist": track.get("artist", "Unknown"),
            "duration": track.get("duration_sec", 0),
            "start_offset_sec": state.get("resume_position_sec", 0),
            "transition_type": state.get("transition_plan", {}).get("transition_type", "crossfade"),
        }
        
        if state.get("tts_path"):
            minimal_meta["tts_path"] = state["tts_path"]
        if track.get("artwork_url"):
            minimal_meta["artwork_url"] = track["artwork_url"]
        
        return {"next_segment_meta": minimal_meta}
    
    logger.error("Cannot build segment metadata - no audio path")
    return {"last_error": "No rendered audio path"}


# =============================================================================
# Graph Builder
# =============================================================================

def build_render_graph() -> StateGraph:
    """
    Build the RenderGraph subgraph.
    
    Flow:
    1. validate_inputs - Check paths
    2. Route: single or transition
    3. render_single OR render_transition
    4. build_output - Create segment metadata
    """
    graph = StateGraph(DJStateV3)
    
    # Add nodes
    graph.add_node("validate_inputs", validate_inputs_node)
    graph.add_node("render_single", render_single_node)
    graph.add_node("render_transition", render_transition_node)
    graph.add_node("build_output", build_output_node)
    
    # Entry point
    graph.set_entry_point("validate_inputs")
    
    # Validation -> conditional routing
    def route_after_validation(state: DJStateV3) -> str:
        if state.get("last_error"):
            return "build_output"  # Will produce error output
        return check_render_type(state)
    
    graph.add_conditional_edges(
        "validate_inputs",
        route_after_validation,
        {
            "single": "render_single",
            "transition": "render_transition",
            "intro": "render_single",
            "build_output": "build_output",
        }
    )
    
    # Both render types -> build_output
    graph.add_edge("render_single", "build_output")
    graph.add_edge("render_transition", "build_output")
    
    # Output -> END
    graph.add_edge("build_output", END)
    
    return graph


def get_render_subgraph():
    """Get compiled render subgraph."""
    return build_render_graph().compile()
