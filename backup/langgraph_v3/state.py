"""
DJStateV3 - State schema for LangGraph v3 orchestration.

This TypedDict defines the complete state that flows through all graphs.
It includes identity, execution state, playback, preferences, RAG context,
selection, acquisition, transition, speech, and output fields.
"""
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Annotated
from typing_extensions import TypedDict

from langgraph.graph.message import add_messages

from backend_v2.langgraph_v3.types import (
    AcquisitionStatus,
    TrackInfo,
    TransitionPlan,
    SegmentMeta,
    MoodTargets,
    RetrievedDoc,
    FeedbackSignal,
    TrainingDecision,
    DebugEvent,
)

logger = logging.getLogger("ai-dj.langgraph-state")


class DJStateV3(TypedDict, total=False):
    """
    Complete state schema for AI DJ v3 LangGraph orchestration.
    
    This state flows through all graphs and subgraphs. Fields are organized
    by concern and most are optional (total=False) to allow incremental building.
    
    The `messages` field uses LangGraph's add_messages reducer for proper
    message accumulation during tool calling.
    """
    
    # === Identity (set once per session) ===
    user_id: str
    session_id: str
    thread_id: str  # Alias for session_id, used by checkpointer
    mood_id: Optional[str]
    context_name: Optional[str]
    
    # === Execution State ===
    step_id: int  # Increments each super-step
    segment_index: int  # Number of segments produced in this session
    is_initial_segment: bool  # True for first segment (intro)
    last_error: Optional[str]
    debug_events: List[Dict[str, Any]]
    
    # === Playback State ===
    current_song: Optional[Dict[str, Any]]  # Currently selected/playing track
    last_song: Optional[Dict[str, Any]]  # Previous track (Song A in transition)
    songs_played: List[str]  # UUIDs of all played songs
    recent_artists: List[str]  # Recent artist names for cooldown
    
    # === Resume State ===
    resume_song_uuid: Optional[str]
    resume_position_sec: Optional[float]
    is_resuming: bool
    
    # === Preferences (snapshot from PreferenceBundle) ===
    bundle_snapshot: Optional[Dict[str, Any]]  # Serialized PreferenceBundle
    mood_targets: Optional[Dict[str, Any]]  # MoodTargets as dict
    disliked_uuids: List[str]
    blocked_artists: List[str]
    artist_cooldowns: Dict[str, int]  # artist -> segments until playable
    explicit_allowed: bool
    
    # === Spotify Context ===
    spotify_top_artists: List[Dict[str, Any]]
    spotify_top_tracks: List[Dict[str, Any]]
    spotify_genres: List[str]
    
    # === RAG Context ===
    retrieval_query: Optional[str]
    retrieved_docs: List[Dict[str, Any]]
    retrieval_sources: List[str]
    should_retrieve: bool
    
    # === Selection State ===
    candidate_tracks: List[Dict[str, Any]]
    selected_track: Optional[Dict[str, Any]]
    selection_rationale: Optional[str]
    selection_source: Optional[str]  # "library", "catalog", "rag", "fallback"
    
    # === Acquisition State ===
    acquisition_status: Optional[str]  # AcquisitionStatus value
    local_path: Optional[str]
    acquisition_attempts: int
    fallback_track: Optional[Dict[str, Any]]
    
    # === Transition State ===
    transition_plan: Optional[Dict[str, Any]]  # TransitionPlan as dict
    transition_audio_snippet_a: Optional[str]  # Base64 audio of Song A tail
    transition_audio_snippet_b: Optional[str]  # Base64 audio of Song B head
    
    # === Speech State ===
    speech_script: Optional[str]
    speech_topics_used: List[str]
    tts_path: Optional[str]
    should_speak: bool
    persona_addendum: Optional[str]
    
    # === Render State ===
    rendered_path: Optional[str]
    render_metadata: Optional[Dict[str, Any]]
    
    # === Output ===
    next_segment_meta: Optional[Dict[str, Any]]  # SegmentMeta as dict
    
    # === Feedback and Training ===
    pending_feedback: Optional[Dict[str, Any]]  # FeedbackSignal as dict
    training_signals: List[Dict[str, Any]]
    training_decision: Optional[Dict[str, Any]]  # TrainingDecision as dict
    
    # === Messages (for tool calling with LLM) ===
    messages: Annotated[List[Any], add_messages]


# =============================================================================
# State Helpers
# =============================================================================

def create_initial_state(
    user_id: str,
    session_id: str,
    mood_id: Optional[str] = None,
    context_name: Optional[str] = None,
    resume_song_uuid: Optional[str] = None,
    resume_position_sec: Optional[float] = None,
) -> DJStateV3:
    """
    Create initial state for a new graph execution.
    
    Args:
        user_id: User ID
        session_id: Session ID (also used as thread_id)
        mood_id: Optional mood ID
        context_name: Optional context name
        resume_song_uuid: Optional song UUID to resume from
        resume_position_sec: Optional position to resume from
        
    Returns:
        Initial DJStateV3 with all required fields initialized
    """
    return {
        # Identity
        "user_id": user_id,
        "session_id": session_id,
        "thread_id": session_id,  # Alias for checkpointer
        "mood_id": mood_id,
        "context_name": context_name,
        
        # Execution
        "step_id": 0,
        "segment_index": 0,
        "is_initial_segment": True,
        "last_error": None,
        "debug_events": [],
        
        # Playback
        "current_song": None,
        "last_song": None,
        "songs_played": [],
        "recent_artists": [],
        
        # Resume
        "resume_song_uuid": resume_song_uuid,
        "resume_position_sec": resume_position_sec,
        "is_resuming": resume_song_uuid is not None,
        
        # Preferences
        "bundle_snapshot": None,
        "mood_targets": None,
        "disliked_uuids": [],
        "blocked_artists": [],
        "artist_cooldowns": {},
        "explicit_allowed": True,
        
        # Spotify
        "spotify_top_artists": [],
        "spotify_top_tracks": [],
        "spotify_genres": [],
        
        # RAG
        "retrieval_query": None,
        "retrieved_docs": [],
        "retrieval_sources": [],
        "should_retrieve": False,
        
        # Selection
        "candidate_tracks": [],
        "selected_track": None,
        "selection_rationale": None,
        "selection_source": None,
        
        # Acquisition
        "acquisition_status": None,
        "local_path": None,
        "acquisition_attempts": 0,
        "fallback_track": None,
        
        # Transition
        "transition_plan": None,
        "transition_audio_snippet_a": None,
        "transition_audio_snippet_b": None,
        
        # Speech
        "speech_script": None,
        "speech_topics_used": [],
        "tts_path": None,
        "should_speak": True,
        "persona_addendum": None,
        
        # Render
        "rendered_path": None,
        "render_metadata": None,
        
        # Output
        "next_segment_meta": None,
        
        # Feedback/Training
        "pending_feedback": None,
        "training_signals": [],
        "training_decision": None,
        
        # Messages
        "messages": [],
    }


def add_debug_event(
    state: DJStateV3,
    node: str,
    event_type: str,
    message: str,
    data: Optional[Dict[str, Any]] = None,
) -> DJStateV3:
    """
    Add a debug event to state.
    
    Returns a new state dict with the event added (immutable pattern).
    """
    from backend_v2.utils.time import utc_now
    
    event = DebugEvent(
        timestamp=utc_now(),
        node=node,
        event_type=event_type,
        message=message,
        data=data or {},
    )
    
    events = list(state.get("debug_events", []))
    events.append(event.to_dict())
    
    return {**state, "debug_events": events}


def get_track_info(state: DJStateV3, key: str = "selected_track") -> Optional[TrackInfo]:
    """
    Extract TrackInfo from state dict field.
    
    Args:
        state: Current state
        key: Field name containing track dict
        
    Returns:
        TrackInfo object or None
    """
    track_dict = state.get(key)
    if not track_dict:
        return None
    return TrackInfo.from_dict(track_dict)


def get_transition_plan(state: DJStateV3) -> Optional[TransitionPlan]:
    """Extract TransitionPlan from state."""
    plan_dict = state.get("transition_plan")
    if not plan_dict:
        return None
    return TransitionPlan.from_dict(plan_dict)


def get_mood_targets(state: DJStateV3) -> Optional[MoodTargets]:
    """Extract MoodTargets from state."""
    targets_dict = state.get("mood_targets")
    if not targets_dict:
        return None
    
    return MoodTargets(
        mood_id=targets_dict.get("mood_id", ""),
        mood_name=targets_dict.get("mood_name", ""),
        energy_target=targets_dict.get("energy_target", 0.5),
        valence_target=targets_dict.get("valence_target", 0.5),
        danceability_target=targets_dict.get("danceability_target", 0.5),
        genres=targets_dict.get("genres", []),
        example_artists=targets_dict.get("example_artists", []),
        avoid_genres=targets_dict.get("avoid_genres", []),
        vibe_keywords=targets_dict.get("vibe_keywords", []),
        dj_personality=targets_dict.get("dj_personality", "casual_funny"),
    )


def build_segment_meta(state: DJStateV3) -> Optional[SegmentMeta]:
    """
    Build SegmentMeta from state for pipeline output.
    
    This creates the dict that goes into segment_queue.
    
    Returns:
        SegmentMeta object or None if state is incomplete
    """
    path = state.get("rendered_path") or state.get("local_path")
    if not path:
        logger.warning("Cannot build segment_meta: no path available")
        return None
    
    track = state.get("selected_track") or state.get("current_song")
    if not track:
        logger.warning("Cannot build segment_meta: no track available")
        return None
    
    transition_plan = state.get("transition_plan") or {}
    last_song = state.get("last_song")
    
    meta = SegmentMeta(
        path=path,
        song_uuid=track.get("uuid", track.get("song_uuid", "")),
        title=track.get("title", ""),
        artist=track.get("artist", ""),
        duration=track.get("duration_sec", track.get("duration", 0.0)),
        start_offset_sec=state.get("resume_position_sec", 0.0),
        transition_type=transition_plan.get("transition_type", "crossfade"),
        tts_path=state.get("tts_path"),
        artwork_url=track.get("artwork_url"),
    )
    
    # Add song2 info if this is a transition
    if last_song:
        meta.song2_uuid = last_song.get("uuid", last_song.get("song_uuid"))
        meta.song2_title = last_song.get("title")
        meta.song2_artist = last_song.get("artist")
    
    return meta


def validate_state_for_output(state: DJStateV3) -> tuple[bool, str]:
    """
    Validate state has all required fields for segment output.
    
    Returns:
        (is_valid, error_message)
    """
    errors = []
    
    if not state.get("user_id"):
        errors.append("Missing user_id")
    if not state.get("session_id"):
        errors.append("Missing session_id")
    
    # For output, we need either a rendered path or a track with local path
    if not state.get("rendered_path") and not state.get("local_path"):
        track = state.get("selected_track") or state.get("current_song")
        if not track:
            errors.append("No track selected and no rendered path")
        elif not track.get("local_path"):
            errors.append("Selected track has no local_path")
    
    if errors:
        return False, "; ".join(errors)
    return True, ""


def advance_segment(state: DJStateV3) -> DJStateV3:
    """
    Advance state for next segment.
    
    Moves selected_track to last_song, increments segment_index, etc.
    Returns new state dict (immutable pattern).
    """
    new_state = dict(state)
    
    # Move current to last
    current = new_state.get("selected_track") or new_state.get("current_song")
    if current:
        new_state["last_song"] = current
        
        # Track in history
        songs_played = list(new_state.get("songs_played", []))
        song_uuid = current.get("uuid", current.get("song_uuid"))
        if song_uuid and song_uuid not in songs_played:
            songs_played.append(song_uuid)
        new_state["songs_played"] = songs_played[-50:]  # Keep last 50
        
        # Track artist for cooldown
        recent_artists = list(new_state.get("recent_artists", []))
        artist = current.get("artist")
        if artist:
            recent_artists.append(artist)
        new_state["recent_artists"] = recent_artists[-20:]  # Keep last 20
    
    # Increment segment index
    new_state["segment_index"] = new_state.get("segment_index", 0) + 1
    new_state["is_initial_segment"] = False
    new_state["is_resuming"] = False
    
    # Clear per-segment state
    new_state["selected_track"] = None
    new_state["current_song"] = None
    new_state["selection_rationale"] = None
    new_state["acquisition_status"] = None
    new_state["local_path"] = None
    new_state["transition_plan"] = None
    new_state["speech_script"] = None
    new_state["tts_path"] = None
    new_state["rendered_path"] = None
    new_state["next_segment_meta"] = None
    new_state["candidate_tracks"] = []
    new_state["retrieved_docs"] = []
    new_state["messages"] = []  # Clear tool messages
    
    # Advance cooldowns
    cooldowns = dict(new_state.get("artist_cooldowns", {}))
    for artist in list(cooldowns.keys()):
        cooldowns[artist] -= 1
        if cooldowns[artist] <= 0:
            del cooldowns[artist]
    new_state["artist_cooldowns"] = cooldowns
    
    return new_state


def serialize_state(state: DJStateV3) -> Dict[str, Any]:
    """
    Serialize state to JSON-compatible dict.
    
    Handles any non-serializable fields.
    """
    result = dict(state)
    
    # Messages may contain non-serializable objects
    if "messages" in result:
        result["messages"] = [
            m.dict() if hasattr(m, "dict") else str(m)
            for m in result.get("messages", [])
        ]
    
    return result


def check_artist_cooldown(state: DJStateV3, artist: str) -> bool:
    """
    Check if an artist is on cooldown.
    
    Returns True if artist can be played, False if on cooldown.
    """
    if not artist:
        return True
    
    cooldowns = state.get("artist_cooldowns", {})
    artist_lower = artist.lower()
    
    # Check exact match
    for cooled_artist, remaining in cooldowns.items():
        if cooled_artist.lower() == artist_lower and remaining > 0:
            return False
    
    return True


def add_artist_cooldown(state: DJStateV3, artist: str, segments: int = 5) -> DJStateV3:
    """
    Add cooldown for an artist.
    
    Returns new state with cooldown added.
    """
    if not artist:
        return state
    
    cooldowns = dict(state.get("artist_cooldowns", {}))
    cooldowns[artist] = segments
    
    return {**state, "artist_cooldowns": cooldowns}
