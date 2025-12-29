"""StatusEventLog model for persisting key status events.

Stores error events and major state transitions for observability and debugging.
Only key events are persisted (not all real-time updates).
"""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, DateTime, Float, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column

from backend_v2.db.base import Base
from backend_v2.utils.time import utc_now


class StatusEventLog(Base):
    """Persisted status event for observability.
    
    This table stores:
    - Error events (for debugging and alerting)
    - Major state transitions (session start/stop, onboarding complete)
    - Events correlated with LLM traces (via correlation_id)
    
    Not all real-time StatusEvents are persisted - only key ones.
    """
    __tablename__ = "status_event_logs"
    
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
    session_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        nullable=True,
        index=True
    )
    correlation_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        nullable=True,
        index=True  # For joining with LLM trace logs
    )
    
    # Event classification
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    step: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="info")
    
    # Messages
    user_message: Mapped[str] = mapped_column(Text, nullable=False)
    debug_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Progress (if applicable)
    progress: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Structured payload as JSON string
    payload_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False
    )
    
    def __repr__(self) -> str:
        return f"<StatusEventLog(id={self.id}, category={self.category}, step={self.step}, severity={self.severity})>"


# Indexes for efficient queries
Index("ix_status_event_logs_user_created", StatusEventLog.user_id, StatusEventLog.created_at.desc())
Index("ix_status_event_logs_category_severity", StatusEventLog.category, StatusEventLog.severity)
Index("ix_status_event_logs_correlation", StatusEventLog.correlation_id)
