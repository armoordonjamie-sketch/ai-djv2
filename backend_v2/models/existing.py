"""Existing table models ported from backend/db.py.

These models represent the existing database schema with added user_id columns
for multi-user support.

Evidence: Porting from backend/db.py:29-126 with user_id additions
"""
import uuid
from datetime import datetime
from typing import Optional, List

from sqlalchemy import String, Text, Float, Integer, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend_v2.db.base import Base


class Song(Base):
    """Song metadata and cache information.
    
    Evidence: Porting from backend/db.py:29-41
    """
    __tablename__ = "songs"
    
    uuid: Mapped[str] = mapped_column(String(36), primary_key=True)
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    artist: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    release_date: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    language_code: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    explicit: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    local_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    duration_sec: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    filesize_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    play_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_played_at: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    # Batch 4: Canonical IDs and metadata
    isrc: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True)
    recording_mbid: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    release_mbid: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    artist_mbid: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    apple_song_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    artwork_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    genres: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array
    tags: Mapped[Optional[str]] = mapped_column(Text, nullable=True)    # JSON array
    
    # Relationships
    features: Mapped[Optional["SongFeatures"]] = relationship(
        "SongFeatures", 
        back_populates="song",
        uselist=False,
        cascade="all, delete-orphan"
    )
    lyrics_analysis: Mapped[Optional["LyricsAnalysis"]] = relationship(
        "LyricsAnalysis",
        back_populates="song",
        uselist=False,
        cascade="all, delete-orphan"
    )
    
    def __repr__(self) -> str:
        return f"<Song(uuid={self.uuid}, title={self.title}, artist={self.artist})>"



# Index for song queries
Index("ix_songs_play_count", Song.play_count)


class SongFeatures(Base):
    """Audio features for a song.
    
    Evidence: Porting from backend/db.py:43-58
    """
    __tablename__ = "song_features"
    
    song_uuid: Mapped[str] = mapped_column(
        String(36), 
        ForeignKey("songs.uuid", ondelete="CASCADE"),
        primary_key=True
    )
    acousticness: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    danceability: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    energy: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    instrumentalness: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    key: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    mode: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    liveness: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    loudness: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    speechiness: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    tempo: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    time_signature: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    valence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Relationships
    song: Mapped["Song"] = relationship("Song", back_populates="features")
    
    def __repr__(self) -> str:
        return f"<SongFeatures(song_uuid={self.song_uuid}, tempo={self.tempo}, energy={self.energy})>"


class LyricsAnalysis(Base):
    """Lyrics analysis results.
    
    Evidence: Porting from backend/db.py:60-75
    """
    __tablename__ = "lyrics_analysis"
    
    song_uuid: Mapped[str] = mapped_column(
        String(36), 
        ForeignKey("songs.uuid", ondelete="CASCADE"),
        primary_key=True
    )
    themes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    moods: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    brands: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    locations: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    cultural_ref_people: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    cultural_ref_non_people: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    narrative_style: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    emotional_intensity_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    imagery_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    complexity_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    rhyme_scheme_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    repetitiveness_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Relationships
    song: Mapped["Song"] = relationship("Song", back_populates="lyrics_analysis")
    
    def __repr__(self) -> str:
        return f"<LyricsAnalysis(song_uuid={self.song_uuid})>"


class Session(Base):
    """DJ session record.
    
    Evidence: Porting from backend/db.py:77-85 with user_id, mood_id, context_id added
    """
    __tablename__ = "sessions"
    
    session_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    # NEW: User scoping columns
    user_id: Mapped[Optional[str]] = mapped_column(
        String(36), 
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    mood_id: Mapped[Optional[str]] = mapped_column(
        String(36), 
        ForeignKey("moods.id", ondelete="SET NULL"),
        nullable=True
    )
    context_id: Mapped[Optional[str]] = mapped_column(
        String(36), 
        ForeignKey("user_contexts.id", ondelete="SET NULL"),
        nullable=True
    )
    started_at: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    ended_at: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    mode: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # "autonomous" or "guided"
    user_context_snapshot: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    session_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    gag_cooldowns: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    
    # Relationships
    play_history: Mapped[List["PlayHistory"]] = relationship(
        "PlayHistory",
        back_populates="session",
        cascade="all, delete-orphan"
    )
    segments: Mapped[List["Segment"]] = relationship(
        "Segment",
        back_populates="session",
        cascade="all, delete-orphan"
    )
    # Note: No llm_traces relationship since LLMTrace.session_id has no FK constraint
    
    def __repr__(self) -> str:
        return f"<Session(session_id={self.session_id}, user_id={self.user_id})>"


class PlayHistory(Base):
    """Play history record.
    
    Evidence: Porting from backend/db.py:87-98 with user_id, mood_id added
    """
    __tablename__ = "play_history"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[Optional[str]] = mapped_column(
        String(36), 
        ForeignKey("sessions.session_id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )
    # NEW: User scoping columns
    user_id: Mapped[Optional[str]] = mapped_column(
        String(36), 
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    mood_id: Mapped[Optional[str]] = mapped_column(
        String(36), 
        ForeignKey("moods.id", ondelete="SET NULL"),
        nullable=True
    )
    song_uuid: Mapped[Optional[str]] = mapped_column(
        String(36), 
        ForeignKey("songs.uuid", ondelete="SET NULL"),
        nullable=True
    )
    started_at: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    ended_at: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    skipped: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    transition_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    transition_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    
    # Relationships
    session: Mapped[Optional["Session"]] = relationship("Session", back_populates="play_history")
    
    def __repr__(self) -> str:
        return f"<PlayHistory(id={self.id}, song_uuid={self.song_uuid})>"


# Index for play history queries
Index("ix_play_history_user_started", PlayHistory.user_id, PlayHistory.started_at)


class Segment(Base):
    """Rendered audio segment.
    
    Evidence: Porting from backend/db.py:100-114 with user_id, mood_id added
    """
    __tablename__ = "segments"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[Optional[str]] = mapped_column(
        String(36), 
        ForeignKey("sessions.session_id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )
    # NEW: User scoping columns
    user_id: Mapped[Optional[str]] = mapped_column(
        String(36), 
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    mood_id: Mapped[Optional[str]] = mapped_column(
        String(36), 
        ForeignKey("moods.id", ondelete="SET NULL"),
        nullable=True
    )
    segment_index: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    song_uuid: Mapped[Optional[str]] = mapped_column(
        String(36), 
        ForeignKey("songs.uuid", ondelete="SET NULL"),
        nullable=True
    )
    file_path_transport: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    file_path_archive: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    duration_sec: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    transition_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    tts_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    banter_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    # Relationships
    session: Mapped[Optional["Session"]] = relationship("Session", back_populates="segments")
    
    def __repr__(self) -> str:
        return f"<Segment(id={self.id}, segment_index={self.segment_index})>"


class LLMTrace(Base):
    """LLM interaction trace for debugging.
    
    Evidence: Porting from backend/db.py:116-126 with user_id, mood_id added
    
    Note: session_id is nullable without FK constraint to support pre-generation
    scenarios where no real session exists (e.g., "pre-gen-{mood_id}").
    """
    __tablename__ = "llm_trace"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[Optional[str]] = mapped_column(
        String(36), 
        # NO foreign key constraint - supports pre-generation with fake session IDs
        nullable=True,
        index=True
    )
    # NEW: User scoping columns
    user_id: Mapped[Optional[str]] = mapped_column(
        String(36), 
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    mood_id: Mapped[Optional[str]] = mapped_column(
        String(36), 
        ForeignKey("moods.id", ondelete="SET NULL"),
        nullable=True
    )
    agent_name: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    response: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    thinking_budget: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    # Correlation ID for linking with StatusEventLog
    correlation_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    
    # Relationships - no direct session relationship since there's no FK constraint
    
    def __repr__(self) -> str:
        return f"<LLMTrace(id={self.id}, agent_name={self.agent_name})>"
