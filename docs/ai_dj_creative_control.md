# AI DJ Creative Control - Making the AI Actually DJ

**Date:** 2025-12-29  
**Motivation:** "The whole point of this app is that it's supposed to be an AI DJ" - let the AI make the creative selections

## Problem

The previous implementation used deterministic MMR (Maximal Marginal Relevance) to automatically select tracks from the catalog. While this worked, it **removed the AI's creative decision-making** - the core feature of an "AI DJ" experience.

**Old Flow:**
```
1. Search catalog with queries → Get 100 tracks
2. Apply MMR diversity algorithm → Auto-select track (deterministic)
3. Acquire & play
```

**Problem:** The AI wasn't involved in track selection at all. It was just an algorithmic filter.

## Solution

**New Flow (Hybrid Approach):**
```
1. Search catalog with queries → Get 100 diverse candidates
2. Feed top 20 candidates to AI → AI makes creative choice
3. Acquire AI's selection & play
```

**Key Insight:** Use the catalog search for *discovery* (finding good options), but give the AI the *final creative decision* (DJ magic).

## Implementation

### 1. Modified `select_track_via_catalog()` (`backend_v2/orchestration/agents.py`)

**Before:**
```python
# Deterministic MMR selection
selected_catalog_track = await select_diverse_track(
    bundle=bundle,
    prev_track=prev_catalog_track,
    recent_tracks=recent_catalog_tracks,
    lambda_param=0.5
)
```

**After:**
```python
# Get scored candidates from catalog
scored_catalog_tracks = await search_catalog_tracks(
    bundle=bundle,
    prev_track=prev_catalog_track,
    excluded_titles={...},
    limit=100  # Get a good pool for LLM to choose from
)

# Let the AI choose from these candidates
client = get_openrouter_client()
if client.enabled:
    # Format top 20 candidates for LLM
    top_candidates = scored_catalog_tracks[:20]
    
    # Ask AI DJ to select
    selection = await client.generate_catalog_selection(
        bundle=bundle,
        candidates=candidate_descriptions,
        prev_song=prev_song,
        recent_artists=bundle.history.recent_artists[:10],
    )
    
    # Use AI's choice
    selected_catalog_track = top_candidates[selected_index - 1][0]
```

### 2. Added `generate_catalog_selection()` (`backend_v2/integrations/openrouter.py`)

New LLM method specifically designed for catalog selection with a **creative DJ prompt**:

```python
async def generate_catalog_selection(
    self,
    bundle: "PreferenceBundle",
    candidates: List[Dict[str, Any]],
    prev_song: Optional[Dict[str, Any]] = None,
    recent_artists: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    """Let AI DJ make the creative choice from catalog candidates."""
```

**Key Prompt Elements:**

```
You are an expert AI DJ curating the perfect music journey.

YOUR ROLE:
- You're not just matching mood - you're creating a JOURNEY
- Be adventurous! Deep cuts, emerging artists, and hidden gems are ENCOURAGED
- Balance familiarity with discovery
- Think like a real DJ: flow, energy, surprise, delight

SELECTION PHILOSOPHY:
1. Musical Flow - Does this track flow naturally?
2. Energy Arc - Building, sustaining, or bringing it down?
3. Adventurousness - Predictable or delightfully unexpected?
4. Variety - Have we played this artist recently?
5. User Taste - Does this match their preferences?

ENCOURAGED BEHAVIORS:
- Pick deep cuts over obvious hits (if they fit the vibe)
- Introduce new artists the user hasn't heard
- Take creative risks - surprise them with excellence
- Trust your DJ instincts

The candidates are PRE-SCORED for basic fit. Your job is to make the CREATIVE choice.
Don't just pick #1 - think about what makes the best MOMENT.
```

**Temperature:** 0.85 (higher than standard 0.7 for more creative choices)

## What This Achieves

### ✅ AI Personality Shines
The AI can now make creative decisions like:
- "Let's go deeper into this artist's catalog with a lesser-known track"
- "Time to introduce a new artist that fits this vibe perfectly"
- "This unexpected choice will create a beautiful moment"

### ✅ Balanced Discovery
- **Catalog search** handles diversity (genres, variety, filtering)
- **AI selection** handles creativity (flow, surprises, DJ intuition)

### ✅ Context-Aware Choices
The AI sees:
- Previous track (for flow)
- Recent artists (for variety awareness)
- User likes/dislikes
- Mood targets
- All 20 candidates with scores

### ✅ Adventurous But Safe
- Catalog pre-filters to mood-appropriate tracks
- AI picks from good options (not random)
- Can be adventurous within guardrails

## Example AI Selection

**Input to LLM:**
```json
Candidates: [
  {"index": 1, "artist": "Taylor Swift", "title": "Cruel Summer", "score": 0.92},
  {"index": 2, "artist": "Olivia Rodrigo", "title": "vampire", "score": 0.89},
  {"index": 3, "artist": "Gracie Abrams", "title": "I miss you, I'm sorry", "score": 0.87},
  ...
]

Previous Track: Taylor Swift - Opalite
Recent Artists: ["Taylor Swift", "Sabrina Carpenter", "Taylor Swift"]
```

**AI Response:**
```json
{
  "selected_index": 3,
  "rationale": "While Cruel Summer (#1) is the highest scored and another Taylor Swift track would flow well, we've played her twice recently. Gracie Abrams brings a fresh voice with similar indie-pop sensibility. 'I miss you, I'm sorry' has the perfect emotional vulnerability to create a beautiful moment of discovery, and the tempo/energy will flow seamlessly from Opalite."
}
```

**Result:** The AI chose variety + discovery over the safe/obvious pick!

## Technical Flow

### Data Flow
```
┌─────────────────────┐
│ Catalog Search      │
│ - Query: genres +   │
│   artists           │
│ - Filter: exclude   │
│   history           │
│ - Score: relevance  │
│ - Result: 100 tracks│
└──────┬──────────────┘
       │
       ▼
┌─────────────────────┐
│ Top 20 to LLM       │
│ - Artist            │
│ - Title             │
│ - Album             │
│ - Score             │
│ - Features (tempo,  │
│   energy)           │
└──────┬──────────────┘
       │
       ▼
┌─────────────────────┐
│ AI DJ Selection     │
│ Context:            │
│ - Prev track        │
│ - Recent artists    │
│ - User likes        │
│ - Mood targets      │
│ Temp: 0.85 (creative)│
└──────┬──────────────┘
       │
       ▼
┌─────────────────────┐
│ Acquisition         │
│ - Download if needed│
│ - Store in DB       │
│ - Return track      │
└─────────────────────┘
```

### LLM Trace Storage

Every AI selection is now logged to `llm_trace` table:

```sql
INSERT INTO llm_trace (
  agent_name = 'catalog_selector',
  prompt = 'Candidates: 20 from catalog',
  response = 'Selected #3: Gracie Abrams - I miss you...',
  model = 'google/gemini-2.5-flash'
)
```

This allows you to:
- See what the AI is choosing and why
- Debug if selections seem off
- Understand the AI's decision-making
- Fine-tune prompts based on actual behavior

## Fallback Behavior

**If OpenRouter is disabled:**
```python
if not client.enabled:
    logger.warning("⚠️ OpenRouter disabled, falling back to MMR selection")
    from backend_v2.catalog.selector import mmr_select
    selected = mmr_select(scored_catalog_tracks, recent_catalog_tracks, lambda_param=0.5, k=1)
    selected_catalog_track = selected[0] if selected else scored_catalog_tracks[0][0]
```

**Graceful degradation:** Falls back to deterministic MMR if LLM unavailable.

## Advantages Over Pure Deterministic

### ❌ Deterministic MMR
- Predictable patterns
- No creative surprises
- Formulaic selection
- Can't explain choices

### ✅ AI DJ Selection
- Creative decision-making
- Can take risks
- Explains reasoning
- Learns from feedback
- Creates "moments"

## Testing

### How to Verify AI is Selecting

**1. Check backend logs:**
```bash
grep "catalog_selector" backend_logs.txt
```

Should see:
```
🎯 Asking AI DJ to select from catalog candidates...
🎵 AI selected: Gracie Abrams - I miss you, I'm sorry
   Rationale: While Cruel Summer (#1) is highest scored...
```

**2. Query LLM traces:**
```sql
SELECT agent_name, prompt, response, created_at 
FROM llm_trace 
WHERE agent_name = 'catalog_selector' 
ORDER BY created_at DESC 
LIMIT 10;
```

**3. Watch for variety:**
- Should see different artists
- Should see deep cuts, not just hits
- Rationales should mention flow, variety, discovery

### Expected Behavior

**Good Signs:**
- Different artists across session
- Some unexpected but delightful picks
- Rationales mention "variety", "fresh voice", "discovery"
- Occasional "risky but rewarding" choices

**Red Flags:**
- Same 2-3 artists repeating
- Only picking index #1 (top score)
- Generic rationales
- No "catalog_selector" traces in DB

## Configuration

### Tuning Creativity

**More Conservative (safer picks):**
```python
temperature=0.6  # In generate_catalog_selection()
```

**More Adventurous (riskier picks):**
```python
temperature=0.95  # Current: 0.85
```

### Candidate Pool Size

**More options for AI (slower):**
```python
limit=150  # In search_catalog_tracks()
top_candidates = scored_catalog_tracks[:30]  # Send more to LLM
```

**Faster with less choice:**
```python
limit=50
top_candidates = scored_catalog_tracks[:10]
```

## Related Files

- `backend_v2/orchestration/agents.py` - Main selection flow
- `backend_v2/integrations/openrouter.py` - LLM prompt for catalog selection
- `backend_v2/catalog/selector.py` - Catalog search (unchanged, still handles discovery)

## Future Enhancements

### 1. Feedback Loop
Track which AI selections get liked/disliked:
```python
if user_liked:
    # Include in future prompts: "You picked [track] before and user loved it"
    # Reinforce similar creative choices
```

### 2. Adaptive Adventurousness
Adjust based on session:
```python
if songs_played < 5:
    temperature = 0.7  # Start safer
elif user_engagement_high:
    temperature = 0.9  # Get adventurous
else:
    temperature = 0.8  # Balanced
```

### 3. A/B Testing
Compare AI vs deterministic selections:
```python
# 50% sessions: AI selection
# 50% sessions: MMR selection
# Track: skip rate, like rate, session length
```

### 4. Multi-Step Reasoning
Use thinking budget for complex decisions:
```python
thinking_budget = 2000  # Let AI reason through choices
# AI can explicitly weigh tradeoffs, plan energy arc
```

## Impact

### Before (Deterministic)
- ❌ Repetitive artist selection
- ❌ Predictable patterns
- ❌ No creative surprises
- ❌ Not truly "AI DJ"

### After (AI Creative Control)
- ✅ True AI DJ personality
- ✅ Creative, thoughtful selections
- ✅ Variety + discovery
- ✅ Explains reasoning
- ✅ Can take risks and delight users

**Bottom Line:** The AI now actually DJs, making creative musical decisions rather than just following an algorithm.

