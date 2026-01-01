"""Spotify user context models for storing OAuth tokens and enriched listening data."""
import uuid
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import String, Text, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend_v2.db.base import Base
from backend_v2.utils.time import utc_now

if TYPE_CHECKING:
    from backend_v2.models.user import User


class SpotifyUserContext(Base):
    """Spotify user context model.
    
    Stores OAuth tokens and comprehensive Spotify listening data including:
    - Raw data: top tracks/artists, playlists, recently played
    - AI-enriched analysis: preferences, habits, mood analysis
    - Track statistics for DJ speech hooks
    """
    __tablename__ = "spotify_user_context"
    
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True
    )
    spotify_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    
    # Raw Spotify data (JSON)
    top_artists_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    top_tracks_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    recently_played_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    playlists_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # AI-enriched analysis (JSON)
    music_preferences_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    listening_habits_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    genres_analysis_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    mood_analysis_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Track statistics for DJ speech hooks (JSON)
    # Format: [{title, artist, rank, time_range, isrc}, ...]
    favorite_tracks_with_stats_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # OAuth tokens
    access_token: Mapped[str] = mapped_column(String(512), nullable=False)
    refresh_token: Mapped[str] = mapped_column(String(512), nullable=False)
    token_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False
    )
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    
    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="spotify_context")
    
    def __repr__(self) -> str:
        return f"<SpotifyUserContext(id={self.id}, user_id={self.user_id}, spotify_id={self.spotify_id})>"


class DJSpeechHistory(Base):
    """DJ speech history model for tracking continuity and avoiding repetition.
    
    Stores:
    - Recent DJ speeches for context
    - Mentioned artists/tracks to avoid repetition
    - Session-based tracking
    """
    __tablename__ = "dj_speech_history"
    
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    session_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    
    # Speech content
    speech_text: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Mentioned entities (JSON arrays)
    mentioned_artists: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    mentioned_tracks: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
        index=True
    )
    
    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="dj_speech_history")
    
    def __repr__(self) -> str:
        return f"<DJSpeechHistory(id={self.id}, user_id={self.user_id}, session_id={self.session_id})>"


# Indexes for efficient queries
# Note: Single column indexes are already created via index=True on the column definitions
# Only composite indexes need to be defined here
Index("ix_dj_speech_history_user_session", DJSpeechHistory.user_id, DJSpeechHistory.session_id)

