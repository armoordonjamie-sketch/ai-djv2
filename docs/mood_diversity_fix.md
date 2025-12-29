# Fix: Mood Diversity & AI Track Selection

## Problem

User reported that all 5 moods created during onboarding:
1. Were the same (all Pop, similar energy)
2. Had identical-sounding intro TTS

## Root Cause

The system has **AI Open Selection** that should pick ANY song and download it, but it was:
1. **Falling back to local library** (limited to 202 songs, energy range 0.6-0.85)
2. **Running intro generation in parallel** → download concurrency locks → only first download succeeded
3. **Not preventing duplicates** → Energy & Party used the same song
4. **Not logging failures** → silent fallback made it hard to debug

## Changes Made

### 1. Sequential Intro Generation (`backend_v2/services/mood_generator.py`)

**Before:** All 5 intros generated in parallel with `asyncio.gather`
**After:** Sequential generation to avoid:
- Download concurrency lock contention
- YouTube rate limiting
- Duplicate song selection

```python
# Now generates one intro at a time with detailed logging
for idx, mood_id in enumerate(progress.created_mood_ids):
    logger.info(f"Generating intro {idx+1}/{len(progress.created_mood_ids)} for mood {mood_id}")
    result = await generate_mood_intro(session, user_id, mood_id)
    # ...
```

### 2. Enhanced Logging (`backend_v2/orchestration/agents.py`)

Added emoji-prefixed logs to track Open Selection flow:
- `🎯 STEP 1: Asking AI to suggest...`
- `🎵 AI suggested: Artist - Title`
- `📥 Attempting to acquire...`
- `✅ OPEN SELECTION SUCCESS`
- `❌ Failed to acquire` / `⚠ Falling back to local library`

**Why:** Makes it obvious which mode was used and where failures occur.

### 3. Duplicate Prevention (`backend_v2/orchestration/generation.py`)

Now passes already-used intro song UUIDs to `select_track`:

```python
# Get already-used intro song UUIDs
used_intro_uuids = [uuid for mood in user_moods if mood.intro_song_uuid]

selected = await select_track(
    db, bundle, state,
    history_ids=used_intro_uuids  # Exclude songs already used
)
```

**Why:** Prevents Energy and Party from using the same song.

### 4. Increased Mood Match Weights (`backend_v2/services/preference_bundle.py`)

Increased energy/valence mismatch penalty from `0.2` to `0.5`:

```python
energy_diff = abs(energy - bundle.mood.energy_target)
score -= energy_diff * 0.5  # Was 0.2

valence_diff = abs(valence - bundle.mood.valence_target)
score -= valence_diff * 0.5  # Was 0.2
```

**Why:** Even when falling back to local library, this makes scoring MORE sensitive to mood differences, so it picks more extreme songs for Chill (lowest energy) and Party (highest energy).

## Expected Results

### If Open Selection Works (YouTube Downloads Succeed)

All 5 moods should get **diverse songs** downloaded from YouTube:
- Chill: Low-energy acoustic/ambient tracks
- Party: High-energy EDM/dance tracks
- Each mood gets a UNIQUE song

Logs will show:
```
🎯 STEP 1: Asking AI to suggest the perfect song (Open Choice)...
🎵 AI suggested: Artist - Title
📥 Attempting to acquire: Artist - Title
[Downloader] Searching YouTube...
[Downloader] Downloading...
✅ OPEN SELECTION SUCCESS: Artist - Title
```

### If Open Selection Fails (Downloads Timeout/Fail)

Moods will still use local library, BUT with **better diversity**:
- Chill gets the LOWEST energy song available (~0.602)
- Party gets the HIGHEST energy song available (~0.849)
- No duplicate songs across moods

Logs will show:
```
🎯 STEP 1: Asking AI to suggest the perfect song (Open Choice)...
🎵 AI suggested: Artist - Title
📥 Attempting to acquire: Artist - Title
❌ Failed to acquire: Artist - Title
⚠ STEP 2: Open Selection failed/disabled. Falling back to local library.
```

## Testing Instructions

1. **Delete existing moods:**
   ```bash
   cd C:\Users\JamiePC\Desktop\ai-djv2
   python backend_v2/scripts/delete_user_moods.py
   ```

2. **Restart backend** (if running)

3. **Create new account and onboard**

4. **Watch backend logs** for:
   - `🎯 STEP 1` messages (Open Selection attempts)
   - `✅ OPEN SELECTION SUCCESS` (downloads worked)
   - OR `❌ Failed to acquire` (downloads failed)
   - `Generating intro 1/5`, `2/5`, etc. (sequential)

5. **Check database:**
   ```bash
   python backend_v2/scripts/check_moods.py
   ```
   
   Should see:
   - 5 different songs (no duplicates)
   - More diverse energy levels
   - Potentially new songs (not from original 202)

## Fallback Plan

If downloads still fail for all moods, the increased scoring weights ensure library fallback picks more diverse songs. But we'll see WHY downloads are failing from the enhanced logs.

## Files Modified

1. `backend_v2/services/mood_generator.py` - Sequential intro generation
2. `backend_v2/orchestration/agents.py` - Enhanced logging
3. `backend_v2/orchestration/generation.py` - Duplicate prevention
4. `backend_v2/services/preference_bundle.py` - Increased mood match weights

## Documentation Added

- `docs/mood_similarity_diagnosis.md` - Full analysis of the issue
- `docs/track_selection_diagnosis.md` - Architecture explanation
- `docs/mood_diversity_fix.md` - This file

---

**Status:** Ready for testing. User should delete moods and re-onboard to see the improvements.

