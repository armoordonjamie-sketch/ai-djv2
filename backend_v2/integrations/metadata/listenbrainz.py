"""ListenBrainz client for user listening history and metadata lookups."""
import logging
from typing import Optional, Dict, Any

import httpx

from backend_v2.config import LISTENBRAINZ_USER_TOKEN

logger = logging.getLogger("ai-dj.listenbrainz")

LB_API_BASE = "https://api.listenbrainz.org/1"
LB_USER_AGENT = "JamifyDJ/1.0"


class ListenBrainzClient:
    """Async ListenBrainz API client."""

    def __init__(self):
        self.base_url = LB_API_BASE
        self.headers = {
            "User-Agent": LB_USER_AGENT,
            "Accept": "application/json",
        }
        if LISTENBRAINZ_USER_TOKEN:
            self.headers["Authorization"] = f"Token {LISTENBRAINZ_USER_TOKEN}"
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def enabled(self) -> bool:
        """Check if client is properly configured."""
        return bool(LISTENBRAINZ_USER_TOKEN)

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

    async def _request(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Make an API request if configured."""
        if not self.enabled:
            logger.warning("ListenBrainz client not configured (missing user token)")
            return None

        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        client = await self._get_client()
        try:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as exc:
            logger.warning(f"ListenBrainz API error: {exc}")
            return None

    async def get_recent_listens(
        self,
        username: str,
        count: int = 5,
    ) -> Optional[Dict[str, Any]]:
        """Fetch recent listens for a user."""
        return await self._request(
            f"user/{username}/listens",
            params={"count": count},
        )


_client: Optional[ListenBrainzClient] = None


def get_listenbrainz_client() -> ListenBrainzClient:
    """Get the singleton ListenBrainz client."""
    global _client
    if _client is None:
        _client = ListenBrainzClient()
    return _client
