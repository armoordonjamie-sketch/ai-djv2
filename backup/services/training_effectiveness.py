"""Calculate and track training effectiveness metrics."""
import logging
from typing import Dict, Any, List
from datetime import timedelta
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend_v2.models.training_metrics import TrainingMetrics
from backend_v2.models.feedback import FeedbackEvent
from backend_v2.utils.time import utc_now

logger = logging.getLogger("ai-dj.effectiveness")


async def calculate_effectiveness(
    db: AsyncSession,
    training_metric_id: str,
) -> float:
    """Calculate effectiveness score for a training event.
    
    Score is based on subsequent feedback:
    - Subsequent likes for this artist: +1 per like
    - Subsequent dislikes for this artist: -1 per dislike
    - No feedback: 0 (neutral)
    
    Normalized to 0-1 range where:
    - 1.0 = Perfect (only likes after training)
    - 0.5 = Neutral (no feedback or mixed)
    - 0.0 = Bad (only dislikes after training)
    
    Returns:
        Effectiveness score (0-1)
    """
    # Get training metric
    result = await db.execute(
        select(TrainingMetrics).where(TrainingMetrics.id == training_metric_id)
    )
    metric = result.scalar_one_or_none()
    if not metric:
        return 0.5
    
    # Get subsequent feedback for this artist (7 days after training)
    cutoff = metric.created_at + timedelta(days=7)
    
    feedback_result = await db.execute(
        select(FeedbackEvent).where(
            and_(
                FeedbackEvent.user_id == metric.user_id,
                FeedbackEvent.mood_id == metric.mood_id,
                FeedbackEvent.track_artist == metric.track_artist,
                FeedbackEvent.created_at > metric.created_at,
                FeedbackEvent.created_at <= cutoff,
            )
        )
    )
    subsequent_feedback = list(feedback_result.scalars().all())
    
    if not subsequent_feedback:
        return 0.5  # No subsequent feedback = neutral
    
    likes = sum(1 for f in subsequent_feedback if f.value == "like")
    dislikes = sum(1 for f in subsequent_feedback if f.value == "dislike")
    
    # Update metric
    metric.subsequent_likes = likes
    metric.subsequent_dislikes = dislikes
    
    # Calculate score
    total = likes + dislikes
    if total == 0:
        score = 0.5
    else:
        # Score = (likes - dislikes + total) / (2 * total)
        # This normalizes to 0-1 where:
        # - All likes = 1.0
        # - Equal = 0.5
        # - All dislikes = 0.0
        score = (likes - dislikes + total) / (2 * total)
    
    metric.effectiveness_score = score
    await db.commit()
    
    return score


async def get_effectiveness_report(
    db: AsyncSession,
    user_id: str,
    days: int = 30,
) -> Dict[str, Any]:
    """Generate effectiveness report for user's training."""
    cutoff = utc_now() - timedelta(days=days)
    
    # Get all training metrics
    result = await db.execute(
        select(TrainingMetrics).where(
            and_(
                TrainingMetrics.user_id == user_id,
                TrainingMetrics.created_at >= cutoff,
            )
        )
    )
    metrics = list(result.scalars().all())
    
    if not metrics:
        return {
            "total_training_events": 0,
            "average_effectiveness": 0.5,
            "by_agent": {},
            "by_feedback_type": {},
        }
    
    # Calculate effectiveness for each (if not already calculated)
    for metric in metrics:
        if metric.effectiveness_score is None:
            await calculate_effectiveness(db, metric.id)
    
    # Aggregate statistics
    total = len(metrics)
    avg_effectiveness = sum(m.effectiveness_score or 0.5 for m in metrics) / total
    
    # By agent
    by_agent = {}
    for metric in metrics:
        agent = metric.agent_name
        if agent not in by_agent:
            by_agent[agent] = {"count": 0, "avg_score": 0, "scores": []}
        by_agent[agent]["count"] += 1
        by_agent[agent]["scores"].append(metric.effectiveness_score or 0.5)
    
    for agent in by_agent:
        scores = by_agent[agent]["scores"]
        by_agent[agent]["avg_score"] = sum(scores) / len(scores)
        del by_agent[agent]["scores"]
    
    # By feedback type
    by_feedback = {}
    for metric in metrics:
        ftype = metric.feedback_type
        if ftype not in by_feedback:
            by_feedback[ftype] = {"count": 0, "avg_score": 0, "scores": []}
        by_feedback[ftype]["count"] += 1
        by_feedback[ftype]["scores"].append(metric.effectiveness_score or 0.5)
    
    for ftype in by_feedback:
        scores = by_feedback[ftype]["scores"]
        by_feedback[ftype]["avg_score"] = sum(scores) / len(scores)
        del by_feedback[ftype]["scores"]
    
    return {
        "total_training_events": total,
        "average_effectiveness": avg_effectiveness,
        "by_agent": by_agent,
        "by_feedback_type": by_feedback,
        "days_analyzed": days,
    }

