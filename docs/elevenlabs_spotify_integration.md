# ElevenLabs Agent Spotify Integration

## Overview

Updated the ElevenLabs onboarding agent to access and utilize user's Spotify listening data during the voice onboarding conversation. This enables personalized music discovery based on the user's actual listening history.

## Changes Made

### 1. Updated System Prompt (`backend_v2/scripts/setup_elevenlabs_agent.py`)

**Added Spotify Integration Section:**
- Instructs the agent to call `get_spotify_context` early in the conversation
- Guides the agent to use Spotify data as a starting point for exploration
- Teaches natural referencing of user's listening history
- Example: "I see you love [artist from Spotify] - let me play their latest hit"
- Example: "You had this on repeat last month!"

**Key Instructions:**
- Call the tool AFTER initial greeting
- Use Spotify data as exploration starting point
- Reference top tracks naturally without explicitly mentioning "Spotify data"
- Act like you already know their taste

### 2. Added New Tool: `get_spotify_context`

**Tool Definition:**
```python
{
    "type": "webhook",
    "name": "get_spotify_context",
    "description": "Get the user's Spotify listening data if they've connected their account",
    "api_schema": {
        "url": "https://jamify.jamiearmoordon.co.uk/api/v1/deezer/spotify-context",
        "method": "POST"
    }
}
```

**Returns:**
- `has_spotify`: Boolean indicating if user connected Spotify
- `top_artists`: List of top 5 artists (medium term = last 6 months)
- `top_tracks`: List of top 5 tracks with play stats (title, artist, rank, time_range)
- `favorite_genres`: List of favorite genres from AI analysis
- `listening_summary`: Natural language summary of listening habits

### 3. Created Backend Endpoint (`backend_v2/api/deezer_tools.py`)

**New Endpoint:** `POST /api/v1/deezer/spotify-context`

**Functionality:**
1. Validates onboarding tool secret
2. Queries `SpotifyUserContext` table for user's data
3. Extracts and formats top artists (medium term priority)
4. Extracts top tracks with play statistics
5. Extracts favorite genres from AI analysis
6. Builds natural language summary
7. Returns formatted response for LLM consumption

**Response Format:**
```json
{
  "has_spotify": true,
  "top_artists": ["Taylor Swift", "Ed Sheeran", "Olivia Rodrigo"],
  "top_tracks": [
    {
      "title": "Anti-Hero",
      "artist": "Taylor Swift",
      "rank": 1,
      "time_range": "last 6 months"
    }
  ],
  "favorite_genres": ["pop", "indie pop", "dance pop"],
  "listening_summary": "This user listens daily. Top artists: Taylor Swift, Ed Sheeran, Olivia Rodrigo. Favorite genres: pop, indie pop, dance pop."
}
```

## Usage Flow

### 1. User with Spotify Connected

```
User: "Hey"
Agent: "Hey! I'm about to be your DJ — what's the last song that got stuck in your head?"
[Agent calls get_spotify_context internally]
Agent: "Actually, I see you're into Taylor Swift! Let me play something from her latest album..."
[Plays preview]
Agent: "You feeling this?"
```

### 2. User without Spotify

```
User: "Hey"
Agent: "Hey! I'm about to be your DJ — what's the last song that got stuck in your head?"
[Agent calls get_spotify_context - returns has_spotify: false]
[Agent proceeds with normal conversation flow]
```

### 3. Referencing Play History

```
Agent: "You had this on repeat last month! Want something similar?"
[Based on rank and time_range from top_tracks]
```

## Benefits

### For Users
- **Instant Personalization**: Agent knows their taste from the start
- **Natural Experience**: Feels like talking to someone who knows your music
- **Faster Onboarding**: Less time spent explaining preferences
- **Accurate Results**: Based on real listening data, not guesses

### For the Agent
- **Better Starting Point**: Real data instead of cold start
- **Contextual Recommendations**: Can reference actual play counts
- **Improved Accuracy**: Uses proven listening history
- **Natural Conversation**: Can reference user's favorites authentically

## Technical Details

### Database Access
- Queries `spotify_user_context` table via SQLAlchemy
- Parses JSON fields: `top_artists_json`, `favorite_tracks_with_stats_json`, `genres_analysis_json`, `listening_habits_json`
- Handles missing data gracefully (returns `has_spotify: false`)

### Security
- Uses `X-Onboard-Secret` header for authentication
- Only accessible via ElevenLabs agent webhook
- No sensitive token data exposed (only listening preferences)

### Performance
- Lightweight query (single table lookup)
- Response timeout: 10 seconds
- Minimal data transfer (top 5 of each category)
- Cached in agent conversation context

## Tool Priority

The new Spotify tool is listed as **Tool #0** (before all other tools) to emphasize its importance:

```
## SPOTIFY TOOL (Use This First!)

### 0. get_spotify_context
**When to use**: EARLY in conversation (after greeting)
**Action**: get_spotify_context() → Returns user's top artists, tracks, and preferences
**How to use**: If data exists, start exploration with their top artists/tracks
**If no data**: Proceed normally with conversation flow
```

## Example Conversations

### Scenario 1: Spotify User Loves Pop

```
User: "Hi"
Agent: [calls get_spotify_context]
Agent: "Hey! I see you're big on Taylor Swift and Olivia Rodrigo - let me play their latest collab style track..."
[Plays similar artist from related_artists]
User: "Love it!"
Agent: "Nice! You had 'Anti-Hero' on repeat last month, right? Let me try another Swift-inspired banger..."
```

### Scenario 2: Spotify User with Eclectic Taste

```
User: "What's up"
Agent: [calls get_spotify_context]
Agent: "Hey! Your Spotify is wild - everything from Frank Ocean to Daft Punk! Let me play something that matches that range..."
[Uses favorite_genres to guide selection]
```

### Scenario 3: No Spotify Connection

```
User: "Hello"
Agent: [calls get_spotify_context - returns has_spotify: false]
Agent: "Hey! I'm about to be your DJ — what's the last song that got stuck in your head?"
[Proceeds with normal flow]
```

## Testing

To test the Spotify integration:

1. **Update the Agent:**
   ```bash
   cd backend_v2/scripts
   python setup_elevenlabs_agent.py
   ```

2. **Connect Spotify** (as user):
   - Navigate to `/connect-spotify`
   - Authorize Spotify
   - Complete data fetch

3. **Start Voice Onboarding:**
   - Navigate to `/onboarding`
   - Begin conversation
   - Notice agent references your Spotify data naturally

4. **Check Agent Behavior:**
   - Agent should call `get_spotify_context` early
   - Agent should reference your top artists
   - Agent should mention play counts naturally
   - Agent should use your genres to guide exploration

## Files Modified

- ✅ `backend_v2/scripts/setup_elevenlabs_agent.py` - Added tool definition and updated prompt
- ✅ `backend_v2/api/deezer_tools.py` - Added `/spotify-context` endpoint
- ✅ `docs/elevenlabs_spotify_integration.md` - This documentation

## Next Steps

1. **Monitor Agent Conversations**: Check if agent is calling the tool and using data effectively
2. **Refine Prompt**: Adjust based on how agent utilizes Spotify data
3. **Add More Context**: Consider exposing playlist themes or mood analysis
4. **A/B Testing**: Compare onboarding success rates with/without Spotify data
5. **Analytics**: Track how often Spotify data influences final profile

## Notes

- Tool is **optional** - agent handles gracefully if no Spotify data
- Response is **LLM-optimized** - concise with natural language summary
- Data is **time-sensitive** - uses medium_term (6 months) as primary source
- Implementation is **non-intrusive** - doesn't change existing flow for non-Spotify users
- Security is maintained - only preference data exposed, no tokens

