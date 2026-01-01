# Spotify Callback Session ID Fix - December 30, 2025

## Issues Encountered

### Issue 1: Missing session_id
Spotify OAuth callback was failing with 422 error:
```json
{"detail":[{"type":"missing","loc":["query","session_id"],"msg":"Field required","input":null}],"body":null}
```

### Issue 2: Invalid redirect URI
After attempting to add session_id to redirect_uri, got error:
```
INVALID_CLIENT: Invalid redirect URI
```

Spotify requires redirect_uri to exactly match what's registered in the app settings.

## Root Cause
The backend expected `session_id` as a separate query parameter, but it wasn't being passed through the OAuth flow. The `session_id` is needed to retrieve the PKCE `code_verifier` from temporary storage.

## Solution
**Encode the `session_id` into the `state` parameter**, which is the standard OAuth way to pass custom tracking data through the authorization flow.

### Why the state parameter?
- OAuth providers always echo back the `state` parameter unchanged
- It's specifically designed for passing application-specific data
- Doesn't require modifying the registered `redirect_uri`
- Maintains CSRF protection while adding session tracking

### Backend Changes
**File**: `backend_v2/api/spotify.py`

#### 1. Modify `/authorize` endpoint to encode session_id in state
```python
@router.get("/authorize")
async def authorize_spotify(user: User = Depends(get_current_user_http)):
    spotify_client = get_spotify_client()
    
    # Generate PKCE pair and state
    auth_url, code_verifier, original_state = spotify_client.get_authorization_url()
    
    # Generate session ID
    session_id = secrets.token_urlsafe(32)
    
    # Encode session_id into the state parameter (format: "original_state:session_id")
    combined_state = f"{original_state}:{session_id}"
    
    # Replace state in auth_url
    auth_url = auth_url.replace(f"state={original_state}", f"state={combined_state}")
    
    # Store PKCE data with original state
    _pkce_store[session_id] = {
        "code_verifier": code_verifier,
        "state": original_state,  # Store original for validation
        "user_id": user.id,
        "expires_at": datetime.utcnow() + timedelta(minutes=10)
    }
    
    return {"auth_url": auth_url, "session_id": session_id}
```

#### 2. Modify `/callback` endpoint to extract session_id from state
```python
@router.get("/callback")
async def spotify_callback(
    code: str = Query(...),
    state: str = Query(...),  # Now contains "original_state:session_id"
    db: AsyncSession = Depends(get_async_session),
):
    # Extract session_id from state parameter
    if ":" not in state:
        raise HTTPException(status_code=400, detail="Invalid state format")
    
    original_state, session_id = state.rsplit(":", 1)
    
    # Retrieve PKCE data
    pkce_data = _pkce_store.get(session_id)
    if not pkce_data:
        raise HTTPException(status_code=400, detail="Invalid or expired session")
    
    # Verify original state matches
    if original_state != pkce_data["state"]:
        raise HTTPException(status_code=400, detail="State mismatch")
    
    # Continue with token exchange...
```

### Frontend Change
**File**: `frontend/src/components/SpotifyConnect.tsx`

```typescript
const handleConnect = async () => {
    setIsConnecting(true)
    
    try {
        // Get authorization URL (session_id already encoded in state by backend)
        const { auth_url } = await api.getSpotifyAuthUrl()
        
        // Open OAuth popup - no modification needed!
        const popup = window.open(auth_url, 'Spotify Login', ...)
    }
}
```

## How It Works

### Before Fix
```
1. GET /spotify/authorize
   ← { auth_url: "...&state=def&...", session_id: "abc123" }

2. Open popup with auth_url

3. Spotify redirects: /callback?code=xyz&state=def
   ❌ Backend expects session_id as separate parameter

4. Backend can't find session_id
   → 422 Error: "Field required"
```

### After Fix (Using State Parameter)
```
1. Backend generates:
   - original_state: "def"
   - session_id: "abc123"
   - combined_state: "def:abc123"
   - Stores: _pkce_store["abc123"] = {state: "def", ...}

2. GET /spotify/authorize
   ← { auth_url: "...&state=def:abc123&...", session_id: "abc123" }

3. Open popup with auth_url containing combined state

4. User authorizes on Spotify

5. Spotify redirects: /callback?code=xyz&state=def:abc123
   ✅ State parameter preserved by Spotify

6. Backend extracts:
   - Split state by ":"
   - original_state = "def"
   - session_id = "abc123"
   - Validates original_state matches stored state
   → Success!
```

## Why State Parameter?
The `state` parameter is the OAuth-standard way to pass custom data:
- **Always preserved**: OAuth providers echo it back unchanged
- **No URI modification**: Doesn't alter the registered `redirect_uri`
- **CSRF protection**: Still validates against tampering
- **Clean design**: Purpose-built for this exact use case

## Alternative Solutions Considered

### ❌ Store session_id in cookie
- Cookies might be blocked by browser privacy settings
- Additional security concerns with SameSite attributes
- Complex cookie management across domains

### ❌ Modify redirect_uri to include session_id
- **Tried first, but failed with "INVALID_CLIENT"**
- Spotify requires exact match with registered redirect_uri
- Would need to register every possible variation
- Not scalable or maintainable

### ❌ Store session_id in browser storage (localStorage/sessionStorage)
- Vulnerable to cross-window/cross-tab issues
- Popup window might not share storage context
- Not reliable across different browser security modes

### ✅ Encode in state parameter (chosen solution)
- **OAuth standard practice** for passing custom data
- No modification to registered redirect_uri needed
- Works reliably across all browsers
- Maintains CSRF protection
- Clean separation: original_state for security, session_id for tracking

## Backend Endpoint Structure

### `/spotify/authorize` (GET)
Returns:
```json
{
    "auth_url": "https://accounts.spotify.com/authorize?...&state=ECpeO4...:RxAKFI...",
    "session_id": "RxAKFIQ13wpjxPC5XI1xYxtSIvZUOzESQQKW47nEDEo"
}
```
Note: The `state` parameter in auth_url contains "original_state:session_id"

### `/spotify/callback` (GET)
Expects query parameters:
- `code` - Spotify authorization code
- `state` - Combined format: "original_state:session_id"

The callback:
1. Splits `state` by ":" to extract session_id
2. Uses session_id to retrieve PKCE `code_verifier` from storage
3. Validates original_state matches stored state for CSRF protection
4. Exchanges code for access tokens

## Complete OAuth Flow with Popup

1. **User clicks "Connect Spotify"** on `/connect-spotify` page
2. **Frontend** calls `GET /api/v1/spotify/authorize`
3. **Backend** returns:
   - `auth_url` with encoded state: `"original_state:session_id"`
   - `session_id` for reference
4. **Frontend** opens popup window with `auth_url`
5. **User** authorizes on Spotify in popup
6. **Spotify** redirects to: `/callback?code=...&state=original_state:session_id`
7. **Backend** `/callback` endpoint:
   - Extracts session_id from state
   - Validates CSRF protection
   - Exchanges code for tokens
   - Stores tokens in database
   - Redirects to `/spotify-connected`
8. **Frontend** `/spotify-connected` page:
   - Shows success message
   - Auto-closes popup after 1.5 seconds
9. **Parent window** (SpotifyConnect component):
   - Polls to detect popup closure
   - Checks connection status via `GET /api/v1/spotify/status`
   - Calls `onSuccess()` callback
   - Navigates to `/onboarding`

## Testing Checklist
- [x] User clicks "Connect Spotify"
- [x] Popup opens with Spotify authorization
- [x] User authorizes
- [x] No 422 error (session_id properly passed)
- [x] No INVALID_CLIENT error (redirect_uri unchanged)
- [x] No 404 error (route exists)
- [x] Success page shows in popup
- [x] Popup auto-closes
- [x] Parent detects connection and proceeds to onboarding

## Files Modified
- `backend_v2/api/spotify.py` - Modified `/authorize` and `/callback` endpoints
  - `/authorize`: Encodes session_id into state parameter
  - `/callback`: Extracts session_id from state parameter, redirects to `/spotify-connected`
- `frontend/src/components/SpotifyConnect.tsx` - Simplified to use auth_url directly
- `frontend/src/pages/SpotifyConnectedPage.tsx` - **NEW** Success page that closes popup window
- `frontend/src/App.tsx` - Added `/spotify-connected` route

## Impact
- ✅ Fixes 422 error (missing session_id)
- ✅ Fixes INVALID_CLIENT error (redirect_uri mismatch)
- ✅ Enables successful Spotify OAuth flow
- ✅ Follows OAuth standard practices
- ✅ No changes needed to Spotify app settings
- ✅ Maintains CSRF protection via state validation

