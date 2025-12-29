"""Deezer metadata provider for song enrichment.

Uses Deezer's Simple API to get:
- Artwork URLs (higher quality)
- BPM/tempo data
- Genre information
- Preview URLs

No authentication required for read operations.
"""
import logging
from typing import Optional, Dict, Any

from backend_v2.integrations.deezer import get_deezer_client

logger = logging.getLogger("ai-dj.metadata.deezer")


class DeezerMetadataClient:
    """Deezer metadata provider for enrichment."""
    
    def __init__(self):
        self.client = get_deezer_client()
    
    async def get_track_metadata(
        self,
        artist: str,
        title: str,
    ) -> Optional[Dict[str, Any]]:
        """Get track metadata from Deezer.
        
        Args:
            artist: Artist name
            title: Track title
            
        Returns:
            Dict with artwork_url, bpm, genres, preview_url, or None
        """
        try:
            # Search for the track
            query = f'artist:"{artist}" track:"{title}"'
            tracks = await self.client.search_tracks(query, limit=5, strict=True)
            
            if not tracks:
                # Try looser search
                query = f"{artist} {title}"
                tracks = await self.client.search_tracks(query, limit=5)
            
            if not tracks:
                logger.debug(f"No Deezer results for {artist} - {title}")
                return None
            
            # Find best match
            track = self._find_best_match(tracks, artist, title)
            if not track:
                track = tracks[0]  # Use first result
            
            result = {
                "deezer_id": track.get("id"),
                "preview_url": track.get("preview"),
                "duration_sec": track.get("duration"),
            }
            
            # Get artwork (prefer high quality)
            album = track.get("album", {})
            if album.get("cover_xl"):
                result["artwork_url"] = album["cover_xl"]
            elif album.get("cover_big"):
                result["artwork_url"] = album["cover_big"]
            elif album.get("cover_medium"):
                result["artwork_url"] = album["cover_medium"]
            
            # Get BPM if available (from track data)
            if track.get("bpm"):
                result["bpm"] = track["bpm"]
            
            # Get artist info
            artist_data = track.get("artist", {})
            if artist_data.get("name"):
                result["artist_name"] = artist_data["name"]
            
            logger.info(f"Deezer metadata found for {artist} - {title}")
            return result
            
        except Exception as e:
            logger.error(f"Deezer metadata lookup failed: {e}")
            return None
    
    def _find_best_match(
        self,
        tracks: list,
        artist: str,
        title: str,
    ) -> Optional[Dict[str, Any]]:
        """Find the best matching track from search results."""
        artist_lower = artist.lower()
        title_lower = title.lower()
        
        for track in tracks:
            track_artist = track.get("artist", {}).get("name", "").lower()
            track_title = track.get("title", "").lower()
            
            # Exact match
            if artist_lower in track_artist and title_lower in track_title:
                return track
            
            # Partial match
            if artist_lower in track_artist or track_artist in artist_lower:
                if title_lower in track_title or track_title in title_lower:
                    return track
        
        return None


# Singleton
_client: Optional[DeezerMetadataClient] = None


def get_deezer_metadata_client() -> DeezerMetadataClient:
    """Get the singleton Deezer metadata client."""
    global _client
    if _client is None:
        _client = DeezerMetadataClient()
    return _client
