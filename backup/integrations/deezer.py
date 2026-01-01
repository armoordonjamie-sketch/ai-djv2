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
    
    async def get_artist_details(self, artist_id: int) -> Optional[Dict[str, Any]]:
        """Get full artist details including genre information.
        
        Args:
            artist_id: Deezer artist ID
            
        Returns:
            Artist object with full details, or None if not found
        """
        cache_key = self._cache_key("artist_details", artist_id=artist_id)
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached
        
        logger.debug(f"Fetching artist details for {artist_id}")
        data = await self._request(f"/artist/{artist_id}")
        
        if not data:
            logger.debug(f"No artist details found for {artist_id}")
            return None
        
        result = {
            "id": data.get("id"),
            "name": data.get("name"),
            "picture": data.get("picture_medium") or data.get("picture"),
            "nb_fan": data.get("nb_fan", 0),
            "nb_album": data.get("nb_album", 0),
            "link": data.get("link"),
        }
        
        # Extract genre if available (genre is usually an object with id and name)
        genre = data.get("genre")
        if genre and isinstance(genre, dict):
            result["genre_id"] = genre.get("id")
            result["genre_name"] = genre.get("name")
            logger.debug(f"Artist {artist_id} has genre: {result.get('genre_name')} (id={result.get('genre_id')})")
        else:
            logger.debug(f"Artist {artist_id} has no genre information")
        
        self._set_cached(cache_key, result)
        return result
    
    async def get_artists_by_genre(
        self,
        genre_id: int,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get top artists in a specific genre.
        
        Args:
            genre_id: Deezer genre ID
            limit: Maximum number of artists (default 10)
            
        Returns:
            List of artist objects
        """
        cache_key = self._cache_key("genre_artists", genre_id=genre_id, limit=limit)
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached
        
        logger.debug(f"Getting artists for genre {genre_id}")
        
        # Try genre artists endpoint first (more reliable)
        data = await self._request(f"/genre/{genre_id}/artists", {"limit": limit})
        
        if not data or not data.get("data"):
            # Fallback to chart endpoint (may not support genre_id parameter)
            logger.debug(f"Genre artists endpoint returned no data, trying chart endpoint")
            data = await self._request("/chart/artists", {"limit": limit})
            if not data or not data.get("data"):
                logger.debug(f"Chart endpoint also returned no data for genre {genre_id}")
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
        logger.debug(f"Got {len(artists)} artists for genre {genre_id}")
        return artists
    
    async def get_related_artists(
        self, 
        artist_id: int, 
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get artists related to a given artist.
        
        Uses fallback strategies when the related endpoint returns no data:
        1. Try the /artist/{id}/related endpoint (primary method)
        2. If empty, get artist's genre and find artists in same genre
        3. If no genre, use artist's top tracks to find other artists
        
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
        
        # Primary method: use related endpoint
        data = await self._request(f"/artist/{artist_id}/related", {"limit": limit})
        
        if data and data.get("data"):
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
        
        # Fallback strategy 1: Get artist's genre and find similar artists
        logger.debug(f"No related artists found for {artist_id}, trying genre-based fallback")
        artist_details = await self.get_artist_details(artist_id)
        
        if not artist_details:
            logger.debug(f"Could not fetch artist details for {artist_id}, skipping genre fallback")
        elif not artist_details.get("genre_id"):
            logger.debug(f"Artist {artist_id} has no genre_id, trying alternative methods")
        else:
            genre_id = artist_details["genre_id"]
            genre_name = artist_details.get("genre_name", "unknown")
            logger.debug(f"Trying to find artists in genre {genre_name} (id={genre_id})")
            genre_artists = await self.get_artists_by_genre(genre_id, limit=limit * 2)
            
            if not genre_artists:
                logger.debug(f"No artists found for genre {genre_id}")
            else:
                # Filter out the original artist and limit results
                filtered = [
                    a for a in genre_artists 
                    if a["id"] != artist_id
                ][:limit]
                
                if filtered:
                    logger.info(f"Found {len(filtered)} artists in same genre for {artist_id} (genre_id={genre_id}, genre_name={genre_name})")
                    self._set_cached(cache_key, filtered)
                    return filtered
                else:
                    logger.debug(f"All genre artists filtered out (same as original artist {artist_id})")
        
        # Fallback strategy 2: Use artist's top tracks to find other artists
        logger.debug(f"Trying top tracks fallback for {artist_id}")
        top_tracks = await self.get_artist_top_tracks(artist_id, limit=10)
        
        if top_tracks:
            # Collect unique artist IDs from top tracks (excluding the original artist)
            other_artist_ids = set()
            for track in top_tracks:
                # Tracks from get_artist_top_tracks have artist as a string name
                # We need to search for these artists to get their IDs
                artist_name = track.get("artist")
                if artist_name and isinstance(artist_name, str):
                    # Search for the artist to get their ID
                    found_artist = await self.search_artist(artist_name)
                    if found_artist and found_artist["id"] != artist_id:
                        other_artist_ids.add(found_artist["id"])
            
            # Get details for found artists (limit to avoid too many requests)
            if other_artist_ids:
                related_artists = []
                for other_id in list(other_artist_ids)[:limit]:
                    artist_details = await self.get_artist_details(other_id)
                    if artist_details:
                        related_artists.append({
                            "id": artist_details["id"],
                            "name": artist_details["name"],
                            "picture": artist_details.get("picture"),
                            "nb_fan": artist_details.get("nb_fan", 0),
                        })
                
                if related_artists:
                    logger.info(f"Found {len(related_artists)} artists via top tracks for {artist_id}")
                    self._set_cached(cache_key, related_artists)
                    return related_artists
            else:
                logger.debug(f"No other artists found in top tracks for {artist_id}")
        else:
            logger.debug(f"No top tracks available for {artist_id}")
        
        # Fallback strategy 3: Search for artists with similar popularity/fan count
        # This is a last resort - search for artists in similar popularity range
        if artist_details:
            artist_name = artist_details.get("name")
            nb_fan = artist_details.get("nb_fan", 0)
            
            if artist_name:
                logger.debug(f"Trying search-based fallback for artist '{artist_name}'")
                # Search for the artist name and get top results (excluding the original)
                search_data = await self._request("/search/artist", {"q": artist_name, "limit": 20})
                
                if search_data and search_data.get("data"):
                    # Filter out the original artist and get similar popularity artists
                    similar_artists = []
                    for artist in search_data["data"]:
                        if artist["id"] != artist_id:
                            # Prefer artists with similar fan counts (within 10x range)
                            artist_fans = artist.get("nb_fan", 0)
                            if nb_fan > 0:
                                ratio = max(artist_fans, 1) / max(nb_fan, 1)
                                if ratio < 0.1 or ratio > 10:
                                    continue  # Skip artists with very different popularity
                            
                            similar_artists.append({
                                "id": artist["id"],
                                "name": artist["name"],
                                "picture": artist.get("picture_medium") or artist.get("picture"),
                                "nb_fan": artist_fans,
                            })
                            
                            if len(similar_artists) >= limit:
                                break
                    
                    if similar_artists:
                        logger.info(f"Found {len(similar_artists)} similar artists via search for {artist_id}")
                        self._set_cached(cache_key, similar_artists)
                        return similar_artists
        
        # If all fallbacks fail, return empty list
        # Only log at debug level since this is expected for some artists
        logger.debug(f"No related artists found for {artist_id} after all fallback strategies")
        self._set_cached(cache_key, [])  # Cache empty result to avoid repeated attempts
        return []
    
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
