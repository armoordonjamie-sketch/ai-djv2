"""Spotify OAuth and data enrichment API endpoints."""
import json
import logging
import secrets
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import asyncio
from openrouter import OpenRouter

from backend_v2.auth.dependencies import get_current_user_http
from backend_v2.db.session import get_async_session
from backend_v2.models.user import User
from backend_v2.models.spotify_context import SpotifyUserContext
from backend_v2.integrations.spotify import SpotifyOAuth
from backend_v2.schemas.spotify_enrichment import get_enrichment_schema
from backend_v2.config import OPENROUTER_API_KEY
from backend_v2.utils.time import utc_now, ensure_utc

logger = logging.getLogger("ai-dj.api.spotify")

router = APIRouter(prefix="/api/v1/spotify", tags=["spotify"])

# In-memory storage for PKCE state (in production, use Redis or similar)
_pkce_store: Dict[str, Dict[str, Any]] = {}


def get_spotify_client() -> SpotifyOAuth:
    """Get Spotify OAuth client from environment."""
    import os
    client_id = os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
    redirect_uri = os.getenv("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8000/api/v1/spotify/callback")
    
    if not client_id:
        raise HTTPException(status_code=500, detail="Spotify client ID not configured")
    
    return SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri
    )


async def enrich_spotify_data_with_ai(spotify_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Enrich Spotify data using OpenRouter AI.
    
    Args:
        spotify_data: Aggregated Spotify data
    
    Returns:
        Enriched data dictionary or None on error
    """
    if not OPENROUTER_API_KEY:
        logger.warning("OpenRouter API key not configured, skipping AI enrichment")
        return None
    
    schema = get_enrichment_schema()
    
    # Build comprehensive prompt
    prompt_parts = [
        "Analyze the following comprehensive Spotify user data and extract detailed insights:",
        "",
        "1. Favorite Artists: Identify top favorite artists across all time ranges, including their genres, popularity, and why they might be favorites.",
        "2. Favorite Songs: Identify favorite songs from top tracks across all time ranges, including artist, album, and why they're favorites.",
        "3. Last Listened To: Analyze recently played tracks and identify patterns in what they're listening to now.",
        "4. Top Played: Organize top tracks and artists by time range (short_term=last 4 weeks, medium_term=last 6 months, long_term=all time).",
        "5. Favorite Tracks Stats: Extract favorite tracks with their rank and time_range for DJ speech hooks.",
        "6. User Profile Summary: Create a comprehensive profile including listener type, music discovery style, and listening patterns.",
        "7. Playlist Analysis: Analyze playlists to identify themes, favorite playlists, and playlist creation style.",
        "8. Music Preferences: Extract genres, energy levels, moods, tempo ranges, and decade preferences.",
        "9. Listening Habits: Analyze when they listen, how often, playlist vs album preference, discovery methods, and repeat behavior.",
        "10. Genres Analysis: Identify primary genres, genre diversity, and how genres evolve across time ranges.",
        "11. Mood Analysis: Identify dominant moods, mood patterns, and how mood affects listening choices.",
        "",
        "Spotify Data:",
        json.dumps(spotify_data, indent=2),
        "",
        "Provide a comprehensive, detailed analysis that captures the user's complete music profile and preferences."
    ]
    
    prompt = "\n".join(prompt_parts)
    
    messages = [
        {
            "role": "system",
            "content": "You are a music analysis expert. Analyze Spotify user data and extract their music preferences and listening profile. Respond with valid JSON matching the provided schema."
        },
        {
            "role": "user",
            "content": prompt
        }
    ]
    
    payload = {
        "model": "google/gemini-2.0-flash-001",  # 1M context, fast
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 4000,  # Increased for complete response
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "spotify_enrichment",
                "strict": True,
                "schema": schema
            }
        }
    }
    
    try:
        logger.info("Sending request to OpenRouter via httpx...")
        
        # Use direct httpx call instead of SDK (SDK hangs on response parsing)
        import httpx
        
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json",  # Prevent streaming response
            "HTTP-Referer": "https://jamify.jamiearmoordon.co.uk",
            "X-Title": "Jamify AI DJ"
        }
        
        request_body = {
            "model": payload["model"],
            "messages": payload["messages"],
            "temperature": payload["temperature"],
            "response_format": payload["response_format"],
            "stream": False,  # Explicitly disable streaming
        }
        
        # Create client without context manager to debug hanging
        logger.info("Creating httpx client...")
        client = httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0, read=30.0))
        
        try:
            logger.info("Sending httpx POST...")
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=request_body
            )
            logger.info(f"POST returned, status: {response.status_code}")
            
            response.raise_for_status()
            
            # Explicitly read response content
            logger.info("Reading response body...")
            content_bytes = await response.aread()
            logger.info(f"Read {len(content_bytes)} bytes")
            
            logger.info("Parsing JSON...")
            result = json.loads(content_bytes.decode('utf-8'))
            logger.info(f"JSON parsed successfully")
        finally:
            logger.info("Closing httpx client...")
            await client.aclose()
            logger.info("Client closed")
        
        logger.info(f"OpenRouter response received: {len(str(result))} chars")
        
        # Extract content from response
        if result.get('choices') and len(result['choices']) > 0:
            content = result['choices'][0]['message'].get('content', '')
        else:
            logger.error("No choices in OpenRouter response")
            return None
        
        if not content:
            logger.error("No content in OpenRouter response")
            return None
        
        logger.info(f"OpenRouter content: {len(content)} chars")
        
        # Parse JSON response
        logger.info("Parsing JSON response...")
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as e:
            # Log the problematic part of the content
            error_pos = e.pos if hasattr(e, 'pos') else len(content)
            logger.error(f"JSON parse error at position {error_pos}: {e}")
            logger.error(f"Content around error: ...{content[max(0, error_pos-100):error_pos+100]}...")
            
            # Try to fix common truncation issues by finding last valid JSON
            # Look for last complete object
            for end_pos in range(len(content), 0, -1):
                try:
                    parsed = json.loads(content[:end_pos] + "}")
                    logger.warning(f"Recovered truncated JSON by adding closing brace")
                    break
                except:
                    try:
                        parsed = json.loads(content[:end_pos] + "}}")
                        logger.warning(f"Recovered truncated JSON by adding two closing braces")
                        break
                    except:
                        continue
            else:
                return None
        
        logger.info("Successfully enriched Spotify data with AI")
        return parsed
                
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse OpenRouter JSON response: {e}")
        return None
    except httpx.HTTPStatusError as e:
        logger.error(f"OpenRouter HTTP error: {e.response.status_code} - {e.response.text}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error in OpenRouter call: {e}")
        import traceback
        logger.debug(traceback.format_exc())
        return None


async def _fetch_spotify_data_sync(db: AsyncSession, user_id: str, access_token: str):
    """Fetch and enrich Spotify data synchronously.
    
    Called during OAuth callback - blocks redirect until complete.
    This ensures data is available for voice onboarding agent.
    """
    logger.info(f"Starting synchronous Spotify data fetch for user {user_id}")
    
    try:
        # Get user's Spotify context
        stmt = select(SpotifyUserContext).where(SpotifyUserContext.user_id == user_id)
        result = await db.execute(stmt)
        spotify_context = result.scalar_one_or_none()
        
        if not spotify_context:
            logger.error(f"No Spotify context found for user {user_id}")
            return
        
        # Fetch comprehensive Spotify data
        spotify_client = get_spotify_client()
        try:
            spotify_data = await spotify_client.aggregate_user_data(access_token)
        except Exception as e:
            logger.error(f"Failed to fetch Spotify data for user {user_id}: {e}")
            return
        
        # Store raw data
        spotify_context.top_artists_json = json.dumps(spotify_data["top_artists"])
        spotify_context.top_tracks_json = json.dumps(spotify_data["top_tracks"])
        spotify_context.recently_played_json = json.dumps(spotify_data["recently_played"])
        spotify_context.playlists_json = json.dumps(spotify_data["playlists"])
        
        # Enrich with AI
        logger.info(f"Starting AI enrichment for user {user_id}")
        enriched_data = await enrich_spotify_data_with_ai(spotify_data)
        
        if enriched_data:
            logger.info(f"Storing enriched data for user {user_id}")
            spotify_context.music_preferences_json = json.dumps(enriched_data.get("music_preferences", {}))
            spotify_context.listening_habits_json = json.dumps(enriched_data.get("listening_habits", {}))
            spotify_context.genres_analysis_json = json.dumps(enriched_data.get("genres_analysis", {}))
            spotify_context.mood_analysis_json = json.dumps(enriched_data.get("mood_analysis", {}))
            spotify_context.favorite_tracks_with_stats_json = json.dumps(enriched_data.get("favorite_tracks_stats", []))
        
        spotify_context.last_synced_at = utc_now()
        spotify_context.updated_at = utc_now()
        
        await db.commit()
        logger.info(f"Successfully fetched and enriched Spotify data for user {user_id}")
        
    except Exception as e:
        logger.error(f"Spotify data fetch failed for user {user_id}: {e}")
        import traceback
        logger.debug(traceback.format_exc())


@router.get("/authorize")
async def authorize_spotify(
    user: User = Depends(get_current_user_http),
):
    """Generate Spotify OAuth authorization URL with PKCE.
    
    Returns:
        Authorization URL and session ID for tracking
    """
    spotify_client = get_spotify_client()
    
    # Generate PKCE pair and state
    auth_url, code_verifier, original_state = spotify_client.get_authorization_url()
    
    # Generate session ID
    session_id = secrets.token_urlsafe(32)
    
    # Encode session_id into the state parameter (format: "original_state:session_id")
    # This allows us to pass session_id through the OAuth flow without modifying redirect_uri
    combined_state = f"{original_state}:{session_id}"
    
    # Replace state in auth_url with combined state
    auth_url = auth_url.replace(f"state={original_state}", f"state={combined_state}")
    
    # Store PKCE data temporarily (expires in 10 minutes)
    _pkce_store[session_id] = {
        "code_verifier": code_verifier,
        "state": original_state,  # Store original state for validation
        "user_id": user.id,
        "expires_at": datetime.utcnow() + timedelta(minutes=10)
    }
    
    logger.info(f"Generated Spotify auth URL for user {user.id}, session {session_id}")
    
    return {
        "auth_url": auth_url,
        "session_id": session_id
    }


@router.get("/callback")
async def spotify_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_async_session),
):
    """Handle Spotify OAuth callback.
    
    Exchanges authorization code for tokens and stores them.
    State parameter format: "original_state:session_id"
    """
    # Extract session_id from state parameter
    # Format: "original_state:session_id"
    if ":" not in state:
        raise HTTPException(status_code=400, detail="Invalid state parameter format")
    
    try:
        original_state, session_id = state.rsplit(":", 1)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid state parameter format")
    
    # Retrieve PKCE data
    pkce_data = _pkce_store.get(session_id)
    if not pkce_data:
        raise HTTPException(status_code=400, detail="Invalid or expired session")
    
    # Check expiration
    if datetime.utcnow() > pkce_data["expires_at"]:
        del _pkce_store[session_id]
        raise HTTPException(status_code=400, detail="Session expired")
    
    # Verify state matches original
    if original_state != pkce_data["state"]:
        del _pkce_store[session_id]
        raise HTTPException(status_code=400, detail="State mismatch - possible CSRF attack")
    
    code_verifier = pkce_data["code_verifier"]
    user_id = pkce_data["user_id"]
    
    # Clean up PKCE data
    del _pkce_store[session_id]
    
    # Exchange code for tokens
    spotify_client = get_spotify_client()
    try:
        token_data = await spotify_client.exchange_code_for_tokens(code, code_verifier)
    except Exception as e:
        logger.error(f"Failed to exchange code for tokens: {e}")
        raise HTTPException(status_code=400, detail="Failed to exchange authorization code")
    
    access_token = token_data["access_token"]
    refresh_token = token_data["refresh_token"]
    expires_in = token_data["expires_in"]
    
    # Get user profile to get Spotify ID
    try:
        profile = await spotify_client.get_user_profile(access_token)
        spotify_id = profile["id"]
    except Exception as e:
        logger.error(f"Failed to fetch Spotify profile: {e}")
        raise HTTPException(status_code=400, detail="Failed to fetch Spotify profile")
    
    # Check if user already has Spotify context
    stmt = select(SpotifyUserContext).where(SpotifyUserContext.user_id == user_id)
    result = await db.execute(stmt)
    spotify_context = result.scalar_one_or_none()
    
    if spotify_context:
        # Update existing context
        spotify_context.spotify_id = spotify_id
        spotify_context.access_token = access_token
        spotify_context.refresh_token = refresh_token
        spotify_context.token_expires_at = utc_now() + timedelta(seconds=expires_in)
        spotify_context.updated_at = utc_now()
    else:
        # Create new context
        spotify_context = SpotifyUserContext(
            user_id=user_id,
            spotify_id=spotify_id,
            access_token=access_token,
            refresh_token=refresh_token,
            token_expires_at=utc_now() + timedelta(seconds=expires_in)
        )
        db.add(spotify_context)
    
    # Update user's spotify_connected_at
    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    if user:
        user.spotify_connected_at = utc_now()
    
    await db.commit()
    
    logger.info(f"Successfully connected Spotify for user {user_id}")
    
    # Fetch and enrich Spotify data SYNCHRONOUSLY before redirect
    # This ensures data is available for voice onboarding agent
    await _fetch_spotify_data_sync(db, user_id, access_token)
    
    # Redirect to frontend success page
    import os
    frontend_base = os.getenv("FRONTEND_URL", "http://localhost:5173")
    frontend_url = f"{frontend_base}/spotify-connected"
    return RedirectResponse(url=frontend_url)


@router.post("/fetch")
async def fetch_spotify_data(
    user: User = Depends(get_current_user_http),
    db: AsyncSession = Depends(get_async_session),
):
    """Fetch Spotify data and enrich with AI analysis.
    
    This endpoint:
    1. Fetches comprehensive Spotify data (top tracks/artists, playlists, etc.)
    2. Enriches data with AI analysis
    3. Stores everything in the database
    """
    # Get user's Spotify context
    stmt = select(SpotifyUserContext).where(SpotifyUserContext.user_id == user.id)
    result = await db.execute(stmt)
    spotify_context = result.scalar_one_or_none()
    
    if not spotify_context:
        raise HTTPException(status_code=404, detail="Spotify not connected")
    
    # Check if token needs refresh
    token_expires_at = ensure_utc(spotify_context.token_expires_at)
    if utc_now() >= token_expires_at:
        spotify_client = get_spotify_client()
        try:
            token_data = await spotify_client.refresh_access_token(spotify_context.refresh_token)
            spotify_context.access_token = token_data["access_token"]
            spotify_context.token_expires_at = utc_now() + timedelta(seconds=token_data["expires_in"])
            await db.commit()
        except Exception as e:
            logger.error(f"Failed to refresh Spotify token: {e}")
            raise HTTPException(status_code=401, detail="Failed to refresh Spotify token")
    
    # Release any existing transaction before long-running I/O
    # This ensures we don't hold a DB lock while fetching from Spotify/OpenRouter
    await db.commit()
    
    # Fetch comprehensive Spotify data
    spotify_client = get_spotify_client()
    try:
        spotify_data = await spotify_client.aggregate_user_data(spotify_context.access_token)
    except Exception as e:
        logger.error(f"Failed to fetch Spotify data: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch Spotify data")
    
    # Store raw data
    spotify_context.top_artists_json = json.dumps(spotify_data["top_artists"])
    spotify_context.top_tracks_json = json.dumps(spotify_data["top_tracks"])
    spotify_context.recently_played_json = json.dumps(spotify_data["recently_played"])
    spotify_context.playlists_json = json.dumps(spotify_data["playlists"])
    
    # Enrich with AI
    logger.info(f"Starting AI enrichment for user {user.id}")
    enriched_data = await enrich_spotify_data_with_ai(spotify_data)
    logger.info(f"AI enrichment completed for user {user.id}, enriched_data={'exists' if enriched_data else 'None'}")
    
    if enriched_data:
        # Store enriched data
        logger.info(f"Storing enriched data for user {user.id}")
        try:
            spotify_context.music_preferences_json = json.dumps(enriched_data.get("music_preferences", {}))
            spotify_context.listening_habits_json = json.dumps(enriched_data.get("listening_habits", {}))
            spotify_context.genres_analysis_json = json.dumps(enriched_data.get("genres_analysis", {}))
            spotify_context.mood_analysis_json = json.dumps(enriched_data.get("mood_analysis", {}))
            spotify_context.favorite_tracks_with_stats_json = json.dumps(enriched_data.get("favorite_tracks_stats", []))
            logger.info(f"JSON serialization complete for user {user.id}")
        except Exception as e:
            logger.error(f"Error serializing enriched data for user {user.id}: {e}")
            # Continue anyway with raw data stored
    
    spotify_context.last_synced_at = utc_now()
    spotify_context.updated_at = utc_now()
    
    logger.info(f"Committing database changes for user {user.id}")
    await db.commit()
    logger.info(f"Database commit successful for user {user.id}")
    
    logger.info(f"Successfully fetched and enriched Spotify data for user {user.id}")
    
    # Ensure last_synced_at is properly formatted
    synced_at_iso = spotify_context.last_synced_at.isoformat() if spotify_context.last_synced_at else None
    
    logger.info(f"Returning success response for user {user.id}")
    
    return {
        "success": True,
        "message": "Spotify data fetched and enriched successfully",
        "synced_at": synced_at_iso
    }


@router.get("/status")
async def get_spotify_status(
    user: User = Depends(get_current_user_http),
    db: AsyncSession = Depends(get_async_session),
):
    """Check if user has connected Spotify.
    
    Returns:
        Connection status and Spotify ID if connected
    """
    stmt = select(SpotifyUserContext).where(SpotifyUserContext.user_id == user.id)
    result = await db.execute(stmt)
    spotify_context = result.scalar_one_or_none()
    
    if not spotify_context:
        return {
            "connected": False
        }
    
    return {
        "connected": True,
        "spotify_id": spotify_context.spotify_id,
        "last_synced_at": spotify_context.last_synced_at.isoformat() if spotify_context.last_synced_at else None
    }


@router.post("/disconnect")
async def disconnect_spotify(
    user: User = Depends(get_current_user_http),
    db: AsyncSession = Depends(get_async_session),
):
    """Disconnect Spotify and remove all stored data.
    
    Returns:
        Success message
    """
    stmt = select(SpotifyUserContext).where(SpotifyUserContext.user_id == user.id)
    result = await db.execute(stmt)
    spotify_context = result.scalar_one_or_none()
    
    if spotify_context:
        await db.delete(spotify_context)
    
    # Update user's spotify_connected_at
    stmt = select(User).where(User.id == user.id)
    result = await db.execute(stmt)
    user_obj = result.scalar_one_or_none()
    if user_obj:
        user_obj.spotify_connected_at = None
    
    await db.commit()
    
    logger.info(f"Disconnected Spotify for user {user.id}")
    
    return {
        "success": True,
        "message": "Spotify disconnected successfully"
    }

