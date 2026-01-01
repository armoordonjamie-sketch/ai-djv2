# AI Adventurousness Fix

**Date:** 2025-12-29  
**Issue:** AI was not being adventurous with song selection, repeating the same 2 artists (Taylor Swift, Sabrina Carpenter) over and over

## Root Cause Analysis

### Investigation Process
1. Checked LLM traces in database - found NO track selection traces
2. Realized the new catalog-based flow doesn't use LLM for selection
3. Track selection uses direct Deezer API search + MMR diversity algorithm
4. Problem: Search queries were TOO NARROW

### The Actual Problem

**Location:** `backend_v2/catalog/selector.py:259-294`

The search query generation was creating a feedback loop:

```python
# OLD CODE - TOO NARROW
favorite_artists = bundle.get_favorite_artists()[:3]  # ['Taylor Swift', 'Sabrina Carpenter']
for artist in favorite_artists:
    queries.append(artist)

if len(queries) < 3 and bundle.mood.example_artists:
    for artist in bundle.mood.example_artists[:2]:  # ['Taylor Swift', 'Sabrina Carpenter']
        queries.append(artist)
```

**Result:** Queries = `['Taylor Swift', 'Sabrina Carpenter']` EVERY SINGLE TIME

**Why this caused repetition:**
1. Deezer only returns top 50 tracks per artist
2. MMR diversity can ONLY pick from what Deezer returns
3. If we only search 2 artists, we only get their songs
4. Even with diversity filtering, we're stuck in a 100-track pool (50 per artist)
5. After playing 10-15 songs, we start repeating because the pool is exhausted

## The Fix

### Change 1: Balanced Query Strategy (`backend_v2/catalog/selector.py`)

**Before:** Artist-heavy queries (same 2 artists repeated)
**After:** Balanced FAMILIAR + EXPLORATORY approach

```python
# NEW CODE - BALANCED APPROACH
# Build exclusion set for recently-played artists
recent_artists_lower = {a.lower() for a in bundle.history.recent_artists[:15] if a}

# Step 1: Add ONE favorite artist (if not recently played)
favorite_artists = [a for a in bundle.get_favorite_artists()[:5] if a.lower() not in recent_artists_lower]
if favorite_artists:
    queries.append(favorite_artists[0])

# Step 2: Add GENRE-BASED search for exploration (HIGH PRIORITY)
if bundle.mood.genre_seeds:
    queries.append(" ".join(bundle.mood.genre_seeds[:2]))

# Step 3: Add ONE mood example artist (if different and not recently played)
# ...

# Step 4: Add a SECOND favorite artist if we still have room
```

**Key Changes:**
- ✅ Excludes recently-played artists from search queries
- ✅ Prioritizes GENRE searches over artist searches
- ✅ Limits to ONE favorite artist initially (not 3)
- ✅ Avoids duplicate artists between favorites and mood examples
- ✅ Creates more diverse query sets

### Change 2: Increased Diversity Weight (`backend_v2/orchestration/agents.py:578`)

```python
# Before
lambda_param=0.7  # Balanced relevance/diversity

# After
lambda_param=0.5  # Lower = more diversity-focused
```

**MMR Lambda Parameter:**
- `1.0` = Pure relevance (always pick highest-scored track)
- `0.5` = Balanced (50% relevance, 50% diversity)
- `0.0` = Pure diversity (maximum variety)

Lowering from 0.7 to 0.5 makes the AI more adventurous while still respecting mood/preferences.

## Example Query Evolution

### Session Start
- Queries: `['Taylor Swift', 'pop indie', 'Sabrina Carpenter']`
- Result: Mix of Taylor Swift, Sabrina Carpenter, AND genre-based discoveries

### After 5 Songs (Taylor Swift played 3 times)
- Recent artists: `['Taylor Swift', 'Sabrina Carpenter', ...]`
- Queries: `['Olivia Rodrigo', 'pop indie', 'Gracie Abrams']`  ← NEW ARTISTS!
- Result: Fresh artists while staying in the same genre/vibe

### After 10 Songs
- Recent artists: `['Taylor Swift', 'Sabrina Carpenter', 'Olivia Rodrigo', 'Gracie Abrams', ...]`
- Queries: `['Chappell Roan', 'pop indie', 'Maisie Peters']`  ← EVEN MORE VARIETY!
- Result: Continuous discovery within the user's taste profile

## Technical Details

### MMR (Maximal Marginal Relevance) Algorithm

The MMR algorithm balances two competing goals:
1. **Relevance:** How well does the track match the mood/preferences?
2. **Diversity:** How different is it from recently played tracks?

**Formula:**
```
MMR(track) = λ × Relevance(track) + (1-λ) × Diversity(track)
```

Where:
- `Relevance` = Score based on mood energy/valence, genre match, user likes
- `Diversity` = Dissimilarity to recent tracks (artist, title, features)
- `λ` = Balance parameter (0.5 = equal weight)

**Our Changes:**
- Increased diversity weight (λ: 0.7 → 0.5)
- Improved diversity calculation by excluding recent artists from searches
- Expanded candidate pool via genre-based queries

### Search Query Rotation

The new system rotates between:
1. **Familiar:** One favorite artist (changes as artists are played)
2. **Exploratory:** Genre-based search (e.g., "pop indie")
3. **Adjacent:** One mood example artist (not recently played)

This creates a **sliding window** of discovery:
- Start: Familiar artists
- Middle: Mix of familiar + adjacent
- Later: New discoveries in the same genre space

## Expected Behavior After Fix

### Good Variety ✅
- Session with 20 songs should have 10-15 different artists
- Same artist may appear 2-3 times max (not 10+ times)
- Genre stays consistent with mood
- User preferences are respected

### Still Personalized ✅
- Tracks match mood energy/valence targets
- Genres align with user favorites
- Liked artists appear more frequently (but not exclusively)
- Disliked artists/genres are avoided

### Adventurous But Safe ✅
- Discovers new artists within user's taste profile
- Doesn't jump to completely unrelated genres
- Balances familiarity with novelty
- Respects feedback (likes/dislikes)

## Testing

### Manual Test
1. Start a new stream with "Flow" mood
2. Let it play 15-20 songs
3. Check play history - should see 10+ different artists
4. Verify genres stay within mood (pop, indie, etc.)

### Backend Logs to Watch
```
📚 Searching global catalog with MMR diversity...
Searching catalog with 3 queries: ['Artist A', 'genre genre', 'Artist B']...
🚫 Excluding N previously played tracks from selection
Selected diverse track: New Artist - Cool Song
```

**Good signs:**
- Query list changes over time
- "Excluding N tracks" count increases
- Different artists selected

**Bad signs:**
- Same 2 queries every time
- "Excluding 0 tracks" (history not working)
- Same artist 5+ times in a row

## Related Files

- `backend_v2/catalog/selector.py` (search query generation)
- `backend_v2/orchestration/agents.py` (MMR lambda parameter)
- `backend_v2/catalog/providers/deezer.py` (Deezer API integration)

## Future Improvements

1. **Adaptive Lambda:** Adjust diversity weight based on session length
   - Early session: λ=0.7 (more familiar)
   - Mid session: λ=0.5 (balanced)
   - Late session: λ=0.3 (more adventurous)

2. **Similar Artist Discovery:** Use Deezer's "related artists" API
   - Query: "Taylor Swift" → Also search "Olivia Rodrigo", "Sabrina Carpenter"
   - Expands discovery without leaving taste profile

3. **Feedback-Driven Exploration:** Increase diversity after likes
   - User likes a deep cut → Search for more deep cuts
   - User likes new artist → Explore similar new artists

4. **Genre Blending:** Mix adjacent genres for variety
   - "Pop" + "Indie" → "Indie Pop"
   - "Electronic" + "Pop" → "Synth Pop"

