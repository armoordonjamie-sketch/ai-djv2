"""Deezer API client for music discovery during onboarding.

Uses Deezer's Simple API (no authentication required):
- Search artists and tracks
- Get artist top tracks with 30-second previews
- Get related artists for music exploration

Rate limit: 50 requests / 5 seconds

API docs: https://developers.deezer.com/api
"""
import asyncio
import logging
import hashlib
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

import httpx

from backend_v2.utils.time import utc_now, ensure_utc

logger = logging.getLogger("ai-dj.deezer")

# Deezer API configuration
DEEZER_API_BASE = "https://api.deezer.com"


class DeezerClient:
    """Deezer API client for music discovery.
    
    No authentication required for read operations.
    """
    
    def __init__(self):
        self.api_base = DEEZER_API_BASE
        self._client: Optional[httpx.AsyncClient] = None
        
        # In-memory cache
        self._cache: Dict[str, Any] = {}
        self._cache_ttl = timedelta(hours=24)
        
        # Rate limiting: 50 requests / 5 seconds
        self._request_times: List[datetime] = []
        self._rate_limit = 50
        self._rate_window = 5.0  # seconds
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client
    
    async def close(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
    
    def _cache_key(self, method: str, **params) -> str:
        """Generate cache key."""
        key_data = f"{method}:{json.dumps(params, sort_keys=True)}"
        return hashlib.md5(key_data.encode()).hexdigest()
    
    def _get_cached(self, key: str) -> Optional[Any]:
        """Get cached result if valid."""
        if key in self._cache:
            result, timestamp = self._cache[key]
            timestamp = ensure_utc(timestamp)
            if timestamp is not None and utc_now() - timestamp < self._cache_ttl:
                return result
            del self._cache[key]
        return None
    
    def _set_cached(self, key: str, result: Any):
        """Store result in cache."""
        self._cache[key] = (result, utc_now())
    
    async def _rate_limit_wait(self):
        """Wait if we're hitting rate limits."""
        now = utc_now()
        
        # Remove old request times outside the window
        cutoff = now - timedelta(seconds=self._rate_window)
        recent_times: List[datetime] = []
        for t in self._request_times:
            t = ensure_utc(t)
            if t is not None and t > cutoff:
                recent_times.append(t)
        self._request_times = recent_times
        
        # If at limit, wait for the oldest request to expire
        if len(self._request_times) >= self._rate_limit:
            oldest = self._request_times[0]
            wait_time = (oldest + timedelta(seconds=self._rate_window) - now).total_seconds()
            if wait_time > 0:
                logger.debug(f"Rate limiting: waiting {wait_time:.2f}s")
                await asyncio.sleep(wait_time)
        
        self._request_times.append(now)
    
    async def _request(self, endpoint: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """Make a rate-limited request to Deezer API."""
        await self._rate_limit_wait()
        
        client = await self._get_client()
        url = f"{self.api_base}{endpoint}"
        
        try:
            response = await client.get(url, params=params)
            
            if response.status_code != 200:
                logger.warning(f"Deezer API error: {response.status_code} - {response.text[:200]}")
                return None
            
            data = response.json()
            
            # Check for Deezer API error response
            if "error" in data:
                logger.warning(f"Deezer API error: {data['error']}")
                return None
            
            return data
            
        except Exception as e:
            logger.error(f"Deezer API request failed: {e}")
            return None
    
    async def search_artist(self, name: str) -> Optional[Dict[str, Any]]:
        """Search for an artist by name.
        
        Args:
            name: Artist name to search for
            
        Returns:
            Artist object with id, name, picture, nb_fan, etc.
        """
        cache_key = self._cache_key("search_artist", name=name)
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached
        
        logger.info(f"Searching Deezer for artist: {name}")
        
        data = await self._request("/search/artist", {"q": name, "limit": 1})
        
        if not data or not data.get("data"):
            logger.info(f"No artist found for: {name}")
            return None
        
        artist = data["data"][0]
        result = {
            "id": artist["id"],
            "name": artist["name"],
            "picture": artist.get("picture_medium") or artist.get("picture"),
            "nb_fan": artist.get("nb_fan", 0),
            "nb_album": artist.get("nb_album", 0),
            "link": artist.get("link"),
        }
        
        self._set_cached(cache_key, result)
        logger.info(f"Found artist: {result['name']} (id={result['id']}, fans={result['nb_fan']})")
        return result
    
    async def get_artist_top_tracks(
        self, 
        artist_id: int, 
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get an artist's top tracks.
        
        Args:
            artist_id: Deezer artist ID
            limit: Maximum number of tracks (default 10)
            
        Returns:
            List of track objects with title, preview URL, album info, etc.
        """
        cache_key = self._cache_key("artist_top", artist_id=artist_id, limit=limit)
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached
        
        logger.info(f"Getting top tracks for artist {artist_id}")
        
        data = await self._request(f"/artist/{artist_id}/top", {"limit": limit})
        
        if not data or not data.get("data"):
            logger.info(f"No tracks found for artist {artist_id}")
            return []
        
        tracks = []
        for track in data["data"]:
            tracks.append({
                "id": track["id"],
                "title": track["title"],
                "title_short": track.get("title_short", track["title"]),
                "duration": track.get("duration", 0),
                "rank": track.get("rank", 0),
                "preview": track.get("preview"),  # 30-second MP3 URL
                "explicit": track.get("explicit_lyrics", False),
                "artist": track.get("artist", {}).get("name"),
                "album": {
                    "title": track.get("album", {}).get("title"),
                    "cover": track.get("album", {}).get("cover_medium"),
                }
            })
        
        self._set_cached(cache_key, tracks)
        logger.info(f"Got {len(tracks)} top tracks for artist {artist_id}")
        return tracks
    
    async def get_related_artists(
        self, 
        artist_id: int, 
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get artists related to a given artist.
        
        Args:
            artist_id: Deezer artist ID
            limit: Maximum number of related artists (default 10)
            
        Returns:
            List of related artist objects
        """
        cache_key = self._cache_key("related", artist_id=artist_id, limit=limit)
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached
        
        logger.info(f"Getting related artists for {artist_id}")
        
        data = await self._request(f"/artist/{artist_id}/related", {"limit": limit})
        
        if not data or not data.get("data"):
            logger.info(f"No related artists found for {artist_id}")
            return []
        
        artists = []
        for artist in data["data"]:
            artists.append({
                "id": artist["id"],
                "name": artist["name"],
                "picture": artist.get("picture_medium") or artist.get("picture"),
                "nb_fan": artist.get("nb_fan", 0),
            })
        
        self._set_cached(cache_key, artists)
        logger.info(f"Got {len(artists)} related artists for {artist_id}")
        return artists
    
    async def search_tracks(
        self,
        query: str,
        limit: int = 10,
        strict: bool = False,
    ) -> List[Dict[str, Any]]:
        """Search for tracks using Deezer's advanced search.
        
        Supports advanced search syntax:
        - artist:"name" - specific artist
        - track:"name" - specific track
        - album:"name" - specific album
        - bpm_min:120, bpm_max:180 - BPM range
        - dur_min:180, dur_max:300 - duration in seconds
        
        Args:
            query: Search query (supports advanced syntax)
            limit: Maximum results (default 10)
            strict: Disable fuzzy matching
            
        Returns:
            List of track objects with preview URLs
        """
        cache_key = self._cache_key("search_tracks", query=query, limit=limit)
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached
        
        logger.info(f"Searching Deezer tracks: {query}")
        
        params = {"q": query, "limit": limit}
        if strict:
            params["strict"] = "on"
        
        data = await self._request("/search", params)
        
        if not data or not data.get("data"):
            logger.info(f"No tracks found for: {query}")
            return []
        
        tracks = []
        for track in data["data"]:
            tracks.append({
                "id": track["id"],
                "title": track["title"],
                "title_short": track.get("title_short", track["title"]),
                "duration": track.get("duration", 0),
                "rank": track.get("rank", 0),
                "preview": track.get("preview"),
                "explicit": track.get("explicit_lyrics", False),
                "artist": {
                    "id": track.get("artist", {}).get("id"),
                    "name": track.get("artist", {}).get("name"),
                },
                "album": {
                    "id": track.get("album", {}).get("id"),
                    "title": track.get("album", {}).get("title"),
                    "cover": track.get("album", {}).get("cover_medium"),
                }
            })
        
        self._set_cached(cache_key, tracks)
        logger.info(f"Found {len(tracks)} tracks for: {query}")
        return tracks


# Singleton instance
_client: Optional[DeezerClient] = None


def get_deezer_client() -> DeezerClient:
    """Get the singleton Deezer client."""
    global _client
    if _client is None:
        _client = DeezerClient()
    return _client
