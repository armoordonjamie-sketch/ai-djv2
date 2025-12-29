# Backend Mood & Track Redesign - Architecture Documentation

## Current Architecture (Before Redesign)

### Mood Generation Flow

**Entry Point:** `/api/onboard/start` endpoint
- User completes voice onboarding via ElevenLabs
- Profile data stored in `user_profiles` table
- Triggers `mood_generator.start_mood_generation(user_id)`

**Mood Creation:** `backend_v2/services/mood_generator.py:generate_personalized_moods()`

1. Creates 5 hardcoded mood templates:
   - Flow (energy=0.6, valence=0.6)
   - Energy (energy=0.85, valence=0.75)
   - Chill (energy=0.35, valence=0.55)
   - Party (energy=0.9, valence=0.85)
   - Late Night (energy=0.45, valence=0.4)

2. Each mood inherits from user profile:
   - `genres_json` = user's favorite genres (e.g., ["Pop"])
   - `dj_personality` = user's selected style (e.g., "casual_funny")

3. Sequentially generates intros for each mood:
   - Calls `orchestration/generation.py:generate_mood_intro()`
   - Selects track via `agents.select_track()`
   - Generates intro speech
   - Renders audio segment

**Result:** All 5 moods differ in energy/valence targets but share genres and personality.

### Track Selection Flow

**Entry Point:** DJLoop or intro generation calls `agents.select_track()`

**File:** `backend_v2/orchestration/agents.py:select_track()`

**Two-Stage Selection:**

#### Stage 1: AI Open Selection (Lines 361-418)
```
IF OpenRouter enabled:
  1. Call generate_song_suggestion(bundle, prev_song)
     → AI suggests ANY song (title, artist)
  2. Call acquire_song_by_name(artist, title, timeout=45s)
     → Check local cache
     → If not found, download from YouTube using yt-dlp
  3. Validation checks:
     → Not too similar to previous song
     → Not in recent history
     → Artist not disliked
  4. Apply scoring/feedback rules
  5. IF acquired AND valid:
     → Return song
  6. ELSE:
     → Fall through to Stage 2
```

**Issues with Stage 1:**
- Downloads timeout after 45 seconds
- Concurrency locks prevent parallel downloads
- Silent fallback on failure (no logging)
- During intro generation, parallel attempts cause lock contention

#### Stage 2: Local Library Fallback (Lines 420-487)
```
1. Call get_scored_candidates(db, bundle, prev_song, history_ids, limit=15)
   → Query songs table WHERE local_path IS NOT NULL
   → Exclude songs in history_ids
   → Apply hard constraints (tempo, energy, genre denylist)
   → Score each candidate using score_candidate()
   → Return top 15 sorted by score

2. Format candidates for LLM

3. Call LLM for refinement (or use top scored candidate as fallback)

4. Return selected song
```

**File:** `backend_v2/services/preference_bundle.py:get_scored_candidates()`

Query constraints:
```sql
SELECT songs.* FROM songs
JOIN song_features ON songs.uuid = song_features.song_uuid
WHERE songs.local_path IS NOT NULL  -- ONLY CACHED SONGS
  AND songs.uuid NOT IN (history_ids)
LIMIT 200
```

Then applies:
- Hard constraints filter (tempo >= 90 BPM, energy >= 0.30)
- Genre denylist (ballad, ambient, etc.)
- User no-go list
- Explicit lyrics preference

**Scoring:** `score_candidate()` (Lines 792-904)
- Base score: 0.5
- Penalties: recent plays, recent artist, disliked artists
- Boosts: liked songs
- Mood matching: 
  - `score -= energy_diff * 0.5`
  - `score -= valence_diff * 0.5`
- Transition compatibility (tempo, key)

**Problem:** Local library has limited range (energy 0.602-0.849), so "Chill" mood (target 0.35) can't find truly low-energy songs.

### Download/Acquisition Flow

**File:** `backend_v2/tools/song_downloader.py:download_song()`

Process:
1. Search YouTube: `ytsearch1:{artist} - {title} official audio`
2. Extract video info
3. Download audio with yt-dlp
4. Convert to MP3 (192kbps)
5. Store in `data/cache/songs/`
6. Insert into `songs` table
7. Enrich metadata (MusicBrainz, Apple Music)

**Concurrency Control:** `agents.py:acquire_song_by_name()` (Lines 190-203)
- Global `_download_locks` dict per normalized query
- Timeout 1 second to acquire lock
- If lock acquisition fails, return None immediately

**Timeout:** Configurable via `DOWNLOAD_TIMEOUT_SECONDS` (default 120s, but agents.py uses 45s for track selection)

### DJ Loop Flow

**File:** `backend_v2/orchestration/loop.py:DJLoop._run()`

Continuous loop:
```
WHILE not shutdown:
  IF segment_queue full:
    Wait 5 seconds
  ELSE IF no current_song:
    → _produce_initial_segment()
       1. Build preference bundle
       2. Check for pre-generated intro (bundle.mood.intro_segment_path)
       3. If exists, queue it and skip generation
       4. Otherwise:
          - select_track(prev_song=None, history_ids=songs_played)
          - Generate intro speech (if should_dj_speak)
          - Render intro mix
          - Queue segment
  ELSE:
    → _produce_mix_segment()
       1. Build preference bundle
       2. select_track(prev_song=current_song, history_ids=songs_played)
       3. plan_transition()
       4. Maybe generate speech
       5. Render DJ mix
       6. Queue segment
       
  Sleep 2 seconds
```

**History Tracking:**
- `self.songs_played` - List of UUIDs played
- `self.failed_song_uuids` - List of UUIDs that failed to render
- Both lists passed to `select_track()` as `history_ids`

### Intro Speech Generation

**File:** `backend_v2/integrations/openrouter.py:generate_dj_intro_speech()`

**Prompt Structure:**
```
PERSONALITY STYLE: {bundle.mood.dj_personality}
USER CONTEXT: {bundle.context.raw_text[:300]}
RECENT BANTER: (history to avoid repetition)

First Song:
- Title: {song_title}
- Artist: {song_artist}

Generate DJ intro...
```

**Problem:** No mood-specific context included (no energy/valence, no mood name in prompt, no example artists for the mood).

### Database Schema (Relevant Tables)

**moods:**
```sql
- id (UUID, PK)
- user_id (FK to users)
- name (VARCHAR)
- color (VARCHAR)
- energy_target (FLOAT)
- valence_target (FLOAT)
- genres_json (TEXT) -- JSON array
- dj_personality (VARCHAR)
- intro_segment_path (VARCHAR) -- Pre-generated intro
- intro_song_uuid (VARCHAR)
- is_default (BOOLEAN)
```

**songs:**
```sql
- uuid (VARCHAR, PK)
- title, artist (VARCHAR)
- local_path (VARCHAR) -- NULL if not downloaded
- duration_sec (FLOAT)
- artwork_url (VARCHAR)
- isrc, recording_mbid, apple_song_id (VARCHAR) -- External IDs
- genres, tags (TEXT) -- JSON arrays
```

**song_features:**
```sql
- song_uuid (VARCHAR, PK, FK)
- energy, valence, tempo (FLOAT)
- danceability, acousticness, instrumentalness (FLOAT)
- key, mode (INT)
```

**play_history:**
```sql
- id (INT, PK)
- session_id, user_id, mood_id (VARCHAR, FK)
- song_uuid (VARCHAR, FK)
- started_at, ended_at (VARCHAR)
- transition_type (VARCHAR)
```

---

## Issues Identified

### 1. Mood Homogeneity

**Symptom:** All 5 moods feel similar during onboarding

**Root Causes:**
- All moods inherit same genres from user profile
- All moods use same DJ personality
- Intro speech doesn't emphasize mood differences
- No unique "vibe" or "era" hints per mood

**Evidence:**
```
| Mood       | Energy | Valence | Genres | Personality  |
|------------|--------|---------|--------|--------------|
| Flow       | 0.6    | 0.6     | [Pop]  | casual_funny |
| Energy     | 0.85   | 0.75    | [Pop]  | casual_funny |
| Chill      | 0.35   | 0.55    | [Pop]  | casual_funny |
| Party      | 0.9    | 0.85    | [Pop]  | casual_funny |
| Late Night | 0.45   | 0.4     | [Pop]  | casual_funny |
```

All differ only in energy/valence targets.

### 2. Track Selection Constrained by Local Library

**Symptom:** Moods can't achieve target energy levels

**Example:**
- Chill mood (target energy=0.35) gets songs with energy ~0.74
- Party mood (target energy=0.9) gets songs with energy ~0.76
- Energy and Party use the SAME song

**Root Cause:**
- Local library has only 202 songs
- Energy range: 0.602 to 0.849 (limited extremes)
- All songs happen to be Pop genre
- Selection is constrained by `local_path IS NOT NULL`

**Why Open Selection Fails:**
- 45-second timeout too short for reliable downloads
- Parallel intro generation causes lock contention
- Silent fallback makes debugging hard

### 3. No Separation of "Selection" from "Acquisition"

**Current Flow (Coupled):**
```
select_track() {
  AI suggests song
  → Try to acquire (download if needed)
  → IF acquisition fails, fall back to local library
  → Return song with local_path
}
```

**Problem:**
- Acquisition failures cause immediate fallback to limited library
- No way to queue multiple acquisition attempts
- Can't select "ideal" track and then wait for download
- No retry mechanism for failed downloads

### 4. Limited Observability

**Missing Events:**
- When Open Selection is attempted
- Why downloads fail (timeout vs error vs not found)
- When fallback to local library occurs
- Which provider (YouTube, cache, etc.) was used

**Result:** Hard to debug why moods sound similar

---

## Proposed New Architecture

### Overview

Separate concerns into distinct layers:

1. **Mood Generation Layer:** Create meaningfully different moods
2. **Catalog Discovery Layer:** Search global music catalog (Spotify/Apple)
3. **Selection Layer:** Choose "TrackIntent" (what to play) without availability constraint
4. **Acquisition Layer:** Async pipeline to obtain audio files
5. **Rendering Layer:** Mix tracks once acquired

```
┌─────────────────────────────────────────────────────────┐
│ Mood Generation                                         │
│ - Enhanced templates with genre seeds, vibe keywords    │
│ - Validate spread (min pairwise distance)               │
│ - Mood-specific intro prompts                           │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│ DJ Loop                                                 │
│ - Build preference bundle                               │
│ - Check for pre-generated intro                         │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│ Catalog Discovery (NEW)                                 │
│ - Query Spotify/Apple Music APIs                        │
│ - Get audio features for candidates                     │
│ - Pool 50-200 tracks from global catalog                │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│ Track Selection (Decoupled)                            │
│ - Score candidates from catalog                         │
│ - Apply MMR diversity ranking                           │
│ - Create TrackIntent (PENDING)                          │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│ Acquisition Pipeline (NEW)                              │
│ - Check local cache first                               │
│ - Try YouTube download (primary)                        │
│ - Try alternative sources (fallback)                    │
│ - Update TrackIntent status (ACQUIRED/FAILED)           │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│ Rendering & Playback                                    │
│ - Wait for TrackIntent → ACQUIRED                       │
│ - Render audio segment                                  │
│ - Queue for streaming                                   │
└─────────────────────────────────────────────────────────┘
```

### New Data Models

**TrackIntent:** Represents "what we want to play"
- Decouples selection from availability
- Status: PENDING → ACQUIRED/FAILED
- Can be queued for async acquisition

**AcquisitionJob:** Background work to obtain audio
- Multiple attempts per intent
- Tracks provider, errors, retry count
- Emits status events for observability

### Benefits

1. **Moods are distinct:** Different genre seeds, vibe keywords, intro styles
2. **Selection not constrained:** Can pick any track in the world
3. **Async acquisition:** Download in background, fallback on failure
4. **Robust error handling:** Retry logic, alternative selection
5. **Full observability:** Events for every stage

---

## Migration Strategy

### Phase-by-Phase Rollout

**Phase 1-2:** Enhance mood generation (no breaking changes)
- Existing moods continue to work
- New moods get enhanced templates

**Phase 3:** Add TrackIntent models (additive)
- New tables, no impact on existing flow
- Can run in parallel with old system

**Phase 4:** Add catalog providers (additive)
- Optional feature, graceful degradation

**Phase 5:** Integrate acquisition pipeline
- Can coexist with old `acquire_song_by_name()`
- Gradual cutover

**Phase 6-7:** Observability and tests
- Pure additive features

### Backward Compatibility

- Existing `select_track()` still works (uses local library)
- New `select_track_intent()` is opt-in
- DJLoop can use either path based on feature flag
- No data loss, no service disruption

---

## Testing Strategy

### Unit Tests

- Mood spread validation
- TrackIntent state machine transitions
- Provider interface mocks
- MMR diversity algorithm

### Integration Tests

- End-to-end: mood creation → intro generation
- Acquisition pipeline: intent → multiple providers → fallback
- DJLoop: intent-based flow with acquisition

### Manual Testing

- Re-onboard and verify 5 distinct moods
- Check intro TTS for uniqueness
- Monitor acquisition success rate
- Verify fallback behavior on download failure

---

## Success Metrics

1. **Mood Distinctness:**
   - Average pairwise distance > 0.2
   - Intro prompts contain unique keywords

2. **Track Diversity:**
   - % of tracks from AI Open Selection (not library fallback)
   - Acquisition success rate per provider

3. **User Experience:**
   - Time to first track (should not increase)
   - Playback stalls due to acquisition failures (should be zero)

---

## Files Modified/Created

See implementation plan for detailed file list.

**Key Changes:**
- `mood_generator.py`: Enhanced templates
- `agents.py`: TrackIntent-aware selection
- `loop.py`: Acquisition-aware flow
- `openrouter.py`: Mood-specific prompts

**New Modules:**
- `models/track_intent.py`
- `catalog/providers/`
- `services/acquisition.py`
- `services/acquisition_worker.py`

---

## ✅ IMPLEMENTATION STATUS

### Completed (December 2024)

**Phase 1 - Documentation:** ✅
- Documented current architecture, call graph, and failure modes

**Phase 2 - Mood Generation:** ✅
- Enhanced `MoodTemplate` with rich fields (`genre_seeds`, `vibe_keywords`, `example_artists`, `danceability_target`, `tempo_range`, `era_hint`, `intro_personality`)
- Updated `MOOD_TEMPLATES` with distinct characteristics per mood
- Added `_calculate_mood_spread()` and `_enforce_mood_spread()` for validation
- Modified `generate_dj_intro_speech()` to use mood-specific context for unique intros

**Phase 3 - TrackIntent Models:** ✅
- Created `TrackIntent` and `AcquisitionJob` models (`backend_v2/models/track_intent.py`)
- Created Alembic migration (`backend_v2/migrations/versions/001_track_intents.py`)
- Added new columns to `Mood` model for rich templates

**Phase 4 - Catalog Discovery:** ✅
- Created `CatalogProvider` interface (`backend_v2/catalog/providers/base.py`)
- Implemented `DeezerCatalogProvider` using existing Deezer API integration
- Created global catalog selector with MMR diversity ranking (`backend_v2/catalog/selector.py`)
- Scoring algorithm balances mood-relevance with diversity (cosine similarity)

**Phase 5 - Acquisition Pipeline:** ✅
- Multi-provider acquisition service (`backend_v2/services/acquisition.py`)
  - `LocalCacheProvider`: Check existing songs
  - `YouTubeProvider`: Download via yt-dlp
  - Fallback chain with timeout handling
- Background acquisition worker (`backend_v2/services/acquisition_worker.py`)
  - Async job processing
  - Concurrency control (max 2 concurrent)

**Phase 6 - Observability:** ✅
- Added status events for acquisition stages (`SEARCHING_CATALOG`, `ACQUIRING_TRACK`, `ACQUISITION_FAILED`, `SELECTING_ALTERNATIVE`)
- Created metrics collector (`backend_v2/monitoring/metrics.py`)
  - Tracks acquisition success rates per provider
  - Tracks mood distinctness scores
  - Tracks fallback frequencies

**Phase 7 - Integration:** 🔄 In Progress
- DJLoop update pending
- Tests pending

### Files Created

```
backend_v2/
├── models/track_intent.py (NEW)
├── migrations/versions/001_track_intents.py (NEW)
├── catalog/
│   ├── __init__.py (NEW)
│   ├── providers/
│   │   ├── __init__.py (NEW)
│   │   ├── base.py (NEW)
│   │   └── deezer.py (NEW)
│   └── selector.py (NEW)
├── services/
│   ├── acquisition.py (NEW)
│   └── acquisition_worker.py (NEW)
└── monitoring/
    ├── __init__.py (NEW)
    └── metrics.py (NEW)
```

### Files Modified

```
backend_v2/
├── models/mood.py (MODIFIED - added rich template columns)
├── services/mood_generator.py (MODIFIED - enhanced templates, mood spread validation)
├── integrations/openrouter.py (MODIFIED - mood-specific intro prompts)
└── schemas/status_events.py (MODIFIED - added acquisition events)
```

---

## Conclusion

The redesign addresses root causes of mood similarity and track selection limitations by:

1. Making moods meaningfully different through enhanced templates
2. Decoupling selection from availability via TrackIntent model
3. Enabling global catalog discovery through provider abstractions
4. Building robust async acquisition with fallbacks
5. Providing full observability through status events

This creates a scalable foundation for truly personalized AI DJ experiences.

