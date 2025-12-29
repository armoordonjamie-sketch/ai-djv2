# Backend V2 Multi-User Pipeline Implementation Plan

This plan implements a complete AI DJ pipeline in `backend_v2/` that mirrors the working `backend/` pipeline but with multi-user isolation, per-user streaming, and database-backed preferences.

> [!IMPORTANT]  
> **No changes to `\backend\` directory.** All code goes in `backend_v2/` only.

---

## Phase 1: Core Pipeline Structure

### [NEW] backend_v2/orchestration/__init__.py
Empty init file

### [NEW] backend_v2/orchestration/state.py
- Port `DJState` TypedDict with new user-scoping fields:
  - `user_id: str`
  - `mood_id: Optional[str]`
  - `context_id: Optional[str]`
- Port `NowPlayingSegment`, `DecisionStep` from backend/orchestration/graph.py

### [NEW] backend_v2/orchestration/agents.py
- Port minimal set of agent functions adapted for multi-user:
  - `InitialSongSelectorAgent` - uses PreferenceBundle instead of load_user_context()
  - `TrackSelectorAgent` - uses PreferenceBundle
  - `PlanningAgent` - uses PreferenceBundle
  - `TransitionPlannerAgent` - no changes needed
  - `SpeechWriterAgent` - uses PreferenceBundle + mood personality
  - `TTSAgent` - no changes needed
  - `AudioRendererTool` - delegates to audio module
  - `PersistenceNode` - includes user_id/mood_id in all writes
  - `EmitEventsNode` - emits to user-scoped connections only

### [NEW] backend_v2/orchestration/loop.py
- Port `DJLoop` class adapted to:
  - Accept `user_id`, `mood_id`, `context_id` from SessionRunner
  - Pass user context through state
  - Use per-user segment queue (from SessionRunner)
  - Use per-user event emitter

### [NEW] backend_v2/orchestration/events.py
- Implement `UserScopedEventEmitter` class:
  - `_connections: Dict[str, Set[WebSocket]]` - user_id -> connections
  - `connect(user_id, websocket)`
  - `disconnect(user_id, websocket)`
  - `emit_to_user(user_id, event_type, data)` - only to that user's connections

---

## Phase 2: Audio Processing Module

### [NEW] backend_v2/audio/__init__.py
### [NEW] backend_v2/audio/mix.py
- Port `create_dj_mix()` and `create_intro_mix()` from backend/dj_mix.py
- Port `get_loudness()`, `get_duration()`, `normalize_stream()` helpers
- No changes to logic, just relocated to backend_v2

### [NEW] backend_v2/audio/transitions.py
- Port transition functions from backend/transitions.py:
  - `TRANSITION_FUNCTIONS` registry
  - `apply_crossfade`, `apply_eq_blend`, `apply_bass_swap`, etc.

---

## Phase 3: Streaming Module

### [NEW] backend_v2/streaming/__init__.py
### [NEW] backend_v2/streaming/pipeline.py
- Port `RadioPipeline` class from backend/streaming/radio_pipeline.py
- Adapt for per-user isolation:
  - Each user gets their own RadioPipeline instance (managed by SessionRunner)
  - OR shared pipeline with user-tagged client queues
- Port `ICYStreamWrapper` if needed

---

## Phase 4: Integrations Module

### [NEW] backend_v2/integrations/__init__.py
### [NEW] backend_v2/integrations/openrouter.py
- Port `OpenRouterClient` from backend/integrations/openrouter.py
- Add support for per-user prompt template overrides
- Add support for per-user agent settings (thinking_budget, temperature)

### [NEW] backend_v2/integrations/elevenlabs.py
- Port `ElevenLabsClient` from backend/integrations/elevenlabs.py
- No major changes needed

---

## Phase 5: PreferenceBundle Service

### [NEW] backend_v2/services/preference_bundle.py

```python
@dataclass
class PreferenceBundle:
    user_id: str
    session_id: str
    context: ContextData  # name, raw_text, parsed_json
    mood: MoodData  # id, name, genres, energy_target, valence_target, dj_personality, color
    mood_profile: MoodProfileData  # summary_text, weights_json, version
    feedback: FeedbackData  # recent_likes[], recent_dislikes[]
    history: HistoryData  # recent_plays[]
    agent_settings: Dict[str, Any]  # per-agent settings
    prompt_templates: Dict[str, str]  # name -> template_text

async def build_preference_bundle(
    db: AsyncSession,
    user_id: str,
    mood_id: Optional[str] = None,
    context_name: Optional[str] = None
) -> PreferenceBundle:
    # Fallback logic:
    # - context: requested context_name -> "default" -> create minimal
    # - mood: requested mood_id -> user's default mood -> create minimal
```

---

## Phase 6: SessionRunner Integration

### [MODIFY] backend_v2/services/session_manager.py
- Import and create DJLoop in `SessionRunner._run_dj_loop()`
- Pass user_id, mood_id, context_id to loop
- Connect loop's segment queue to RadioPipeline
- Connect loop's event emitter to user-scoped WS emitter

---

## Phase 7: WebSocket Endpoint

### [NEW] backend_v2/api/ws.py
- `@app.websocket("/api/v1/ws")`
- Cookie-first authentication (extract from request)
- Fallback: query token ONLY if `WS_ALLOW_QUERY_TOKEN=true` (default false)
- On connect: register with user-scoped emitter
- On disconnect: unregister
- Versioned events: `{"v": 1, "type": "...", "data": {...}}`
- Event types: `now_playing`, `segment_ready`, `decision_trace`, `dj_says`

### [MODIFY] backend_v2/main.py
- Import and mount websocket router

---

## Phase 8: Database Migrations

### [NEW] Alembic migration: Add canonical ID columns to songs

```sql
ALTER TABLE songs ADD COLUMN isrc VARCHAR(12) NULL;
ALTER TABLE songs ADD COLUMN recording_mbid VARCHAR(36) NULL;
ALTER TABLE songs ADD COLUMN release_mbid VARCHAR(36) NULL;
ALTER TABLE songs ADD COLUMN artist_mbid VARCHAR(36) NULL;
ALTER TABLE songs ADD COLUMN apple_song_id VARCHAR(20) NULL;
ALTER TABLE songs ADD COLUMN apple_album_id VARCHAR(20) NULL;
ALTER TABLE songs ADD COLUMN apple_artist_id VARCHAR(20) NULL;
ALTER TABLE songs ADD COLUMN artwork_url TEXT NULL;
ALTER TABLE songs ADD COLUMN genres_json TEXT NULL;
ALTER TABLE songs ADD COLUMN tags_json TEXT NULL;

-- Create unique indexes (allowing NULLs)
CREATE UNIQUE INDEX ix_songs_isrc ON songs(isrc) WHERE isrc IS NOT NULL;
CREATE UNIQUE INDEX ix_songs_recording_mbid ON songs(recording_mbid) WHERE recording_mbid IS NOT NULL;
```

### [MODIFY] backend_v2/models/existing.py
- Add new columns to `Song` model

---

## Phase 9: Metadata Providers

### [NEW] backend_v2/integrations/metadata/__init__.py
### [NEW] backend_v2/integrations/metadata/musicbrainz.py
- Global async rate limiter: `asyncio.Semaphore(1)` + 1 second delay
- User-Agent from `MUSICBRAINZ_USER_AGENT` env var (required)
- Cache in DB (song_identifiers or inline on songs table)
- `match_track(artist, title, duration) -> {recording_mbid, isrc, tags, ...}`

### [NEW] backend_v2/integrations/metadata/apple_music.py
- Developer token from `APPLE_MUSIC_DEVELOPER_TOKEN` env var
- Storefront from `APPLE_MUSIC_STOREFRONT` (default "gb")
- Catalog search: `search_track(artist, title) -> {apple_song_id, artwork_url, genres}`

### [NEW] backend_v2/integrations/metadata/listenbrainz.py
- Per-user token storage (encrypted with `INTEGRATIONS_ENCRYPTION_KEY`)
- `connect(user_token, user_name)` - store encrypted token
- `disconnect()` - delete token
- `status()` - return connected state (never return token)
- `fetch_recent_listens(user_id)` - for PreferenceBundle seeding

### [NEW] backend_v2/api/integrations.py
- `POST /api/v1/integrations/listenbrainz/connect`
- `GET /api/v1/integrations/listenbrainz/status`
- `DELETE /api/v1/integrations/listenbrainz/disconnect`

---

## Verification Plan

### Automated Tests

#### 1. PreferenceBundle Tests
**File**: `backend_v2/tests/test_preference_bundle.py`
**Run**: `pytest backend_v2/tests/test_preference_bundle.py -v`

```python
# Test cases:
- test_context_fallback_to_default()
- test_mood_fallback_to_user_default()
- test_feedback_loaded_per_user()
- test_prompt_templates_mood_override()
```

#### 2. MusicBrainz Rate Limiter Tests
**File**: `backend_v2/tests/test_musicbrainz.py`
**Run**: `pytest backend_v2/tests/test_musicbrainz.py -v`

```python
# Test cases:
- test_rate_limiter_enforces_1_second_delay()
- test_user_agent_header_required()
- test_cache_hit_bypasses_api()
```

#### 3. WebSocket Per-User Scoping Tests
**File**: `backend_v2/tests/test_websocket.py`
**Run**: `pytest backend_v2/tests/test_websocket.py -v`

```python
# Test cases:
- test_user_only_receives_own_events()
- test_cookie_auth_required()
- test_event_format_versioned()
```

#### 4. Stream Lifecycle Tests
**File**: `backend_v2/tests/test_stream.py`
**Run**: `pytest backend_v2/tests/test_stream.py -v`

```python
# Test cases:
- test_start_creates_session()
- test_start_idempotent()
- test_status_returns_session_info()
- test_stop_terminates_session()
- test_session_limit_returns_503()
```

### Manual Verification

#### 1. Local Development Setup
```bash
cd c:\Users\JamiePC\Desktop\ai-djv2
pip install -r backend-v2/requirements.txt
alembic upgrade head
uvicorn backend_v2.main:app --reload --port 8000
```

#### 2. Test Stream Endpoint
1. Open browser to `http://localhost:8000/docs`
2. Register a user via `POST /api/v1/auth/register`
3. Login via `POST /api/v1/auth/login` (sets cookies)
4. Start stream via `POST /api/v1/stream/start`
5. Open `http://localhost:8000/api/v1/stream` in new tab
6. Should hear continuous audio (may take ~30s for first segment)

#### 3. Test WebSocket Events
1. Open browser dev tools console
2. Connect: `new WebSocket('ws://localhost:8000/api/v1/ws')`
3. Listen for events: `ws.onmessage = (e) => console.log(JSON.parse(e.data))`
4. Should see `{v:1, type:"segment_ready", data:{...}}`

#### 4. Multi-User Isolation Test
1. Open two incognito windows
2. Register/login different users in each
3. Start streams in both
4. Verify each sees only their own WS events
5. Verify each gets their own audio stream

---

## File Tree Summary

```
backend_v2/
├── api/
│   ├── integrations.py          [NEW] ListenBrainz endpoints
│   └── ws.py                    [NEW] WebSocket endpoint
├── audio/
│   ├── __init__.py              [NEW]
│   ├── mix.py                   [NEW] Port from dj_mix.py
│   └── transitions.py           [NEW] Port from transitions.py
├── integrations/
│   ├── __init__.py              [NEW]
│   ├── openrouter.py            [NEW] Port + enhancements
│   ├── elevenlabs.py            [NEW] Port
│   └── metadata/
│       ├── __init__.py          [NEW]
│       ├── musicbrainz.py       [NEW] Rate-limited client
│       ├── apple_music.py       [NEW] Catalog search
│       └── listenbrainz.py      [NEW] User integration
├── orchestration/
│   ├── __init__.py              [NEW]
│   ├── state.py                 [NEW] DJState + types
│   ├── agents.py                [NEW] Port + adapt agents
│   ├── loop.py                  [NEW] Port DJLoop
│   └── events.py                [NEW] User-scoped emitter
├── services/
│   ├── preference_bundle.py     [NEW]
│   └── session_manager.py       [MODIFY] DJLoop integration
├── streaming/
│   ├── __init__.py              [NEW]
│   └── pipeline.py              [NEW] Port RadioPipeline
├── models/
│   └── existing.py              [MODIFY] Add canonical ID columns
├── migrations/
│   └── versions/
│       └── xxx_add_canonical_ids.py  [NEW]
├── tests/
│   ├── test_preference_bundle.py     [NEW]
│   ├── test_musicbrainz.py           [NEW]
│   ├── test_websocket.py             [NEW]
│   └── test_stream.py                [NEW]
└── main.py                      [MODIFY] Mount WS router
```

---

## User Review Required

> [!WARNING]
> **Scope is large.** This plan ports ~3000 lines of working code from `backend/` to `backend_v2/` with adaptations. Recommend implementing in batches:
> 
> **Batch 1**: Orchestration + streaming (get audio playing)  
> **Batch 2**: PreferenceBundle + track selection  
> **Batch 3**: WebSocket + events  
> **Batch 4**: Metadata providers + migrations  

Questions:

1. **Batch approach OK?** Or do you want everything in one pass?
2. **RadioPipeline**: Should I implement per-user instances (simpler) or shared instance with user-tagged queues (more efficient)?
3. **Test priority**: Focus on unit tests first, or integration tests?
