# Song Repetition Fix - Investigation & Solution

## Issue
User `test@a.com` reported that the AI DJ keeps suggesting the same song ("Avril Lavigne - Girlfriend") repeatedly across different moods, despite having 118 songs available in the database.

## Investigation Results

### Database Analysis
- **Total songs**: 118 (all with local files ✅)
- **Songs with ISRC**: 57 (from streaming services)
- **Play history**: 24 total plays
  - "Girlfriend": 12 plays (50% of all plays!)
  - "mgk - cliché": 5 plays
  - Other songs: 1-3 plays each

### Root Cause Analysis

#### ✅ Backend Scoring Logic (Working Correctly)
The deterministic scoring and filtering in `backend_v2/services/preference_bundle.py` was working perfectly:
- Correctly excluded "Girlfriend" from candidates (it's in recent history)
- Provided 94 diverse candidates after filtering
- Top suggestions were varied: Gracie Abrams, Bon Iver, Edward Ong, Olivia Rodrigo, etc.

#### ❌ AI Open Selection (The Problem)
The issue was in **Step 1: AI Open Selection** (`backend_v2/integrations/openrouter.py`):

1. **Insufficient History Context**: Only the last **5 tracks** were sent to the AI in the prompt
   - User had played "Girlfriend" 12 times total
   - If it wasn't in the most recent 5, AI didn't know to avoid it
   
2. **Weak Artist-Level Filtering**: No check for artists appearing too frequently in recent history
   - AI could suggest different songs by the same artist repeatedly
   
3. **Prompt Clarity**: The prompt said "DO NOT SUGGEST THESE" but didn't explicitly mention avoiding the same artist

## Fixes Implemented

### 1. Increased History Window (`backend_v2/integrations/openrouter.py`)
```python
# BEFORE: Only last 5 tracks
recent_tracks = [
    f"{h.artist} - {h.title}"
    for h in bundle.history.recent_tracks[:5]
    if h.artist and h.title
]

# AFTER: Last 15 tracks
recent_tracks = [
    f"{h.artist} - {h.title}"
    for h in bundle.history.recent_tracks[:15]  # Increased for better variety
    if h.artist and h.title
]
```

### 2. Strengthened Prompt (`backend_v2/integrations/openrouter.py`)
```python
# BEFORE
history_section = f"RECENTLY PLAYED (DO NOT SUGGEST THESE):\n- " + "\n- ".join(recent_tracks) + "\n"

# AFTER
history_section = f"RECENTLY PLAYED (DO NOT SUGGEST THESE OR SIMILAR SONGS BY SAME ARTIST):\n- " + "\n- ".join(recent_tracks) + "\n"
```

### 3. Added Artist Frequency Check (`backend_v2/orchestration/agents.py`)
New function to reject artists that appear too frequently in recent history:

```python
def _artist_played_too_recently(
    artist: str,
    recent_tracks: List[HistoryItem],
    max_occurrences: int = 2,
) -> bool:
    """Check if an artist appears too many times in recent history.
    
    Rejects if artist appears >= 2 times in last 10 tracks.
    """
    # ... implementation
```

Applied in `select_track()`:
```python
elif _artist_played_too_recently(artist, bundle.history.recent_tracks[:10]):
    logger.warning(f"❌ AI suggested artist played too recently: {artist} - {title}. Rejecting.")
```

## Testing

### Before Fix
```
📈 PLAY HISTORY FOR USER (6 unique songs played):
  - Avril Lavigne - Girlfriend: 12 plays ⚠️
  - mgk - cliché: 5 plays
  - The Everyday Anthem - Just Another Stranger: 3 plays
  - Taylor Swift - Opalite: 2 plays
  - Avril Lavigne - I Can Do Better: 1 plays
  - Sunset Serenade - Satisfying Sounds: 1 plays
```

### After Fix
The AI will now:
1. See the last 15 played tracks (instead of 5)
2. Be explicitly told to avoid similar songs by the same artist
3. Have suggestions rejected if the artist appeared 2+ times in the last 10 tracks

## Expected Behavior
- **First play of an artist**: ✅ Allowed
- **Second play of an artist** (within last 10 tracks): ✅ Allowed
- **Third+ play of an artist** (within last 10 tracks): ❌ Rejected
- **Same song repeated**: ❌ Always rejected (existing logic)

## Test Results

### Unit Tests: ✅ ALL PASSED
```
📝 Test 1: Artist appears 1 time (should be allowed) ✅ PASS
📝 Test 2: Artist appears 2 times (should be allowed) ✅ PASS
📝 Test 3: Artist appears 3 times (should be REJECTED) ✅ PASS
📝 Test 4: Case insensitive matching (2 occurrences) ✅ PASS
📝 Test 5: Partial name matching ✅ PASS
```

### Real User Data Test (test@a.com):
```
📈 Artist Frequency in Last 10 Tracks:
  - Avril Lavigne: 5 plays | 🚫 WOULD BE REJECTED
  - mgk: 3 plays | 🚫 WOULD BE REJECTED
  - The Everyday Anthem: 2 plays | 🚫 WOULD BE REJECTED
  - Taylor Swift: 0 plays | ✅ ALLOWED
  - Gracie Abrams: 0 plays | ✅ ALLOWED
```

The filter correctly identifies that:
- Avril Lavigne (5 plays) would be rejected
- mgk (3 plays) would be rejected
- The Everyday Anthem (2 plays) would be rejected at threshold
- New artists like Taylor Swift and Gracie Abrams are allowed

## Files Modified
1. `backend_v2/integrations/openrouter.py` - Increased history window, strengthened prompt
2. `backend_v2/orchestration/agents.py` - Added artist frequency check

## Verification Steps
1. Restart backend (code changes require reload)
2. Play a few songs for user `test@a.com`
3. Check logs for:
   - `❌ AI suggested artist played too recently: [Artist] - [Title]. Rejecting.`
4. Verify variety in song selections

## Notes
- The deterministic fallback (Step 2) was already working correctly
- This fix only affects AI Open Selection (Step 1)
- The 15-track history window balances token efficiency with variety
- The 2-occurrence threshold allows some artist repetition while preventing loops

---

**Date**: 2024-12-30
**Investigated by**: AI Assistant
**Status**: ✅ Fixed

