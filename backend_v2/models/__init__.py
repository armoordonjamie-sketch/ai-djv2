"""SQLAlchemy models for AI-DJ Backend v2.

All models are imported here for easy access and Alembic auto-detection.
"""
# Import all models so they're registered with Base.metadata
from backend_v2.models.user import User, RefreshToken
from backend_v2.models.user_profile import UserProfile
from backend_v2.models.context import UserContext
from backend_v2.models.mood import Mood, MoodProfile
from backend_v2.models.feedback import FeedbackEvent
from backend_v2.models.settings import AgentSettings, PromptTemplate
from backend_v2.models.status_event_log import StatusEventLog
from backend_v2.models.existing import (
    Song,
    SongFeatures,
    LyricsAnalysis,
    Session,
    PlayHistory,
    Segment,
    LLMTrace,
)

__all__ = [
    # User & Auth
    "User",
    "RefreshToken",
    "UserProfile",
    # User Resources
    "UserContext",
    "Mood",
    "MoodProfile",
    "FeedbackEvent",
    "AgentSettings",
    "PromptTemplate",
    "StatusEventLog",
    # Existing Tables
    "Song",
    "SongFeatures",
    "LyricsAnalysis",
    "Session",
    "PlayHistory",
    "Segment",
    "LLMTrace",
]

