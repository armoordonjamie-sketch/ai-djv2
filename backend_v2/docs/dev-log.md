# Backend v2 Development Log

## 2025-12-21 — Initial Implementation

### What Was Built
Complete multi-user authenticated backend in `backend-v2/` folder.

**Phases Completed:**
- ✅ Phase 0: Project structure, config, env vars
- ✅ Phase 1: SQLAlchemy models, Alembic setup
- ✅ Phase 2: Cookie-first auth, CSRF protection
- ✅ Phase 3: User resource APIs (contexts, moods, settings, prompts)
- ✅ Phase 4: Feedback API, training service
- ✅ Phase 5: Session manager with caps

### Key Decisions

| Decision | Rationale |
|----------|-----------|
| HttpOnly cookies | HTMLAudioElement streaming requires cookies (can't set Auth header) |
| CSRF double-submit | Stateless CSRF that works with cookie auth |
| 1 session per user | Simplifies resource management, prevents abuse |
| ListenBrainz/MusicBrainz | Free, open-source music metadata |
| No query tokens | Security best practice (WS_ALLOW_QUERY_TOKEN off by default) |

### TODO
- [ ] Generate Alembic migrations for canonical IDs
- [x] ~~WebSocket endpoint with cookie auth~~ → `api/ws.py`
- [x] ~~Integrate session manager with DJ orchestration loop~~ → `orchestration/loop.py`
- [ ] Rate limiting (SlowAPI)
- [ ] Prometheus metrics endpoint

---

## 2025-12-21 — Batch 1 & 2: Streaming + Orchestration

### Batch 1: Stream Lifecycle + WebSocket
- Created `streaming/pipeline.py` with `UserRadioPipeline` class
  - Per-user FFmpeg encoder (PCM→MP3)
  - Segment queue + output queue architecture
  - Idle cleanup and session caps
- Created `api/ws.py` — WebSocket endpoint at `/api/v1/ws`
  - Cookie-first auth (Bearer fallback)
  - Versioned event format: `{v:1, type:"...", data:{...}}`
- Created `orchestration/events.py` with `UserEventEmitter`
  - Per-user connection registry
  - `emit_now_playing()`, `emit_segment_ready()`, `emit_dj_says()`

### Batch 2: Orchestration + Audio
- Created `orchestration/state.py`
  - `DJState` TypedDict with `user_id`, `mood_id`, `context_id`
  - `SessionContext` dataclass for preferences
- Created `orchestration/loop.py` with `DJLoop` class
  - Background task for continuous segment production
  - Placeholder track selection (Batch 3 will add PreferenceBundle)
- Created `audio/mix.py` — simplified port from `backend/dj_mix.py`
  - `create_intro_mix()` and `create_dj_mix()`
  - LUFS normalization, crossfade transitions, TTS ducking
- Updated `streaming/pipeline.py` with segment decoder
  - Decodes MP3→PCM via FFmpeg subprocess
  - Feeds PCM to encoder stdin

### Tests & Verification
8 integration tests passing (start/stop/ws).

**Manual Verification (Browser):**
- Auth: Register/Login + Cookie check ✅
- CSRF: 
  - `POST /start` without token → 403 Forbidden ✅
  - `POST /start` with token → 200 OK ✅
  - Fixed issue where CSRF middleware exceptions were causing 500s; switched to JSONResponse.
- Stream: Audio element plays content, correct headers ✅
- WebSocket: Connected, Ping/Pong work, receiving per-user events ✅

---

## 2025-12-21 — Batch 3: Personalization + Real AI Agents

### Overview
Complete implementation of personalized AI DJ orchestration with database-backed preferences,
deterministic candidate scoring, LLM-based track selection, and TTS speech synthesis.

### New Files Created

| File | Description |
|------|-------------|
| `services/preference_bundle.py` | PreferenceBundle dataclasses, caching, DB loading, candidate scoring |
| `integrations/openrouter.py` | OpenRouter client adapted for PreferenceBundle |
| `integrations/elevenlabs.py` | ElevenLabs TTS client with per-user settings |
| `integrations/__init__.py` | Package exports |
| `orchestration/agents.py` | Track selector, transition planner, speech writer, TTS agents |
| `tests/test_preference_bundle.py` | 12 unit tests for caching and scoring |

### Key Components

**PreferenceBundle** — Aggregates user preferences from database:
- Context (user's listening context with raw text)
- Mood (energy/valence targets, genres, DJ personality)
- MoodProfile (learned weights from feedback training)
- Feedback (recent likes/dislikes for few-shot prompting)
- History (recent plays for variety enforcement)
- AgentSettings (per-user thinking budgets, temperatures)
- PromptTemplates (user-defined prompt overrides)

**Deterministic Scoring** — Pre-filters candidates before LLM:
- Hard ban: Disliked songs get score -1000
- Artist penalty: Disliked artists get -500
- Recent plays: Heavy penalty (-0.8) for last 5 songs
- Liked songs: Boost (+0.3)
- Energy/valence matching: Penalty proportional to distance from targets
- Transition compatibility: Tempo and key compatibility bonuses

**Agents Flow:**
1. `select_track()` → Scores candidates, calls LLM for final pick, falls back to top deterministic
2. `plan_transition()` → Generates transition type and parameters via LLM
3. `write_intro_speech()` / `write_transition_speech()` → LLM-generated DJ banter
4. `synthesize_speech()` → ElevenLabs TTS synthesis

### Modified Files

| File | Changes |
|------|---------|
| `orchestration/loop.py` | Complete rewrite to use real agents |
| `services/session_manager.py` | Actually starts DJLoop now |
| `db/session.py` | Added `get_db_session()` context manager |
| `config.py` | Added individual thinking budget constants |

### Tests
12 tests passing for PreferenceBundle service:
- Cache set/get/miss/invalidate
- Candidate scoring (basic, disliked, liked, recent, energy)
- Helper methods (get_agent_setting, get_prompt_template, get_disliked_song_uuids)

### API/Event Compatibility
- All endpoints unchanged
- Event format unchanged: `{v:1, type:"...", data:{...}}`
- `now_playing`: Emitted with real song metadata
- `dj_says`: Emitted with generated speech script
- `segment_ready`: Emitted with segment index and duration

---

## 2025-12-21 — Batch 4: Metadata Providers + Song Downloader

### Overview
Implemented metadata enrichment from MusicBrainz and Apple Music (via Apify scraper),
plus song downloading with automatic enrichment on download.

### New Files Created

| File | Description |
|------|-------------|
| `tools/song_downloader.py` | yt-dlp song downloader with auto-enrichment |
| `tools/__init__.py` | Tools package init |
| `integrations/metadata/musicbrainz.py` | MusicBrainz API client with rate limiting |
| `integrations/metadata/apple_music.py` | Apple Music via Apify scraper (no dev account needed) |
| `integrations/metadata/enrichment.py` | Unified enrichment service combining both providers |
| `integrations/metadata/__init__.py` | Metadata package exports |
| `scripts/migrate_user_columns.py` | Migration for user_id columns on existing tables |
| `scripts/migrate_metadata_columns.py` | Migration for metadata columns on songs table |
| `scripts/__init__.py` | Scripts package init |

### Key Components

**SongDownloader** — Downloads songs using yt-dlp:
- YouTube search and audio extraction (MP3)
- Cookie support for bot detection bypass
- Auto-stores in database with UUID
- Auto-enriches with MusicBrainz + Apple Music metadata

**MusicBrainz Client** — Free music metadata API:
- Rate-limited at 1 req/sec (per API terms)
- In-memory caching (24hr TTL)
- Provides: Recording MBID, Release MBID, Artist MBID, ISRCs, tags

**Apple Music via Apify** — Artwork and genre enrichment:
- Uses `jupri~apple-music` Apify actor
- No Apple Developer account required
- Provides: Artwork URLs (up to 1000x1000), genres, Apple Song ID

**MetadataEnrichmentService** — Unified interface:
- Runs both providers in parallel
- Falls back to Cover Art Archive for artwork
- Persists enrichment to `songs` table

### Database Migrations

**user_id columns** (sessions, play_history, segments):
```bash
python -m backend_v2.scripts.migrate_user_columns
```

**metadata columns** (songs):
```bash
python -m backend_v2.scripts.migrate_metadata_columns
```

New columns on `songs`:
- `isrc`, `recording_mbid`, `release_mbid`, `artist_mbid`
- `apple_song_id`, `artwork_url`
- `genres`, `tags` (JSON arrays)

### Updated Files

| File | Changes |
|------|---------|
| `models/existing.py` | Added metadata columns to Song model |
| `config.py` | Replaced Apple Music keys with `APIFY_API_TOKEN` |
| `orchestration/agents.py` | Added `acquire_song_by_name()` for AI-suggested downloads |

### .env Configuration
```env
# Required for MusicBrainz (contact email)
MUSICBRAINZ_CONTACT_EMAIL=you@example.com

# Optional for Apple Music metadata (free Apify tier)
APIFY_API_TOKEN=your_token_here
```

### Usage Example
```python
from backend_v2.tools.song_downloader import get_song_downloader

downloader = get_song_downloader()
result = await downloader.download_song(
    query="Daft Punk Get Lucky",
    artist="Daft Punk",
    title="Get Lucky"
)
# Result includes file_path, plus song is stored and enriched in DB
```

---

## 2025-12-21 — Batch 5: DJ Personality + Speech Safeguards

### Overview
Ported legacy DJ personality rules from `user_context.txt` and speech sanitizers
from `backend/integrations/openrouter.py` into a structured persona system.

### Legacy Analysis

The legacy system had persona rules embedded in raw text files:
- **Forbidden terms**: BPM, key, Camelot, crossfade, FFmpeg (never say on-air)
- **Roast topics with cooldowns**: VW Golf (5 seg), short legs (5), Jeanie sweets (4), Jamie genius (3)
- **Music constraints**: "High energy only - NO slow songs, NO ballads"
- **UK season rules**: Cap Christmas tracks outside Nov-Dec

### New Files Created

| File | Description |
|------|-------------|
| `services/persona.py` | DJPersona model, RoastTopic cooldowns, compile_persona() |
| `tests/test_persona.py` | 16 unit tests for cooldowns and sanitizers |

### How V2 Matches Legacy

| Legacy | V2 Implementation |
|--------|-------------------|
| `user_context.txt` roast rules | `RoastTopic` class with `max_per_n_segments` |
| `On-Air Rules` forbidden terms | `DJPersona.forbidden_terms` + regex patterns |
| `_sanitize_speech_context()` | Already in `openrouter.py:586` |
| `_sanitize_tts_output()` | Already in `openrouter.py:610` |
| banter_history + do_not_repeat | Combined in speech agents via `persona.get_do_not_repeat()` |

### Modified Files

| File | Changes |
|------|---------|
| `orchestration/agents.py` | Added persona import, `get_persona_for_user()`, `advance_persona_cooldowns()` |
| `orchestration/agents.py` | Updated `write_intro_speech()` and `write_transition_speech()` with persona do_not_repeat |

### Tests
16 persona tests passing:
- Persona compilation from PreferenceBundle
- Roast topic cooldown enforcement (`can_use()`, `use()`, `advance()`)
- Forbidden term pattern matching (BPM, Camelot codes)
- do_not_repeat list generation

---

## 2025-12-21 — Batch 6: Song Suggestions + Hard Constraints + Production Readiness

### Overview
Implemented legacy-style song suggestion with strict "Artist - Title" format enforcement,
hard constraints for persona music rules ("NO slow songs, NO ballads"), safe download
guards, library expansion loop, and Prometheus metrics.

### New Files Created

| File | Description |
|------|-------------|
| `integrations/search_queries.py` | Search query generator with strict format validation |
| `services/library_expansion.py` | Auto-download service when library is small |
| `monitoring/metrics.py` | Prometheus counters, gauges, histograms |
| `monitoring/__init__.py` | Monitoring package exports |
| `tests/test_hard_constraints.py` | Tests for constraints, downloads, query format |
| `docs/personality_and_selection_gap_report.md` | Phase A audit findings |

### Config Additions (`config.py`)

```python
# Hard Constraints
DEFAULT_MIN_TEMPO_BPM = 90          # Reject songs below this tempo
DEFAULT_MIN_ENERGY = 0.30           # Reject songs below this energy
BALLAD_GENRE_DENYLIST = ["ballad", "lullaby", "ambient", ...]

# Download Safety
DOWNLOAD_DENYLIST_PATTERNS = [      # Reject these patterns
    "full album", "live set", "sped up", "nightcore", ...
]
MAX_CONCURRENT_DOWNLOADS = 2        # Prevent resource exhaustion
DOWNLOAD_TIMEOUT_SECONDS = 120      # Prevent stalling
```

### Endpoints Added

| Endpoint | Description |
|----------|-------------|
| `GET /metrics` | Prometheus metrics for monitoring |

### Key Changes

| File | Changes |
|------|---------|
| `services/preference_bundle.py` | Added `check_hard_constraints()`, `apply_hard_constraints()` |
| `services/preference_bundle.py` | Updated `get_scored_candidates()` to filter before scoring |
| `orchestration/agents.py` | Rewrote `acquire_song_by_name()` with validation, concurrency, timeout |
| `main.py` | Added `/metrics` endpoint |

### How It Works

```
Songs → Hard Constraints Filter → Scoring → LLM Pick → Selection
         (tempo, energy, genre)    (user preferences)
```

1. **Hard constraints** filter BEFORE scoring (removes slow songs, ballads)
2. **Scoring** applies user preferences, history, transition compatibility
3. **LLM** picks from top candidates with fallback to deterministic

### MusicBrainz Compliance
- ✅ 1 req/sec rate limiter (`RateLimiter` class)
- ✅ User-Agent header with contact email
- ✅ In-memory caching (24h TTL)

### Tests
22 tests passing:
- Hard constraint rejection (tempo, energy, genre denylist)
- Download validation (denylist patterns, format)
- Search query format ("Artist - Title" enforcement)

---

## Notes


### Running Locally
```bash
pip install -r backend-v2/requirements.txt
uvicorn backend_v2.main:app --reload --port 8000
```

### Migration Workflow
**New database:**
```bash
alembic upgrade head
```

**Existing database (tables created by old db.py):**
```bash
# Apply user_id columns to existing tables
python -m backend_v2.scripts.migrate_user_columns

# Apply metadata columns to songs table
python -m backend_v2.scripts.migrate_metadata_columns

# Mark alembic as current
alembic stamp head
```

## 2025-12-21 — Audio Glitch Fixes (Production Readiness)

### Problem
Users reported audible stutters/glitches at segment boundaries during continuous playback.
Root cause analysis:
1. **MP3 padding**: Decoding intermediate MP3 segments caused gapless playback issues due to codec padding.
2. **Buffer underruns**: The `pipeline.py` feeder was feeding the encoder in bursts, causing buffer fluctuation.

### Solution Implemented
Implemented a 2-stage fix:

**Stage 1: Pacing & Stabilization**
- Updated `backend_v2/streaming/pipeline.py` to use `ffmpeg -re` (realtime limit) for input feeding.
- Added `aresample=async=1:first_pts=0` filter to stabilize timestamps and prevent drift.
- Removed manual Python-side sleep pacing.

**Stage 2: WAV Transport**
- Updated `backend_v2/audio/mix.py` to use `.wav` (PCM s16le) for intermediate segments instead of MP3.
- This ensures sample-accurate stitching at the encoder level, eliminating MP3 boundary artifacts.
- Metadata updated to reflect `wav` format.

### Verification
- `tests/test_audio_stitching.py` created to verify logic.
- Server logs confirm fed segments match duration.

---

## 2025-12-21 — Batch 8: Voice Onboarding

### Overview
Voice-based onboarding flow using ElevenLabs Conversational AI with Custom LLM proxy to OpenRouter.

### Architecture

```
Client → POST /onboard/start → signed_url
  │
  └→ WebSocket to ElevenLabs ConvAI
       │
       └→ ElevenLabs calls POST /v1/chat/completions
            │
            └→ Backend proxies to OpenRouter (google/gemini-2.5-flash-lite)
                 │
                 └→ Agent calls tool: submit_onboarding_profile
                      ↓
              POST /onboard/submit → Persist user_contexts + user.onboarded_at
```

### Files Created

| File | Description |
|------|-------------|
| `api/onboard.py` | Onboarding API (status, start, submit) |
| `api/llm_proxy.py` | Custom LLM proxy for ElevenLabs |

### Files Modified

| File | Changes |
|------|---------|
| `models/user.py` | Added `onboarded_at` column |
| `config.py` | Added onboarding env vars |
| `api/stream.py` | Added stream gating (409 if not onboarded) |
| `main.py` | Registered onboard and llm_proxy routers |

### Config Additions

```python
ELEVENLABS_ONBOARD_AGENT_ID: Optional[str]
ELEVENLABS_CUSTOM_LLM_SECRET: Optional[str]
ONBOARD_TOOL_SECRET: Optional[str]
OPENROUTER_ONBOARD_MODEL: str = "google/gemini-2.5-flash-lite"
```

### ElevenLabs Dashboard Setup

1. Create Private Agent "Jamify Onboarding"
2. Set Custom LLM:
   - Base URL: `https://YOUR_URL`
   - Auth: `Bearer {ELEVENLABS_CUSTOM_LLM_SECRET}`
   - Extra Body: Enabled
3. Create tool `submit_onboarding_profile` → POSTs to `/api/v1/onboard/submit`

### Stream Gating

`POST /api/v1/stream/start` returns 409:
```json
{"detail": {"code": "onboarding_required", "next": "/api/v1/onboard/start"}}
```

---

## 2025-12-21 — Batch 8: Structured Onboarding Profile System

### Overview
Implemented end-to-end structured user profile capture for personalized AI DJ experiences. Expanded the ElevenLabs onboarding tool to collect arrays (genres, artists, songs) and enums (explicit_lyrics, dj_personality), persists to a dedicated `user_profiles` table, and integrates with all AI agents.

### New Database Table

**user_profiles** (1:1 with users)
| Column | Type | Description |
|--------|------|-------------|
| `display_name` | TEXT | User's preferred name |
| `favorite_genres` | TEXT (JSON) | Array of genres |
| `favorite_artists` | TEXT (JSON) | Array of artists |
| `favorite_songs` | TEXT (JSON) | Array of songs |
| `no_go` | TEXT (JSON) | Music to avoid |
| `explicit_lyrics` | TEXT | "ok" / "avoid" / "depends" |
| `dj_personality` | TEXT | Style preference enum |
| `age_range`, `location`, `occupation` | TEXT | Demographics |

### Files Created

| File | Description |
|------|-------------|
| `models/user_profile.py` | UserProfile SQLAlchemy model |
| `scripts/migrate_user_profiles.py` | Table migration script |

### Files Modified

| File | Changes |
|------|---------|
| `api/onboard.py` | Expanded payload schema, upsert to user_profiles |
| `scripts/setup_elevenlabs_agent.py` | Tool schema with arrays/enums, PATCH support |
| `services/preference_bundle.py` | Added UserProfileData, profile loading, hard constraints |
| `services/persona.py` | Profile-based DJ personality compilation |
| `integrations/openrouter.py` | build_profile_context helper, updated prompts |
| `tests/test_persona.py` | Updated fixtures with UserProfileData |
| `config.py` | Added ELEVENLABS_ONBOARD_TOOL_ID |

### Data Flow

```
ElevenLabs Agent
    ↓
POST /onboard/submit (with X-Onboard-Secret)
    ↓
Upsert to user_profiles table
    ↓
build_preference_bundle() loads profile
    ↓
PreferenceBundle.profile (UserProfileData)
    ├→ compile_persona() → DJPersona (tone, constraints)
    ├→ build_profile_context() → LLM prompts
    └→ apply_hard_constraints() → Filters explicit/no-go
```

### ElevenLabs Tool Schema

The `submit_onboarding_profile` webhook tool now accepts:
- **Arrays**: `favorite_genres`, `favorite_artists`, `favorite_songs`, `no_go`
- **Enums**: `explicit_lyrics`, `dj_personality`
- **Dynamic variable**: `user_id` (auto-populated)

### Usage in Agents

| Component | Uses Profile For |
|-----------|------------------|
| `compile_persona()` | Tone, constraints, preferred artists/genres |
| `generate_song_suggestion()` | Favorites, no-go in prompts |
| `generate_dj_speech()` | Display name, personality style |
| `apply_hard_constraints()` | Explicit filtering, no-go genre filtering |
