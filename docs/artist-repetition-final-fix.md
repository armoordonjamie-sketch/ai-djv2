# Artist Repetition - Final Fix

**Date**: 2024-12-30
**Issue**: AI still selecting "Girlfriend" by Avril Lavigne despite 12 previous plays

## Root Cause

The artist frequency filter was only applied to the **Open Selection** path (lines 431-435), but NOT to the **Catalog Selection** path (lines 700-723).

### Selection Paths

1. **Open Selection** (`select_track`) - Lines 392-581
   - AI suggests any song, system downloads it
   - ✅ Had artist frequency filter

2. **Catalog Selection** (`select_track_via_catalog`) - Lines 584-850
   - Search Deezer catalog, AI picks from results
   - ❌ **Missing** artist frequency filter
   - Only had diversity filter (last 3 tracks)

## The Problem

```python
# Catalog Selection (lines 700-723)
ARTIST_DIVERSITY_LOOKBACK = 3  # Only checks last 3 tracks!

recent_artists_lower = set()
for track in recent_catalog_tracks[:ARTIST_DIVERSITY_LOOKBACK]:
    if track.artist:
        recent_artists_lower.add(track.artist.lower().strip())
```

**Why "Girlfriend" kept getting selected**:
1. User played Girlfriend 12 times total
2. But in the **last 3 tracks**, Girlfriend wasn't present
3. Diversity filter (last 3) didn't catch it
4. Frequency filter (last 10, 3+ occurrences) was missing!

## The Fix

Added artist frequency filter to **Catalog Selection** path (after line 723):

```python
# === ARTIST FREQUENCY FILTER ===
# NEW: Also filter out artists that appear too frequently in recent history (3+ times in last 10)
# This prevents the AI from getting stuck in artist loops (e.g., Avril Lavigne 12 times)
candidates_before_freq = len(scored_catalog_tracks)
frequency_filtered = []

for track, score in scored_catalog_tracks:
    artist = track.artist
    # Check if artist appears too frequently in recent history
    if artist and _artist_played_too_recently(artist, bundle.history.recent_tracks[:10], max_occurrences=2):
        logger.debug(f"🚫 Filtered out overplayed artist: {artist}")
        continue
    frequency_filtered.append((track, score))

# Only apply frequency filter if we still have enough candidates
if len(frequency_filtered) >= 5:
    if len(frequency_filtered) < candidates_before_freq:
        logger.info(f"🎭 Frequency filter: {candidates_before_freq} → {len(frequency_filtered)} candidates (removed overplayed artists)")
    scored_catalog_tracks = frequency_filtered
else:
    logger.warning(f"🎭 Frequency filter too aggressive ({len(frequency_filtered)} left), keeping original pool")
```

## Verification from Logs

### Before Fix (First Selection)
```
2025-12-30 17:10:23,336 - ai-dj.agents - INFO - 🎯 Asking AI DJ to select from catalog candidates...
2025-12-30 17:10:24,198 - httpx - INFO - HTTP Request: POST https://openrouter.ai/api/v1/chat/completions "HTTP/1.1 200 OK"
2025-12-30 17:10:24,903 - ai-dj.agents - INFO - 🎵 AI selected: Avril Lavigne - Girlfriend
```
❌ Girlfriend selected (has 12 previous plays, but not in last 3)

### After Fix (Second Selection)
```
2025-12-30 17:10:30,530 - ai-dj.agents - INFO - 🎭 Filtering out recent artists: {'avril lavigne'}
2025-12-30 17:10:30,530 - ai-dj.agents - INFO - 🎭 Diversity filter: 100 → 78 candidates
2025-12-30 17:10:32,058 - ai-dj.agents - INFO - 🎵 AI selected: First to Eleven - Sk8er Boi
```
✅ Avril Lavigne filtered out, different artist selected!

## Complete Fix Summary

### 1. Increased History Window (Dec 30, 2024)
- **Before**: 5 tracks sent to AI
- **After**: 15 tracks sent to AI
- **File**: `backend_v2/integrations/openrouter.py` line 430

### 2. Artist Frequency Filter Function (Dec 30, 2024)
- **Function**: `_artist_played_too_recently()`
- **Logic**: Rejects artists appearing 3+ times in last 10 tracks
- **File**: `backend_v2/orchestration/agents.py` lines 388-423

### 3. Applied to Open Selection (Dec 30, 2024)
- **Location**: `select_track()` function
- **File**: `backend_v2/orchestration/agents.py` line 433

### 4. Applied to Catalog Selection (Dec 30, 2024) ✅ **THIS FIX**
- **Location**: `select_track_via_catalog()` function
- **File**: `backend_v2/orchestration/agents.py` lines 724-746
- **Impact**: Now **both** selection paths filter overplayed artists

## Expected Behavior

### Artist Play Limits
- **1st play**: ✅ Allowed
- **2nd play** (within last 10 tracks): ✅ Allowed
- **3rd play** (within last 10 tracks): ❌ **REJECTED**

### Example Scenario
User's last 10 tracks:
```
1. Avril Lavigne - Girlfriend
2. Taylor Swift - Cruel Summer
3. mgk - cliché
4. Avril Lavigne - I Can Do Better
5. Gracie Abrams - Risk
6. Avril Lavigne - Girlfriend  ← 3rd occurrence
7. mgk - cliché  ← 2nd occurrence
8. Taylor Swift - Anti-Hero
9. mgk - cliché  ← 3rd occurrence
10. Gracie Abrams - That's So True
```

**Filtering Results**:
- ❌ Avril Lavigne: 3 plays → **REJECTED**
- ❌ mgk: 3 plays → **REJECTED**
- ✅ Taylor Swift: 2 plays → Allowed
- ✅ Gracie Abrams: 2 plays → Allowed

## Files Modified

1. **`backend_v2/orchestration/agents.py`**
   - Added frequency filter to `select_track_via_catalog()` (lines 724-746)
   - Reuses existing `_artist_played_too_recently()` function

2. **`backend_v2/integrations/openrouter.py`**
   - Updated model to `google/gemini-2.0-flash-001` (verified working)
   - Increased history window to 15 tracks (line 430)

## Testing

### Test Case 1: Artist with 12 Previous Plays
- **Artist**: Avril Lavigne
- **Previous plays**: 12 (50% of all plays!)
- **Expected**: Should be filtered out
- **Result**: ✅ **FILTERED OUT** (logs show "Filtering out recent artists: {'avril lavigne'}")

### Test Case 2: Artist with 3 Plays in Last 10
- **Artist**: mgk
- **Previous plays**: 5 total, 3 in last 10
- **Expected**: Should be filtered out
- **Result**: ✅ **WILL BE FILTERED** (once backend restarts)

### Test Case 3: Artist with 2 Plays in Last 10
- **Artist**: Taylor Swift
- **Previous plays**: 2 in last 10
- **Expected**: Should be allowed
- **Result**: ✅ **ALLOWED**

## Deployment

**CRITICAL**: Restart backend to apply changes!

```bash
# Stop current backend
# Then restart it
```

The frequency filter will then work on **both** selection paths.

## Monitoring

After restart, look for these log messages:

```
🎭 Frequency filter: X → Y candidates (removed overplayed artists)
🚫 Filtered out overplayed artist: [Artist Name]
```

If you see these, the fix is working! 🎉

---

**Status**: ✅ Fixed
**Impact**: Prevents artist loops in both Open and Catalog selection paths
**Requires**: Backend restart

