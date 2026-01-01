"""Spotify OAuth PKCE implementation for secure authentication."""
import secrets
import hashlib
import base64
import logging
from typing import Dict, Any, Optional, Tuple
from urllib.parse import urlencode

import httpx

logger = logging.getLogger("spotify-test.oauth")


class SpotifyOAuth:
    """Handles Spotify OAuth 2.0 Authorization Code Flow with PKCE."""
    
    def __init__(
        self,
        client_id: str,
        client_secret: Optional[str] = None,  # Not needed for PKCE, but some flows may require it
        redirect_uri: str = "http://127.0.0.1:8000/api/spotify/callback",
        scope: str = "user-read-private user-read-email user-top-read playlist-read-private playlist-read-collaborative user-read-recently-played"
    ):
        """Initialize Spotify OAuth client.
        
        Args:
            client_id: Spotify app client ID
            client_secret: Optional client secret (not needed for PKCE)
            redirect_uri: Redirect URI registered with Spotify
            scope: Space-separated list of scopes
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.scope = scope
        self.auth_url = "https://accounts.spotify.com/authorize"
        self.token_url = "https://accounts.spotify.com/api/token"
        self.api_base = "https://api.spotify.com/v1"
    
    def generate_pkce_pair(self) -> Tuple[str, str]:
        """Generate PKCE code verifier and challenge.
        
        Returns:
            Tuple of (code_verifier, code_challenge)
        """
        # Generate code verifier (43-128 characters, URL-safe)
        code_verifier = base64.urlsafe_b64encode(
            secrets.token_bytes(32)
        ).decode('utf-8').rstrip('=')
        
        # Generate code challenge (SHA256 hash of verifier)
        code_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode()).digest()
        ).decode('utf-8').rstrip('=')
        
        return code_verifier, code_challenge
    
    def get_authorization_url(self, state: Optional[str] = None, code_verifier: Optional[str] = None) -> Tuple[str, str, str]:
        """Generate Spotify authorization URL with PKCE.
        
        Following Spotify iOS Auth SDK patterns:
        - Uses PKCE (Proof Key for Code Exchange) by default
        - Includes state parameter for CSRF protection
        - Returns state for validation in callback
        
        Args:
            state: Optional state parameter for CSRF protection (will generate if not provided)
            code_verifier: Optional code verifier (will generate if not provided)
        
        Returns:
            Tuple of (authorization_url, code_verifier, state)
        """
        # Generate PKCE pair if not provided
        if not code_verifier:
            code_verifier, code_challenge = self.generate_pkce_pair()
        else:
            # Generate challenge from provided verifier
            code_challenge = base64.urlsafe_b64encode(
                hashlib.sha256(code_verifier.encode()).digest()
            ).decode('utf-8').rstrip('=')
        
        # Generate state for CSRF protection if not provided
        if not state:
            state = secrets.token_urlsafe(32)
        
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
            "scope": self.scope,
            "code_challenge_method": "S256",
            "code_challenge": code_challenge,
            "state": state,
            "show_dialog": "true"  # Force dialog to ensure all scopes are granted
        }
        
        auth_url = f"{self.auth_url}?{urlencode(params)}"
        return auth_url, code_verifier, state
    
    async def exchange_code_for_tokens(
        self,
        code: str,
        code_verifier: str
    ) -> Dict[str, Any]:
        """Exchange authorization code for access and refresh tokens.
        
        Args:
            code: Authorization code from callback
            code_verifier: Original code verifier used in authorization
        
        Returns:
            Dictionary with access_token, refresh_token, expires_in, etc.
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.token_url,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": self.redirect_uri,
                    "client_id": self.client_id,
                    "code_verifier": code_verifier,
                },
                headers={
                    "Content-Type": "application/x-www-form-urlencoded"
                },
                timeout=30.0
            )
            response.raise_for_status()
            return response.json()
    
    async def refresh_access_token(self, refresh_token: str) -> Dict[str, Any]:
        """Refresh access token using refresh token.
        
        Args:
            refresh_token: Refresh token from initial authorization
        
        Returns:
            Dictionary with new access_token, expires_in, etc.
        """
        async with httpx.AsyncClient() as client:
            data = {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": self.client_id,
            }
            
            # Add client_secret if available (some apps may require it)
            if self.client_secret:
                data["client_secret"] = self.client_secret
            
            response = await client.post(
                self.token_url,
                data=data,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded"
                },
                timeout=30.0
            )
            response.raise_for_status()
            return response.json()
    
    async def get_user_profile(self, access_token: str) -> Dict[str, Any]:
        """Get current user's profile.
        
        Args:
            access_token: Valid access token
        
        Returns:
            User profile dictionary
        
        Raises:
            httpx.HTTPStatusError: If the API request fails
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.api_base}/me",
                headers={
                    "Authorization": f"Bearer {access_token}"
                },
                timeout=30.0
            )
            
            if response.status_code == 403:
                # Try to get more details about the error
                error_body = response.text
                logger.error(f"403 Forbidden accessing /me endpoint. Response: {error_body}")
                logger.error("This usually means:")
                logger.error("1. The user denied the required scopes during authorization")
                logger.error("2. The token doesn't have 'user-read-private' or 'user-read-email' scope")
                logger.error("3. Check that your Spotify app has the correct scopes configured")
            
            response.raise_for_status()
            return response.json()
    
    async def get_user_playlists(self, access_token: str, limit: int = 50) -> Dict[str, Any]:
        """Get user's playlists.
        
        Args:
            access_token: Valid access token
            limit: Maximum number of playlists to return
        
        Returns:
            Playlists response dictionary
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.api_base}/me/playlists",
                headers={
                    "Authorization": f"Bearer {access_token}"
                },
                params={"limit": limit},
                timeout=30.0
            )
            response.raise_for_status()
            return response.json()
    
    async def get_user_top_tracks(self, access_token: str, limit: int = 50, time_range: str = "medium_term") -> Dict[str, Any]:
        """Get user's top tracks.
        
        Args:
            access_token: Valid access token
            limit: Maximum number of tracks (1-50)
            time_range: Time range (short_term, medium_term, long_term)
        
        Returns:
            Top tracks response dictionary
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.api_base}/me/top/tracks",
                headers={
                    "Authorization": f"Bearer {access_token}"
                },
                params={
                    "limit": limit,
                    "time_range": time_range
                },
                timeout=30.0
            )
            response.raise_for_status()
            return response.json()
    
    async def get_user_top_artists(self, access_token: str, limit: int = 50, time_range: str = "medium_term") -> Dict[str, Any]:
        """Get user's top artists.
        
        Args:
            access_token: Valid access token
            limit: Maximum number of artists (1-50)
            time_range: Time range (short_term, medium_term, long_term)
        
        Returns:
            Top artists response dictionary
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.api_base}/me/top/artists",
                headers={
                    "Authorization": f"Bearer {access_token}"
                },
                params={
                    "limit": limit,
                    "time_range": time_range
                },
                timeout=30.0
            )
            response.raise_for_status()
            return response.json()
    
    async def get_recently_played(self, access_token: str, limit: int = 50) -> Dict[str, Any]:
        """Get user's recently played tracks.
        
        Args:
            access_token: Valid access token
            limit: Maximum number of tracks (1-50)
        
        Returns:
            Recently played tracks response dictionary
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.api_base}/me/player/recently-played",
                headers={
                    "Authorization": f"Bearer {access_token}"
                },
                params={"limit": limit},
                timeout=30.0
            )
            response.raise_for_status()
            return response.json()
    
    async def aggregate_user_data(self, access_token: str) -> Dict[str, Any]:
        """Aggregate all user data for AI analysis.
        
        Fetches comprehensive user data including:
        - User profile
        - Playlists
        - Top tracks (all time ranges: short_term, medium_term, long_term)
        - Top artists (all time ranges: short_term, medium_term, long_term)
        - Recently played tracks
        
        Args:
            access_token: Valid access token
        
        Returns:
            Dictionary containing all user data organized by category
        """
        logger.info("Fetching comprehensive user data from Spotify API...")
        
        # Fetch profile
        profile = await self.get_user_profile(access_token)
        
        # Fetch playlists
        playlists_response = await self.get_user_playlists(access_token, limit=50)
        
        # Fetch top tracks for all time ranges
        logger.info("Fetching top tracks (short_term, medium_term, long_term)...")
        top_tracks_short = await self.get_user_top_tracks(access_token, limit=50, time_range="short_term")
        top_tracks_medium = await self.get_user_top_tracks(access_token, limit=50, time_range="medium_term")
        top_tracks_long = await self.get_user_top_tracks(access_token, limit=50, time_range="long_term")
        
        # Fetch top artists for all time ranges
        logger.info("Fetching top artists (short_term, medium_term, long_term)...")
        top_artists_short = await self.get_user_top_artists(access_token, limit=50, time_range="short_term")
        top_artists_medium = await self.get_user_top_artists(access_token, limit=50, time_range="medium_term")
        top_artists_long = await self.get_user_top_artists(access_token, limit=50, time_range="long_term")
        
        # Fetch recently played tracks
        logger.info("Fetching recently played tracks...")
        recently_played_response = await self.get_recently_played(access_token, limit=50)
        
        return {
            "profile": profile,
            "playlists": playlists_response.get("items", []),
            "top_tracks": {
                "short_term": top_tracks_short.get("items", []),
                "medium_term": top_tracks_medium.get("items", []),
                "long_term": top_tracks_long.get("items", [])
            },
            "top_artists": {
                "short_term": top_artists_short.get("items", []),
                "medium_term": top_artists_medium.get("items", []),
                "long_term": top_artists_long.get("items", [])
            },
            "recently_played": recently_played_response.get("items", []),
            "summary": {
                "total_playlists": playlists_response.get("total", 0),
                "top_tracks_short": len(top_tracks_short.get("items", [])),
                "top_tracks_medium": len(top_tracks_medium.get("items", [])),
                "top_tracks_long": len(top_tracks_long.get("items", [])),
                "top_artists_short": len(top_artists_short.get("items", [])),
                "top_artists_medium": len(top_artists_medium.get("items", [])),
                "top_artists_long": len(top_artists_long.get("items", [])),
                "recently_played_count": len(recently_played_response.get("items", []))
            }
        }

