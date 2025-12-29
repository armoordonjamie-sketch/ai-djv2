"""DJ State types for orchestration.

Ported from backend/orchestration/graph.py with multi-user adaptations.
"""
from typing import TypedDict, List, Dict, Any, Optional
from dataclasses import dataclass, field

from backend_v2.utils.time import utc_isoformat, utc_now


class NowPlayingSegment(TypedDict):
    """Information about a currently playing segment."""
    song_uuid: str
    title: str
    artist: str
    started_at: str
    duration_sec: float
    artwork_url: Optional[str]


class DecisionStep(TypedDict):
    """A single decision in the AI's decision trace."""
    agent: str
    action: str
    rationale: str
    timestamp: str
    metadata: Optional[Dict[str, Any]]


class DJState(TypedDict, total=False):
    """State passed between orchestration agents.
    
    This is the central state object that flows through the LangGraph pipeline.
    Updated with multi-user fields: user_id, mood_id, context_id.
    """
    # === Multi-user fields (NEW) ===
    user_id: str
    mood_id: Optional[str]
    context_id: Optional[str]
    
    # === Session fields ===
    session_id: str
    
    # === Playback state ===
    now_playing: List[NowPlayingSegment]
    decision_trace: List[DecisionStep]
    segment_queue_size: Optional[int]
    
    # === Song selection ===
    selected_song_uuid: Optional[str]
    song_a_uuid: Optional[str]  # Previous song (for transitions)
    song_b_uuid: Optional[str]  # Current/next song
    song_a_path: Optional[str]  # File path for song A
    song_b_path: Optional[str]  # File path for song B
    
    # === Planning state ===
    transition_plan: Optional[Dict[str, Any]]
    speech_script: Optional[str]
    tts_audio_path: Optional[str]
    rendered_segment_path: Optional[str]
    download_status: Optional[str]
    
    # === Orchestration control ===
    songs_since_last_speech: int
    failed_song_uuids: List[str]


@dataclass
class SessionContext:
    """User session context for DJ orchestration.
    
    Contains user preferences, mood settings, and history
    loaded from database at session start.
    """
    user_id: str
    session_id: str
    mood_id: Optional[str] = None
    context_id: Optional[str] = None
    
    # Loaded from PreferenceBundle
    user_name: str = "Listener"
    music_preferences: List[str] = field(default_factory=list)
    genres: List[str] = field(default_factory=lambda: ["pop"])
    energy_target: float = 0.5
    valence_target: float = 0.5
    dj_personality: str = "chill"
    raw_context: str = ""
    mood_profile_summary: str = ""
    
    # History
    recent_plays: List[str] = field(default_factory=list)  # song UUIDs
    recent_likes: List[str] = field(default_factory=list)
    recent_dislikes: List[str] = field(default_factory=list)
    banter_history: List[str] = field(default_factory=list)
    
    # Settings
    agent_settings: Dict[str, Any] = field(default_factory=dict)
    prompt_templates: Dict[str, str] = field(default_factory=dict)


def create_initial_state(
    user_id: str,
    session_id: str,
    mood_id: Optional[str] = None,
    context_id: Optional[str] = None,
) -> DJState:
    """Create initial DJState for a new session.
    
    Args:
        user_id: Authenticated user ID
        session_id: Session ID for this streaming session
        mood_id: Optional mood ID for personalization
        context_id: Optional user context ID
        
    Returns:
        Initialized DJState ready for orchestration
    """
    return DJState(
        user_id=user_id,
        session_id=session_id,
        mood_id=mood_id,
        context_id=context_id,
        now_playing=[],
        decision_trace=[],
        segment_queue_size=0,
        selected_song_uuid=None,
        song_a_uuid=None,
        song_b_uuid=None,
        song_a_path=None,
        song_b_path=None,
        transition_plan=None,
        speech_script=None,
        tts_audio_path=None,
        rendered_segment_path=None,
        download_status=None,
        songs_since_last_speech=0,
        failed_song_uuids=[],
    )


def add_decision_step(
    state: DJState,
    agent: str,
    action: str,
    rationale: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> DJState:
    """Add a decision step to the trace.
    
    Returns a new state with the step appended.
    """
    step = DecisionStep(
        agent=agent,
        action=action,
        rationale=rationale,
        timestamp=utc_isoformat(utc_now()),
        metadata=metadata,
    )
    
    trace = list(state.get("decision_trace", []))
    trace.append(step)
    
    return {**state, "decision_trace": trace}
