"""StatusEvent schema for real-time status updates.

Provides structured events for communicating backend progress to frontend.
Events are versioned (v2) and designed to be human-readable while also
providing structured data for UI components.

Categories:
- onboarding: Voice capture, mood creation, etc.
- playback: Stream start/stop, skip, mood switch
- generation: Track selection, TTS, mixing
- training: Feedback processing, personalization updates
- network: Connection status
- error: Any errors

Evidence: Part 1 of Status Events implementation plan
"""
from enum import Enum
from typing import Optional, Dict, Any
from datetime import datetime

from pydantic import BaseModel, Field


class StatusCategory(str, Enum):
    """High-level category for status events."""
    ONBOARDING = "onboarding"
    PLAYBACK = "playback"
    GENERATION = "generation"
    TRAINING = "training"
    NETWORK = "network"
    ERROR = "error"


class StatusStep(str, Enum):
    """Specific step/state within a category.
    
    Organized by category for clarity.
    """
    # === Generation Steps ===
    PLANNING = "planning"
    SELECTING_TRACK = "selecting_track"
    TRACK_SELECTED = "track_selected"
    SEARCHING_CATALOG = "searching_catalog"  # NEW: Searching global catalog
    TRACK_INTENT_CREATED = "track_intent_created"  # NEW: Intent created
    ACQUIRING_TRACK = "acquiring_track"  # NEW: Downloading/acquiring
    ACQUISITION_SUCCESS = "acquisition_success"  # NEW: Acquired successfully
    ACQUISITION_FAILED = "acquisition_failed"  # NEW: Acquisition failed
    SELECTING_ALTERNATIVE = "selecting_alternative"  # NEW: Fallback selection
    DOWNLOADING_TRACK = "downloading_track"
    GENERATING_INTRO = "generating_intro"
    GENERATING_TTS = "generating_tts"
    MIXING = "mixing"
    ENCODING = "encoding"
    QUEUED = "queued"
    READY = "ready"
    
    # === Playback Steps ===
    STARTING = "starting"
    PLAYING = "playing"
    PAUSED = "paused"
    SKIPPING = "skipping"
    STOPPED = "stopped"
    SWITCHING_MOOD = "switching_mood"
    BUFFERING = "buffering"
    RECOVERING = "recovering"
    
    # === Training Steps ===
    FEEDBACK_RECEIVED = "feedback_received"
    TRAINING_STARTED = "training_started"
    TRAINING_APPLIED = "training_applied"
    TRAINING_COMPLETE = "training_complete"
    
    # === Onboarding Steps ===
    MIC_PERMISSION = "mic_permission"
    VOICE_CAPTURE = "voice_capture"
    VOICE_PROCESSING = "voice_processing"
    MOOD_PARSING = "mood_parsing"
    MOOD_CREATING = "mood_creating"
    INTRO_GENERATING = "intro_generating"
    ONBOARDING_COMPLETE = "onboarding_complete"
    
    # === Network Steps ===
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    DISCONNECTED = "disconnected"
    
    # === Error Steps ===
    RETRYING = "retrying"
    FAILED = "failed"


class Severity(str, Enum):
    """Event severity level."""
    INFO = "info"
    WARN = "warn"
    ERROR = "error"


class StatusEventPayload(BaseModel):
    """Optional structured payload for status events."""
    # Track info
    track_id: Optional[str] = None
    track_title: Optional[str] = None
    track_artist: Optional[str] = None
    artwork_url: Optional[str] = None
    
    # Progress info
    segment_index: Optional[int] = None
    queue_depth: Optional[int] = None
    
    # Mood info
    mood_id: Optional[str] = None
    mood_name: Optional[str] = None
    
    # Training info
    feedback_value: Optional[str] = None
    
    # Error info
    error_code: Optional[str] = None
    retry_count: Optional[int] = None
    
    class Config:
        extra = "allow"  # Allow additional fields


class StatusEvent(BaseModel):
    """Real-time status event for frontend updates.
    
    Designed to be:
    - Versioned (v=2 for this schema)
    - Human-readable (user_message for UI)
    - Debug-friendly (debug_message for devs)
    - Structured (payload for programmatic access)
    """
    # Identity
    id: str = Field(..., description="Unique event ID (UUID)")
    ts: datetime = Field(default_factory=datetime.utcnow, description="Event timestamp")
    user_id: str = Field(..., description="User this event belongs to")
    session_id: Optional[str] = Field(None, description="Session ID if applicable")
    correlation_id: Optional[str] = Field(None, description="Links related events")
    
    # Classification
    category: StatusCategory = Field(..., description="High-level category")
    step: StatusStep = Field(..., description="Specific step/state")
    
    # Progress (optional)
    progress: Optional[float] = Field(None, ge=0.0, le=1.0, description="Progress 0.0-1.0")
    eta_seconds: Optional[int] = Field(None, ge=0, description="Estimated time remaining")
    
    # Messages
    user_message: str = Field(..., description="User-friendly message for UI")
    debug_message: Optional[str] = Field(None, description="Detailed message (dev mode only)")
    
    # Payload
    payload: Optional[StatusEventPayload] = Field(None, description="Structured event data")
    
    # Severity
    severity: Severity = Field(default=Severity.INFO, description="Event severity")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() + "Z"
        }


# === WebSocket Event Format ===
# Events are sent as:
# {
#     "v": 2,
#     "type": "status",
#     "data": { ... StatusEvent fields ... },
#     "ts": "2024-01-01T00:00:00Z"
# }
