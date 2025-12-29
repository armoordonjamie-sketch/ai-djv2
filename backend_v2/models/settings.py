"""Agent settings and prompt template models.

Allows users to customize AI agent behavior and prompts.
"""
import uuid
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import String, Text, Boolean, Integer, DateTime, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend_v2.db.base import Base
from backend_v2.utils.time import utc_now

if TYPE_CHECKING:
    from backend_v2.models.user import User
    from backend_v2.models.mood import Mood


class AgentSettings(Base):
    """Per-user settings for AI agents.
    
    Allows customization of:
    - Thinking budgets
    - Temperature settings
    - Model preferences
    - Feature toggles
    
    Evidence: Implementing agent_settings table per implementation_plan.md Phase 1
    """
    __tablename__ = "agent_settings"
    
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
    agent_name: Mapped[str] = mapped_column(
        String(50), 
        nullable=False
    )  # e.g., "track_selector", "speech_writer", "transition_planner"
    settings_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON object
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False
    )
    
    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="agent_settings")
    
    # Unique constraint: one setting per agent per user
    __table_args__ = (
        UniqueConstraint("user_id", "agent_name", name="uq_agent_settings_user_agent"),
    )
    
    def __repr__(self) -> str:
        return f"<AgentSettings(id={self.id}, user_id={self.user_id}, agent={self.agent_name})>"


class PromptTemplate(Base):
    """User-customizable prompt templates.
    
    Templates can be:
    - Global scope: Used across all moods
    - Mood scope: Used only for specific mood
    
    Versioning allows rollback and A/B testing.
    
    Evidence: Implementing prompt_templates table per implementation_plan.md Phase 1
    """
    __tablename__ = "prompt_templates"
    
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
    name: Mapped[str] = mapped_column(String(100), nullable=False)  # e.g., "dj_personality_system"
    scope: Mapped[str] = mapped_column(String(20), default="global", nullable=False)  # "global" or "mood"
    mood_id: Mapped[Optional[str]] = mapped_column(
        String(36), 
        ForeignKey("moods.id", ondelete="SET NULL"),
        nullable=True
    )
    role: Mapped[str] = mapped_column(String(20), default="system", nullable=False)  # "system" or "user"
    template_text: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False
    )
    
    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="prompt_templates")
    
    def __repr__(self) -> str:
        return f"<PromptTemplate(id={self.id}, name={self.name}, v{self.version}, active={self.is_active})>"


# Indexes for efficient template lookups
Index("ix_prompt_templates_user_name_active", PromptTemplate.user_id, PromptTemplate.name, PromptTemplate.is_active)
