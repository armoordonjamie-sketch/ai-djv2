# Onboarding Improvements - Implementation Notes

## What Was Implemented

This implementation enhances the onboarding data collection and utilization to improve AI DJ personalization.

### Files Modified

1. **`backend_v2/models/user_profile.py`**
   - Added 4 new columns to `UserProfile` model:
     - `energy_preference`: VARCHAR(20) - "high_energy", "low_energy", "mixed"
     - `tempo_preference`: VARCHAR(20) - "fast", "slow", "mixed"
     - `listening_contexts`: TEXT (JSON array) - ["workout", "focus", "party", etc.]
     - `era_preference`: VARCHAR(20) - "new_releases", "classics", "mixed", "no_preference"

2. **`backend_v2/api/onboard.py`**
   - Updated `OnboardSubmitPayload` schema with new fields
   - Updated `submit_onboarding` endpoint to persist new fields
   - Enhanced `_build_raw_context` to include new preferences in text summary

3. **`backend_v2/services/preference_bundle.py`**
   - Extended `UserProfileData` dataclass with new fields
   - Added helper methods: `prefers_high_energy()`, `prefers_classics()`, etc.
   - Added bundle helpers: `get_energy_preference()`, `get_era_preference()`, etc.
   - Updated builder to load new fields from database

4. **`backend_v2/integrations/openrouter.py`**
   - Enhanced `build_profile_context()` to include:
     - Better utilization of `favorite_songs` (now shows 5 songs with emphasis)
     - Energy preference with emoji indicators
     - Tempo preference with emoji indicators
     - Listening contexts
     - Era preference

5. **`backend_v2/catalog/selector.py`**
   - Updated `search_catalog_tracks()` to include favorite songs as search queries
   - Enhanced `score_track_relevance()` with:
     - Energy preference scoring (+0.1 for matching preference)
     - Tempo preference scoring (+0.08 for matching preference)
     - Favorite song title matching (+0.2 boost)
     - Era preference scoring using popularity as proxy

6. **`backend_v2/scripts/setup_elevenlabs_agent.py`**
   - Updated system prompt to guide agent to infer preferences from preview reactions
   - Added guidance for learning energy, tempo, era preferences naturally
   - Added listening context collection guidance
   - Updated tool schema with new fields and descriptions

### New Files Created

1. **`backend_v2/scripts/migrate_enhanced_preferences.py`**
   - Database migration script for new columns

## How to Run Locally

### 1. Run Database Migration

```bash
cd backend_v2
python -m backend_v2.scripts.migrate_enhanced_preferences
```

### 2. Update ElevenLabs Agent

```bash
cd backend_v2
python -m backend_v2.scripts.setup_elevenlabs_agent
```

This will update the ElevenLabs agent with:
- New system prompt
- Updated tool schema with new fields

### 3. Verify Changes

The backend will automatically use the new fields once the migration is complete.

## Interfaces & Contracts

### OnboardSubmitPayload (Extended)

```python
class OnboardSubmitPayload(BaseModel):
    # Existing fields...
    user_id: str
    display_name: Optional[str]
    favorite_genres: Optional[List[str]]
    favorite_artists: Optional[List[str]]
    favorite_songs: Optional[List[str]]  # NOW BETTER UTILIZED
    no_go: Optional[List[str]]
    explicit_lyrics: Optional[Literal["ok", "avoid", "depends"]]
    dj_personality: Optional[str]
    raw_context: Optional[str]
    
    # NEW FIELDS
    energy_preference: Optional[Literal["high_energy", "low_energy", "mixed"]]
    tempo_preference: Optional[Literal["fast", "slow", "mixed"]]
    listening_contexts: Optional[List[str]]  # ["workout", "focus", "party", etc.]
    era_preference: Optional[Literal["new_releases", "classics", "mixed", "no_preference"]]
```

### PreferenceBundle New Helpers

```python
# Get new preference fields
bundle.get_favorite_songs() -> List[str]
bundle.get_energy_preference() -> Optional[str]
bundle.get_tempo_preference() -> Optional[str]
bundle.get_listening_contexts() -> List[str]
bundle.get_era_preference() -> str
```

## Architecture Decisions

### 1. Inferring Preferences from Preview Reactions
Instead of asking users checklist questions, the agent is instructed to **infer** energy/tempo/era preferences from how users react to song previews. This provides more natural conversation flow and accurate data.

### 2. Favorite Songs as Search Seeds
Favorite songs are now used as additional search queries in the catalog selector, improving the chances of finding music the user will love.

### 3. Era Preference Scoring via Popularity
Since Deezer doesn't reliably provide release year, we use track popularity as a proxy:
- High popularity (≥70) → likely newer/current hits
- Lower popularity (<50) → likely older/classic tracks

### 4. Listening Contexts for Future Use
Listening contexts are collected and stored but not yet actively used in track selection. Future enhancement: auto-suggest moods based on context (e.g., "Workout" mood when user says they listen during gym).

## TODOs & Known Limitations

1. **Era scoring heuristic**: Using popularity as a proxy for release era is imperfect. Could be improved with actual release date data.

2. **Listening contexts not yet used in mood generation**: Currently stored but not utilized. Could enhance mood generation to create context-specific moods.

3. **Tempo preference ranges**: Currently using fixed thresholds (120 BPM for fast, 100 BPM for slow). Could be refined based on genre.

## Dependencies Added

No new dependencies - all changes use existing packages.

## Testing Checklist

- [ ] Run database migration successfully
- [ ] Update ElevenLabs agent via setup script
- [ ] Complete onboarding with new agent
- [ ] Verify new fields are saved to user_profiles
- [ ] Verify track selection considers new preferences
- [ ] Verify LLM prompts include new preference data

