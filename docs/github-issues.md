# GitHub Issues - Ready to Create

This file contains formatted GitHub issues that can be copied and pasted into the GitHub issue creation form.

## How to Use

1. Go to https://github.com/armoordonjamie-sketch/ai-djv2/issues/new
2. Copy the title and body from each issue below
3. Add appropriate labels: `bug`, `backend`, and priority label (`critical`, `high`, or `medium`)

---

## Issue 1: HistoryItem used as dict in catalog selection

**Labels:** `bug`, `backend`, `critical`

**Title:**
```
[Critical] HistoryItem used as dict in catalog selection
```

**Body:**
```markdown
## Location
`backend_v2/orchestration/agents.py:543-552`

## Symptom
`HistoryItem` is a dataclass, but the code calls `hist_item.get(...)`, which raises `AttributeError` once history is non-empty.

## Impact
Catalog selection flow crashes during recent-track conversion, causing fallback failures or a stalled loop.

## Suggested Fix
- Replace dict access with attributes: `hist_item.artist`, `hist_item.title`.
- If features are required for MMR, either extend `HistoryItem` to include features or query the DB for features by `song_uuid` before building `CatalogTrack`.

## Reference
See [docs/issues.md](docs/issues.md) for full details.
```

---

## Issue 2: Missing required argument in fallback to legacy selection

**Labels:** `bug`, `backend`, `critical`

**Title:**
```
[Critical] Missing required argument in fallback to legacy selection
```

**Body:**
```markdown
## Location
`backend_v2/orchestration/agents.py:582`

## Symptom
`select_track(db, bundle, prev_song)` omits the required `state` argument.

## Impact
Raises a `TypeError` at runtime when catalog flow falls back.

## Suggested Fix
- Call `select_track(db, bundle, state, prev_song, history_ids)` with the correct signature.

## Reference
See [docs/issues.md](docs/issues.md) for full details.
```

---

## Issue 3: Invalid access to song features and missing intent field

**Labels:** `bug`, `backend`, `critical`

**Title:**
```
[Critical] Invalid access to song features and missing intent field
```

**Body:**
```markdown
## Location
`backend_v2/orchestration/agents.py:630-633`

## Symptom
- `song.features[0]` is used, but `Song.features` is `uselist=False` and should be accessed as `song.features`.
- `intent.rationale` does not exist; the column is `selection_rationale`.

## Impact
Crash immediately after successful acquisition, preventing playback.

## Suggested Fix
- Use `song.features.energy` / `song.features.valence` / `song.features.tempo`.
- Use `intent.selection_rationale` (or fallback to a default string).

## Reference
See [docs/issues.md](docs/issues.md) for full details.
```

---

## Issue 4: Selected song does not include a `features` dict

**Labels:** `bug`, `backend`, `high`

**Title:**
```
[High] Selected song does not include a `features` dict
```

**Body:**
```markdown
## Location
`backend_v2/orchestration/agents.py:625-635`

## Symptom
The returned dict puts `energy`, `valence`, and `tempo` at top level instead of under `features`.

## Impact
Transition planning and mixing logic expect `song['features']`, so they lose feature data and fall back to generic transitions.

## Suggested Fix
- Return a `features` dict consistent with `select_track` and `get_scored_candidates` outputs.

## Reference
See [docs/issues.md](docs/issues.md) for full details.
```

---

## Issue 5: Genres/tags are passed as raw JSON strings

**Labels:** `bug`, `backend`, `high`

**Title:**
```
[High] Genres/tags are passed as raw JSON strings
```

**Body:**
```markdown
## Location
`backend_v2/services/preference_bundle.py:952-960`

## Symptom
`song.genres` and `song.tags` are stored as JSON strings, but `apply_hard_constraints` treats them as lists and lowercases each element.

## Impact
Denylist/no-go checks operate on characters, so genre filtering silently fails.

## Suggested Fix
- Parse JSON strings to lists when building `song_dict`.
- If parsing fails, fall back to an empty list and log a warning.

## Reference
See [docs/issues.md](docs/issues.md) for full details.
```

---

## Issue 6: Explicit-lyrics filtering never triggers

**Labels:** `bug`, `backend`, `high`

**Title:**
```
[High] Explicit-lyrics filtering never triggers
```

**Body:**
```markdown
## Location
`backend_v2/services/preference_bundle.py:747-753`

## Symptom
`apply_hard_constraints` checks `song['explicit']`, but the song dict never includes it.

## Impact
Users who set explicit_lyrics=avoid still get explicit tracks.

## Suggested Fix
- Add `explicit` from `Song.explicit` into each song dict.
- Normalize to boolean when checking (SQLite uses 0/1).

## Reference
See [docs/issues.md](docs/issues.md) for full details.
```

---

## Issue 7: Caller cannot override `reject_unknown` to False

**Labels:** `bug`, `backend`, `medium`

**Title:**
```
[Medium] Caller cannot override `reject_unknown` to False
```

**Body:**
```markdown
## Location
`backend_v2/services/preference_bundle.py:670`

## Symptom
`reject_unknown = reject_unknown if reject_unknown else REJECT_UNKNOWN_FEATURES` forces the config default when `reject_unknown` is `False`.

## Impact
Callers cannot disable unknown-feature rejection.

## Suggested Fix
- Use `reject_unknown = REJECT_UNKNOWN_FEATURES if reject_unknown is None else reject_unknown`.

## Reference
See [docs/issues.md](docs/issues.md) for full details.
```

---

## Issue 8: Unhandled JSON parse errors in user context

**Labels:** `bug`, `backend`, `medium`

**Title:**
```
[Medium] Unhandled JSON parse errors in user context
```

**Body:**
```markdown
## Location
`backend_v2/services/preference_bundle.py:414`

## Symptom
`json.loads(context_row.parsed_json)` is unguarded.

## Impact
A single malformed context record crashes bundle construction and the DJ loop.

## Suggested Fix
- Wrap in try/except, log the parse error, and set `parsed_json` to `None`.

## Reference
See [docs/issues.md](docs/issues.md) for full details.
```

---

## Issue 9: Mood metadata missing from MoodData

**Labels:** `bug`, `backend`, `medium`

**Title:**
```
[Medium] Mood metadata missing from MoodData
```

**Body:**
```markdown
## Location
`backend_v2/services/preference_bundle.py:43` (MoodData definition) and `build_preference_bundle`

## Symptom
MoodData does not carry `danceability_target`, `genre_seeds_json`, `vibe_keywords_json`, `intro_personality`, or `era_hint`.

## Impact
Prompt generation and catalog scoring that look for these fields always see them as missing, so mood-specific personalization is not applied.

## Suggested Fix
- Extend `MoodData` and populate these fields in `build_preference_bundle`.
- Update usages to reference the structured fields directly instead of `hasattr` checks.

## Reference
See [docs/issues.md](docs/issues.md) for full details.
```

---

## Suggested Fix Order

1. Fix the runtime crashes in `agents.py` (issues 1-4).
2. Fix hard-constraint input parsing and explicit filtering (issues 5-6).
3. Harden bundle building and optional overrides (issues 7-8).
4. Extend MoodData to unlock prompt/catalog personalization (issue 9).

