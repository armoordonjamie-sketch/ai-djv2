"""DJ Persona compiler for personalized speech generation.

Compiles user context into structured persona rules:
- Tone and style guidelines
- Roast topics with cooldown enforcement
- Forbidden terms for TTS sanitization
- Music hard constraints (no slow songs, etc.)
- Season-aware seeding rules

Ported from legacy user_context.txt parsing + speech rules.
"""
import re
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any, Set

from backend_v2.services.preference_bundle import PreferenceBundle

logger = logging.getLogger("ai-dj.persona")


# =============================================================================
# Persona Models
# =============================================================================

@dataclass
class RoastTopic:
    """A roastable topic with cooldown tracking."""
    name: str
    keywords: List[str]
    max_per_n_segments: int
    segments_since_last_use: int = 0
    
    def can_use(self) -> bool:
        """Check if this topic can be used (cooldown elapsed)."""
        return self.segments_since_last_use >= self.max_per_n_segments
    
    def use(self):
        """Mark topic as used, reset cooldown."""
        self.segments_since_last_use = 0
    
    def advance(self):
        """Advance one segment."""
        self.segments_since_last_use += 1


@dataclass
class SeasonRule:
    """Season-aware music seeding rule."""
    name: str
    months: List[int]  # 1-12
    max_tracks_per_n: int
    n_tracks: int  # e.g., max 2 per 10 songs
    active_count: int = 0
    
    def is_active(self) -> bool:
        """Check if this rule applies to current month."""
        return datetime.now().month in self.months
    
    def can_add(self) -> bool:
        """Check if we can add another track of this type."""
        return self.active_count < self.max_tracks_per_n
    
    def add_track(self):
        """Record a track of this type."""
        self.active_count += 1
    
    def reset_window(self):
        """Reset count for new window."""
        self.active_count = 0


@dataclass 
class DJPersona:
    """Compiled DJ persona with all rules and state."""
    
    # Identity
    user_names: List[str] = field(default_factory=list)
    tone: str = "witty, personable"
    cultural_blend: str = ""
    
    # Roast system
    roast_topics: Dict[str, RoastTopic] = field(default_factory=dict)
    
    # Forbidden terms (for TTS output)
    forbidden_terms: Set[str] = field(default_factory=set)
    forbidden_patterns: List[str] = field(default_factory=list)
    
    # Music hard constraints
    music_hard_constraints: List[str] = field(default_factory=list)
    
    # Season rules
    season_rules: Dict[str, SeasonRule] = field(default_factory=dict)
    
    # Preferred artists/genres for seeding
    preferred_artists: List[str] = field(default_factory=list)
    preferred_genres: List[str] = field(default_factory=list)
    signature_tracks: List[str] = field(default_factory=list)
    
    # Raw context for LLM
    raw_context: str = ""
    
    def get_system_prompt_addendum(self) -> str:
        """Generate persona-specific system prompt addition."""
        lines = []
        
        if self.user_names:
            lines.append(f"User names: {', '.join(self.user_names)}")
        
        if self.tone:
            lines.append(f"Tone: {self.tone}")
        
        if self.cultural_blend:
            lines.append(f"Cultural blend: {self.cultural_blend}")
        
        if self.music_hard_constraints:
            lines.append(f"HARD MUSIC RULES: {'; '.join(self.music_hard_constraints)}")
        
        return "\n".join(lines)
    
    def get_do_not_repeat(self) -> List[str]:
        """Get list of roast topics currently on cooldown."""
        return [
            topic.name 
            for topic in self.roast_topics.values() 
            if not topic.can_use()
        ]
    
    def record_speech(self, speech_text: str):
        """Analyze speech and update cooldowns."""
        speech_lower = speech_text.lower()
        
        for topic in self.roast_topics.values():
            # Check if any keyword appears in speech
            if any(kw.lower() in speech_lower for kw in topic.keywords):
                topic.use()
                logger.debug(f"Roast topic used: {topic.name}")
    
    def advance_segment(self):
        """Advance all cooldowns by one segment."""
        for topic in self.roast_topics.values():
            topic.advance()
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize for storage/logging."""
        return {
            "user_names": self.user_names,
            "tone": self.tone,
            "roast_topics": {
                name: {
                    "max_per_n": t.max_per_n_segments,
                    "since_last": t.segments_since_last_use,
                    "can_use": t.can_use(),
                }
                for name, t in self.roast_topics.items()
            },
            "forbidden_terms_count": len(self.forbidden_terms),
            "music_hard_constraints": self.music_hard_constraints,
            "preferred_artists_count": len(self.preferred_artists),
        }


# =============================================================================
# Default Persona Rules (from legacy user_context.txt)
# =============================================================================

DEFAULT_FORBIDDEN_TERMS = {
    # Technical DJ terms
    "bpm", "beats per minute", "tempo",
    "key", "camelot", "pitch class",
    "energy score", "danceability", "valence",
    "crossfade", "blend", "eq", "filter",
    "ffmpeg", "atrim", "filtergraph",
    "decibels", "db", "lufs", "loudness",
    # Audio jargon
    "waveform", "spectrogram", "frequency",
    "mix length", "bars", "phrase",
}

DEFAULT_FORBIDDEN_PATTERNS = [
    r'\b\d{2,3}\s*(bpm|beats?\s*per\s*minute)\b',  # "120 BPM"
    r'\b(bpm|beats?\s*per\s*minute)\s*of?\s*\d{2,3}\b',  # "BPM of 120"
    r'\b(key\s+of\s+)?[A-G](#|b)?\s*(major|minor|m)\b',  # "key of A minor"
    r'\b\d{1,2}[AB]\b',  # Camelot codes like "8A", "11B"
    r'\bcamelot\s*(wheel|code|key)?\b',
    r'\b(crossfade|eq[_\s]?blend|filtergraph|ffmpeg|atrim)\b',
    r'\benergy\s*(score|level|rating)?\s*:?\s*\d+(\.\d+)?\b',
    r'\b(danceability|valence)\s*:?\s*\d+(\.\d+)?\b',
    r'\b\d+(\.\d+)?\s*(db|decibels?|lufs)\b',
]

DEFAULT_ROAST_TOPICS = {
    "vw_golf": RoastTopic(
        name="VW Golf",
        keywords=["golf", "vw", "volkswagen", "car"],
        max_per_n_segments=5,
    ),
    "short_legs": RoastTopic(
        name="Short legs",
        keywords=["short", "legs", "height", "tall", "speed-walk"],
        max_per_n_segments=5,
    ),
    "jeanie_sweets": RoastTopic(
        name="Jeanie sweets",
        keywords=["jeanie", "mum", "sweets", "confectionery", "candy"],
        max_per_n_segments=4,
    ),
    "ace_favourite": RoastTopic(
        name="Ace being favourite",
        keywords=["ace", "therapy dog", "favourite", "popularity"],
        max_per_n_segments=4,
    ),
    "jamie_genius": RoastTopic(
        name="Jamie is a genius",
        keywords=["jamie", "genius", "coded", "built", "created"],
        max_per_n_segments=3,
    ),
    "birthday": RoastTopic(
        name="June 13th birthday",
        keywords=["june 13", "birthday", "june thirteenth"],
        max_per_n_segments=20,  # ~once per hour at 3min segments
    ),
}

DEFAULT_MUSIC_CONSTRAINTS = [
    "High energy only - NO slow songs, NO ballads, NO sleepy vibes",
]

DEFAULT_SEASON_RULES = {
    "christmas": SeasonRule(
        name="Christmas tracks",
        months=[11, 12],  # Nov-Dec only
        max_tracks_per_n=2,
        n_tracks=10,
    ),
}


# =============================================================================
# Persona Compiler
# =============================================================================

def compile_persona(bundle: PreferenceBundle) -> DJPersona:
    """Compile persona from PreferenceBundle.
    
    Extracts persona rules from:
    - bundle.profile (structured onboarding data - primary source)
    - bundle.context.raw_text (user context file content - legacy)
    - bundle.mood settings (dj_personality, genres)
    
    Args:
        bundle: User's preference bundle
        
    Returns:
        Compiled DJPersona with all rules loaded
    """
    persona = DJPersona()
    
    # Load forbidden terms and patterns
    persona.forbidden_terms = DEFAULT_FORBIDDEN_TERMS.copy()
    persona.forbidden_patterns = DEFAULT_FORBIDDEN_PATTERNS.copy()
    
    # Load roast topics with cooldown state
    persona.roast_topics = {
        name: RoastTopic(
            name=topic.name,
            keywords=topic.keywords.copy(),
            max_per_n_segments=topic.max_per_n_segments,
        )
        for name, topic in DEFAULT_ROAST_TOPICS.items()
    }
    
    # Load music constraints
    persona.music_hard_constraints = DEFAULT_MUSIC_CONSTRAINTS.copy()
    
    # Load season rules
    persona.season_rules = {
        name: SeasonRule(
            name=rule.name,
            months=rule.months.copy(),
            max_tracks_per_n=rule.max_tracks_per_n,
            n_tracks=rule.n_tracks,
        )
        for name, rule in DEFAULT_SEASON_RULES.items()
    }
    
    # === Apply profile data (NEW: structured onboarding) ===
    if bundle.profile:
        # Set user name from profile
        if bundle.profile.display_name:
            persona.user_names = [bundle.profile.display_name]
        
        # Set preferred artists from profile
        if bundle.profile.favorite_artists:
            persona.preferred_artists = bundle.profile.favorite_artists.copy()
        
        # Set preferred genres from profile
        if bundle.profile.favorite_genres:
            persona.preferred_genres = bundle.profile.favorite_genres.copy()
        
        # Add no-go items as hard constraints
        if bundle.profile.no_go:
            for no_go_item in bundle.profile.no_go:
                persona.music_hard_constraints.append(f"AVOID: {no_go_item}")
        
        # Add explicit lyrics constraint if avoiding
        if not bundle.profile.allows_explicit():
            persona.music_hard_constraints.append("NO explicit lyrics")
        
        # Set tone based on DJ personality preference
        dj_personality = bundle.profile.dj_personality
        PERSONALITY_TONES = {
            "casual_funny": "witty, casual, fun, humorous",
            "minimal_talk": "brief, concise, minimal chat",
            "hype_energetic": "energetic, hyped up, enthusiastic",
            "light_roast": "playfully teasing, light roasting, witty",
            "more_talk_between_songs": "chatty, talkative, conversational",
        }
        if dj_personality in PERSONALITY_TONES:
            persona.tone = PERSONALITY_TONES[dj_personality]
        
        # Use raw_context from profile if available
        if bundle.profile.raw_context:
            persona.raw_context = bundle.profile.raw_context
    
    # === Parse legacy raw context if available (fallback) ===
    if bundle.context and bundle.context.raw_text:
        raw_text = bundle.context.raw_text
        if not persona.raw_context:
            persona.raw_context = raw_text
        
        # Extract user names (only if not already set from profile)
        if not persona.user_names and "User:" in raw_text:
            match = re.search(r'User:\s*(.+?)(?:\n|$)', raw_text)
            if match:
                names = match.group(1).strip()
                persona.user_names = [n.strip() for n in re.split(r'[,\s]+and\s+|,\s*', names)]
        
        # Extract tone (only if not set from profile)
        if persona.tone == "witty, personable" and "Tone" in raw_text:
            match = re.search(r'Tone[:\s]+(.+?)(?:\n|$)', raw_text, re.IGNORECASE)
            if match:
                persona.tone = match.group(1).strip()
        
        # Extract cultural blend
        if "Cultural blend" in raw_text:
            match = re.search(r'Cultural\s+blend[:\s]+(.+?)(?:\n|$)', raw_text, re.IGNORECASE)
            if match:
                persona.cultural_blend = match.group(1).strip()
        
        # Extract preferred artists (append to profile artists)
        artist_patterns = [
            r'(?:Add|Include|Mix in)[:\s]+(.+?)(?:\n|$)',
            r'(?:Artists?|Bands?)[:\s]+(.+?)(?:\n|$)',
        ]
        for pattern in artist_patterns:
            matches = re.findall(pattern, raw_text, re.IGNORECASE)
            for match in matches:
                artists = re.split(r',\s*|\s+and\s+', match)
                persona.preferred_artists.extend([a.strip() for a in artists if a.strip()])
        
        # Extract signature tracks
        if "Signature tracks" in raw_text:
            match = re.search(r'Signature\s+tracks[:\s]+(.+?)(?:\n|$)', raw_text, re.IGNORECASE)
            if match:
                tracks = re.split(r',\s*', match.group(1))
                persona.signature_tracks = [t.strip() for t in tracks if t.strip()]
    
    # Apply mood-based settings (can override)
    if bundle.mood:
        # Merge mood genres (don't replace profile genres)
        if bundle.mood.genres:
            for genre in bundle.mood.genres:
                if genre not in persona.preferred_genres:
                    persona.preferred_genres.append(genre)
        
        # Adjust tone based on mood DJ personality (override profile if set)
        if bundle.mood.dj_personality == "minimal":
            persona.tone = "brief, understated"
        elif bundle.mood.dj_personality == "chatty":
            persona.tone = "energetic, talkative, fun"
    
    logger.info(f"Compiled persona: {len(persona.user_names)} names, "
                f"{len(persona.roast_topics)} roast topics, "
                f"{len(persona.preferred_artists)} artists, "
                f"tone='{persona.tone}'")
    
    return persona


def get_compiled_persona(bundle: PreferenceBundle) -> DJPersona:
    """Get or compile persona for a user.
    
    TODO: Add caching by user_id + context version
    """
    return compile_persona(bundle)
