"""Base catalog provider interface for track discovery.

Catalog providers allow querying external music catalogs (Spotify, Apple Music, etc.)
for track metadata and audio features without requiring local files.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class AudioFeatures:
    """Audio features for a track."""
    energy: Optional[float] = None  # 0.0-1.0
    valence: Optional[float] = None  # 0.0-1.0
    tempo: Optional[float] = None  # BPM
    danceability: Optional[float] = None  # 0.0-1.0
    acousticness: Optional[float] = None  # 0.0-1.0
    instrumentalness: Optional[float] = None  # 0.0-1.0
    key: Optional[int] = None  # 0-11
    mode: Optional[int] = None  # 0=minor, 1=major
    loudness: Optional[float] = None  # dB
    speechiness: Optional[float] = None  # 0.0-1.0
    liveness: Optional[float] = None  # 0.0-1.0
    time_signature: Optional[int] = None  # 3, 4, 5, etc.


@dataclass
class CatalogTrack:
    """Track metadata from a catalog provider."""
    # Identity
    title: str
    artist: str
    album: Optional[str] = None
    
    # External IDs
    provider: str = ""  # "spotify", "apple_music", etc.
    provider_id: str = ""  # Provider-specific ID
    isrc: Optional[str] = None
    
    # Metadata
    duration_ms: Optional[int] = None
    release_date: Optional[str] = None
    artwork_url: Optional[str] = None
    genres: List[str] = None
    popularity: Optional[int] = None  # 0-100 (if available)
    
    # Audio features
    features: Optional[AudioFeatures] = None
    
    def __post_init__(self):
        if self.genres is None:
            self.genres = []


class CatalogProvider(ABC):
    """Abstract base class for catalog providers."""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name (e.g., 'spotify', 'apple_music')."""
        pass
    
    @property
    @abstractmethod
    def enabled(self) -> bool:
        """Whether this provider is enabled (API keys configured, etc.)."""
        pass
    
    @abstractmethod
    async def search_tracks(
        self,
        query: str,
        limit: int = 50,
        filters: Optional[dict] = None
    ) -> List[CatalogTrack]:
        """Search for tracks matching the query.
        
        Args:
            query: Search query string (e.g., "artist name genre keyword")
            limit: Maximum number of results to return
            filters: Optional filters (genre, year, etc.)
            
        Returns:
            List of tracks with metadata
        """
        pass
    
    @abstractmethod
    async def get_track(self, track_id: str) -> Optional[CatalogTrack]:
        """Get track metadata by provider ID.
        
        Args:
            track_id: Provider-specific track ID
            
        Returns:
            Track metadata or None if not found
        """
        pass
    
    @abstractmethod
    async def get_audio_features(self, track_id: str) -> Optional[AudioFeatures]:
        """Get audio features for a track.
        
        Args:
            track_id: Provider-specific track ID
            
        Returns:
            Audio features or None if not available
        """
        pass


class MockCatalogProvider(CatalogProvider):
    """Mock provider for testing that returns no results."""
    
    @property
    def name(self) -> str:
        return "mock"
    
    @property
    def enabled(self) -> bool:
        return True
    
    async def search_tracks(
        self,
        query: str,
        limit: int = 50,
        filters: Optional[dict] = None
    ) -> List[CatalogTrack]:
        return []
    
    async def get_track(self, track_id: str) -> Optional[CatalogTrack]:
        return None
    
    async def get_audio_features(self, track_id: str) -> Optional[AudioFeatures]:
        return None

