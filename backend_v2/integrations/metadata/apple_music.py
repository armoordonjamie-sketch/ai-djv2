"""Apple Music metadata via Apify scraper.

Uses the jupri/apple-music Apify actor to extract:
- Artwork URLs (high-res album art)
- Genre information
- Song/artist metadata

No Apple Developer account required - uses web scraping.

Requires:
- APIFY_API_TOKEN environment variable
"""
import asyncio
import logging
import hashlib
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

import httpx

from backend_v2.config import APIFY_API_TOKEN
from backend_v2.utils.time import utc_now, ensure_utc

logger = logging.getLogger("ai-dj.applemusic")

# Apify configuration
# Note: Apify uses ~ to separate username from actor name in API URLs
APIFY_ACTOR_ID = "jupri~apple-music"
APIFY_API_BASE = "https://api.apify.com/v2"


class AppleMusicClient:
    """Apple Music metadata client using Apify scraper."""
    
    def __init__(self):
        self.actor_id = APIFY_ACTOR_ID
        self.api_base = APIFY_API_BASE
        self.token = APIFY_API_TOKEN
        self._client: Optional[httpx.AsyncClient] = None
        
        # In-memory cache
        self._cache: Dict[str, Any] = {}
        self._cache_ttl = timedelta(days=7)  # Artwork URLs are stable
    
    @property
    def enabled(self) -> bool:
        """Check if client is properly configured."""
        return bool(self.token)
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=60.0)
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
    
    async def search_song(
        self,
        artist: str,
        title: str,
    ) -> Optional[Dict[str, Any]]:
        """Search for a song on Apple Music via Apify.
        
        Args:
            artist: Artist name
            title: Song title
            
        Returns:
            Song data with artwork, genres, etc.
        """
        cache_key = self._cache_key("search_song", artist=artist, title=title)
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached
        
        if not self.enabled:
            logger.warning("Apify API token not configured")
            return None
        
        client = await self._get_client()
        
        # Build search query for Apify
        query = f"song:{artist} {title}"
        
        # Apify run-sync endpoint
        url = f"{self.api_base}/acts/{self.actor_id}/run-sync-get-dataset-items"
        
        # Input for the Apple Music scraper - per documentation:
        # { "query": ["song:Nightwish"], "limit": 10 }
        input_data = {
            "query": [query],
            "limit": 5,
        }
        
        try:
            logger.info(f"Searching Apple Music via Apify: {query}")
            
            response = await client.post(
                url,
                params={
                    "token": self.token,
                    "timeout": 120,  # 2 min timeout
                },
                json=input_data,
                headers={"Content-Type": "application/json"},
            )
            
            if response.status_code == 408:
                logger.warning("Apify request timed out")
                return None
            
            if response.status_code != 201:
                logger.warning(f"Apify search failed: {response.status_code} - {response.text[:200]}")
                return None
            
            items = response.json()
            
            if not items:
                logger.info(f"No Apple Music result for: {artist} - {title}")
                return None
            
            # Take best match
            song = items[0]
            result = self._parse_song(song)
            
            self._set_cached(cache_key, result)
            logger.info(f"Found: {result.get('title')} by {result.get('artist')}")
            return result
            
        except Exception as e:
            logger.error(f"Apify Apple Music search error: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _parse_song(self, song: Dict[str, Any]) -> Dict[str, Any]:
        """Parse Apify scraper song response.
        
        The exact structure depends on the jupri/apple-music actor output.
        We handle common field names flexibly.
        """
        result = {
            "apple_song_id": song.get("id") or song.get("trackId") or song.get("url"),
            "title": song.get("name") or song.get("trackName") or song.get("title"),
            "artist": song.get("artistName") or song.get("artist"),
            "album": song.get("albumName") or song.get("album") or song.get("collectionName"),
            "duration_ms": song.get("durationInMillis") or song.get("trackTimeMillis"),
            "release_date": song.get("releaseDate"),
            "genres": song.get("genreNames") or song.get("genres") or [],
            "explicit": song.get("contentRating") == "explicit" or song.get("explicit", False),
        }
        
        # Parse artwork URL - various possible field names
        artwork = (
            song.get("artworkUrl100") or
            song.get("artworkUrl") or
            song.get("artwork") or
            song.get("artworkUrl60") or
            song.get("image")
        )
        
        if artwork:
            # Upgrade to higher resolution if it's a templated URL
            if isinstance(artwork, dict):
                # artwork might be object with url property
                url = artwork.get("url", "")
            else:
                url = str(artwork)
            
            # Replace resolution placeholder with high-res
            if "{w}" in url and "{h}" in url:
                result["artwork_url"] = url.replace("{w}", "1000").replace("{h}", "1000")
            elif "100x100" in url:
                result["artwork_url"] = url.replace("100x100", "1000x1000")
            elif "60x60" in url:
                result["artwork_url"] = url.replace("60x60", "1000x1000")
            else:
                result["artwork_url"] = url
        
        # Handle genres as list
        if isinstance(result["genres"], str):
            result["genres"] = [result["genres"]]
        
        return result
    
    async def get_song_artwork(
        self,
        artist: str,
        title: str,
        size: int = 500,
    ) -> Optional[str]:
        """Get artwork URL for a song.
        
        Args:
            artist: Artist name
            title: Song title
            size: Artwork size in pixels (default: 500)
            
        Returns:
            Artwork URL or None
        """
        result = await self.search_song(artist, title)
        
        if result and result.get("artwork_url"):
            url = result["artwork_url"]
            # Replace 1000x1000 with requested size
            return url.replace("1000x1000", f"{size}x{size}")
        
        return None
    
    async def enrich_track(
        self,
        artist: str,
        title: str,
    ) -> Optional[Dict[str, Any]]:
        """Enrich track with Apple Music metadata.
        
        Args:
            artist: Artist name
            title: Song title
            
        Returns:
            Dict with artwork_url, genres, apple_song_id, etc.
        """
        logger.info(f"Enriching track from Apple Music: {artist} - {title}")
        
        result = await self.search_song(artist, title)
        
        if result:
            logger.info(f"Enriched: {result.get('apple_song_id')} - {result.get('title')}")
            return result
        
        return None


# Singleton instance
_client: Optional[AppleMusicClient] = None


def get_apple_music_client() -> AppleMusicClient:
    """Get the singleton Apple Music client."""
    global _client
    if _client is None:
        _client = AppleMusicClient()
    return _client
