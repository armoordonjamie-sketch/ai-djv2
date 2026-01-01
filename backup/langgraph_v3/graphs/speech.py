"""
Speech Graph - Generate DJ speech script and TTS audio.

This subgraph handles:
1. Compile DJ persona from user preferences
2. LLM generates speech script
3. Synthesize TTS audio
4. Record used topics to memory
"""
import logging
import os
from typing import Any, Dict, List

from langgraph.graph import StateGraph, END

from backend_v2.langgraph_v3.state import DJStateV3

logger = logging.getLogger("ai-dj.graph.speech")


# =============================================================================
# Routing Functions
# =============================================================================

def should_speak(state: DJStateV3) -> str:
    """
    Decide if speech should be generated.
    
    Returns "speak" or "skip".
    """
    # Skip speech if explicitly disabled
    if not state.get("should_speak", True):
        return "skip"
    
    # Check if this is initial segment (always speak intro)
    if state.get("is_initial_segment", False):
        return "speak"
    
    # Skip speech based on segment count (speak every 2-3 segments)
    segment_index = state.get("segment_index", 0)
    if segment_index % 3 == 0:
        return "speak"
    
    # Random chance for additional speech
    import random
    if random.random() < 0.3:  # 30% chance
        return "speak"
    
    return "skip"


# =============================================================================
# Nodes
# =============================================================================

async def compile_persona_node(state: DJStateV3) -> Dict[str, Any]:
    """
    Compile DJ persona from user preferences and memory.
    """
    from backend_v2.services.persona import compile_persona
    from backend_v2.services.preference_bundle import PreferenceBundle
    from backend_v2.langgraph_v3.memory.store import load_user_memory
    
    user_id = state.get("user_id")
    bundle_snapshot = state.get("bundle_snapshot") or {}
    mood_targets = state.get("mood_targets") or {}
    
    logger.debug(f"Compiling persona for user {user_id}")
    
    persona_addendum = ""
    
    try:
        # Load from long-term memory
        memory = await load_user_memory(user_id)
        banter_constraints = memory.get("banter", {})
        
        # Build constraints string
        off_limits = banter_constraints.get("off_limits", [])
        recently_used = banter_constraints.get("roast_topics_used", [])[-10:]
        
        if off_limits:
            persona_addendum += f"\n\nDO NOT mention these topics (user indicated they're off-limits): {', '.join(off_limits)}"
        
        if recently_used:
            persona_addendum += f"\n\nAvoid repeating these recently-used roast topics: {', '.join(recently_used)}"
        
        # Add mood personality
        dj_personality = mood_targets.get("dj_personality", "casual_funny")
        persona_addendum += f"\n\nPersonality style: {dj_personality}"
        
        # Add user name if available
        profile = bundle_snapshot.get("profile", {})
        display_name = profile.get("display_name") if profile else None
        if display_name:
            persona_addendum += f"\n\nAddress the user as: {display_name}"
        
    except Exception as e:
        logger.warning(f"Error compiling persona: {e}")
    
    return {"persona_addendum": persona_addendum}


async def write_speech_node(state: DJStateV3) -> Dict[str, Any]:
    """
    Use LLM to generate speech script.
    """
    from backend_v2.integrations.openrouter import get_openrouter_client
    
    last_song = state.get("last_song") or {}
    current_song = state.get("selected_track") or {}
    is_initial = state.get("is_initial_segment", False)
    mood_targets = state.get("mood_targets") or {}
    persona_addendum = state.get("persona_addendum", "")
    
    logger.debug("Generating speech script")
    
    try:
        client = get_openrouter_client()
        
        if is_initial:
            # Generate intro speech
            script = await client.generate_intro_speech(
                mood_name=mood_targets.get("mood_name", "your DJ session"),
                user_name=(state.get("bundle_snapshot") or {}).get("profile", {}).get("display_name"),
                personality=mood_targets.get("dj_personality", "casual_funny"),
                first_song_artist=current_song.get("artist"),
                first_song_title=current_song.get("title"),
            )
        else:
            # Generate transition speech
            script = await client.generate_transition_speech(
                song_a_artist=last_song.get("artist"),
                song_a_title=last_song.get("title"),
                song_b_artist=current_song.get("artist"),
                song_b_title=current_song.get("title"),
                transition_type=state.get("transition_plan", {}).get("transition_type", "crossfade"),
                personality=mood_targets.get("dj_personality", "casual_funny"),
                persona_addendum=persona_addendum,
            )
        
        if script:
            logger.info(f"Generated speech: {len(script)} chars")
            
            # Extract topics used (simple keyword detection)
            topics_used = _extract_topics(script)
            
            return {
                "speech_script": script,
                "speech_topics_used": topics_used,
            }
            
    except Exception as e:
        logger.error(f"Speech generation failed: {e}")
    
    return {}


async def synthesize_tts_node(state: DJStateV3) -> Dict[str, Any]:
    """
    Synthesize TTS audio from speech script.
    """
    script = state.get("speech_script")
    if not script:
        return {}
    
    from backend_v2.integrations.elevenlabs import get_elevenlabs_client
    
    session_id = state.get("session_id")
    segment_index = state.get("segment_index", 0)
    
    logger.debug(f"Synthesizing TTS: {len(script)} chars")
    
    try:
        # Generate unique filename
        tts_filename = f"speech_{session_id}_{segment_index}.mp3"
        tts_dir = os.path.join("data", "tts_output")
        os.makedirs(tts_dir, exist_ok=True)
        tts_path = os.path.join(tts_dir, tts_filename)
        
        # Synthesize
        client = get_elevenlabs_client()
        result_path = await client.synthesize_speech(
            text=script,
            output_filename=tts_filename,
        )
        
        if result_path and os.path.exists(result_path):
            logger.info(f"TTS synthesized: {result_path}")
            return {"tts_path": result_path}
            
    except Exception as e:
        logger.error(f"TTS synthesis failed: {e}")
    
    return {}


async def record_topics_node(state: DJStateV3) -> Dict[str, Any]:
    """
    Record used topics to long-term memory.
    """
    user_id = state.get("user_id")
    topics_used = state.get("speech_topics_used", [])
    
    if not topics_used:
        return {}
    
    from backend_v2.langgraph_v3.memory.store import update_banter_constraints
    
    try:
        await update_banter_constraints(
            user_id=user_id,
            topics_used=topics_used,
        )
        logger.debug(f"Recorded {len(topics_used)} topics to memory")
    except Exception as e:
        logger.warning(f"Failed to record topics: {e}")
    
    return {}


async def skip_speech_node(state: DJStateV3) -> Dict[str, Any]:
    """
    Skip speech generation (passthrough).
    """
    logger.debug("Skipping speech generation")
    return {}


# =============================================================================
# Helper Functions
# =============================================================================

def _extract_topics(script: str) -> List[str]:
    """
    Extract roast/banter topics from speech script.
    
    Simple keyword detection.
    """
    topics = []
    script_lower = script.lower()
    
    # Common roast topics
    roast_keywords = {
        "job": ["work", "job", "office", "boss", "career", "unemploy"],
        "age": ["old", "young", "age", "generation", "boomer", "millennial", "zoomer"],
        "music_taste": ["taste", "playlist", "listening to", "playing"],
        "location": ["city", "town", "weather", "traffic"],
        "habits": ["coffee", "sleep", "exercise", "gym", "diet"],
        "relationships": ["dating", "partner", "single", "married"],
        "technology": ["phone", "social media", "tiktok", "instagram"],
    }
    
    for topic, keywords in roast_keywords.items():
        for keyword in keywords:
            if keyword in script_lower:
                topics.append(topic)
                break
    
    return list(set(topics))


# =============================================================================
# Graph Builder
# =============================================================================

def build_speech_graph() -> StateGraph:
    """
    Build the SpeechGraph subgraph.
    
    Flow:
    1. Route: speak or skip
    2. compile_persona - Build persona constraints
    3. write_speech - LLM generates script
    4. synthesize_tts - Generate audio
    5. record_topics - Update memory
    """
    graph = StateGraph(DJStateV3)
    
    # Add nodes
    graph.add_node("compile_persona", compile_persona_node)
    graph.add_node("write_speech", write_speech_node)
    graph.add_node("synthesize_tts", synthesize_tts_node)
    graph.add_node("record_topics", record_topics_node)
    graph.add_node("skip_speech", skip_speech_node)
    
    # Entry with conditional routing
    graph.set_conditional_entry_point(
        should_speak,
        {
            "speak": "compile_persona",
            "skip": "skip_speech",
        }
    )
    
    # Speech flow
    graph.add_edge("compile_persona", "write_speech")
    graph.add_edge("write_speech", "synthesize_tts")
    graph.add_edge("synthesize_tts", "record_topics")
    graph.add_edge("record_topics", END)
    
    # Skip flow
    graph.add_edge("skip_speech", END)
    
    return graph


def get_speech_subgraph():
    """Get compiled speech subgraph."""
    return build_speech_graph().compile()
