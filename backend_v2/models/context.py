"""User context model.

Contexts allow users to define personalized preferences for the DJ.
"""
import uuid
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import String, Text, DateTime, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend_v2.db.base import Base

if TYPE_CHECKING:
    from backend_v2.models.user import User


class UserContext(Base):
    """User context for personalization.
    
    Each user can have multiple named contexts (e.g., "default", "workout", "chill").
    The raw_text is the user-provided text, and parsed_json is the structured version.
    
    Evidence: Implementing user_contexts table per implementation_plan.md Phase 1
    """
    __tablename__ = "user_contexts"
    
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
    raw_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    parsed_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON stored as text
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, 
        default=datetime.utcnow, 
        onupdate=datetime.utcnow,
        nullable=False
    )
    
    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="contexts")
    
    # Unique constraint: one context name per user
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_user_contexts_user_id_name"),
    )
    
    def __repr__(self) -> str:
        return f"<UserContext(id={self.id}, user_id={self.user_id}, name={self.name})>"
