# Personality and Selection Gap Report

## Phase A Audit Findings

**Date**: 2025-12-21  
**Auditor**: Batch 6 Agent

---

## Current V2 Implementation Status

### ✅ What Exists

| Component | Location | Status |
|-----------|----------|--------|
| PreferenceBundle | `services/preference_bundle.py` | Complete |
| Deterministic scoring | `score_candidate()` | Exists but incomplete |
| LLM track selection | `orchestration/agents.py:select_track()` | Exists |
| Song download | `orchestration/agents.py:acquire_song_by_name()` | Exists but unsafe |
| Persona service | `services/persona.py` | Exists with cooldowns |
| Speech sanitizers | `integrations/openrouter.py` | Complete |

### ❌ What's Missing

| Feature | Legacy Location | V2 Gap |
|---------|-----------------|--------|
| Search query generator | `openrouter.py:generate_search_queries()` | **NOT IMPLEMENTED** |
| "Artist - Title" format enforcement | Legacy system prompt + validation | Not enforced |
| Hard tempo/energy constraints | Persona says "NO slow songs" | Not enforced in scoring |
| MIN_TEMPO, MIN_ENERGY config | N/A | Does not exist |
| Download concurrency guard | N/A | Not implemented |
| Download deny list (albums, mixes) | N/A | Not implemented |

---

## Detailed Gap Analysis

### 1. Search Query Generation

**Legacy** (`backend/integrations/openrouter.py:724-844`):
- `generate_search_queries()` creates 5-10 seed queries
- Enforces "Artist - Title" format in system prompt
- Uses raw_context for personalization
- Avoids recently played songs/artists

**V2 Gap**:
- **No equivalent function exists**
- Tests reference `mock_client.generate_search_queries` but implementation absent
- `acquire_song_by_name()` accepts arbitrary `artist`, `title` with no validation

---

### 2. Persona Music Constraints

**Legacy** (`data/user_context.txt`):
```
Music Preferences:
- High energy only no slow songs no ballads no sleepy vibes
```

**V2 Current** (`services/persona.py:228`):
```python
DEFAULT_MUSIC_CONSTRAINTS = [
    "High energy only - NO slow songs, NO ballads, NO sleepy vibes",
]
```

**Gap**: Constraint text exists but **NOT ENFORCED** in `score_candidate()`:
- No check for `song.features.tempo < MIN_TEMPO`
- No check for `song.features.energy < MIN_ENERGY`
- No genre/tag check for "ballad"
- Constraints are informational only, not blocking

---

### 3. Deterministic Scoring

**V2 Current** (`services/preference_bundle.py:511-620`):

| Check | Type | Effect |
|-------|------|--------|
| Disliked songs | HARD BAN | Returns -1000 |
| Disliked artists | HARD BAN | Returns -500 |
| Recent plays | Penalty | -0.1 to -0.8 |
| Energy mismatch | Penalty | -0.2 × distance |
| Valence mismatch | Penalty | -0.2 × distance |

**Gap**: 
- Tempo/energy thresholds **not hard bans** (only soft penalties)
- Slow songs (e.g., tempo < 90 BPM) could still be selected if they score well otherwise
- Persona constraints not consulted

---

### 4. Download Safety

**V2 Current** (`orchestration/agents.py:69-144`):
```python
async def acquire_song_by_name(db, artist, title, target_uuid):
    query = f"{artist} - {title} official audio"
    result = await downloader.download_song(query=query, ...)
```

**Gaps**:
1. **No format validation**: Could receive malformed "artist" or "title"
2. **No concurrency guard**: Same song could be downloaded twice simultaneously
3. **No deny list**: Albums, mixes, live sets, "sped up" versions not blocked
4. **No timeout handling**: Stalled download blocks DJLoop

---

## Function Mapping: Legacy → V2

| Legacy Function | V2 Equivalent | Status |
|-----------------|---------------|--------|
| `generate_search_queries()` | None | **MISSING** |
| `generate_track_selection()` | `select_track()` | Partial |
| `generate_transition_plan()` | `plan_transition()` | Complete |
| `generate_dj_speech()` | `write_transition_speech()` | Complete |
| `_sanitize_speech_context()` | Same name in openrouter.py | Complete |
| `_sanitize_tts_output()` | Same name in openrouter.py | Complete |

---

## Impact Assessment

### Why It Matters

1. **User hears slow songs despite persona ban**
   - Persona says "NO slow songs" but scoring doesn't enforce it
   - User trust eroded when DJ ignores stated preferences

2. **Garbage downloads pollute library**
   - Without "Artist - Title" enforcement, LLM may output single artists, genres, or vibes
   - Downloads fail or return wrong content
   - Storage wasted, metadata enrichment fails

3. **No library expansion**
   - Without search query generation, library never grows beyond initial songs
   - User eventually hears same songs on loop

4. **Potential duplicate downloads**
   - Multiple concurrent download requests for same query waste bandwidth
   - Could create duplicate DB entries

---

## Required Fixes (Phase B)

### B1: Implement Search Query Generator
- Create `integrations/search_queries.py`
- Strict "Artist - Title" validation with retry
- Persona + mood influence on suggestions

### B2: Hard Constraint Enforcement
- Add MIN_TEMPO = 90 BPM (configurable)
- Add MIN_ENERGY = 0.3 (configurable)
- Reject before scoring, not just penalize

### B3: Safe Downloads
- Validate query format before download
- Add concurrency lock per query
- Add deny list patterns

### B4: Scoring Improvements
- Limit candidates to top 20-50 for LLM
- Robust fallback on LLM failure
