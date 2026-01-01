"""Training effectiveness metrics model."""
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Float, Integer, DateTime, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from backend_v2.db.base import Base
from backend_v2.utils.time import utc_now


class TrainingMetrics(Base):
    """Track training effectiveness over time."""
    __tablename__ = "training_metrics"
    
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    mood_id: Mapped[str] = mapped_column(String(36), ForeignKey("moods.id", ondelete="CASCADE"))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"))
    
    # Training metadata
    agent_name: Mapped[str] = mapped_column(String(50))  # train_from_like, etc.
    feedback_type: Mapped[str] = mapped_column(String(20))  # like, dislike, skip, batch
    track_artist: Mapped[Optional[str]] = mapped_column(String(255))
    track_title: Mapped[Optional[str]] = mapped_column(String(255))
    
    # Before/after state
    artists_before: Mapped[Optional[str]] = mapped_column(Text)  # JSON list
    artists_after: Mapped[Optional[str]] = mapped_column(Text)  # JSON list
    artists_added: Mapped[int] = mapped_column(Integer, default=0)
    artists_removed: Mapped[int] = mapped_column(Integer, default=0)
    artists_demoted: Mapped[int] = mapped_column(Integer, default=0)
    
    # LLM decisions
    llm_reasoning: Mapped[Optional[str]] = mapped_column(Text)
    tool_calls_made: Mapped[int] = mapped_column(Integer, default=0)
    llm_tokens: Mapped[int] = mapped_column(Integer, default=0)
    
    # Effectiveness tracking
    subsequent_likes: Mapped[int] = mapped_column(Integer, default=0)  # Likes after this training
    subsequent_dislikes: Mapped[int] = mapped_column(Integer, default=0)  # Dislikes after
    effectiveness_score: Mapped[Optional[float]] = mapped_column(Float)  # Calculated later
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    
    def __repr__(self) -> str:
        return f"<TrainingMetrics(id={self.id}, agent={self.agent_name}, feedback_type={self.feedback_type})>"

