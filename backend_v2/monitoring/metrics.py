"""Observability metrics for mood generation and track acquisition."""
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger("ai-dj.metrics")


class MetricsCollector:
    """Simple in-memory metrics collector.
    
    In production, consider using Prometheus, StatsD, or similar.
    """
    
    def __init__(self):
        # Acquisition metrics
        self.acquisition_attempts: Dict[str, int] = defaultdict(int)  # provider -> count
        self.acquisition_successes: Dict[str, int] = defaultdict(int)  # provider -> count
        self.acquisition_failures: Dict[str, int] = defaultdict(int)  # provider -> count
        self.acquisition_times: Dict[str, List[float]] = defaultdict(list)  # provider -> [duration_sec]
        
        # Mood distinctness metrics
        self.mood_distinctness_scores: List[float] = []
        
        # Fallback metrics
        self.fallback_count = 0
        self.catalog_selection_count = 0
        self.local_library_fallback_count = 0
    
    def record_acquisition_attempt(self, provider: str):
        """Record an acquisition attempt."""
        self.acquisition_attempts[provider] += 1
    
    def record_acquisition_success(self, provider: str, duration_sec: float):
        """Record successful acquisition."""
        self.acquisition_successes[provider] += 1
        self.acquisition_times[provider].append(duration_sec)
    
    def record_acquisition_failure(self, provider: str):
        """Record failed acquisition."""
        self.acquisition_failures[provider] += 1
    
    def record_mood_distinctness(self, score: float):
        """Record mood distinctness score (average pairwise distance)."""
        self.mood_distinctness_scores.append(score)
    
    def record_fallback(self):
        """Record a fallback event (acquisition failed, selecting alternative)."""
        self.fallback_count += 1
    
    def record_catalog_selection(self):
        """Record selection from global catalog."""
        self.catalog_selection_count += 1
    
    def record_local_library_fallback(self):
        """Record fallback to local library."""
        self.local_library_fallback_count += 1
    
    def get_acquisition_success_rate(self, provider: Optional[str] = None) -> float:
        """Get acquisition success rate.
        
        Args:
            provider: Specific provider or None for overall
            
        Returns:
            Success rate (0.0-1.0)
        """
        if provider:
            attempts = self.acquisition_attempts[provider]
            successes = self.acquisition_successes[provider]
        else:
            attempts = sum(self.acquisition_attempts.values())
            successes = sum(self.acquisition_successes.values())
        
        if attempts == 0:
            return 0.0
        
        return successes / attempts
    
    def get_average_acquisition_time(self, provider: Optional[str] = None) -> float:
        """Get average acquisition time in seconds.
        
        Args:
            provider: Specific provider or None for overall
            
        Returns:
            Average time in seconds
        """
        if provider:
            times = self.acquisition_times[provider]
        else:
            times = []
            for provider_times in self.acquisition_times.values():
                times.extend(provider_times)
        
        if not times:
            return 0.0
        
        return sum(times) / len(times)
    
    def get_mood_distinctness(self) -> float:
        """Get average mood distinctness score.
        
        Returns:
            Average distinctness (higher = more diverse moods)
        """
        if not self.mood_distinctness_scores:
            return 0.0
        
        return sum(self.mood_distinctness_scores) / len(self.mood_distinctness_scores)
    
    def get_summary(self) -> Dict:
        """Get metrics summary.
        
        Returns:
            Dict with all metrics
        """
        return {
            "acquisition": {
                "overall_success_rate": self.get_acquisition_success_rate(),
                "average_time_sec": self.get_average_acquisition_time(),
                "by_provider": {
                    provider: {
                        "attempts": self.acquisition_attempts[provider],
                        "successes": self.acquisition_successes[provider],
                        "failures": self.acquisition_failures[provider],
                        "success_rate": self.get_acquisition_success_rate(provider),
                        "avg_time_sec": self.get_average_acquisition_time(provider),
                    }
                    for provider in self.acquisition_attempts.keys()
                },
            },
            "mood_distinctness": {
                "average_score": self.get_mood_distinctness(),
                "sample_count": len(self.mood_distinctness_scores),
            },
            "fallbacks": {
                "total": self.fallback_count,
                "catalog_selections": self.catalog_selection_count,
                "local_library_fallbacks": self.local_library_fallback_count,
            },
        }
    
    def log_summary(self):
        """Log metrics summary."""
        summary = self.get_summary()
        logger.info("=== Metrics Summary ===")
        logger.info(f"Acquisition success rate: {summary['acquisition']['overall_success_rate']:.1%}")
        logger.info(f"Average acquisition time: {summary['acquisition']['average_time_sec']:.1f}s")
        logger.info(f"Mood distinctness: {summary['mood_distinctness']['average_score']:.3f}")
        logger.info(f"Fallback events: {summary['fallbacks']['total']}")
        logger.info(f"Catalog selections: {summary['fallbacks']['catalog_selections']}")


# Global metrics collector
_metrics: Optional[MetricsCollector] = None


def get_metrics() -> MetricsCollector:
    """Get global metrics collector."""
    global _metrics
    if _metrics is None:
        _metrics = MetricsCollector()
    return _metrics
