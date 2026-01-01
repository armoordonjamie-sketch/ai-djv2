"""Search query generator for song suggestions.

Generates strictly formatted "Artist - Title" queries for library expansion.
Uses persona preferences, mood, and history to suggest relevant songs.

Key features:
- Strict "Artist - Title" format validation
- Retry logic with fallback
- Deduplication against recent plays
- Persona/mood influence on suggestions
"""
import re
import logging
from typing import List, Optional, Dict, Any, TYPE_CHECKING

from backend_v2.integrations.openrouter import get_openrouter_client

if TYPE_CHECKING:
    from backend_v2.services.preference_bundle import PreferenceBundle
    from backend_v2.services.persona import DJPersona

logger = logging.getLogger("ai-dj.search_queries")


# =============================================================================
# Validation
# =============================================================================

# Pattern: "Artist Name - Song Title" with at least 2 chars each side
ARTIST_TITLE_PATTERN = re.compile(r'^(.{2,})\s+-\s+(.{2,})$')

# Patterns to strip from queries
STRIP_PATTERNS = [
    r'^\d+\.\s*',       # Leading numbers like "1. "
    r'^[-•*]\s*',        # Leading bullets
    r'^["\']',           # Leading quotes
    r'["\']$',           # Trailing quotes
    r'\s*\([^)]*\)$',    # Trailing parenthetical
]

# Deny list patterns (reject these queries)
DENY_PATTERNS = [
    r'\bfull\s+album\b',
    r'\b(1|2|3|one|two|three)\s+hour\b',
    r'\blive\s+(set|session|concert)\b',
    r'\bmix\s*(tape|compilation)?\b',
    r'\bsped\s+up\b',
    r'\bslowed\s*(down|and\s+reverb)?\b',
    r'\bremix\b',  # Allow remixes by specific handling if needed
    r'\b(full|complete)\s+discography\b',
    r'\bplaylist\b',
]


def validate_query(query: str) -> Optional[str]:
    """Validate and clean a single search query.
    
    Returns cleaned query if valid, None if invalid.
    """
    if not query or not isinstance(query, str):
        return None
    
    cleaned = query.strip()
    
    # Apply strip patterns
    for pattern in STRIP_PATTERNS:
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE).strip()
    
    # Check for deny patterns
    for pattern in DENY_PATTERNS:
        if re.search(pattern, cleaned, re.IGNORECASE):
            logger.debug(f"Query rejected by deny pattern: {cleaned}")
            return None
    
    # Must match Artist - Title format
    match = ARTIST_TITLE_PATTERN.match(cleaned)
    if not match:
        logger.debug(f"Query doesn't match Artist - Title format: {cleaned}")
        return None
    
    artist, title = match.groups()
    
    # Both parts must be meaningful
    if len(artist.strip()) < 2 or len(title.strip()) < 2:
        return None
    
    return f"{artist.strip()} - {title.strip()}"


def validate_queries(queries: List[str]) -> List[str]:
    """Validate and dedupe a list of queries."""
    seen = set()
    valid = []
    
    for query in queries:
        cleaned = validate_query(query)
        if cleaned and cleaned.lower() not in seen:
            seen.add(cleaned.lower())
            valid.append(cleaned)
    
    return valid


def remove_already_in_library(
    queries: List[str],
    recent_plays: List[str],
    downloaded_titles: List[str],
) -> List[str]:
    """Remove queries for songs we already have."""
    recent_lower = {p.lower() for p in recent_plays}
    downloaded_lower = {d.lower() for d in downloaded_titles}
    
    return [
        q for q in queries
        if q.lower() not in recent_lower and q.lower() not in downloaded_lower
    ]


# =============================================================================
# Query Generation
# =============================================================================

async def generate_search_queries(
    bundle: "PreferenceBundle",
    persona: Optional["DJPersona"] = None,
    count: int = 5,
    max_retries: int = 2,
) -> List[str]:
    """Generate song search queries based on user preferences.
    
    Generates strictly validated "Artist - Title" format queries
    influenced by persona preferences, mood, and history.
    
    Args:
        bundle: User's preference bundle
        persona: Compiled DJ persona (optional)
        count: Number of queries to generate
        max_retries: Max regeneration attempts if validation fails
        
    Returns:
        List of validated "Artist - Title" queries
    """
    client = get_openrouter_client()
    
    if not client.enabled:
        logger.warning("OpenRouter disabled, returning fallback queries")
        return _get_fallback_queries(persona, count)
    
    # Build context for LLM
    recent_plays_str = ""
    recent_track_names = [
        f"{h.artist} - {h.title}"
        for h in bundle.history.recent_tracks[:15]
        if h.artist and h.title
    ]
    if recent_track_names:
        recent_plays_str = f"""
Recently Played (DO NOT suggest these):
{', '.join(recent_track_names)}
"""
    elif bundle.history.recent_plays[:15]:
        recent_plays_str = f"""
Recently Played (DO NOT suggest these):
{', '.join(bundle.history.recent_plays[:15])}
"""
    
    recent_artists_str = ""
    if bundle.history.recent_artists[:10]:
        recent_artists_str = f"""
Recent Artists (prefer variety):
{', '.join(set(bundle.history.recent_artists[:10]))}
"""
    
    # Persona preferences
    persona_section = ""
    if persona:
        if persona.preferred_artists:
            persona_section += f"\nPreferred Artists: {', '.join(persona.preferred_artists[:15])}"
        if persona.preferred_genres:
            persona_section += f"\nPreferred Genres: {', '.join(persona.preferred_genres[:10])}"
        if persona.music_hard_constraints:
            persona_section += f"\nHARD RULES: {'; '.join(persona.music_hard_constraints)}"
    
    # Mood context
    mood_section = f"""
Current Mood: {bundle.mood.name}
- Energy target: {bundle.mood.energy_target:.1f} (0=calm, 1=energetic)
- Valence target: {bundle.mood.valence_target:.1f} (0=sad, 1=happy)
- Genres: {', '.join(bundle.mood.genres)}
"""

    system_prompt = f"""You are generating song search queries for a personalized music library.

CRITICAL RULES - FOLLOW EXACTLY:
1. OUTPUT MUST BE IN "Artist - Title" FORMAT.
2. DO NOT output just an artist name (e.g. "Queen" → BAD, "Queen - Bohemian Rhapsody" → GOOD)
3. DO NOT output genres, moods, or descriptions
4. Each query must be a SPECIFIC SONG that exists
5. AVOID: albums, mixes, live sets, compilations, sped up versions

WRONG EXAMPLES (will be rejected):
- "Synth-pop UK" ❌
- "80s British pop anthems" ❌
- "Queen" ❌
- "energetic dance music" ❌

CORRECT EXAMPLES:
- "Queen - Radio Ga Ga" ✓
- "Dua Lipa - Levitating" ✓
- "Michael Jackson - Billie Jean" ✓
{persona_section}
{mood_section}
{recent_plays_str}
{recent_artists_str}

Output ONLY a JSON array of {count} search queries in "Artist - Title" format.
Example: ["Artist1 - Song1", "Artist2 - Song2"]
"""

    user_prompt = f"""Generate {count} song suggestions that match the mood and persona.
Each must be "Artist - Title" format. Output JSON array only."""

    # Attempt generation with retries
    for attempt in range(max_retries + 1):
        try:
            result = await client.chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.7 if attempt == 0 else 0.5,  # Lower temp on retry
                thinking_budget=500,
                json_mode=True,
                use_lite_model=True,
                session_id=None,  # Standalone query generation
            )
            
            if not result or not result.get('parsed'):
                continue
            
            parsed = result['parsed']
            
            # Handle different response shapes
            if isinstance(parsed, list):
                queries = parsed
            elif isinstance(parsed, dict) and 'queries' in parsed:
                queries = parsed['queries']
            else:
                logger.warning(f"Unexpected response shape: {type(parsed)}")
                continue
            
            # Validate all queries
            valid = validate_queries(queries)
            
            # Remove already-played
            valid = remove_already_in_library(
                valid,
                recent_track_names or bundle.history.recent_plays,
                [],  # TODO: get actually downloaded titles
            )
            
            if len(valid) >= 3:
                logger.info(f"Generated {len(valid)} valid queries (attempt {attempt + 1})")
                return valid[:count]
            
            logger.warning(f"Only {len(valid)} valid queries, retrying...")
            
        except Exception as e:
            logger.error(f"Query generation error: {e}")
    
    # Fallback to persona signature tracks
    logger.warning("All retries failed, using fallback queries")
    return _get_fallback_queries(persona, count)


def _get_fallback_queries(persona: Optional["DJPersona"], count: int) -> List[str]:
    """Get fallback queries from persona or defaults."""
    if persona and persona.signature_tracks:
        return persona.signature_tracks[:count]
    
    # Ultimate fallback - popular high-energy songs
    fallback = [
        "Daft Punk - Get Lucky",
        "Queen - Don't Stop Me Now",
        "ABBA - Dancing Queen",
        "Michael Jackson - Billie Jean",
        "Gloria Gaynor - I Will Survive",
    ]
    return fallback[:count]


# =============================================================================
# Singleton
# =============================================================================

class SearchQueryGenerator:
    """Singleton wrapper for search query generation."""
    
    _instance: Optional["SearchQueryGenerator"] = None
    
    @classmethod
    def get_instance(cls) -> "SearchQueryGenerator":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    async def generate(
        self,
        bundle: "PreferenceBundle",
        persona: Optional["DJPersona"] = None,
        count: int = 5,
    ) -> List[str]:
        """Generate validated search queries."""
        return await generate_search_queries(bundle, persona, count)


def get_search_query_generator() -> SearchQueryGenerator:
    """Get the search query generator singleton."""
    return SearchQueryGenerator.get_instance()
