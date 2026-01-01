"""FastAPI server for Spotify onboarding data enrichment test."""
import asyncio
import logging
import os
import json
from pathlib import Path
from typing import Optional, Dict, Any
from dotenv import load_dotenv

from fastapi import FastAPI, HTTPException, Request, Response, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, JSONResponse
from pydantic import BaseModel
import secrets
import httpx
from urllib.parse import urlencode, parse_qs

from spotify_oauth import SpotifyOAuth
from openrouter_client import OpenRouterClient
from database import SpotifyDatabase

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("spotify-test.main")

# Initialize FastAPI app
app = FastAPI(title="Spotify Onboarding Test")

# Mount static files
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Global state (in production, use Redis or database)
spotify_oauth: Optional[SpotifyOAuth] = None
openrouter_client: Optional[OpenRouterClient] = None
db: Optional[SpotifyDatabase] = None

# Store PKCE verifiers temporarily (use Redis in production)
pkce_verifiers: Dict[str, str] = {}  # session_id -> code_verifier
pkce_states: Dict[str, str] = {}  # session_id -> state

# In-memory session token cache (for local dev, DB is source of truth)
session_tokens_cache: Dict[int, Dict[str, Any]] = {}  # session_id -> tokens


# Pydantic models
class SpotifyFetchRequest(BaseModel):
    session_id: int


class SpotifyFetchResponse(BaseModel):
    success: bool
    summary: Dict[str, Any]
    enriched: Dict[str, Any]
    session_id: Optional[int] = None
    message: Optional[str] = None


# Initialize components on startup
@app.on_event("startup")
async def startup():
    """Initialize global components."""
    global openrouter_client, db, spotify_oauth
    
    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    if not openrouter_key:
        logger.warning("OPENROUTER_API_KEY not set. AI enrichment will be disabled.")
    else:
        openrouter_client = OpenRouterClient(openrouter_key)
    
    # Initialize Spotify OAuth (required)
    spotify_client_id = os.getenv("SPOTIFY_CLIENT_ID")
    spotify_client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
    spotify_redirect_uri = os.getenv("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8000/api/spotify/callback")
    
    if not spotify_client_id:
        logger.error("=" * 60)
        logger.error("SPOTIFY_CLIENT_ID is required but not set!")
        logger.error("=" * 60)
        logger.error("Please create a .env file in the test-sp directory with:")
        logger.error("  SPOTIFY_CLIENT_ID=your_client_id_here")
        logger.error("  SPOTIFY_CLIENT_SECRET=your_client_secret_here")
        logger.error("  SPOTIFY_REDIRECT_URI=http://127.0.0.1:8000/api/spotify/callback")
        logger.error("")
        logger.error("Get your credentials from: https://developer.spotify.com/dashboard")
        logger.error("See .env.example for a template")
        logger.error("=" * 60)
        raise ValueError(
            "SPOTIFY_CLIENT_ID environment variable is required. "
            "Please create a .env file with your Spotify app credentials. "
            "See .env.example for a template."
        )
    
    spotify_oauth = SpotifyOAuth(
        client_id=spotify_client_id,
        client_secret=spotify_client_secret,
        redirect_uri=spotify_redirect_uri
    )
    logger.info("Spotify OAuth initialized with PKCE")
    
    db = SpotifyDatabase()
    logger.info("Server initialized")


@app.get("/")
async def root():
    """Serve the main HTML page."""
    index_path = static_dir / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return {"message": "Frontend not found. Please check static files."}


@app.get("/api/config")
async def get_config():
    """Get configuration including OAuth availability."""
    return {
        "spotify_oauth_enabled": spotify_oauth is not None
    }


@app.post("/api/spotify/fetch", response_model=SpotifyFetchResponse)
async def fetch_spotify_data(request: SpotifyFetchRequest):
    """Fetch Spotify data and enrich with AI using OAuth tokens.
    
    Requires a session_id with valid OAuth tokens.
    """
    try:
        if not db:
            raise HTTPException(status_code=500, detail="Database not initialized")
        
        if not spotify_oauth:
            raise HTTPException(
                status_code=500,
                detail="Spotify OAuth not initialized. This should not happen."
            )
        
        # Get tokens from database
        tokens = session_tokens_cache.get(request.session_id)
        if not tokens:
            tokens = db.get_session_tokens(request.session_id)
            if tokens:
                session_tokens_cache[request.session_id] = tokens
        
        if not tokens or not tokens.get('access_token'):
            raise HTTPException(
                status_code=401,
                detail="No access token found for this session. Please connect via OAuth first."
            )
        
        access_token = tokens['access_token']
        refresh_token = tokens.get('refresh_token')
        expires_at = tokens.get('expires_at')
        
        # Check if token is expired
        from datetime import datetime, timedelta
        if expires_at and isinstance(expires_at, str):
            try:
                expires_at = datetime.fromisoformat(expires_at)
            except (ValueError, TypeError):
                expires_at = None
        
        token_expired = expires_at and expires_at <= datetime.now()
        
        if token_expired:
            # Try to refresh if refresh token exists
            if refresh_token and spotify_oauth:
                try:
                    logger.info(f"Token expired for session {request.session_id}, attempting refresh...")
                    new_token_data = await spotify_oauth.refresh_access_token(refresh_token)
                    
                    new_access_token = new_token_data.get('access_token')
                    new_expires_in = new_token_data.get('expires_in', 3600)
                    new_refresh_token = new_token_data.get('refresh_token', refresh_token)  # Keep old if not provided
                    
                    new_expires_at = datetime.now() + timedelta(seconds=new_expires_in)
                    
                    # Update database
                    db.update_session_tokens(
                        request.session_id,
                        new_access_token,
                        new_refresh_token,
                        new_expires_at
                    )
                    
                    # Update cache
                    tokens = {
                        "access_token": new_access_token,
                        "refresh_token": new_refresh_token,
                        "expires_at": new_expires_at
                    }
                    session_tokens_cache[request.session_id] = tokens
                    access_token = new_access_token
                    
                    token_preview = f"{new_access_token[:4]}...{new_access_token[-4:]}" if len(new_access_token) > 8 else "***"
                    logger.info(f"Token refreshed for session {request.session_id} (token: {token_preview})")
                except Exception as e:
                    logger.error(f"Token refresh failed: {e}")
                    raise HTTPException(
                        status_code=401,
                        detail="Access token expired and refresh failed. Please reconnect via OAuth."
                    )
            else:
                raise HTTPException(
                    status_code=401,
                    detail="Access token expired and no refresh token available. Please reconnect via OAuth."
                )
        
        # Fetch Spotify data using OAuth token
        logger.info(f"Fetching Spotify data for session {request.session_id}...")
        aggregated_data = await spotify_oauth.aggregate_user_data(access_token)
        
        if not aggregated_data:
            raise HTTPException(
                status_code=500,
                detail="Failed to fetch Spotify data"
            )
        
        # Get or create session
        session = db.get_session(request.session_id)
        if not session:
            # Create session from profile
            profile = aggregated_data.get('profile', {})
            user_id = profile.get('id')
            user_email = profile.get('email')
            request.session_id = db.create_session(user_id, user_email)
            # Update tokens for new session
            if tokens:
                db.update_session_tokens(
                    request.session_id,
                    tokens['access_token'],
                    tokens.get('refresh_token'),
                    tokens.get('expires_at')
                )
        
        # Save structured data to database
        logger.info("Saving structured data to database...")
        
        # Save user profile
        if aggregated_data.get('profile'):
            db.save_user_profile(request.session_id, aggregated_data['profile'])
            db.save_raw_data(request.session_id, 'profile', aggregated_data['profile'])
        
        # Save playlists
        if aggregated_data.get('playlists'):
            db.save_playlists(request.session_id, aggregated_data['playlists'])
            db.save_raw_data(request.session_id, 'playlists', aggregated_data['playlists'])
        
        # Save top tracks for all time ranges
        top_tracks = aggregated_data.get('top_tracks', {})
        if isinstance(top_tracks, dict):
            for time_range in ['short_term', 'medium_term', 'long_term']:
                if top_tracks.get(time_range):
                    db.save_top_tracks(request.session_id, time_range, top_tracks[time_range])
                    db.save_raw_data(request.session_id, f'top_tracks_{time_range}', top_tracks[time_range])
        else:
            # Backward compatibility
            db.save_raw_data(request.session_id, 'top_tracks', top_tracks)
        
        # Save top artists for all time ranges
        top_artists = aggregated_data.get('top_artists', {})
        if isinstance(top_artists, dict):
            for time_range in ['short_term', 'medium_term', 'long_term']:
                if top_artists.get(time_range):
                    db.save_top_artists(request.session_id, time_range, top_artists[time_range])
                    db.save_raw_data(request.session_id, f'top_artists_{time_range}', top_artists[time_range])
        else:
            # Backward compatibility
            db.save_raw_data(request.session_id, 'top_artists', top_artists)
        
        # Save recently played tracks
        if aggregated_data.get('recently_played'):
            db.save_recently_played(request.session_id, aggregated_data['recently_played'])
            db.save_raw_data(request.session_id, 'recently_played', aggregated_data['recently_played'])
        
        logger.info(f"Fetched data: {aggregated_data.get('summary', {})}")
        
        # Enrich with AI
        enriched_result = None
        if openrouter_client:
            logger.info("Sending data to OpenRouter for comprehensive AI analysis...")
            enriched_result = await openrouter_client.analyze_spotify_data(aggregated_data)
            
            if enriched_result:
                # Save expanded enriched data
                db.save_enriched_data_expanded(request.session_id, enriched_result)
                logger.info("Successfully enriched data with comprehensive AI analysis")
            else:
                logger.warning("Failed to get enriched data from OpenRouter")
        else:
            logger.warning("OpenRouter client not available. Skipping AI enrichment.")
        
        return SpotifyFetchResponse(
            success=True,
            summary=aggregated_data.get('summary', {}),
            enriched=enriched_result or {},
            session_id=request.session_id,
            message="Data fetched and enriched successfully"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching Spotify data: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Fetch error: {str(e)}"
        )


@app.get("/api/spotify/get-session")
async def get_session():
    """Get a new session ID for OAuth or cookie capture."""
    session_id = secrets.token_urlsafe(16)
    return {"session_id": session_id}


@app.get("/api/spotify/oauth/authorize")
async def spotify_oauth_authorize(request: Request):
    """Generate Spotify OAuth authorization URL with PKCE."""
    if not spotify_oauth:
        return JSONResponse(
            status_code=500,
            content={
                "error": "OAuth not initialized",
                "message": "Spotify OAuth is not initialized. This should not happen.",
                "available": False
            }
        )
    
    session_id = request.query_params.get('session_id') or secrets.token_urlsafe(16)
    
    # Generate authorization URL with PKCE (following iOS SDK pattern)
    auth_url, code_verifier, state = spotify_oauth.get_authorization_url()
    
    # Store code verifier and state for later exchange and validation
    pkce_verifiers[session_id] = code_verifier
    pkce_states[session_id] = state
    
    logger.info(f"Generated OAuth URL for session {session_id} with PKCE")
    
    return JSONResponse({
        "auth_url": auth_url,
        "session_id": session_id,
        "state": state
    })


@app.get("/api/spotify/callback")
async def spotify_oauth_callback(
    request: Request,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None
):
    """Handle Spotify OAuth callback and exchange code for tokens."""
    if error:
        logger.error(f"Spotify OAuth error: {error}")
        return HTMLResponse(f"""
        <!DOCTYPE html>
        <html>
        <head><title>Spotify Login Error</title></head>
        <body style="font-family: sans-serif; padding: 40px; text-align: center;">
            <h1>❌ Login Failed</h1>
            <p>Error: {error}</p>
            <p>This window will close automatically...</p>
            <script>
                setTimeout(() => window.close(), 3000);
            </script>
        </body>
        </html>
        """)
    
    if not code:
        return HTMLResponse("""
        <!DOCTYPE html>
        <html>
        <head><title>Spotify Login Error</title></head>
        <body style="font-family: sans-serif; padding: 40px; text-align: center;">
            <h1>❌ No authorization code received</h1>
            <p>This window will close automatically...</p>
            <script>
                setTimeout(() => window.close(), 3000);
            </script>
        </body>
        </html>
        """)
    
    # Validate state parameter (CSRF protection - following iOS SDK pattern)
    session_id = None
    if state:
        # Find session_id by state
        for sid, stored_state in pkce_states.items():
            if stored_state == state:
                session_id = sid
                break
    
    # Fallback to query param if state not found
    if not session_id:
        session_id = request.query_params.get('session_id')
    
    if not session_id or session_id not in pkce_verifiers:
        logger.error(f"Invalid session or state mismatch. Session: {session_id}, State: {state}")
        return HTMLResponse("""
        <!DOCTYPE html>
        <html>
        <head><title>Spotify Login Error</title></head>
        <body style="font-family: sans-serif; padding: 40px; text-align: center;">
            <h1>❌ Invalid session or security validation failed</h1>
            <p>Please try connecting again.</p>
            <p>This window will close automatically...</p>
            <script>
                setTimeout(() => window.close(), 3000);
            </script>
        </body>
        </html>
        """)
    
    # Validate state matches stored state
    if state and session_id in pkce_states:
        if pkce_states[session_id] != state:
            logger.error(f"State mismatch for session {session_id}")
            return HTMLResponse("""
            <!DOCTYPE html>
            <html>
            <head><title>Spotify Login Error</title></head>
            <body style="font-family: sans-serif; padding: 40px; text-align: center;">
                <h1>❌ Security validation failed</h1>
                <p>State parameter mismatch. Please try again.</p>
                <p>This window will close automatically...</p>
                <script>
                    setTimeout(() => window.close(), 3000);
                </script>
            </body>
            </html>
            """)
    
    code_verifier = pkce_verifiers.pop(session_id)
    pkce_states.pop(session_id, None)  # Clean up state
    
    try:
        # Exchange code for tokens
        token_data = await spotify_oauth.exchange_code_for_tokens(code, code_verifier)
        
        access_token = token_data.get('access_token')
        refresh_token = token_data.get('refresh_token')
        expires_in = token_data.get('expires_in', 3600)
        scope = token_data.get('scope', '')
        
        # Log granted scopes for debugging
        if scope:
            logger.info(f"Token granted with scopes: {scope}")
        else:
            logger.warning("No scope information in token response")
        
        # Check if required scopes are present
        required_scopes = ['user-read-private', 'user-read-email']
        granted_scopes_list = scope.split() if scope else []
        missing_scopes = [s for s in required_scopes if s not in granted_scopes_list]
        
        if missing_scopes:
            logger.warning(f"Missing required scopes: {missing_scopes}")
            logger.warning(f"Requested scopes: {spotify_oauth.scope}")
            logger.warning(f"Granted scopes: {scope}")
        
        # Get user profile
        try:
            user_profile = await spotify_oauth.get_user_profile(access_token)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403:
                error_detail = e.response.text
                logger.error("=" * 60)
                logger.error("403 Forbidden - Access Denied")
                logger.error("=" * 60)
                logger.error(f"Requested scopes: {spotify_oauth.scope}")
                logger.error(f"Granted scopes: {scope}")
                if missing_scopes:
                    logger.error(f"Missing required scopes: {missing_scopes}")
                logger.error(f"API Error Response: {error_detail}")
                logger.error("")
                
                # Check if it's a "user not registered" error
                if "user may not be registered" in error_detail.lower() or "not be registered" in error_detail.lower():
                    logger.error("⚠️  ISSUE: User Not Registered as Test User")
                    logger.error("")
                    logger.error("Your Spotify app is in Development Mode and requires test users.")
                    logger.error("")
                    logger.error("SOLUTION:")
                    logger.error("1. Go to https://developer.spotify.com/dashboard")
                    logger.error("2. Click on your app")
                    logger.error("3. Go to 'Users and Access' or 'Edit Settings'")
                    logger.error("4. Add your Spotify account email as a test user")
                    logger.error("5. Save changes")
                    logger.error("6. Try authorizing again")
                    logger.error("")
                    logger.error("Note: Only users added as test users can use the app in Development Mode.")
                else:
                    logger.error("Possible causes:")
                    logger.error("1. User denied required scopes during authorization")
                    logger.error("2. Spotify app doesn't have required scopes enabled in Dashboard")
                    logger.error("3. Token doesn't include 'user-read-private' or 'user-read-email'")
                    logger.error("")
                    logger.error("Solution:")
                    logger.error("- Re-authorize and make sure to grant ALL requested permissions")
                    logger.error("- Check your Spotify app settings in Developer Dashboard")
                    logger.error("- Ensure 'user-read-private' and 'user-read-email' are enabled")
                
                logger.error("=" * 60)
            raise
        user_id = user_profile.get('id')
        user_email = user_profile.get('email')
        
        # Save tokens to database
        from datetime import datetime, timedelta
        expires_at = datetime.now() + timedelta(seconds=expires_in)
        
        # Create or update session in database
        session_id_db = db.create_session(user_id, user_email)
        
        # Save tokens to database
        db.update_session_tokens(
            session_id_db,
            access_token,
            refresh_token,
            expires_at
        )
        
        # Cache tokens
        session_tokens_cache[session_id_db] = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_at": expires_at
        }
        
        token_preview = f"{access_token[:4]}...{access_token[-4:]}" if len(access_token) > 8 else "***"
        logger.info(f"OAuth successful for user {user_id}, session {session_id_db} (token: {token_preview})")
        
        return HTMLResponse(f"""
        <!DOCTYPE html>
        <html>
        <head><title>Spotify Login Success</title></head>
        <body style="font-family: sans-serif; padding: 40px; text-align: center; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; min-height: 100vh; display: flex; align-items: center; justify-content: center;">
            <div>
                <h1>✅ Login Successful!</h1>
                <p>Spotify account connected via OAuth.</p>
                <p>This window will close automatically...</p>
            </div>
            <script>
                if (window.opener) {{
                    window.opener.postMessage({{
                        type: 'spotify-oauth-success',
                        session_id: {session_id_db},
                        tokens: {json.dumps({"access_token": access_token, "refresh_token": refresh_token})}
                    }}, '*');
                }}
                setTimeout(() => window.close(), 2000);
            </script>
        </body>
        </html>
        """)
        
    except Exception as e:
        logger.error(f"OAuth token exchange failed: {e}")
        return HTMLResponse(f"""
        <!DOCTYPE html>
        <html>
        <head><title>Spotify Login Error</title></head>
        <body style="font-family: sans-serif; padding: 40px; text-align: center;">
            <h1>❌ Token Exchange Failed</h1>
            <p>Error: {str(e)}</p>
            <p>This window will close automatically...</p>
            <script>
                setTimeout(() => window.close(), 3000);
            </script>
        </body>
        </html>
        """)


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "openrouter_configured": openrouter_client is not None,
        "database_configured": db is not None
    }


if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("PORT", 8000))
    logger.info(f"Starting server on http://localhost:{port}")
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=True,
        log_level="info"
    )
