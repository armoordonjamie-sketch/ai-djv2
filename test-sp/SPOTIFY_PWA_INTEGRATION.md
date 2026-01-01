# Spotify Integration for PWA iOS App (Using SpotAPI)

## Overview

This guide shows how to integrate SpotAPI authentication in a PWA iOS app by handling authentication **server-side** through your backend. The PWA never directly uses SpotAPI - it communicates with your backend API which handles SpotAPI authentication and data fetching.

## Architecture: Backend Proxy Pattern

The key is to **proxy SpotAPI through your backend** so the PWA doesn't need to handle:
- ❌ CAPTCHA solving
- ❌ Cookie management
- ❌ Direct SpotAPI library usage
- ❌ Session persistence

Instead:
- ✅ PWA sends credentials to backend (secure HTTPS)
- ✅ Backend handles SpotAPI authentication
- ✅ Backend manages sessions/cookies
- ✅ Backend fetches Spotify data
- ✅ Backend returns data to PWA

For a PWA iOS app, use **SpotAPI through a backend proxy** - the backend handles all SpotAPI operations.

### Architecture

```
┌─────────────┐         ┌──────────────┐         ┌─────────────┐
│   PWA App   │─────────▶│   Backend    │─────────▶│   Spotify   │
│  (iOS/Web)  │          │   (FastAPI)  │          │  OAuth API  │
└─────────────┘         └──────────────┘         └─────────────┘
      │                         │                         │
      │ 1. Request auth URL     │                         │
      │◀────────────────────────│                         │
      │                         │                         │
      │ 2. Redirect to Spotify  │                         │
      │──────────────────────────────────────────────────▶│
      │                         │                         │
      │ 3. User authorizes      │                         │
      │◀─────────────────────────────────────────────────│
      │                         │                         │
      │ 4. Callback with code   │                         │
      │────────────────────────▶│                         │
      │                         │                         │
      │                         │ 5. Exchange code+PKCE  │
      │                         │───────────────────────▶│
      │                         │                         │
      │                         │ 6. Access token        │
      │                         │◀───────────────────────│
      │                         │                         │
      │ 7. Token stored         │                         │
      │◀────────────────────────│                         │
```

## Implementation Steps

### 1. Backend: SpotAPI Proxy Endpoints

Create new endpoints in `backend_v2/api/` that use SpotAPI server-side:

**File: `backend_v2/api/spotify_auth.py`**

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
import json
import os
from pathlib import Path

from backend_v2.db.session import get_async_session
from backend_v2.models.user import User
from backend_v2.auth.dependencies import get_current_user_http

# Import SpotAPI (install in backend requirements)
from spotapi import Login, Config, NoopLogger, JSONSaver, User as SpotAPIUser, PrivatePlaylist

router = APIRouter(prefix="/spotify", tags=["spotify"])

class SpotifyCredentials(BaseModel):
    email: str
    password: str
    cookies: Optional[dict] = None  # Optional cookie import

class SpotifyDataResponse(BaseModel):
    profile: dict
    playlists: list
    top_tracks: list
    top_artists: list

@router.post("/auth/connect")
async def spotify_connect(
    credentials: SpotifyCredentials,
    user: User = Depends(get_current_user_http),
    db: AsyncSession = Depends(get_async_session),
):
    """Authenticate with Spotify using SpotAPI (server-side).
    
    The backend handles SpotAPI authentication, so the PWA doesn't need to.
    """
    try:
        # Create session directory for this user
        session_dir = Path("data/spotify_sessions")
        session_dir.mkdir(parents=True, exist_ok=True)
        session_path = session_dir / f"{user.id}.json"
        
        # Initialize SpotAPI
        cfg = Config(logger=NoopLogger())
        
        # Try cookie import first if provided
        if credentials.cookies:
            session_data = {
                "identifier": credentials.email,
                "cookies": credentials.cookies
            }
            with open(session_path, 'w') as f:
                json.dump(session_data, f)
            
            try:
                saver = JSONSaver()
                login_instance = Login.from_saver(saver, str(session_path))
                if login_instance:
                    # Save successful session
                    login_instance.save(saver)
                    return {"success": True, "method": "cookies"}
            except Exception as e:
                logger.warning(f"Cookie import failed: {e}, trying password")
        
        # Fallback to username/password
        login_instance = Login(cfg, credentials.password, email=credentials.email)
        login_instance.login()
        
        # Save session for future use
        saver = JSONSaver()
        login_instance.save(saver)
        
        # Also save to our session file
        session_data = {
            "identifier": credentials.email,
            "cookies": login_instance.base.cookies if hasattr(login_instance, 'base') else {}
        }
        with open(session_path, 'w') as f:
            json.dump(session_data, f)
        
        # Store session reference in database (optional)
        # You could add a spotify_sessions table to track active sessions
        
        return {"success": True, "method": "password"}
        
    except Exception as e:
        logger.error(f"Spotify authentication failed: {e}")
        raise HTTPException(400, f"Authentication failed: {str(e)}")

@router.get("/data")
async def get_spotify_data(
    user: User = Depends(get_current_user_http),
    db: AsyncSession = Depends(get_async_session),
):
    """Fetch Spotify data using stored SpotAPI session."""
    session_path = Path("data/spotify_sessions") / f"{user.id}.json"
    
    if not session_path.exists():
        raise HTTPException(401, "Spotify not connected")
    
    try:
        # Load session
        saver = JSONSaver()
        login_instance = Login.from_saver(saver, str(session_path))
        
        if not login_instance:
            raise HTTPException(401, "Invalid session")
        
        # Fetch data using SpotAPI
        spotify_user = SpotAPIUser(login_instance)
        playlist_client = PrivatePlaylist(login_instance)
        
        # Get profile
        profile = {"email": user.email, "authenticated": True}
        
        # Get playlists
        playlists = []
        if hasattr(playlist_client, 'get_playlists'):
            playlists = playlist_client.get_playlists()
        elif hasattr(playlist_client, 'list_playlists'):
            playlists = playlist_client.list_playlists()
        
        # Get tracks from playlists (extract top tracks)
        all_tracks = []
        for playlist in playlists[:20]:
            playlist_id = playlist.get('id') if isinstance(playlist, dict) else getattr(playlist, 'id', None)
            if playlist_id:
                tracks = playlist_client.get_playlist_tracks(playlist_id) if hasattr(playlist_client, 'get_playlist_tracks') else []
                all_tracks.extend(tracks)
        
        # Extract top artists from tracks
        artists = {}
        for track in all_tracks:
            artist_name = track.get('artist') if isinstance(track, dict) else getattr(track, 'artist', None)
            if artist_name:
                artists[artist_name] = artists.get(artist_name, 0) + 1
        
        top_artists = [{"name": name, "count": count} for name, count in sorted(artists.items(), key=lambda x: x[1], reverse=True)[:50]]
        
        return SpotifyDataResponse(
            profile=profile,
            playlists=playlists[:100],  # Limit for response size
            top_tracks=all_tracks[:100],
            top_artists=top_artists
        )
        
    except Exception as e:
        logger.error(f"Failed to fetch Spotify data: {e}")
        raise HTTPException(500, f"Failed to fetch data: {str(e)}")

@router.post("/auth/disconnect")
async def spotify_disconnect(
    user: User = Depends(get_current_user_http),
    db: AsyncSession = Depends(get_async_session),
):
    """Disconnect Spotify (delete session)."""
    session_path = Path("data/spotify_sessions") / f"{user.id}.json"
    if session_path.exists():
        session_path.unlink()
    return {"success": True}
```

### 2. Frontend: Spotify Connect Component

**File: `frontend/src/components/spotify/SpotifyConnect.tsx`**

```typescript
import { useState } from 'react'
import { useAuth } from '@/providers/AuthProvider'
import { api } from '@/lib/jamifyApi'

export function SpotifyConnect() {
  const { user } = useAuth()
  const [isConnecting, setIsConnecting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [useCookies, setUseCookies] = useState(false)
  const [cookieJson, setCookieJson] = useState('')

  const handleConnect = async () => {
    try {
      setIsConnecting(true)
      setError(null)
      
      let credentials: any = {}
      
      if (useCookies && cookieJson) {
        // Parse cookies JSON
        try {
          const cookies = JSON.parse(cookieJson)
          credentials = { cookies }
        } catch (e) {
          setError('Invalid cookies JSON format')
          setIsConnecting(false)
          return
        }
      } else {
        // Get credentials from user input
        const email = prompt('Enter your Spotify email:')
        const password = prompt('Enter your Spotify password:', { type: 'password' })
        
        if (!email || !password) {
          setIsConnecting(false)
          return
        }
        
        credentials = { email, password }
      }
      
      // Send to backend - backend handles SpotAPI authentication
      const response = await api.post('/spotify/auth/connect', credentials)
      
      if (response.success) {
        // Success! Backend has authenticated and saved session
        alert('Spotify connected successfully!')
        // Refresh page or update UI
        window.location.reload()
      }
      
    } catch (error: any) {
      console.error('Spotify connection failed:', error)
      setError(error.message || 'Connection failed. Try using cookies instead.')
      setIsConnecting(false)
    }
  }

  return (
    <div className="spotify-connect">
      <h3>Connect Spotify</h3>
      
      <div className="auth-options">
        <label>
          <input 
            type="radio" 
            checked={!useCookies} 
            onChange={() => setUseCookies(false)}
          />
          Username/Password
        </label>
        <label>
          <input 
            type="radio" 
            checked={useCookies} 
            onChange={() => setUseCookies(true)}
          />
          Import Cookies (Recommended if login fails)
        </label>
      </div>
      
      {useCookies && (
        <div className="cookie-input">
          <p>Paste cookies JSON from browser DevTools:</p>
          <textarea
            value={cookieJson}
            onChange={(e) => setCookieJson(e.target.value)}
            placeholder='{"sp_dc": "...", "sp_key": "..."}'
            rows={4}
          />
          <small>
            Get cookies: F12 → Application → Cookies → open.spotify.com
          </small>
        </div>
      )}
      
      {error && <div className="error">{error}</div>}
      
      <button 
        onClick={handleConnect} 
        disabled={isConnecting || (useCookies && !cookieJson)}
      >
        {isConnecting ? 'Connecting...' : 'Connect Spotify'}
      </button>
    </div>
  )
}
```

### 3. PWA iOS Considerations

Since authentication happens **server-side**, the PWA just needs to:
1. Collect credentials (email/password or cookies)
2. Send to backend API
3. Backend handles all SpotAPI complexity

**For iOS PWA:**
- ✅ No popup/redirect needed (backend handles it)
- ✅ No CAPTCHA in PWA (backend can handle or use cookies)
- ✅ Secure credential transmission (HTTPS)
- ✅ Session managed server-side

**Cookie Import Option:**
- User can get cookies from Safari (not in PWA)
- Paste cookies JSON in the PWA form
- Backend uses cookies to authenticate
- No CAPTCHA needed

### 4. iOS PWA Specific Handling

```typescript
// Detect iOS PWA for better UX
const isIOSPWA = /iPad|iPhone|iPod/.test(navigator.userAgent) && 
                 (window.matchMedia('(display-mode: standalone)').matches || 
                  (window.navigator as any).standalone === true)

// For iOS PWA, recommend cookie import (more reliable)
if (isIOSPWA) {
  // Show instructions for getting cookies from Safari
  // User opens Safari, logs into Spotify, gets cookies
  // Pastes cookies in PWA form
}
```

### 5. Cookie Import Instructions Component

**File: `frontend/src/components/spotify/CookieInstructions.tsx`**

```typescript
export function CookieInstructions() {
  return (
    <div className="cookie-instructions">
      <h4>How to get Spotify cookies (iOS):</h4>
      <ol>
        <li>Open Safari (not PWA)</li>
        <li>Go to <a href="https://open.spotify.com" target="_blank">open.spotify.com</a></li>
        <li>Log into your Spotify account</li>
        <li>Press Share button → "Show Web Inspector" (if enabled)</li>
        <li>Or use a cookie export extension</li>
        <li>Copy cookies as JSON: <code>{"sp_dc": "...", "sp_key": "..."}</code></li>
        <li>Paste in the form above</li>
      </ol>
      <p><strong>Alternative:</strong> Use username/password (may require CAPTCHA solving on backend)</p>
    </div>
  )
}
```

## Database Schema

Add to `backend_v2/models/`:

```python
class SpotifyToken(Base):
    __tablename__ = "spotify_tokens"
    
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
```

## Environment Variables

Add to `.env`:
```bash
SPOTIFY_CLIENT_ID=your_spotify_client_id
SPOTIFY_CLIENT_SECRET=your_spotify_client_secret
FRONTEND_URL=https://app.jamify.uk  # Or http://localhost:5173 for dev
```

## Security Considerations

1. **PKCE**: Required for mobile/PWA apps (no client secret in frontend)
2. **State Parameter**: Prevents CSRF attacks
3. **Token Storage**: Store tokens server-side, never in localStorage
4. **HTTPS**: Required for OAuth redirects in production
5. **Token Refresh**: Implement automatic refresh before expiration

## Testing in PWA

1. **Development**: Test in browser first
2. **iOS Safari**: Test in Safari before PWA
3. **PWA Standalone**: Install as PWA and test OAuth flow
4. **Network Issues**: Handle offline/network errors gracefully

## Comparison: SpotAPI vs Official OAuth

| Feature | SpotAPI (Test Script) | Official OAuth (PWA) |
|---------|----------------------|---------------------|
| **Setup** | Username/password | App credentials needed |
| **CAPTCHA** | May require | No |
| **PWA Compatible** | ❌ No | ✅ Yes |
| **iOS Compatible** | ❌ No | ✅ Yes |
| **Security** | ⚠️ Lower | ✅ Higher |
| **ToS Compliant** | ⚠️ Questionable | ✅ Yes |
| **Token Management** | Manual | Automatic |
| **Refresh Tokens** | ❌ No | ✅ Yes |

## Migration Path

1. **Phase 1**: Keep test script for development/testing
2. **Phase 2**: Implement OAuth endpoints in backend
3. **Phase 3**: Add frontend OAuth flow component
4. **Phase 4**: Integrate into onboarding flow
5. **Phase 5**: Replace test script with OAuth flow

## References

- [Spotify Authorization Guide](https://developer.spotify.com/documentation/general/guides/authorization-guide/)
- [PKCE Flow](https://developer.spotify.com/documentation/general/guides/authorization-guide/#authorization-code-flow-with-proof-key-for-code-exchange-pkce)
- [iOS PWA Constraints](https://webkit.org/blog/8042/progressive-web-apps/)

