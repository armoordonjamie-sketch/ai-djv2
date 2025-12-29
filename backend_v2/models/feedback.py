"""Feedback event model.

Stores user feedback (like/dislike) on songs for training mood profiles.
"""
import uuid
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import String, Text, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend_v2.db.base import Base

if TYPE_CHECKING:
    from backend_v2.models.user import User
    from backend_v2.models.mood import Mood


class FeedbackEvent(Base):
    """User feedback on songs for preference learning.
    
    Feedback can be:
    - Global (mood_id is null): Applies to all moods
    - Mood-specific (mood_id set): Only affects that mood's profile
    
    If song_uuid is set, we link to the songs table for feature lookup.
    If song_uuid is null, we use track_title/track_artist as fallback.
    
    Evidence: Implementing feedback_events table per implementation_plan.md Phase 1
    """
    __tablename__ = "feedback_events"
    
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
    mood_id: Mapped[Optional[str]] = mapped_column(
        String(36), 
        ForeignKey("moods.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    song_uuid: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("songs.uuid", ondelete="SET NULL"),
        nullable=True
    )
    track_title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    track_artist: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    value: Mapped[str] = mapped_column(String(20), nullable=False)  # "like" or "dislike"
    reason_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, 
        default=datetime.utcnow, 
        nullable=False
    )
    
    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="feedback_events")
    mood: Mapped[Optional["Mood"]] = relationship("Mood", back_populates="feedback_events")
    
    def __repr__(self) -> str:
        return f"<FeedbackEvent(id={self.id}, user_id={self.user_id}, value={self.value})>"


# Indexes for efficient queries
Index("ix_feedback_events_user_created", FeedbackEvent.user_id, FeedbackEvent.created_at.desc())
Index("ix_feedback_events_mood_created", FeedbackEvent.mood_id, FeedbackEvent.created_at.desc())
