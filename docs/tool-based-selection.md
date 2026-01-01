# Tool-Based Track Selection

**Date**: 2024-12-30
**Feature**: AI agents with direct database access via OpenRouter tool calling

## Overview

Upgraded the AI DJ to use OpenRouter's tool calling feature, giving the AI direct access to the database for more intelligent song selection.

## Problem Solved

### Before (Prompt-Only)
- AI received static context in prompts (last 15 tracks, top artists)
- Could not dynamically query history or check artist frequency
- Limited to information provided upfront
- No way to search library or verify song availability

### After (Tool-Based)
- AI can query database in real-time during selection
- Can check artist play counts, search library, analyze patterns
- Makes informed decisions based on fresh data
- Verifies song availability before selection

## Architecture

### Components

1. **`backend_v2/integrations/db_tools.py`**
   - Defines 6 database tools for AI agents
   - Implements tool execution functions
   - Follows OpenRouter tool calling specification

2. **`backend_v2/orchestration/tool_based_selector.py`**
   - New track selector using tool calling
   - Manages AI conversation with tool execution
   - Parses final song selection from AI response

3. **`backend_v2/integrations/openrouter.py`**
   - Updated to support `tools` and `tool_choice` parameters
   - Returns `tool_calls` in response
   - Uses `google/gemini-2.0-flash-001` (paid model, no rate limits)

## Available Tools

### 1. `get_play_history`
Query recent play history with filters:
- `user_id`: User UUID (required)
- `limit`: Max results (default 20, max 100)
- `mood_id`: Filter by mood
- `artist_name`: Filter by artist
- `hours_ago`: Only last N hours

**Example**:
```json
{
  "user_id": "d5ea43ba-222b-457f-8d16-345a22e35fdb",
  "limit": 10,
  "artist_name": "Avril Lavigne"
}
```

### 2. `get_artist_play_count`
Count artist occurrences in recent history:
- `user_id`: User UUID (required)
- `artist_name`: Artist to count (required)
- `last_n_tracks`: Check within last N tracks (default 10)

**Returns**:
```json
{
  "artist": "Avril Lavigne",
  "play_count": 5,
  "in_last_n_tracks": 10,
  "percentage": 50.0
}
```

### 3. `search_songs_in_library`
Search local library:
- `artist`: Artist name filter
- `title`: Song title filter
- `genre`: Genre filter
- `min_duration`: Min duration in seconds
- `max_duration`: Max duration in seconds
- `limit`: Max results (default 20)

**Returns**: List of songs with metadata (uuid, title, artist, bpm, energy, etc.)

### 4. `get_user_feedback`
Get user likes/dislikes:
- `user_id`: User UUID (required)
- `feedback_type`: "like", "dislike", or "all" (default "all")
- `limit`: Max results (default 50)

### 5. `get_spotify_context`
Get Spotify listening data:
- `user_id`: User UUID (required)

**Returns**: Top artists, genres, recent tracks, audio features

### 6. `analyze_listening_patterns`
Analyze listening habits:
- `user_id`: User UUID (required)
- `days`: Days to analyze (default 30)

**Returns**: Total plays, unique artists, top artists, peak listening hour, hourly distribution

## How It Works

### Selection Flow

```
1. AI receives system prompt with mood, context, and tool descriptions
2. AI decides which tools to call (e.g., get_play_history, get_artist_play_count)
3. Backend executes tools and returns results to AI
4. AI analyzes results and may call more tools
5. AI makes final selection based on all gathered data
6. Backend parses selection and acquires song
```

### Example Conversation

**User**: Select next song for mood 'Everyday Anthems'

**AI**: *Calls `get_play_history(user_id="...", limit=10)`*

**Tool Result**: 
```json
[
  {"artist": "Avril Lavigne", "title": "Girlfriend", ...},
  {"artist": "Avril Lavigne", "title": "I Can Do Better", ...},
  ...
]
```

**AI**: *Calls `get_artist_play_count(user_id="...", artist_name="Avril Lavigne", last_n_tracks=10)`*

**Tool Result**:
```json
{
  "artist": "Avril Lavigne",
  "play_count": 5,
  "percentage": 50.0
}
```

**AI**: *Sees Avril Lavigne is overplayed, calls `search_songs_in_library(genre="pop-punk", limit=20)`*

**Tool Result**: [List of 20 pop-punk songs]

**AI**: *Makes final selection*:
```json
{
  "artist": "Paramore",
  "title": "Misery Business",
  "rationale": "Matches pop-punk energy, avoids overplayed Avril Lavigne, fits mood perfectly"
}
```

## Model Configuration

### Updated Models
- **Primary**: `google/gemini-2.0-flash-001` (paid, no rate limits)
- **Lite**: `google/gemini-2.0-flash-001` (same as primary, free tier has rate limits)

### Why Gemini 2.0 Flash?
- ✅ Supports tool calling
- ✅ 1M token context window
- ✅ Fast inference
- ✅ No rate limits on paid tier
- ✅ Cost-effective ($0.075 per 1M input tokens)

### Rate Limit Issue
The free tier `google/gemini-2.0-flash-exp:free` was hitting 429 errors:
```
Provider returned error: google/gemini-2.0-flash-exp:free is temporarily rate-limited upstream
```

**Solution**: Use paid model for all requests.

## Integration Points

### Current Usage
The tool-based selector is a **new option** alongside existing selectors:
- `select_track()` - Original deterministic + LLM selector
- `select_track_via_catalog()` - Deezer catalog search + LLM selector
- `select_track_with_tools()` - **NEW** Tool-based selector

### How to Use

```python
from backend_v2.orchestration.tool_based_selector import select_track_with_tools

# In DJLoop or other orchestration code
song = await select_track_with_tools(
    db=db,
    bundle=bundle,
    state=state,
    prev_song=current_song,
    max_iterations=5,
)
```

### Fallback Strategy
If tool-based selection fails:
1. Falls back to `select_track_via_catalog()`
2. If that fails, falls back to `select_track()`
3. If all fail, returns None

## Benefits

### 1. **Dynamic Artist Frequency Checking**
AI can query `get_artist_play_count()` in real-time instead of relying on static history in prompt.

### 2. **Library Verification**
AI can search library before suggesting songs, reducing acquisition failures.

### 3. **Pattern Analysis**
AI can analyze listening patterns to understand user preferences better.

### 4. **Adaptive Selection**
AI can adjust strategy based on tool results (e.g., if artist is overplayed, search for alternatives).

### 5. **Transparency**
Tool calls are logged, making AI decision-making more transparent.

## Monitoring

### Logs to Watch

```
🤖 Tool-based selection iteration 1/5
🔧 Executing tool: get_play_history with args: {...}
✅ Tool result: [...]
🎵 AI final response: {...}
```

### Metrics
- Tool call count per selection
- Tool execution time
- Selection success rate
- Fallback rate

## Testing

### Test Cases

1. **Artist Frequency Check**
   - AI should call `get_artist_play_count()` for overplayed artists
   - Should avoid selecting artists with 3+ plays in last 10 tracks

2. **Library Search**
   - AI should call `search_songs_in_library()` to find alternatives
   - Should verify song exists before selection

3. **Pattern Analysis**
   - AI should call `analyze_listening_patterns()` for new users
   - Should adapt to user's listening habits

4. **Feedback Integration**
   - AI should call `get_user_feedback()` to avoid disliked songs
   - Should prioritize liked artists/genres

## Future Enhancements

### Potential New Tools

1. **`get_mood_history`**: Analyze which moods user plays most
2. **`get_song_metadata`**: Fetch detailed metadata for a specific song
3. **`get_similar_songs`**: Find songs similar to a given track
4. **`get_transition_candidates`**: Find songs that transition well from current track

### Advanced Features

1. **Multi-Agent System**: Different agents for different tasks (selection, transition planning, etc.)
2. **Tool Chaining**: AI can chain multiple tools for complex queries
3. **Caching**: Cache tool results to reduce database queries
4. **Parallel Tool Calls**: Execute multiple tools simultaneously

## Files Modified

1. **`backend_v2/integrations/openrouter.py`**
   - Added `tools` and `tool_choice` parameters to `chat_completion()`
   - Updated model to `google/gemini-2.0-flash-001`
   - Return `tool_calls` in response

2. **`backend_v2/integrations/db_tools.py`** (NEW)
   - 6 tool definitions following OpenRouter spec
   - Tool execution functions
   - Tool executor with error handling

3. **`backend_v2/orchestration/tool_based_selector.py`** (NEW)
   - Tool-based track selector
   - Agentic loop with tool calling
   - JSON parsing for final selection

4. **`backend_v2/orchestration/agents.py`**
   - Added frequency filter to catalog selection (completed earlier)

## Deployment

**Status**: ✅ Ready for testing
**Requires**: Backend restart to load new modules

```bash
# Restart backend
# Test tool-based selection
```

## Documentation

- OpenRouter Tool Calling: https://openrouter.ai/docs/guides/features/tool-calling
- Gemini 2.0 Flash: https://openrouter.ai/models/google/gemini-2.0-flash-001

---

**Status**: ✅ Implemented
**Impact**: AI agents can now query database directly for intelligent song selection
**Next Steps**: Test integration and monitor tool usage

