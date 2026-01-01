# Spotify OAuth Production Setup

## Deployment Architecture

```
Port 8000 → jamify.jamiearmoordon.co.uk   (Backend API)
Port 5173 → app.jamiearmoordon.co.uk      (Frontend)
```

## Environment Variables Required

Add these to your `.env` file:

```bash
# Spotify API Credentials
SPOTIFY_CLIENT_ID=your_client_id_here
SPOTIFY_CLIENT_SECRET=your_client_secret_here

# Spotify OAuth Callback (BACKEND URL + path)
SPOTIFY_REDIRECT_URI=https://jamify.jamiearmoordon.co.uk/api/v1/spotify/callback

# Frontend URL (for redirects after OAuth completion)
FRONTEND_URL=https://app.jamiearmoordon.co.uk
```

## Spotify Developer Dashboard Configuration

1. Go to: https://developer.spotify.com/dashboard
2. Select your app (or create a new one)
3. Click "Edit Settings"
4. Under "Redirect URIs", add:
   ```
   https://jamify.jamiearmoordon.co.uk/api/v1/spotify/callback
   ```
5. Click "Add"
6. Click "Save" at the bottom

## OAuth Flow

```
1. User clicks "Connect Spotify" in frontend
   ↓
2. Frontend calls: GET https://jamify.jamiearmoordon.co.uk/api/v1/spotify/authorize
   ↓
3. Backend generates auth URL with PKCE and returns it
   ↓
4. Frontend redirects user to Spotify login
   ↓
5. User authorizes the app on Spotify
   ↓
6. Spotify redirects to: https://jamify.jamiearmoordon.co.uk/api/v1/spotify/callback?code=...
   ↓
7. Backend exchanges code for access token
   ↓
8. Backend saves tokens to database
   ↓
9. Backend redirects to: https://app.jamiearmoordon.co.uk/spotify-connected
   ↓
10. Frontend displays success message
```

## For Local Development

When testing locally, use these in your `.env`:

```bash
# Local Development
SPOTIFY_REDIRECT_URI=http://127.0.0.1:8000/api/v1/spotify/callback
FRONTEND_URL=http://localhost:5173

# Also add to Spotify Dashboard:
# http://127.0.0.1:8000/api/v1/spotify/callback
# http://localhost:8000/api/v1/spotify/callback (if needed)
```

## Troubleshooting

### Error: "INVALID_CLIENT: Invalid redirect URI"

**Cause**: The `SPOTIFY_REDIRECT_URI` in `.env` doesn't match what's registered in Spotify Dashboard.

**Fix**: 
1. Check your `.env` file for `SPOTIFY_REDIRECT_URI`
2. Go to Spotify Dashboard → Your App → Edit Settings → Redirect URIs
3. Ensure the URL matches EXACTLY (including `https://` and path)
4. Restart your backend server after changing `.env`

### Error: "Redirect URI mismatch" 

**Cause**: Your Spotify app in the dashboard doesn't have the redirect URI whitelisted.

**Fix**:
1. Add the URI in Spotify Dashboard (see above)
2. Make sure to click "Save"
3. Wait a few seconds for changes to propagate

### Error: "Cannot reach callback URL"

**Cause**: Your backend server isn't accessible at the configured domain.

**Fix**:
1. Verify `jamify.jamiearmoordon.co.uk` resolves to your server IP
2. Ensure port 8000 is open and backend is running
3. Check nginx/reverse proxy configuration
4. Test: `curl https://jamify.jamiearmoordon.co.uk/api/v1/spotify/status`

### Error: Redirects to localhost after OAuth

**Cause**: `FRONTEND_URL` not set in `.env` (defaults to localhost).

**Fix**:
1. Add `FRONTEND_URL=https://app.jamiearmoordon.co.uk` to `.env`
2. Restart backend server

## Security Notes

1. **Never commit `.env`** - It contains secrets!
2. **Use HTTPS in production** - OAuth requires secure callbacks
3. **Keep client_secret secure** - Don't expose in frontend code
4. **Rotate tokens** - Backend automatically refreshes access tokens
5. **Scope control** - Only request necessary Spotify permissions

## Testing the Integration

### 1. Test Authorization Endpoint
```bash
curl -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  https://jamify.jamiearmoordon.co.uk/api/v1/spotify/authorize
```

Expected: Returns `{ "auth_url": "https://accounts.spotify.com/...", "session_id": "..." }`

### 2. Test Status Endpoint
```bash
curl -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  https://jamify.jamiearmoordon.co.uk/api/v1/spotify/status
```

Expected: Returns `{ "connected": false }` (or true if already connected)

### 3. Test Full Flow
1. Navigate to: `https://app.jamiearmoordon.co.uk/connect-spotify`
2. Click "Connect Spotify"
3. Authorize on Spotify
4. Should redirect back to `https://app.jamiearmoordon.co.uk/spotify-connected`
5. Check status endpoint - should now return `connected: true`

## Code Changes Made

### ✅ Fixed in `backend_v2/api/spotify.py`

**Before:**
```python
frontend_url = "http://localhost:5173/spotify-connected"
```

**After:**
```python
import os
frontend_base = os.getenv("FRONTEND_URL", "http://localhost:5173")
frontend_url = f"{frontend_base}/spotify-connected"
```

This ensures the callback redirects to the correct frontend URL based on environment.

## Summary Checklist

- [ ] Add `SPOTIFY_CLIENT_ID` to `.env`
- [ ] Add `SPOTIFY_CLIENT_SECRET` to `.env`
- [ ] Add `SPOTIFY_REDIRECT_URI=https://jamify.jamiearmoordon.co.uk/api/v1/spotify/callback` to `.env`
- [ ] Add `FRONTEND_URL=https://app.jamiearmoordon.co.uk` to `.env`
- [ ] Add redirect URI to Spotify Dashboard
- [ ] Restart backend server
- [ ] Test OAuth flow end-to-end
- [ ] Verify user data is saved in database

## Support

If issues persist:
1. Check backend logs for errors
2. Check browser console for frontend errors
3. Verify DNS resolves correctly: `nslookup jamify.jamiearmoordon.co.uk`
4. Test API health: `curl https://jamify.jamiearmoordon.co.uk/health`

