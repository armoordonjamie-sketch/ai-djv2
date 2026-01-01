# Spotify Onboarding Test Script

This script enriches onboarding data by:
1. Authenticating with Spotify using **OAuth 2.0 PKCE** (required, secure)
2. Fetching user profile, playlists, top tracks, and top artists
3. Sending aggregated data to OpenRouter AI for analysis
4. Using structured output (JSON Schema) to extract preferences and profile summary
5. Saving results to SQLite database (`test_sp.db`)

## Authentication

### OAuth 2.0 PKCE (Required)
This project uses **only** the official Spotify Web API with OAuth 2.0 PKCE authentication, following the patterns from the [Spotify iOS Auth SDK](https://github.com/spotify/ios-auth).

**Features:**
- ✅ Secure PKCE (Proof Key for Code Exchange) flow
- ✅ Automatic token refresh
- ✅ State parameter for CSRF protection
- ✅ No passwords or cookies required
- ✅ Official Spotify authentication method

**Requirements:**
- Spotify Developer account
- Spotify app with Client ID and Client Secret
- Redirect URI configured in Spotify Dashboard

### Redirect URI Requirements

Spotify has strict requirements for redirect URIs:

- ✅ **Use `127.0.0.1` instead of `localhost`** for loopback addresses
- ✅ **HTTP is allowed** for loopback addresses (`127.0.0.1` or `[::1]`)
- ✅ **HTTPS is required** for all other redirect URIs
- ❌ **`localhost` is NOT allowed** as a redirect URI

**Migration Timeline:**
- **April 9, 2025**: New validations enforced for newly created apps
- **November 2025**: All existing apps must migrate

**Examples of valid redirect URIs:**
- `http://127.0.0.1:8000/api/spotify/callback` ✅ (loopback, HTTP allowed)
- `http://[::1]:8000/api/spotify/callback` ✅ (IPv6 loopback, HTTP allowed)
- `https://example.com/callback` ✅ (HTTPS required for non-loopback)
- `http://localhost:8000/callback` ❌ (localhost not allowed)

## Setup

### 1. Install Dependencies

**Python dependencies:**
```bash
pip install -r requirements.txt
```

### 2. Create Spotify App

1. Go to [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
2. Click "Create an app"
3. Fill in app details and accept terms
4. Copy your **Client ID** and **Client Secret**
5. Add redirect URI: `http://127.0.0.1:8000/api/spotify/callback`
   
   **Important:** Spotify requires using `127.0.0.1` instead of `localhost` for loopback addresses. This is required for all apps created after April 9, 2025, and all apps must migrate by November 2025.
6. **Add Test Users** (Required for Development Mode):
   - Go to your app settings
   - Navigate to "Users and Access" or "Edit Settings"
   - Add your Spotify account email as a test user
   - Save changes
   
   **Note:** Apps in Development Mode can only be used by registered test users. Make sure to add any account you want to test with.
7. Save your credentials

### 3. Configure Environment Variables

Create a `.env` file in the `test-sp` directory:

```bash
# Required - Spotify OAuth Configuration
SPOTIFY_CLIENT_ID=your_spotify_client_id_here
SPOTIFY_CLIENT_SECRET=your_spotify_client_secret_here
SPOTIFY_REDIRECT_URI=http://127.0.0.1:8000/api/spotify/callback

# Optional - OpenRouter API (for AI enrichment)
OPENROUTER_API_KEY=your_openrouter_api_key_here

# Optional - Server Configuration
PORT=8000
```

**Required:**
- `SPOTIFY_CLIENT_ID` - Your Spotify app Client ID (from Developer Dashboard)
- `SPOTIFY_CLIENT_SECRET` - Your Spotify app Client Secret (from Developer Dashboard)
- `SPOTIFY_REDIRECT_URI` - Must match the redirect URI in your Spotify app settings (default: `http://127.0.0.1:8000/api/spotify/callback`)
  
  **Note:** Spotify requires using `127.0.0.1` instead of `localhost` for loopback addresses. This is required for all apps created after April 9, 2025, and all apps must migrate by November 2025.

**Optional:**
- `OPENROUTER_API_KEY` - For AI enrichment of Spotify data
- `PORT` - Server port (default: 8000)

### 3. Run the Script

#### Option A: Web Interface (Recommended)

Start the FastAPI server:

```bash
python main.py
```

Then open your browser to:
```
http://localhost:8000
```

The web interface allows you to:
- Connect to Spotify using username/password or cookies
- Fetch Spotify data with a click
- View results in a nice UI
- See AI-enriched data

#### Option B: Command Line

For command-line usage, you can still run the original script logic (if you have a CLI version):

```bash
python main.py --cli
```

The script will:
- Prompt for any missing credentials
- Authenticate with Spotify using SpotAPI
- Fetch your Spotify data (profile, playlists, tracks, artists)
- Send data to OpenRouter AI for analysis
- Save raw and enriched data to `test_sp.db`
- Display a summary

## How It Works

### Authentication

Uses **OAuth 2.0 PKCE** following the [Spotify iOS Auth SDK](https://github.com/spotify/ios-auth) patterns:
- Secure PKCE flow (no client secret needed for token exchange)
- State parameter for CSRF protection
- Automatic token refresh when expired
- Official Spotify Web API authentication

### Data Fetching

- **User Profile**: Retrieved from authenticated session
- **Playlists**: All user playlists
- **Top Tracks**: Extracted from playlists (SpotAPI may not have direct "top tracks" endpoint)
- **Top Artists**: Extracted from playlists and tracks

### AI Analysis

Uses OpenRouter with Gemini 2.5 Flash to analyze Spotify data and extract:
- **Music Preferences**: Genres, energy levels, moods, tempo range
- **Profile Summary**: Listening habits, favorite artists/tracks, playlist themes

### Database

SQLite database (`test_sp.db`) with tables:
- `spotify_sessions` - Authentication sessions
- `spotify_raw_data` - Raw Spotify data (profile, playlists, tracks, artists)
- `enriched_data` - AI-analyzed preferences and profile summary

## Troubleshooting

### CAPTCHA Required

If SpotAPI requires CAPTCHA solving:
1. Use a CAPTCHA solver service (Capsolver) - requires API key
2. Import cookies from browser (recommended):
   - Log into Spotify in your browser
   - Export cookies (use browser extension or dev tools)
   - Import cookies into SpotAPI session

### Authentication Failures

- Verify your Spotify credentials are correct
- Check if Spotify requires 2FA (may need to use app password)
- Try importing cookies from browser session

### API Errors

- Verify OpenRouter API key is valid
- Check network connectivity
- Review logs for detailed error messages

## Files

- `main.py` - FastAPI server (serves web UI and API endpoints)
- `spotify_client.py` - SpotAPI authentication and data fetching
- `openrouter_client.py` - OpenRouter AI integration
- `database.py` - SQLite database operations
- `schemas.py` - JSON Schema definitions for structured output
- `static/` - Frontend files (HTML, CSS, JavaScript)
  - `index.html` - Main web interface
  - `style.css` - Styling
  - `app.js` - Frontend JavaScript
- `requirements.txt` - Python dependencies
- `.env` - Environment variables (create from `.env.example`)

## PWA iOS Integration

**Note**: This test script uses SpotAPI (username/password) which is **not suitable for PWA iOS apps**. 

For production PWA integration, see `SPOTIFY_PWA_INTEGRATION.md` for:
- Official Spotify OAuth 2.0 flow with PKCE
- PWA-compatible authentication
- iOS-specific handling
- Security best practices

The OAuth approach:
- ✅ Works in PWA iOS apps
- ✅ No CAPTCHA required
- ✅ Secure token management
- ✅ ToS compliant
- ✅ Automatic token refresh

## License

This is a test script for enriching onboarding data. Use responsibly and in accordance with Spotify's Terms of Service.

**For production use in PWA apps, implement the official OAuth flow instead.**

