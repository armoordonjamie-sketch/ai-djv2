# Spotify Integration Implementation Summary

## Overview

Successfully integrated Spotify OAuth user context from `test-sp` into `backend_v2`, enabling:
1. Optional Spotify login during onboarding
2. Rich user context from real Spotify listening data (including play counts and rankings)
3. AI-enriched preference analysis using OpenRouter
4. Enhanced AI agent personalization with specific listening stats
5. **DJ speech that references actual listening history** (e.g., "This track you played 23 times last month")
6. **DJ history context** fed to all AI agents for continuity and avoiding repetition

## Backend Implementation

### 1. Spotify OAuth Integration (`backend_v2/integrations/spotify.py`)
- Ported `SpotifyOAuth` class from `test-sp/spotify_oauth.py`
- PKCE OAuth 2.0 Authorization Code Flow with state/CSRF protection
- Methods: `get_authorization_url()`, `exchange_code_for_tokens()`, `refresh_access_token()`, `aggregate_user_data()`
- Tracks play counts and rankings from top tracks across all time ranges (short_term, medium_term, long_term)

### 2. Database Models

#### SpotifyUserContext (`backend_v2/models/spotify_context.py`)
- Stores OAuth tokens (access_token, refresh_token, token_expires_at)
- Raw Spotify data (JSON): top_artists, top_tracks, recently_played, playlists
- AI-enriched analysis (JSON): music_preferences, listening_habits, genres_analysis, mood_analysis
- Track statistics for DJ speech hooks: favorite_tracks_with_stats_json

#### DJSpeechHistory (`backend_v2/models/spotify_context.py`)
- Tracks recent DJ speeches for continuity
- Stores mentioned artists and tracks to avoid repetition
- Session-based tracking with timestamps

#### User Model Updates (`backend_v2/models/user.py`)
- Added `spotify_connected_at` column
- Added relationships to `SpotifyUserContext` and `DJSpeechHistory`

### 3. Spotify API Endpoints (`backend_v2/api/spotify.py`)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/spotify/authorize` | GET | Generate OAuth URL with PKCE |
| `/api/v1/spotify/callback` | GET | Handle OAuth callback, exchange code |
| `/api/v1/spotify/fetch` | POST | Fetch Spotify data and enrich with AI |
| `/api/v1/spotify/status` | GET | Check if user has connected Spotify |
| `/api/v1/spotify/disconnect` | POST | Remove Spotify connection |

### 4. AI Enrichment Schema (`backend_v2/schemas/spotify_enrichment.py`)
- Comprehensive JSON schema for OpenRouter structured output
- Includes: favorite_artists, favorite_songs, top_played (all time ranges), favorite_tracks_stats (with rankings), user_profile_summary, playlist_analysis, music_preferences, listening_habits, genres_analysis, mood_analysis

### 5. PreferenceBundle Updates (`backend_v2/services/preference_bundle.py`)

#### New Data Classes
- `DJHistoryData`: Recent speeches, topics mentioned, last mention times
- Enhanced `UserProfileData` with Spotify fields:
  - `spotify_connected`, `top_artists_*_term`, `top_tracks_with_stats`
  - `spotify_genre_analysis`, `spotify_mood_analysis`, `listening_frequency`, `playlist_themes`

#### Updated `build_preference_bundle()`
- Loads Spotify context from database
- Parses top artists (short/medium/long term)
- Parses favorite tracks with play statistics
- Loads AI-enriched genre and mood analysis
- Loads recent DJ speech history (last 10 speeches)
- Extracts mentioned topics for repetition avoidance

### 6. Mood Generator Enhancements (`backend_v2/services/mood_generator.py`)
- Uses Spotify top artists (medium term) as primary seed artists
- Enhances genres with Spotify genre analysis
- Uses user's actual top artists as `example_artists` in mood templates
- Prioritizes real listening data over template defaults

### 7. Track Selector Enhancements (`backend_v2/catalog/selector.py`)
- Enhanced `search_catalog_tracks()` to use Spotify top artists
- Adds top 5 artists from Spotify medium_term to search queries
- Logs when Spotify artists are used for enhanced search

### 8. Speech Writer Enhancements (`backend_v2/orchestration/agents.py`)

#### New Helper Function: `get_spotify_track_context()`
- Detects if current track is from user's Spotify top tracks
- Returns rank, time_range, title, artist for DJ speech hooks
- Fuzzy matching for track/artist names

#### Enhanced `write_transition_speech()`
- Checks if next song is from Spotify top tracks
- Adds `spotify_hook` to context if match found
- Includes recent DJ speeches in banter history to avoid repetition

#### Enhanced `persist_segment()`
- Saves DJ speech to `DJSpeechHistory` table
- Extracts mentioned artists and tracks from speech text
- Invalidates preference bundle cache to include new history

### 9. OpenRouter Prompt Enhancements (`backend_v2/integrations/openrouter.py`)

#### Enhanced `build_profile_context()`
- Adds Spotify listening data section
- Shows top 5 tracks with rankings and time ranges
- Includes Spotify genre analysis and listening frequency

#### Enhanced `generate_dj_speech()`
- Adds Spotify hook guidance when track is from user's top tracks
- Example: "This track is #3 in user's last 6 months top tracks! Mention it naturally"
- Adds DJ history guidance to avoid repeating recent topics
- Formats time ranges as human-readable labels (last month, last 6 months, all time)

### 10. Database Migration (`backend_v2/migrations/versions/002_spotify_and_dj_history.py`)
- Creates `spotify_user_context` table
- Creates `dj_speech_history` table
- Adds `spotify_connected_at` column to `users` table
- Includes proper indexes for performance

## Frontend Implementation

### 1. API Client (`frontend/src/lib/jamifyApi.ts`)
- `getSpotifyAuthUrl()`: Get OAuth URL and session ID
- `getSpotifyStatus()`: Check connection status
- `fetchSpotifyData()`: Fetch and enrich Spotify data
- `disconnectSpotify()`: Remove Spotify connection

### 2. SpotifyConnect Component (`frontend/src/components/SpotifyConnect.tsx`)
- Handles Spotify OAuth flow with popup window
- Opens OAuth in centered popup (600x700)
- Polls for popup close and checks connection status
- Shows loading state during connection
- Callbacks for success/error handling

### 3. SpotifyConnectPage (`frontend/src/pages/SpotifyConnectPage.tsx`)
- Optional step before voice onboarding
- Explains benefits:
  - Personalized selections based on real listening data
  - Smart recommendations from actual habits
  - Personalized DJ banter ("This track you played 23 times last month!")
- Shows loading state during AI enrichment
- "Connect Spotify" and "Skip for Now" options
- Navigates to voice onboarding after connection

### 4. App Routing (`frontend/src/App.tsx`)
- Added `/connect-spotify` route (protected, before onboarding)
- Imports and registers `SpotifyConnectPage`

### 5. Settings Page (`frontend/src/pages/SettingsPage.tsx`)
- New "Spotify Integration" section
- Shows connection status with green badge if connected
- "Disconnect Spotify" option with confirmation dialog
- "Connect Spotify" button if not connected
- Loads status on page mount

## Key Features

### 1. Spotify Track Detection for DJ Speech
When the DJ plays a track that's in the user's Spotify top tracks, the system:
1. Detects the match using fuzzy matching
2. Retrieves rank and time range (short/medium/long term)
3. Passes this info to the AI as a "Spotify hook"
4. AI naturally mentions it: "I see you had this on repeat last month!" or "This was your #3 most played track recently"

### 2. DJ History Tracking
The system now tracks all DJ speeches to:
1. Avoid repeating the same topics too soon
2. Maintain continuity across the session
3. Extract mentioned artists/tracks automatically
4. Feed this context to future speech generation

### 3. Enhanced Mood Generation
Moods are now personalized with:
1. User's actual Spotify top artists (last 6 months)
2. Spotify genre analysis for better genre matching
3. Real listening data instead of generic templates

### 4. Smart Track Selection
Track selection now uses:
1. Spotify top artists as primary seed artists
2. Enhanced genre matching from Spotify data
3. Better personalization based on real listening habits

## Environment Variables

Add to `.env`:

```bash
SPOTIFY_CLIENT_ID=your_client_id
SPOTIFY_CLIENT_SECRET=your_client_secret
SPOTIFY_REDIRECT_URI=http://127.0.0.1:8000/api/v1/spotify/callback
```

**Important**: Use `127.0.0.1` (not `localhost`) for the redirect URI in Spotify Developer Dashboard.

## Testing

1. **Register/Login** to the app
2. **Navigate to `/connect-spotify`** (or click "Connect Spotify" in Settings)
3. **Authorize** the app in the Spotify OAuth popup
4. **Wait for AI enrichment** (may take 10-30 seconds)
5. **Complete voice onboarding** as normal
6. **Generate moods** - they will now use your Spotify data
7. **Start streaming** - DJ will reference your Spotify listening history
8. **Check Settings** to see Spotify connection status

## Database Migration

Run the migration to create new tables:

```bash
cd backend_v2
alembic upgrade head
```

This will create:
- `spotify_user_context` table
- `dj_speech_history` table
- `spotify_connected_at` column in `users` table

## Files Created/Modified

### Backend
- ✅ `backend_v2/integrations/spotify.py` (created)
- ✅ `backend_v2/models/spotify_context.py` (created)
- ✅ `backend_v2/models/user.py` (modified)
- ✅ `backend_v2/api/spotify.py` (created)
- ✅ `backend_v2/schemas/spotify_enrichment.py` (created)
- ✅ `backend_v2/services/preference_bundle.py` (modified)
- ✅ `backend_v2/services/mood_generator.py` (modified)
- ✅ `backend_v2/catalog/selector.py` (modified)
- ✅ `backend_v2/orchestration/agents.py` (modified)
- ✅ `backend_v2/integrations/openrouter.py` (modified)
- ✅ `backend_v2/main.py` (modified - added Spotify router)
- ✅ `backend_v2/migrations/versions/002_spotify_and_dj_history.py` (created)

### Frontend
- ✅ `frontend/src/lib/jamifyApi.ts` (modified)
- ✅ `frontend/src/components/SpotifyConnect.tsx` (created)
- ✅ `frontend/src/pages/SpotifyConnectPage.tsx` (created)
- ✅ `frontend/src/App.tsx` (modified)
- ✅ `frontend/src/pages/SettingsPage.tsx` (modified)

## Next Steps

1. **Test the OAuth flow** with a real Spotify account
2. **Verify AI enrichment** is working correctly
3. **Test DJ speech** to ensure Spotify hooks are being used
4. **Monitor DJ history** to ensure repetition avoidance works
5. **Add Spotify connection prompt** to the registration flow (optional)
6. **Consider adding Spotify re-sync** functionality to refresh data periodically

## Notes

- Spotify OAuth uses PKCE for security (no client secret needed in frontend)
- AI enrichment can take 10-30 seconds depending on OpenRouter response time
- DJ speech hooks are probabilistic - AI may or may not use them in every speech
- DJ history helps maintain continuity and avoid repetitive banter
- All Spotify data is stored securely and only used for personalization
- Users can disconnect Spotify at any time from Settings

