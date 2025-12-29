"""TrackIntent and AcquisitionJob models for decoupled track selection.

TrackIntent represents "what we want to play" independent of availability.
AcquisitionJob tracks the async work to obtain the audio file.

This decoupling enables:
- Selection from global catalog (not limited by local cache)
- Async acquisition with fallbacks
- Robust error handling and retry logic
"""
import uuid
from datetime import datetime
from enum import Enum
from typing import Optional, TYPE_CHECKING

from sqlalchemy import String, Text, Float, Integer, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend_v2.db.base import Base
from backend_v2.utils.time import utc_now

if TYPE_CHECKING:
    from backend_v2.models.user import User
    from backend_v2.models.mood import Mood
    from backend_v2.models.existing import Song


class TrackIntentStatus(str, Enum):
    """Status of a track intent."""
    PENDING = "PENDING"
    # Legacy alias for backwards compatibility with tests and older code.
    PENDING_ACQUISITION = "PENDING"
    ACQUIRED = "ACQUIRED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class AcquisitionJobStatus(str, Enum):
    """Status of an acquisition job."""
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class TrackIntent(Base):
    """Represents a track that we want to play (selection result).
    
    Status lifecycle:
    - PENDING: Just created, needs acquisition
    - ACQUIRED: Audio file obtained, ready to play
    - FAILED: Acquisition failed after all retries
    - CANCELLED: No longer needed (user skipped, session ended, etc.)
    """
    __tablename__ = "track_intents"
    
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )
    
    # Context
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    mood_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("moods.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    session_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True
    )
    
    # Track identity (what we want to play)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    artist: Mapped[str] = mapped_column(String(255), nullable=False)
    album: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # External catalog IDs (if discovered via providers)
    spotify_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    apple_music_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    isrc: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True)
    
    # Target audio features (from catalog or AI estimate)
    # These help validate that acquired track matches intent
    target_energy: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    target_valence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    target_tempo: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    target_danceability: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Status and resolution
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=TrackIntentStatus.PENDING.value,
        index=True
    )  # PENDING | ACQUIRED | FAILED | CANCELLED
    
    acquired_song_uuid: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("songs.uuid", ondelete="SET NULL"),
        nullable=True
    )
    
    # Metadata
    selection_rationale: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    selection_method: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # "catalog", "ai_suggestion", etc.
    failure_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    acquisition_jobs: Mapped[list["AcquisitionJob"]] = relationship(
        "AcquisitionJob",
        back_populates="intent",
        cascade="all, delete-orphan"
    )
    
    def __repr__(self) -> str:
        return f"<TrackIntent(id={self.id}, artist={self.artist}, title={self.title}, status={self.status})>"


class AcquisitionJob(Base):
    """Background job to acquire audio file for a TrackIntent.
    
    Multiple jobs may be created for a single intent (retries, fallback providers).
    
    Status lifecycle:
    - QUEUED: Job created, waiting to run
    - RUNNING: Currently attempting acquisition
    - SUCCESS: Audio file obtained
    - FAILED: Attempt failed (may retry or try alternative provider)
    """
    __tablename__ = "acquisition_jobs"
    
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )
    
    track_intent_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("track_intents.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Acquisition details
    provider: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True
    )  # "local_cache", "youtube", "spotify", "alternative", etc.
    
    source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    query: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Search query used
    
    # Progress tracking
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    
    # Results
    acquired_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Status
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=AcquisitionJobStatus.QUEUED.value,
        index=True
    )  # QUEUED | RUNNING | SUCCESS | FAILED
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    intent: Mapped["TrackIntent"] = relationship("TrackIntent", back_populates="acquisition_jobs")
    
    def __repr__(self) -> str:
        return f"<AcquisitionJob(id={self.id}, provider={self.provider}, status={self.status})>"


# Indexes for common queries
Index("ix_track_intents_user_status", TrackIntent.user_id, TrackIntent.status)
Index("ix_track_intents_session_status", TrackIntent.session_id, TrackIntent.status)
Index("ix_acquisition_jobs_status_created", AcquisitionJob.status, AcquisitionJob.created_at)

