"""Deezer catalog provider for track discovery.

Uses the existing Deezer API integration to search for tracks and get metadata.
Deezer is free and provides good coverage of popular music.
"""
import logging
from typing import List, Optional

from backend_v2.catalog.providers.base import (
    CatalogProvider,
    CatalogTrack,
    AudioFeatures,
)
from backend_v2.integrations.deezer import get_deezer_client

logger = logging.getLogger("ai-dj.catalog.deezer")


class DeezerCatalogProvider(CatalogProvider):
    """Catalog provider using Deezer API."""
    
    def __init__(self):
        self.client = get_deezer_client()
    
    @property
    def name(self) -> str:
        return "deezer"
    
    @property
    def enabled(self) -> bool:
        # Deezer is always enabled (no API key required)
        return True
    
    async def search_tracks(
        self,
        query: str,
        limit: int = 50,
        filters: Optional[dict] = None
    ) -> List[CatalogTrack]:
        """Search Deezer for tracks matching the query.
        
        Args:
            query: Search query (can include artist:, track: prefixes)
            limit: Maximum results (Deezer supports up to 100)
            filters: Optional filters (not used for Deezer currently)
            
        Returns:
            List of catalog tracks with metadata
        """
        try:
            # Use existing Deezer client
            tracks = await self.client.search_tracks(query, limit=min(limit, 100))
            
            if not tracks:
                return []
            
            catalog_tracks = []
            for track in tracks:
                catalog_track = self._convert_deezer_track(track)
                if catalog_track:
                    catalog_tracks.append(catalog_track)
            
            logger.info(f"Deezer search '{query}': found {len(catalog_tracks)} tracks")
            return catalog_tracks
            
        except Exception as e:
            logger.error(f"Deezer search error: {e}")
            return []
    
    async def get_track(self, track_id: str) -> Optional[CatalogTrack]:
        """Get track metadata by Deezer ID.
        
        Args:
            track_id: Deezer track ID
            
        Returns:
            Track metadata or None
        """
        try:
            # Deezer API endpoint for single track
            result = await self.client._request(f"track/{track_id}")
            if result:
                return self._convert_deezer_track(result)
        except Exception as e:
            logger.error(f"Error fetching Deezer track {track_id}: {e}")
        
        return None
    
    async def get_audio_features(self, track_id: str) -> Optional[AudioFeatures]:
        """Get audio features for a Deezer track.
        
        Note: Deezer provides limited audio features (BPM via track details).
        We can estimate other features using AI if needed.
        
        Args:
            track_id: Deezer track ID
            
        Returns:
            Audio features (limited) or None
        """
        try:
            result = await self.client._request(f"track/{track_id}")
            if result:
                # Deezer provides BPM in track details
                bpm = result.get("bpm")
                
                # Create minimal features from available data
                features = AudioFeatures(
                    tempo=float(bpm) if bpm else None,
                    # Other features would need AI estimation
                )
                return features
        except Exception as e:
            logger.error(f"Error fetching Deezer features {track_id}: {e}")
        
        return None
    
    def _convert_deezer_track(self, track: dict) -> Optional[CatalogTrack]:
        """Convert Deezer API track response to CatalogTrack.
        
        Deezer track format:
        {
            "id": 123456,
            "title": "Song Title",
            "duration": 240,  # seconds
            "artist": {"id": 789, "name": "Artist Name"},
            "album": {"id": 456, "title": "Album Title", "cover_medium": "url"},
            "preview": "url",
            "bpm": 120,
            "explicit_lyrics": false,
            "isrc": "USRC17607839",
            "release_date": "2020-01-01"
        }
        """
        try:
            artist_data = track.get("artist", {})
            album_data = track.get("album", {})
            
            return CatalogTrack(
                title=track.get("title", "Unknown"),
                artist=artist_data.get("name", "Unknown"),
                album=album_data.get("title"),
                provider="deezer",
                provider_id=str(track.get("id", "")),
                isrc=track.get("isrc"),
                duration_ms=track.get("duration", 0) * 1000,  # Deezer uses seconds
                release_date=track.get("release_date"),
                artwork_url=album_data.get("cover_medium") or album_data.get("cover_big"),
                genres=[],  # Deezer doesn't provide genres in track search
                popularity=None,  # Could use rank if available
                features=AudioFeatures(
                    tempo=float(track.get("bpm")) if track.get("bpm") else None,
                )
            )
        except Exception as e:
            logger.error(f"Error converting Deezer track: {e}")
            return None


# Singleton instance
_deezer_provider: Optional[DeezerCatalogProvider] = None


def get_deezer_provider() -> DeezerCatalogProvider:
    """Get singleton Deezer catalog provider."""
    global _deezer_provider
    if _deezer_provider is None:
        _deezer_provider = DeezerCatalogProvider()
    return _deezer_provider

