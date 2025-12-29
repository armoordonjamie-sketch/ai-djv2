"""MusicBrainz client for metadata enrichment.

Provides:
- Track matching by title/artist
- ISRC lookup
- MBIDs (Recording, Release, Artist)
- Rate limiting (~1 req/sec per MusicBrainz guidelines)
- Result caching in database
"""
import asyncio
import logging
import hashlib
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

import httpx

from backend_v2.config import MUSICBRAINZ_CONTACT_EMAIL, MUSICBRAINZ_RATE_LIMIT
from backend_v2.utils.time import utc_now, ensure_utc

logger = logging.getLogger("ai-dj.musicbrainz")

# MusicBrainz API configuration
MB_API_BASE = "https://musicbrainz.org/ws/2"
MB_USER_AGENT = f"JamifyDJ/1.0 ({MUSICBRAINZ_CONTACT_EMAIL or 'contact@example.com'})"


class RateLimiter:
    """Simple rate limiter for API calls."""
    
    def __init__(self, calls_per_second: float = 1.0):
        self.min_interval = 1.0 / calls_per_second
        self.last_call = 0.0
        self._lock = asyncio.Lock()
    
    async def acquire(self):
        """Wait until we can make the next call."""
        async with self._lock:
            now = asyncio.get_event_loop().time()
            wait_time = self.last_call + self.min_interval - now
            
            if wait_time > 0:
                await asyncio.sleep(wait_time)
            
            self.last_call = asyncio.get_event_loop().time()


class MusicBrainzClient:
    """Async MusicBrainz API client with rate limiting."""
    
    def __init__(self):
        self.base_url = MB_API_BASE
        self.headers = {
            "User-Agent": MB_USER_AGENT,
            "Accept": "application/json",
        }
        self.rate_limiter = RateLimiter(calls_per_second=MUSICBRAINZ_RATE_LIMIT)
        self._client: Optional[httpx.AsyncClient] = None
        
        # In-memory cache for session
        self._cache: Dict[str, Any] = {}
        self._cache_ttl = timedelta(hours=24)
    
    @property
    def enabled(self) -> bool:
        """Check if client is properly configured."""
        return bool(MUSICBRAINZ_CONTACT_EMAIL)
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                headers=self.headers,
                timeout=30.0,
            )
        return self._client
    
    async def close(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
    
    def _cache_key(self, method: str, **params) -> str:
        """Generate cache key from method and params."""
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
    
    async def _request(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Make rate-limited API request."""
        if not self.enabled:
            logger.warning("MusicBrainz client not configured (missing contact email)")
            return None
        
        await self.rate_limiter.acquire()
        
        url = f"{self.base_url}/{endpoint}"
        params = params or {}
        params["fmt"] = "json"
        
        try:
            client = await self._get_client()
            response = await client.get(url, params=params)
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 503:
                logger.warning("MusicBrainz rate limited, backing off")
                await asyncio.sleep(3)
                return None
            else:
                logger.warning(f"MusicBrainz API error: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"MusicBrainz request failed: {e}")
            return None
    
    async def search_recording(
        self,
        artist: str,
        title: str,
        limit: int = 5,
    ) -> Optional[List[Dict[str, Any]]]:
        """Search for recordings by artist and title.
        
        Args:
            artist: Artist name
            title: Track title
            limit: Maximum results
            
        Returns:
            List of recording results with MBIDs
        """
        cache_key = self._cache_key("search_recording", artist=artist, title=title)
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached
        
        # Build Lucene query
        query = f'recording:"{title}" AND artist:"{artist}"'
        
        result = await self._request(
            "recording",
            params={
                "query": query,
                "limit": limit,
            }
        )
        
        if result and "recordings" in result:
            recordings = result["recordings"]
            self._set_cached(cache_key, recordings)
            return recordings
        
        return None
    
    async def lookup_recording(
        self,
        mbid: str,
        inc: List[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Lookup recording by MBID.
        
        Args:
            mbid: Recording MBID
            inc: Include relationships (e.g., ["artists", "releases", "isrcs"])
            
        Returns:
            Recording details
        """
        cache_key = self._cache_key("lookup_recording", mbid=mbid, inc=inc)
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached
        
        params = {}
        if inc:
            params["inc"] = "+".join(inc)
        
        result = await self._request(f"recording/{mbid}", params=params)
        
        if result:
            self._set_cached(cache_key, result)
            return result
        
        return None
    
    async def lookup_isrc(self, isrc: str) -> Optional[List[Dict[str, Any]]]:
        """Lookup recordings by ISRC.
        
        Args:
            isrc: International Standard Recording Code
            
        Returns:
            List of matching recordings
        """
        cache_key = self._cache_key("lookup_isrc", isrc=isrc)
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached
        
        result = await self._request(
            "isrc/" + isrc,
            params={"inc": "artists+releases"}
        )
        
        if result and "recordings" in result:
            recordings = result["recordings"]
            self._set_cached(cache_key, recordings)
            return recordings
        
        return None
    
    async def match_track(
        self,
        artist: str,
        title: str,
        isrc: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Match a track and return enriched metadata.
        
        Tries ISRC first if available, then falls back to search.
        
        Args:
            artist: Artist name
            title: Track title
            isrc: Optional ISRC code
            
        Returns:
            Dict with:
            - recording_mbid
            - release_mbid
            - artist_mbid
            - isrc
            - genres (if available)
            - tags (if available)
        """
        logger.info(f"Matching track: {artist} - {title}")
        
        recordings = None
        
        # Try ISRC first
        if isrc:
            recordings = await self.lookup_isrc(isrc)
            if recordings:
                logger.info(f"Matched by ISRC: {isrc}")
        
        # Fall back to search
        if not recordings:
            recordings = await self.search_recording(artist, title)
        
        if not recordings:
            logger.warning(f"No match found for: {artist} - {title}")
            return None
        
        # Take best match (first result)
        recording = recordings[0]
        
        result = {
            "recording_mbid": recording.get("id"),
            "title": recording.get("title"),
            "length_ms": recording.get("length"),
        }
        
        # Extract artist MBID
        if "artist-credit" in recording:
            for credit in recording["artist-credit"]:
                if isinstance(credit, dict) and "artist" in credit:
                    result["artist_mbid"] = credit["artist"].get("id")
                    result["artist_name"] = credit["artist"].get("name")
                    break
        
        # Extract release MBID
        if "releases" in recording and recording["releases"]:
            release = recording["releases"][0]
            result["release_mbid"] = release.get("id")
            result["release_title"] = release.get("title")
        
        # Extract ISRCs
        if "isrcs" in recording and recording["isrcs"]:
            result["isrc"] = recording["isrcs"][0]
        elif isrc:
            result["isrc"] = isrc
        
        # Extract tags/genres (if present)
        if "tags" in recording:
            result["tags"] = [t["name"] for t in recording.get("tags", [])[:10]]
        
        logger.info(f"Matched: {result.get('recording_mbid')} ({result.get('artist_name')} - {result.get('title')})")
        return result


# Singleton instance
_client: Optional[MusicBrainzClient] = None


def get_musicbrainz_client() -> MusicBrainzClient:
    """Get the singleton MusicBrainz client."""
    global _client
    if _client is None:
        _client = MusicBrainzClient()
    return _client
