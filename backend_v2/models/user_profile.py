"""User profile model for onboarding data.

Stores structured profile data collected during voice onboarding.
1:1 relationship with users table.
"""
import uuid
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import String, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend_v2.db.base import Base

if TYPE_CHECKING:
    from backend_v2.models.user import User


# Enum values as constants for validation
EXPLICIT_LYRICS_VALUES = ("ok", "avoid", "depends")
DJ_PERSONALITY_VALUES = (
    "casual_funny",
    "minimal_talk",
    "hype_energetic",
    "light_roast",
    "more_talk_between_songs",
)


class UserProfile(Base):
    """User profile with structured onboarding data.
    
    All fields except user_id are optional to support incremental onboarding
    and backwards compatibility with legacy payloads.
    """
    __tablename__ = "user_profiles"
    
    # Primary key is user_id (1:1 with users)
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    
    # Basic info
    display_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    age_range: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    occupation: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Music preferences (JSON arrays stored as text)
    favorite_genres: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array
    favorite_artists: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array
    favorite_songs: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array
    no_go: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array
    
    # Preferences
    explicit_lyrics: Mapped[Optional[str]] = mapped_column(
        String(20), 
        nullable=True,
        default="ok"
    )  # "ok" | "avoid" | "depends"
    
    dj_personality: Mapped[Optional[str]] = mapped_column(
        String(30),
        nullable=True,
        default="casual_funny"
    )  # enum values from DJ_PERSONALITY_VALUES
    
    # Natural language summary
    raw_context: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )
    
    # Relationship
    user: Mapped["User"] = relationship("User", back_populates="profile")
    
    def __repr__(self) -> str:
        return f"<UserProfile(user_id={self.user_id}, display_name={self.display_name})>"
