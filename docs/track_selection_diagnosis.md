# Track Selection Flow - Why Moods Use Same Library Songs

## Problem

All 5 moods are being created with similar intro songs from the local library (all ~0.7 energy, all Pop), even though the system has an **AI Open Selection** feature that should allow the DJ to pick ANY song from the entire music catalog and download it.

## Current Architecture (CORRECT DESIGN)

The track selection flow in `backend_v2/orchestration/agents.py:select_track()` has **two modes**:

### Mode 1: AI Open Selection (Lines 361-409)
1. AI suggests ANY song (not limited to library)
2. Call `acquire_song_by_name(artist, title)`
3. This function:
   - Checks local cache first
   - If not found, **downloads from YouTube**
   - Returns song dict with local_path

### Mode 2: Local Library Fallback (Lines 411-478)
1. Query local database for scored candidates
2. Filter by features/mood/history
3. LLM picks from candidates
4. Fallback to top-scored candidate

**The design is correct - AI should pick any song, downloader fetches it.**

## Why It's Not Working for Intro Generation

### Investigation Results

1. **OpenRouter IS enabled** ✅ (API key present, 73 chars)
2. **Local library has limited range** ⚠️ (Energy: 0.602-0.849, no low/high energy songs)
3. **All intros used library songs** ⚠️ (not downloaded songs)

**Hypothesis:** During intro generation, AI Open Selection is **failing** or **not being tried**, so it falls back to local library immediately.

### Possible Causes

#### Cause 1: Timeout During Downloads

`acquire_song_by_name` has a **45-second timeout** (line 392 in `select_track`):
```python
acquired = await acquire_song_by_name(
    db, artist, title, timeout_seconds=45
)
```

If downloads are slow or failing:
- AI suggests a song
- Download times out or fails
- Falls back to local library
- **No error logged to user**, just silent fallback

#### Cause 2: Concurrency Lock Contention

When generating 5 moods in parallel (`asyncio.gather` in mood_generator.py line 253), all 5 intros try to download songs simultaneously.

The downloader has concurrency guards (lines 190-203 in `acquire_song_by_name`), so:
- First request acquires lock
- Other requests wait 1 second, then give up
- Result: Only 1-2 songs download, rest fall back to library

#### Cause 3: YouTube Download Failures

If yt-dlp/downloader is failing:
- Network issues
- YouTube rate limiting
- Invalid search results
- Missing ffmpeg/dependencies

#### Cause 4: AI Suggestions Getting Rejected

The Open Selection has **validation guards** (lines 374-389):
- Checks if suggestion too similar to previous
- Checks if in recent history
- Checks if artist is disliked

During intro generation with **empty history**, these should all pass, BUT if AI is suggesting the same song multiple times across moods, duplicates get rejected.

---

## Evidence from Database

Query results show:
- **5 different intro files** were created ✅
- **2 moods share the same song** (Energy & Party both use `5c10a79b-32e6-4e6f-939c-a0614c20fb6b`)
- **All songs from local library** (all have energy ~0.7, all Pop genre)

This suggests:
1. Open Selection either didn't try, OR
2. All download attempts failed/timed out

---

## Solution: Debug & Fix Open Selection for Intro Generation

### Step 1: Add Logging to Track Mode Used

In `select_track`, after a song is selected, log which mode was used:
```python
# After line 409 (AI open choice success)
logger.info(f"✓ Open Selection SUCCESS: {artist} - {title}")

# At line 412 (fallback)
logger.warning(f"⚠ Open Selection FAILED/DISABLED, falling back to library")
```

### Step 2: Serialize Intro Downloads (Not Parallel)

In `backend_v2/services/mood_generator.py:generate_personalized_moods()`, change intro generation from parallel to sequential:

```python
# BEFORE (line 248-253):
tasks = [_generate_intro_task(mid) for mid in progress.created_mood_ids]
if tasks:
    await asyncio.gather(*tasks)  # ❌ All 5 download at once

# AFTER:
for mood_id in progress.created_mood_ids:
    await _generate_intro_task(mood_id)  # ✅ One at a time
```

**Why:** This prevents concurrency lock contention and rate limiting.

### Step 3: Increase Timeout for Intro Generation

Intro generation can afford to be slower (it's a one-time setup). In `backend_v2/orchestration/generation.py:generate_mood_intro()`, when calling `select_track`, we could increase the timeout:

```python
# Around line 54, pass a custom timeout to the download
selected = await select_track(
    db, bundle, state,
    prev_song=None,
    history_ids=[],
    download_timeout=120,  # 2 minutes for intros (vs 45s default)
)
```

**But** `select_track` doesn't currently accept this parameter, so we'd need to modify the signature.

### Step 4: Fallback to More Diverse Library Songs

If downloads fail, at least make library fallback pick MORE DIVERSE songs. In `score_candidate`, **increase the weight** of energy/valence matching:

```python
# Line 856-863 in preference_bundle.py:score_candidate
energy_diff = abs(energy - bundle.mood.energy_target)
score -= energy_diff * 0.5  # ← INCREASE from 0.2 to 0.5

valence_diff = abs(valence - bundle.mood.valence_target)
score -= valence_diff * 0.5  # ← INCREASE from 0.2 to 0.5
```

**Why:** This makes the scoring MORE sensitive to mood differences, so even within the limited library range (0.6-0.85), it will pick the extremes for each mood.

### Step 5: Add Duplicate Prevention for Intros

In `select_track`, before calling `acquire_song_by_name`, check if the suggested song was already used for another mood's intro:

```python
# After line 370 (AI suggestion received)
# Check if this song was already used for another intro for this user
from backend_v2.models.mood import Mood
recent_intro_songs = await db.execute(
    select(Mood.intro_song_uuid).where(
        Mood.user_id == bundle.user_id,
        Mood.intro_song_uuid.isnot(None)
    )
)
used_intro_uuids = [uuid for (uuid,) in recent_intro_songs]

# Later, after acquire_song_by_name returns (line 394)
if acquired.get('uuid') in used_intro_uuids:
    logger.warning(f"AI suggested song already used for another intro: {artist} - {title}")
    # Don't return it, continue to fallback
else:
    return {...}
```

**Why:** Prevents Energy and Party from using the same song.

---

## Quick Fix (User Can Try Now)

**Solution:** Manually delete the moods and re-run onboarding with **sequential intro generation**:

1. Stop backend
2. Run: `python backend_v2/scripts/delete_user_moods.py`
3. Modify `backend_v2/services/mood_generator.py` line 249-253 to be sequential (see Step 2 above)
4. Restart backend
5. Create new account and onboard again
6. Watch logs for "Open Selection" attempts

---

## Root Cause Summary

**The system design is correct:** AI should pick any song, downloader fetches it.

**The bug:** During intro generation, AI Open Selection is silently failing (likely due to timeouts or concurrency), causing immediate fallback to the limited local library.

**The fix:** Make intro generation sequential, add logging to track failures, and improve error handling so users know when downloads fail.

---

## Next Steps

1. Add detailed logging to `select_track` to see which mode is being used
2. Make intro generation sequential (not parallel)
3. Test with a fresh onboarding
4. If still failing, investigate YouTube downloader status
5. Consider adding a status event for "Downloading intro song..."

