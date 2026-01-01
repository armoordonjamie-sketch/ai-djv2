"""
Shared types and dataclasses for LangGraph v3 orchestration.

These types are used across all graphs and nodes.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from enum import Enum


class AcquisitionStatus(str, Enum):
    """Status of track acquisition."""
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    ACQUIRED = "ACQUIRED"
    FAILED = "FAILED"
    FALLBACK = "FALLBACK"


class TransitionType(str, Enum):
    """Types of transitions between tracks."""
    CROSSFADE = "crossfade"
    EQ_BLEND = "eq_blend"
    ECHO_OUT = "echo_out"
    HARD_CUT = "hard_cut"
    BEATMATCH = "beatmatch"


class FeedbackType(str, Enum):
    """Types of user feedback."""
    LIKE = "like"
    DISLIKE = "dislike"
    SKIP = "skip"


@dataclass
class TrackInfo:
    """Information about a track."""
    uuid: str
    title: str
    artist: str
    duration_sec: float = 0.0
    local_path: Optional[str] = None
    artwork_url: Optional[str] = None
    genres: List[str] = field(default_factory=list)
    bpm: Optional[float] = None
    energy: Optional[float] = None
    valence: Optional[float] = None
    danceability: Optional[float] = None
    isrc: Optional[str] = None
    spotify_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "uuid": self.uuid,
            "title": self.title,
            "artist": self.artist,
            "duration_sec": self.duration_sec,
            "local_path": self.local_path,
            "artwork_url": self.artwork_url,
            "genres": self.genres,
            "bpm": self.bpm,
            "energy": self.energy,
            "valence": self.valence,
            "danceability": self.danceability,
            "isrc": self.isrc,
            "spotify_id": self.spotify_id,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TrackInfo":
        """Create from dictionary."""
        return cls(
            uuid=data.get("uuid", data.get("song_uuid", "")),
            title=data.get("title", ""),
            artist=data.get("artist", ""),
            duration_sec=data.get("duration_sec", data.get("duration", 0.0)),
            local_path=data.get("local_path"),
            artwork_url=data.get("artwork_url"),
            genres=data.get("genres", []),
            bpm=data.get("bpm", data.get("tempo")),
            energy=data.get("energy"),
            valence=data.get("valence"),
            danceability=data.get("danceability"),
            isrc=data.get("isrc"),
            spotify_id=data.get("spotify_id"),
        )


@dataclass
class TransitionPlan:
    """Plan for transitioning between tracks."""
    transition_type: TransitionType = TransitionType.CROSSFADE
    start_position_a_seconds: float = 0.0
    start_position_b_seconds: float = 5.0
    transition_duration_seconds: float = 8.0
    mix_length_bars: int = 16
    rationale: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "transition_type": self.transition_type.value if isinstance(self.transition_type, TransitionType) else self.transition_type,
            "start_position_a_seconds": self.start_position_a_seconds,
            "start_position_b_seconds": self.start_position_b_seconds,
            "transition_duration_seconds": self.transition_duration_seconds,
            "mix_length_bars": self.mix_length_bars,
            "rationale": self.rationale,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TransitionPlan":
        """Create from dictionary."""
        transition_type = data.get("transition_type", "crossfade")
        if isinstance(transition_type, str):
            try:
                transition_type = TransitionType(transition_type)
            except ValueError:
                transition_type = TransitionType.CROSSFADE
        
        return cls(
            transition_type=transition_type,
            start_position_a_seconds=data.get("start_position_a_seconds", 0.0),
            start_position_b_seconds=data.get("start_position_b_seconds", 5.0),
            transition_duration_seconds=data.get("transition_duration_seconds", 8.0),
            mix_length_bars=data.get("mix_length_bars", 16),
            rationale=data.get("rationale", ""),
        )


@dataclass
class SegmentMeta:
    """
    Metadata for a produced audio segment.
    
    This matches the contract expected by UserRadioPipeline.segment_queue.
    """
    path: str
    song_uuid: str
    title: str
    artist: str
    duration: float
    start_offset_sec: float = 0.0
    transition_type: str = "crossfade"
    tts_path: Optional[str] = None
    artwork_url: Optional[str] = None
    song2_uuid: Optional[str] = None
    song2_title: Optional[str] = None
    song2_artist: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary matching pipeline contract."""
        result = {
            "path": self.path,
            "song_uuid": self.song_uuid,
            "title": self.title,
            "artist": self.artist,
            "duration": self.duration,
            "start_offset_sec": self.start_offset_sec,
            "transition_type": self.transition_type,
        }
        if self.tts_path:
            result["tts_path"] = self.tts_path
        if self.artwork_url:
            result["artwork_url"] = self.artwork_url
        if self.song2_uuid:
            result["song2_uuid"] = self.song2_uuid
            result["song2_title"] = self.song2_title
            result["song2_artist"] = self.song2_artist
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SegmentMeta":
        """Create from dictionary."""
        return cls(
            path=data["path"],
            song_uuid=data.get("song_uuid", ""),
            title=data.get("title", ""),
            artist=data.get("artist", ""),
            duration=data.get("duration", 0.0),
            start_offset_sec=data.get("start_offset_sec", 0.0),
            transition_type=data.get("transition_type", "crossfade"),
            tts_path=data.get("tts_path"),
            artwork_url=data.get("artwork_url"),
            song2_uuid=data.get("song2_uuid"),
            song2_title=data.get("song2_title"),
            song2_artist=data.get("song2_artist"),
        )


@dataclass
class MoodTargets:
    """Target values for mood-based selection."""
    mood_id: str
    mood_name: str
    energy_target: float = 0.5
    valence_target: float = 0.5
    danceability_target: float = 0.5
    genres: List[str] = field(default_factory=list)
    example_artists: List[str] = field(default_factory=list)
    avoid_genres: List[str] = field(default_factory=list)
    vibe_keywords: List[str] = field(default_factory=list)
    dj_personality: str = "casual_funny"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "mood_id": self.mood_id,
            "mood_name": self.mood_name,
            "energy_target": self.energy_target,
            "valence_target": self.valence_target,
            "danceability_target": self.danceability_target,
            "genres": self.genres,
            "example_artists": self.example_artists,
            "avoid_genres": self.avoid_genres,
            "vibe_keywords": self.vibe_keywords,
            "dj_personality": self.dj_personality,
        }


@dataclass
class RetrievedDoc:
    """A document retrieved from the vector index."""
    track_uuid: str
    title: str
    artist: str
    score: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "track_uuid": self.track_uuid,
            "title": self.title,
            "artist": self.artist,
            "score": self.score,
            "metadata": self.metadata,
        }


@dataclass
class FeedbackSignal:
    """A feedback signal for training."""
    feedback_type: FeedbackType
    track_uuid: str
    track_artist: str
    track_title: str
    reason: Optional[str] = None
    timestamp: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "feedback_type": self.feedback_type.value if isinstance(self.feedback_type, FeedbackType) else self.feedback_type,
            "track_uuid": self.track_uuid,
            "track_artist": self.track_artist,
            "track_title": self.track_title,
            "reason": self.reason,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }


@dataclass
class TrainingDecision:
    """Decision made by the training agent."""
    artists_to_add: List[str] = field(default_factory=list)
    artists_to_remove: List[str] = field(default_factory=list)
    genres_to_boost: List[str] = field(default_factory=list)
    genres_to_demote: List[str] = field(default_factory=list)
    feature_adjustments: Dict[str, float] = field(default_factory=dict)
    rationale: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "artists_to_add": self.artists_to_add,
            "artists_to_remove": self.artists_to_remove,
            "genres_to_boost": self.genres_to_boost,
            "genres_to_demote": self.genres_to_demote,
            "feature_adjustments": self.feature_adjustments,
            "rationale": self.rationale,
        }


@dataclass
class DebugEvent:
    """A debug event for observability."""
    timestamp: datetime
    node: str
    event_type: str
    message: str
    data: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "node": self.node,
            "event_type": self.event_type,
            "message": self.message,
            "data": self.data,
        }
