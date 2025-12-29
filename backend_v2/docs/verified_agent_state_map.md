# Verified Agent + State Map (Jamify)

This document maps every agent/node in the legacy backend orchestration, their inputs/outputs, external calls, and gaps that need addressing for multi-user backend-v2 integration.

---

## DJState Schema (Current)

**File:** [graph.py](file:///c:/Users/JamiePC/Desktop/ai-djv2/backend/orchestration/graph.py#L128-L142)

```python
class DJState(TypedDict):
    now_playing: List[NowPlayingSegment]
    decision_trace: List[DecisionStep]
    session_id: Optional[str]          # ✅ Present but NOT user-scoped
    segment_queue_size: Optional[int]
    selected_song_uuid: Optional[str]
    song_a_uuid: Optional[str]         # Previous song for transitions
    song_b_uuid: Optional[str]         # Next song for transitions
    song_a_path: Optional[str]
    song_b_path: Optional[str]
    transition_plan: Optional[Dict[str, Any]]
    speech_script: Optional[str]
    tts_audio_path: Optional[str]
    rendered_segment_path: Optional[str]
    download_status: Optional[str]
```

### Missing Fields (to add)
| Field | Type | Purpose |
|-------|------|---------|
| `user_id` | `str` | Associate state with authenticated user |
| `mood_id` | `str \| None` | Current mood for personalization |
| `context_name` | `str \| None` | User context name for preferences |

---

## Agent/Node Map

### 1. InitialSongSelectorAgent
| Attribute | Value |
|-----------|-------|
| **File** | [graph.py](file:///c:/Users/JamiePC/Desktop/ai-djv2/backend/orchestration/graph.py#L157-L250) |
| **Inputs** | `session_id` |
| **Outputs** | `selected_song_uuid`, `song_b_uuid`, `decision_trace`, `download_status` |
| **External Calls** | `get_db()`, `get_soundcharts_client()`, `get_openrouter_client()` |
| **User Context** | ⚠️ Calls `load_user_context()` at line 169 |
| **Gap** | Needs `user_id` for per-user selection; uses file-based context |

---

### 2. TrackSelectorAgent
| Attribute | Value |
|-----------|-------|
| **File** | [graph.py](file:///c:/Users/JamiePC/Desktop/ai-djv2/backend/orchestration/graph.py#L399-L504) |
| **Inputs** | `session_id` |
| **Outputs** | `selected_song_uuid`, `decision_trace` |
| **External Calls** | `get_db()`, `get_soundcharts_client()`, `get_openrouter_client()` |
| **User Context** | ⚠️ Calls `load_user_context()` at line 415 |
| **Gap** | Uses file-based context; no mood/user scoping |

---

### 3. PlanningAgent
| Attribute | Value |
|-----------|-------|
| **File** | [graph.py](file:///c:/Users/JamiePC/Desktop/ai-djv2/backend/orchestration/graph.py#L507-L623) |
| **Inputs** | `session_id`, `song_a_uuid` (from history) |
| **Outputs** | `selected_song_uuid`, `song_b_uuid`, `decision_trace` |
| **External Calls** | `get_db()`, `get_soundcharts_client()`, `get_openrouter_client()` |
| **User Context** | ⚠️ Calls `load_user_context()` at line 522 |
| **Gap** | Duplicated `session_id` assignment (lines 516, 519); uses file-based context |

---

### 4. DownloadSongTool
| Attribute | Value |
|-----------|-------|
| **File** | [graph.py](file:///c:/Users/JamiePC/Desktop/ai-djv2/backend/orchestration/graph.py#L253-L338) |
| **Inputs** | `selected_song_uuid` |
| **Outputs** | `song_b_path`, `download_status` |
| **External Calls** | `get_cache_manager()`, `get_db()`, `get_soundcharts_client()`, `SongDownloader()` |
| **User Context** | ✅ None |
| **Gap** | No canonical ID matching (ISRC/MBID) after download |

---

### 5. SaveMetadataNode
| Attribute | Value |
|-----------|-------|
| **File** | [graph.py](file:///c:/Users/JamiePC/Desktop/ai-djv2/backend/orchestration/graph.py#L341-L396) |
| **Inputs** | `selected_song_uuid`, `song_b_path` |
| **Outputs** | (no state changes) |
| **External Calls** | `get_db()`, `get_soundcharts_client()` |
| **User Context** | ✅ None |
| **Gap** | No MusicBrainz/Apple Music enrichment; no artwork_url storage |

---

### 6. CheckCacheTool
| Attribute | Value |
|-----------|-------|
| **File** | [graph.py](file:///c:/Users/JamiePC/Desktop/ai-djv2/backend/orchestration/graph.py#L626-L656) |
| **Inputs** | `song_a_uuid`, `selected_song_uuid` |
| **Outputs** | `song_a_path`, `song_b_path` |
| **External Calls** | `get_cache_manager()` |
| **User Context** | ✅ None |
| **Gap** | None |

---

### 7. TransitionPlannerAgent
| Attribute | Value |
|-----------|-------|
| **File** | [graph.py](file:///c:/Users/JamiePC/Desktop/ai-djv2/backend/orchestration/graph.py#L664-L733) |
| **Inputs** | `song_a_uuid`, `song_b_uuid`, `song_a_path`, `song_b_path`, `session_id` |
| **Outputs** | `transition_plan` |
| **External Calls** | `get_db()`, `analyze_tracks_async()` |
| **User Context** | ✅ None |
| **Gap** | Stores LLM trace without user_id/mood_id |

---

### 8. InitialSpeechWriterAgent
| Attribute | Value |
|-----------|-------|
| **File** | [graph.py](file:///c:/Users/JamiePC/Desktop/ai-djv2/backend/orchestration/graph.py#L736-L794) |
| **Inputs** | `selected_song_uuid` |
| **Outputs** | `speech_script` |
| **External Calls** | `get_openrouter_client()`, `get_db()` |
| **User Context** | ⚠️ Reads `USER_CONTEXT_FILE` directly at lines 747-753 |
| **Gap** | Uses file-based context; no mood personality; no banter history |

---

### 9. SpeechWriterAgent
| Attribute | Value |
|-----------|-------|
| **File** | [graph.py](file:///c:/Users/JamiePC/Desktop/ai-djv2/backend/orchestration/graph.py#L797-L848) |
| **Inputs** | `selected_song_uuid`, `song_a_uuid`, `song_b_uuid`, `transition_plan` |
| **Outputs** | `speech_script` |
| **External Calls** | `get_openrouter_client()` |
| **User Context** | ⚠️ Reads `USER_CONTEXT_FILE` directly at lines 816-822 |
| **Gap** | Uses file-based context; no mood personality; no banter history |

---

### 10. ParallelPlanningNode
| Attribute | Value |
|-----------|-------|
| **File** | [graph.py](file:///c:/Users/JamiePC/Desktop/ai-djv2/backend/orchestration/graph.py#L851-L888) |
| **Inputs** | Full state |
| **Outputs** | `transition_plan`, `speech_script` (merged from sub-agents) |
| **External Calls** | Calls `TransitionPlannerAgent()`, `SpeechWriterAgent()` |
| **User Context** | (delegated to sub-agents) |
| **Gap** | None (wrapper) |

---

### 11. TTSAgent
| Attribute | Value |
|-----------|-------|
| **File** | [graph.py](file:///c:/Users/JamiePC/Desktop/ai-djv2/backend/orchestration/graph.py#L891-L913) |
| **Inputs** | `speech_script` |
| **Outputs** | `tts_audio_path` |
| **External Calls** | `get_elevenlabs_client()` |
| **User Context** | ✅ None |
| **Gap** | None |

---

### 12. InitialAudioRendererTool
| Attribute | Value |
|-----------|-------|
| **File** | [graph.py](file:///c:/Users/JamiePC/Desktop/ai-djv2/backend/orchestration/graph.py#L916-L1043) |
| **Inputs** | `song_b_path`, `tts_audio_path` |
| **Outputs** | `rendered_segment_path` |
| **External Calls** | FFmpeg subprocess |
| **User Context** | ✅ None |
| **Gap** | None |

---

### 13. AudioRendererTool
| Attribute | Value |
|-----------|-------|
| **File** | [graph.py](file:///c:/Users/JamiePC/Desktop/ai-djv2/backend/orchestration/graph.py#L1046-L1132) |
| **Inputs** | `transition_plan`, `song_a_path`, `song_b_path`, `tts_audio_path` |
| **Outputs** | `rendered_segment_path`, `render_metadata`, `render_metadata_path` |
| **External Calls** | `create_dj_mix()` |
| **User Context** | ✅ None |
| **Gap** | None |

---

### 14. PersistenceNode
| Attribute | Value |
|-----------|-------|
| **File** | [graph.py](file:///c:/Users/JamiePC/Desktop/ai-djv2/backend/orchestration/graph.py#L1135-L1176) |
| **Inputs** | `session_id`, `selected_song_uuid`, `rendered_segment_path`, `tts_audio_path` |
| **Outputs** | (no state changes) |
| **External Calls** | `get_db()` |
| **User Context** | ✅ None |
| **Gap** | ⚠️ Does NOT include `user_id` or `mood_id` in `insert_segment()` or `insert_play_history()` |

---

### 15. EmitEventsNode
| Attribute | Value |
|-----------|-------|
| **File** | [graph.py](file:///c:/Users/JamiePC/Desktop/ai-djv2/backend/orchestration/graph.py#L1179-L1221) |
| **Inputs** | `selected_song_uuid`, `decision_trace`, `rendered_segment_path` |
| **Outputs** | (no state changes) |
| **External Calls** | `get_event_emitter()` |
| **User Context** | ✅ None |
| **Gap** | Broadcasts to ALL connections; not user-scoped |

---

## DJLoop Analysis

**File:** [loop.py](file:///c:/Users/JamiePC/Desktop/ai-djv2/backend/orchestration/loop.py#L15-L314)

| Attribute | Value |
|-----------|-------|
| **Session ID** | Generated at line 20: `self.session_id = str(uuid.uuid4())` |
| **User Association** | ❌ None — session is not linked to any user |
| **State Passed** | Lines 231-239 only include `session_id`, `song_a_uuid`, `songs_since_last_speech`, `failed_song_uuids` |
| **Gap** | Needs to accept `user_id`, `mood_id`, `context_name` from SessionRunner |

---

## load_user_context() References

**File:** [graph.py](file:///c:/Users/JamiePC/Desktop/ai-djv2/backend/orchestration/graph.py#L28-L70)

| Location | Agent | Line |
|----------|-------|------|
| Function definition | — | 28-70 |
| InitialSongSelectorAgent | `user_context = load_user_context()` | 169 |
| TrackSelectorAgent | `user_context = load_user_context()` | 415 |
| PlanningAgent | `user_context = load_user_context()` | 522 |
| InitialSpeechWriterAgent | Reads `USER_CONTEXT_FILE` directly | 747-749 |
| SpeechWriterAgent | Reads `USER_CONTEXT_FILE` directly | 816-818 |
| get_ai_search_query | Receives `user_context` as parameter | 73 |

### Replacement Strategy
All references must be replaced with `PreferenceBundle` loaded from DB:
1. `PreferenceBundle.context.raw_text` replaces `user_context["raw_text"]`
2. `PreferenceBundle.mood` provides energy/valence targets
3. `PreferenceBundle.feedback` provides like/dislike history
4. `PreferenceBundle.mood_profile.summary_text` for personalization

---

## Backend-v2 Readiness

### SessionRunner (backend_v2/services/session_manager.py)
✅ Already has:
- `user_id`, `session_id`, `mood_id`, `context_id` fields
- `segment_queue: asyncio.Queue`
- `start()` / `stop()` methods

❌ Missing:
- Actual DJLoop integration (marked TODO at lines 53-55, 74-77)

### Models with user_id/mood_id
✅ Already added in `backend_v2/models/existing.py`:
- `Session.user_id`, `Session.mood_id`, `Session.context_id`
- `PlayHistory.user_id`, `PlayHistory.mood_id`
- `Segment.user_id`, `Segment.mood_id`
- `LLMTrace.user_id`, `LLMTrace.mood_id`

### Stream API
✅ Endpoints exist in `backend_v2/api/stream.py`:
- `POST /api/v1/stream/start` (lines 25-70)
- `GET /api/v1/stream/status` (lines 73-94)
- `POST /api/v1/stream/stop` (lines 97-111)
- `GET /api/v1/stream` (lines 114-166)

❌ Missing:
- `WS /api/v1/ws` endpoint not implemented
- Audio generator pulls from `segment_queue` but no segments are being produced

---

## Songs Table — Current Schema vs Required

### Current (backend_v2/models/existing.py)
```python
class Song(Base):
    uuid: str                # Primary key (Soundcharts UUID)
    title: str
    artist: str
    release_date: str
    language_code: str
    explicit: int
    local_path: str
    duration_sec: float
    filesize_bytes: int
    play_count: int
    last_played_at: str
```

### Required Additions
| Column | Type | Purpose |
|--------|------|---------|
| `isrc` | `String(12)` | ISRC code (canonical recording ID) |
| `recording_mbid` | `String(36)` | MusicBrainz recording MBID |
| `release_mbid` | `String(36)` | MusicBrainz release MBID |
| `artist_mbid` | `String(36)` | MusicBrainz artist MBID |
| `apple_song_id` | `String(20)` | Apple Music song ID |
| `apple_album_id` | `String(20)` | Apple Music album ID |
| `apple_artist_id` | `String(20)` | Apple Music artist ID |
| `artwork_url` | `Text` | Album artwork URL |
| `genres_json` | `Text` | JSON array of genres |
| `tags_json` | `Text` | JSON array of tags (from MusicBrainz) |

---

## Integration Gaps

### MusicBrainz (backend/integrations/musicbrainz.py)
- ✅ Rate limiting (1 req/sec)
- ✅ File-based caching
- ❌ No User-Agent from env `MUSICBRAINZ_USER_AGENT`
- ❌ Not used in DownloadSongTool for canonical matching

### ListenBrainz (backend/integrations/listenbrainz.py)
- ✅ Basic client exists
- ❌ No per-user token storage
- ❌ No connect/disconnect endpoints
- ❌ Not used for scrobbling

### Apple Music
- ❌ No client implementation
- ❌ No artwork fetching

---

## Summary of Required Changes

| Component | Change Type | Priority |
|-----------|-------------|----------|
| DJState | Add `user_id`, `mood_id`, `context_name` | 🔴 Critical |
| DJLoop | Accept user context from SessionRunner | 🔴 Critical |
| load_user_context() | Replace with PreferenceBundle | 🔴 Critical |
| PersistenceNode | Include user_id/mood_id in writes | 🔴 Critical |
| EmitEventsNode | Scope broadcasts to user's connections | 🟡 High |
| SessionRunner | Integrate actual DJLoop | 🔴 Critical |
| Songs table | Add canonical ID columns | 🟡 High |
| SaveMetadataNode | MusicBrainz/Apple enrichment | 🟡 High |
| WS endpoint | Implement /api/v1/ws | 🟡 High |
| ListenBrainz | User integration endpoints | 🟢 Medium |
| Apple Music | Catalog search client | 🟢 Medium |
