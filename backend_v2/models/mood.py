"""Mood and mood profile models.

Moods define target audio characteristics and DJ personality.
MoodProfiles store derived preferences from feedback training.
"""
import uuid
from datetime import datetime
from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import String, Text, Float, Boolean, Integer, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend_v2.db.base import Base
from backend_v2.utils.time import utc_now

if TYPE_CHECKING:
    from backend_v2.models.user import User
    from backend_v2.models.feedback import FeedbackEvent


class Mood(Base):
    """User-defined mood for DJ sessions.
    
    Moods define:
    - Target audio characteristics (energy, valence)
    - Genre preferences
    - DJ personality (minimal, chill, chatty)
    
    Evidence: Implementing moods table per implementation_plan.md Phase 1
    """
    __tablename__ = "moods"
    
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
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    color: Mapped[Optional[str]] = mapped_column(String(7), nullable=True)  # Hex color like #FF5733
    energy_target: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # 0.0 to 1.0
    valence_target: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # 0.0 to 1.0
    danceability_target: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # 0.0 to 1.0
    tempo_min: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # BPM
    tempo_max: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # BPM
    genres_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array of genres
    genre_seeds_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array for mood-specific genres
    vibe_keywords_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array
    avoid_genres_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array
    example_artists_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array
    intro_personality: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # Intro style hint
    era_hint: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # "2010s", "classic", "modern", etc.
    
    # Intro Pre-generation
    intro_segment_path: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    intro_song_uuid: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    intro_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # Track if pre-gen intro was played

    dj_personality: Mapped[str] = mapped_column(
        String(20), 
        default="chill", 
        nullable=False
    )  # "minimal", "chill", "chatty"
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
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
    
    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="moods")
    profile: Mapped[Optional["MoodProfile"]] = relationship(
        "MoodProfile",
        back_populates="mood",
        uselist=False,
        cascade="all, delete-orphan"
    )
    feedback_events: Mapped[List["FeedbackEvent"]] = relationship(
        "FeedbackEvent",
        back_populates="mood",
        cascade="all, delete-orphan"
    )
    
    def __repr__(self) -> str:
        return f"<Mood(id={self.id}, name={self.name}, user_id={self.user_id})>"


class MoodProfile(Base):
    """Derived mood profile from feedback training.
    
    Contains:
    - summary_text: Compact preference description for prompt injection
    - weights_json: Feature adjustment weights {"energy": +0.1, "valence": -0.05, ...}
    - version: Incrementing version for tracking updates
    
    Evidence: Implementing mood_profiles table per implementation_plan.md Phase 1
    """
    __tablename__ = "mood_profiles"
    
    mood_id: Mapped[str] = mapped_column(
        String(36), 
        ForeignKey("moods.id", ondelete="CASCADE"),
        primary_key=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    summary_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    weights_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON object
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False
    )
    
    # Relationships
    mood: Mapped["Mood"] = relationship("Mood", back_populates="profile")
    
    def __repr__(self) -> str:
        return f"<MoodProfile(mood_id={self.mood_id}, version={self.version})>"


# Index for finding default mood
Index("ix_moods_user_id_is_default", Mood.user_id, Mood.is_default)
