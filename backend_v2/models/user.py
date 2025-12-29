"""User and authentication models.

Tables:
- users: Core user accounts
- refresh_tokens: Refresh token storage for token rotation
"""
import uuid
from datetime import datetime
from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import String, Boolean, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend_v2.db.base import Base
from backend_v2.utils.time import utc_now, ensure_utc

if TYPE_CHECKING:
    from backend_v2.models.context import UserContext
    from backend_v2.models.mood import Mood
    from backend_v2.models.feedback import FeedbackEvent
    from backend_v2.models.settings import AgentSettings, PromptTemplate
    from backend_v2.models.user_profile import UserProfile


class User(Base):
    """User account model.
    
    Evidence: Implementing users table per implementation_plan.md Phase 1
    """
    __tablename__ = "users"
    
    id: Mapped[str] = mapped_column(
        String(36), 
        primary_key=True, 
        default=lambda: str(uuid.uuid4())
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
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
    onboarded_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )
    
    # Relationships
    refresh_tokens: Mapped[List["RefreshToken"]] = relationship(
        "RefreshToken", 
        back_populates="user",
        cascade="all, delete-orphan"
    )
    contexts: Mapped[List["UserContext"]] = relationship(
        "UserContext",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    moods: Mapped[List["Mood"]] = relationship(
        "Mood",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    feedback_events: Mapped[List["FeedbackEvent"]] = relationship(
        "FeedbackEvent",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    agent_settings: Mapped[List["AgentSettings"]] = relationship(
        "AgentSettings",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    prompt_templates: Mapped[List["PromptTemplate"]] = relationship(
        "PromptTemplate",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    profile: Mapped[Optional["UserProfile"]] = relationship(
        "UserProfile",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan"
    )
    
    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email})>"


class RefreshToken(Base):
    """Refresh token storage for secure token rotation.
    
    Only the hash of the token is stored, not the raw token.
    This prevents token theft even if the database is compromised.
    
    Evidence: Implementing refresh_tokens table per implementation_plan.md Phase 1
    """
    __tablename__ = "refresh_tokens"
    
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
    token_hash: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False
    )
    
    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="refresh_tokens")
    
    @property
    def is_valid(self) -> bool:
        """Check if token is valid (not expired, not revoked)."""
        if self.revoked_at is not None:
            return False
        expires_at = ensure_utc(self.expires_at)
        return expires_at is not None and utc_now() < expires_at
    
    def __repr__(self) -> str:
        return f"<RefreshToken(id={self.id}, user_id={self.user_id}, valid={self.is_valid})>"


# Index for cleanup queries
Index("ix_refresh_tokens_expires_at", RefreshToken.expires_at)
