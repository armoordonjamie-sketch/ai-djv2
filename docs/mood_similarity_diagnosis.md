# Mood Similarity Issue - Diagnosis

## Problem Report

User reports that all 5 moods created during onboarding:
1. Appear to be the same
2. Have identical intro TTS

## Investigation Results

### ✅ Moods Are Correctly Configured

The moods ARE properly differentiated in the database:

| Mood | Color | Energy Target | Valence Target | Genre | Personality |
|------|-------|---------------|----------------|-------|-------------|
| Flow | Pink (#ec4899) | 0.6 | 0.6 | Pop | casual_funny |
| Energy | Orange (#f59e0b) | 0.85 | 0.75 | Pop | casual_funny |
| Chill | Cyan (#06b6d4) | 0.35 | 0.55 | Pop | casual_funny |
| Party | Purple (#8b5cf6) | 0.9 | 0.85 | Pop | casual_funny |
| Late Night | Slate (#1e293b) | 0.45 | 0.4 | Pop | casual_funny |

**Note:** All moods inherit the user's onboarding data:
- Genre: `["Pop"]` (from voice onboarding)
- Personality: `casual_funny` (from voice onboarding)

### ⚠️ Intro Songs Are TOO SIMILAR

The songs selected for each mood's intro are not diverse enough:

| Mood | Song | Energy (Actual) | Energy (Target) | Valence (Actual) | Valence (Target) |
|------|------|-----------------|-----------------|------------------|------------------|
| Flow | Nonsense - Sabrina Carpenter | **0.78** | 0.6 | 0.41 | 0.6 |
| Energy | Cut To The Feeling - Carly Rae Jepsen | **0.76** | **0.85** | 0.40 | 0.75 |
| Chill | I miss you, I'm sorry - Gracie Abrams | **0.74** | **0.35** | 0.70 | 0.55 |
| **Party** | **Cut To The Feeling - Carly Rae Jepsen** | **0.76** | **0.9** | 0.40 | 0.85 |
| Late Night | False God - Taylor Swift | **0.72** | 0.45 | 0.69 | 0.4 |

**Issues Identified:**

1. **🔴 All songs have similar energy (~0.72-0.78)**, despite mood targets ranging from 0.35 to 0.9
2. **🔴 Chill mood got a 0.74 energy song** (should be ~0.35)
3. **🔴 Party mood got a 0.76 energy song** (should be ~0.9)
4. **🔴 Energy and Party moods use THE SAME SONG**
5. **🟡 All songs are Pop** (limited genre diversity due to user's onboarding input)

### Why This Happens

#### 1. Limited Song Database

The music library appears to have limited songs with:
- Very low energy (< 0.4 for Chill)
- Very high energy (> 0.85 for Party)
- Genre diversity beyond Pop

#### 2. Track Selection Algorithm Issues

Location: `backend_v2/orchestration/agents.py:select_track()`

The track selector uses a scoring algorithm that considers:
- Genre match
- Energy/valence distance from target
- Danceability, acousticness, instrumentalness
- **BUT** the weighting may not prioritize energy/valence match strongly enough

#### 3. All Moods Share Same Context

Because all moods inherit:
- Same genres from user profile
- Same DJ personality

The intro speech generation might produce similar outputs.

---

## Root Causes

### Primary: Track Selection Not Respecting Mood Targets

**File:** `backend_v2/orchestration/agents.py:select_track()`

The scoring algorithm needs to:
1. **Weight energy/valence match MORE HEAVILY** (currently may be treating all features equally)
2. **Penalize duplicate selections** (Energy and Party shouldn't use same song)
3. **Expand search if no good matches found** (relax filters progressively)

### Secondary: Limited Music Library

The current song database appears to have:
- **Limited energy range** (mostly mid-energy songs ~0.7)
- **Limited genre diversity** (all results were Pop)
- **Small total song count**

This is expected during development, but limits personalization.

---

## Impact on User Experience

While moods are technically different:
1. **Initial perception is "all the same"** because intro songs sound similar
2. **Energy/Party feel identical** (literally the same song)
3. **Chill doesn't feel chill** (got a 0.74 energy song instead of 0.35)
4. **Intros may sound repetitive** if speech generation doesn't emphasize mood differences

---

## Recommended Fixes

### Priority 1: Fix Track Selection Algorithm

**File:** `backend_v2/orchestration/agents.py`

1. **Increase energy/valence weighting** in score calculation:
   ```python
   # Current: Equal weight to all features
   # Fix: Weight energy/valence 3x-5x more heavily for initial intro selection
   energy_distance = abs(song_energy - bundle.mood.energy_target)
   valence_distance = abs(song_valence - bundle.mood.valence_target)
   mood_match_score = 5.0 * (1.0 - energy_distance) + 5.0 * (1.0 - valence_distance)
   ```

2. **Add recent track history check** to prevent duplicates:
   ```python
   # Penalize songs used in other moods' intros for this user
   if song_uuid in recently_used_for_intros:
       score *= 0.1  # Heavy penalty
   ```

3. **Add fallback widening** if no good matches:
   ```python
   # If no songs within 0.2 of target, expand search
   # If still none, relax genre requirements
   ```

### Priority 2: Diversify Mood Genres (Optional)

**File:** `backend_v2/services/mood_generator.py`

Instead of all moods inheriting the same genres, could vary by mood:
```python
# Example: Expand genres based on mood type
if template.name == "Chill":
    mood_genres = base_genres + ["ambient", "indie", "folk"]
elif template.name == "Energy":
    mood_genres = base_genres + ["electronic", "rock", "hip-hop"]
# etc.
```

### Priority 3: Mood-Specific Intro Prompts

**File:** `backend_v2/integrations/openrouter.py` or intro speech generation

Add mood context to intro speech generation:
```python
# Include mood characteristics in prompt
prompt += f"This is a {mood.name} mood (energy: {mood.energy_target}, vibe: {mood.description})"
```

---

## Quick Fix for Testing

The fastest way to see differentiation would be to:

1. **Manually add more songs** to the database with diverse energy levels:
   - Low energy (< 0.3): Classical, ambient, lo-fi
   - High energy (> 0.85): EDM, rock, uptempo pop

2. **Re-run onboarding** after adjusting track selection weights

---

## Summary

**The moods themselves are correctly configured** ✅

**The problem is track selection** ⚠️ - it's not respecting the mood energy/valence targets and is selecting very similar songs for all moods.

**Quick test:** Query the songs table to see how many songs exist with energy < 0.4 or energy > 0.85. If the answer is "very few" or "none", that explains why Chill and Party couldn't get appropriate songs.

---

**Next Steps:**

1. Check song library diversity: `SELECT COUNT(*), MIN(energy), MAX(energy), AVG(energy) FROM song_features`
2. Fix track selection weighting in `select_track()`
3. Add duplicate prevention for intro generation
4. Test with re-onboarding

