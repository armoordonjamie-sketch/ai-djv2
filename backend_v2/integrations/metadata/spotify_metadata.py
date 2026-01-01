"""Spotify Web API metadata enrichment service.

Uses Spotify Web API to enrich song metadata:
- Track search and matching
- Artwork URLs (high quality)
- Audio features (energy, valence, tempo, danceability, etc.)
- Genre information
- ISRC codes
- Release dates
- Explicit content flags

Requires:
- Spotify OAuth access token (user-specific or app-level)
- SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET environment variables
"""
import logging
import asyncio
from typing import Optional, Dict, Any, List

import httpx

import os

# Get Spotify credentials from environment (same pattern as api/spotify.py)
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")

logger = logging.getLogger("ai-dj.metadata.spotify")


class SpotifyMetadataClient:
    """Spotify Web API client for metadata enrichment."""
    
    def __init__(self):
        self.client_id = SPOTIFY_CLIENT_ID
        self.client_secret = SPOTIFY_CLIENT_SECRET
        self.api_base = "https://api.spotify.com/v1"
        self.token_url = "https://accounts.spotify.com/api/token"
        self._access_token: Optional[str] = None
        self._token_expires_at: Optional[float] = None
    
    @property
    def enabled(self) -> bool:
        """Check if client is properly configured."""
        return bool(self.client_id and self.client_secret)
    
    async def _get_access_token(self) -> Optional[str]:
        """Get or refresh app-level access token using client credentials flow.
        
        This token can be used for general API access (search, track details, etc.)
        but NOT for user-specific endpoints.
        
        Returns:
            Access token or None if failed
        """
        # Return cached token if still valid
        if self._access_token and self._token_expires_at:
            import time
            if time.time() < self._token_expires_at - 60:  # Refresh 1 min before expiry
                return self._access_token
        
        if not self.enabled:
            logger.warning("Spotify client not configured (missing credentials)")
            return None
        
        try:
            async with httpx.AsyncClient() as client:
                # Client credentials flow
                auth_header = httpx.BasicAuth(self.client_id, self.client_secret)
                response = await client.post(
                    self.token_url,
                    data={"grant_type": "client_credentials"},
                    auth=auth_header,
                    timeout=10.0
                )
                response.raise_for_status()
                token_data = response.json()
                
                self._access_token = token_data["access_token"]
                expires_in = token_data.get("expires_in", 3600)
                import time
                self._token_expires_at = time.time() + expires_in
                
                logger.debug("Obtained Spotify app-level access token")
                return self._access_token
                
        except Exception as e:
            logger.error(f"Failed to obtain Spotify access token: {e}")
            return None
    
    async def search_track(
        self,
        artist: str,
        title: str,
        limit: int = 5
    ) -> Optional[Dict[str, Any]]:
        """Search for a track by artist and title.
        
        Args:
            artist: Artist name
            title: Track title
            limit: Maximum results to return
            
        Returns:
            Best matching track dict or None
        """
        token = await self._get_access_token()
        if not token:
            return None
        
        # Build search query - try exact match first
        query = f'artist:"{artist}" track:"{title}"'
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.api_base}/search",
                    headers={"Authorization": f"Bearer {token}"},
                    params={
                        "q": query,
                        "type": "track",
                        "limit": min(limit, 50),
                    },
                    timeout=10.0
                )
                
                if response.status_code == 401:
                    # Token expired, clear cache and retry once
                    self._access_token = None
                    token = await self._get_access_token()
                    if token:
                        response = await client.get(
                            f"{self.api_base}/search",
                            headers={"Authorization": f"Bearer {token}"},
                            params={
                                "q": query,
                                "type": "track",
                                "limit": min(limit, 50),
                            },
                            timeout=10.0
                        )
                
                response.raise_for_status()
                data = response.json()
                
                tracks = data.get("tracks", {}).get("items", [])
                if not tracks:
                    # Try looser search
                    query = f"{artist} {title}"
                    response = await client.get(
                        f"{self.api_base}/search",
                        headers={"Authorization": f"Bearer {token}"},
                        params={
                            "q": query,
                            "type": "track",
                            "limit": min(limit, 50),
                        },
                        timeout=10.0
                    )
                    response.raise_for_status()
                    data = response.json()
                    tracks = data.get("tracks", {}).get("items", [])
                
                if not tracks:
                    logger.debug(f"No Spotify results for {artist} - {title}")
                    return None
                
                # Find best match
                best_match = self._find_best_match(tracks, artist, title)
                return best_match or tracks[0]
                
        except Exception as e:
            logger.error(f"Spotify track search failed: {e}")
            return None
    
    def _find_best_match(
        self,
        tracks: List[Dict[str, Any]],
        artist: str,
        title: str
    ) -> Optional[Dict[str, Any]]:
        """Find the best matching track from search results."""
        artist_lower = artist.lower()
        title_lower = title.lower()
        
        for track in tracks:
            track_artists = [a.get("name", "").lower() for a in track.get("artists", [])]
            track_title = track.get("name", "").lower()
            
            # Exact match
            if any(artist_lower in ta or ta in artist_lower for ta in track_artists):
                if title_lower in track_title or track_title in title_lower:
                    return track
            
            # Partial match
            if any(artist_lower in ta or ta in artist_lower for ta in track_artists):
                if any(word in track_title for word in title_lower.split() if len(word) > 3):
                    return track
        
        return None
    
    async def get_track_metadata(
        self,
        artist: str,
        title: str
    ) -> Optional[Dict[str, Any]]:
        """Get complete track metadata including audio features.
        
        Args:
            artist: Artist name
            title: Track title
            
        Returns:
            Dict with artwork_url, audio_features, genres, isrc, etc.
        """
        # Search for track
        track = await self.search_track(artist, title)
        if not track:
            return None
        
        track_id = track.get("id")
        if not track_id:
            return None
        
        token = await self._get_access_token()
        if not token:
            return None
        
        try:
            # Get audio features in parallel with track details
            features_task = self._get_audio_features(token, track_id)
            track_task = self._get_track_details(token, track_id)
            
            features, track_details = await asyncio.gather(
                features_task,
                track_task,
                return_exceptions=True
            )
            
            # Build result
            result = {
                "spotify_id": track_id,
                "title": track.get("name"),
                "artist": ", ".join([a.get("name") for a in track.get("artists", [])]),
                "duration_ms": track.get("duration_ms"),
                "explicit": track.get("explicit", False),
                "isrc": track.get("external_ids", {}).get("isrc"),
                "preview_url": track.get("preview_url"),
            }
            
            # Get artwork (prefer largest available)
            album = track.get("album", {})
            album_id = None
            artist_ids = []
            
            if album:
                images = album.get("images", [])
                if images:
                    # Images are sorted by size (largest first)
                    result["artwork_url"] = images[0].get("url")
                result["album_name"] = album.get("name")
                result["release_date"] = album.get("release_date")
                album_id = album.get("id")
                result["album_id"] = album_id
            
            # Get artist IDs for genre lookup
            artists = track.get("artists", [])
            artist_ids = [a.get("id") for a in artists if a.get("id")]
            
            # Fetch genres from album and artists in parallel
            genres = set()
            if album_id or artist_ids:
                tasks = []
                if album_id:
                    tasks.append(self._get_album_genres(token, album_id))
                if artist_ids:
                    tasks.append(self._get_artist_genres(token, artist_ids))
                
                if tasks:
                    genre_results = await asyncio.gather(*tasks, return_exceptions=True)
                    for genre_result in genre_results:
                        if isinstance(genre_result, list):
                            genres.update(genre_result)
                        elif isinstance(genre_result, Exception):
                            logger.debug(f"Genre fetch failed: {genre_result}")
            
            if genres:
                result["genres"] = list(genres)
            
            # Add audio features
            if isinstance(features, dict) and features.get("id"):
                result["features"] = {
                    "energy": features.get("energy"),
                    "valence": features.get("valence"),
                    "tempo": features.get("tempo"),
                    "danceability": features.get("danceability"),
                    "acousticness": features.get("acousticness"),
                    "instrumentalness": features.get("instrumentalness"),
                    "liveness": features.get("liveness"),
                    "speechiness": features.get("speechiness"),
                    "key": features.get("key"),
                    "mode": features.get("mode"),
                    "time_signature": features.get("time_signature"),
                    "loudness": features.get("loudness"),
                }
            
            logger.info(f"Spotify metadata found for {artist} - {title}")
            return result
            
        except Exception as e:
            logger.error(f"Spotify metadata enrichment failed: {e}")
            return None
    
    async def _get_audio_features(
        self,
        token: str,
        track_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get audio features for a track."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.api_base}/audio-features/{track_id}",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=10.0
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.debug(f"Failed to get audio features: {e}")
            return None
    
    async def _get_track_details(
        self,
        token: str,
        track_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get detailed track information."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.api_base}/tracks/{track_id}",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=10.0
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.debug(f"Failed to get track details: {e}")
            return None
    
    async def _get_album_genres(
        self,
        token: str,
        album_id: str
    ) -> List[str]:
        """Get genres from album.
        
        Args:
            token: Access token
            album_id: Spotify album ID
            
        Returns:
            List of genre strings
        """
        if not album_id:
            return []
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.api_base}/albums/{album_id}",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=10.0
                )
                response.raise_for_status()
                album_data = response.json()
                return album_data.get("genres", [])
        except Exception as e:
            logger.debug(f"Failed to get album genres: {e}")
            return []
    
    async def _get_artist_genres(
        self,
        token: str,
        artist_ids: List[str]
    ) -> List[str]:
        """Get genres from artists.
        
        Args:
            token: Access token
            artist_ids: List of Spotify artist IDs
            
        Returns:
            Combined list of unique genre strings from all artists
        """
        if not artist_ids:
            return []
        
        all_genres = set()
        
        # Fetch artists in parallel (Spotify allows up to 50 IDs per request)
        try:
            async with httpx.AsyncClient() as client:
                # Split into batches of 50
                for i in range(0, len(artist_ids), 50):
                    batch = artist_ids[i:i+50]
                    ids_param = ",".join(batch)
                    
                    response = await client.get(
                        f"{self.api_base}/artists",
                        headers={"Authorization": f"Bearer {token}"},
                        params={"ids": ids_param},
                        timeout=10.0
                    )
                    response.raise_for_status()
                    data = response.json()
                    
                    artists = data.get("artists", [])
                    for artist in artists:
                        genres = artist.get("genres", [])
                        all_genres.update(genres)
        except Exception as e:
            logger.debug(f"Failed to get artist genres: {e}")
        
        return list(all_genres)


# Singleton instance
_client: Optional[SpotifyMetadataClient] = None


def get_spotify_metadata_client() -> SpotifyMetadataClient:
    """Get the singleton Spotify metadata client."""
    global _client
    if _client is None:
        _client = SpotifyMetadataClient()
    return _client

