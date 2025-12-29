"""PreferenceBundle service for building user preferences from database.

Aggregates user context, mood, feedback, history, agent settings, profile,
and prompt templates into a single bundle for orchestration agents.

Evidence: Implementing Phase 5 of implementation_plan.md
"""
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple, Literal

from sqlalchemy import select, desc, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend_v2.models.user import User
from backend_v2.models.user_profile import UserProfile
from backend_v2.models.context import UserContext
from backend_v2.models.mood import Mood, MoodProfile
from backend_v2.models.feedback import FeedbackEvent
from backend_v2.models.settings import AgentSettings, PromptTemplate
from backend_v2.models.existing import PlayHistory, Song
from backend_v2.utils.time import utc_now, ensure_utc

logger = logging.getLogger("ai-dj.preference_bundle")


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class ContextData:
    """User context for personalization."""
    id: str
    name: str
    raw_text: str
    parsed_json: Optional[Dict[str, Any]] = None


@dataclass
class MoodData:
    """Mood settings for DJ behavior."""
    id: str
    name: str
    genres: List[str]
    energy_target: float
    valence_target: float
    dj_personality: str
    color: Optional[str] = None
    intro_segment_path: Optional[str] = None
    intro_song_uuid: Optional[str] = None
    # Fix Issue #10: Mood-specific personalization fields for prompts/scoring
    danceability_target: Optional[float] = None
    tempo_min: Optional[int] = None
    tempo_max: Optional[int] = None
    genre_seeds: List[str] = field(default_factory=list)
    vibe_keywords: List[str] = field(default_factory=list)
    avoid_genres: List[str] = field(default_factory=list)
    example_artists: List[str] = field(default_factory=list)
    intro_personality: Optional[str] = None
    era_hint: Optional[str] = None


@dataclass
class MoodProfileData:
    """Derived preferences from feedback training."""
    summary_text: Optional[str] = None
    weights_json: Optional[Dict[str, float]] = None
    version: int = 1


@dataclass
class FeedbackItem:
    """Single feedback event."""
    song_uuid: Optional[str]
    title: Optional[str]
    artist: Optional[str]
    reason: Optional[str] = None


@dataclass
class FeedbackData:
    """Recent user feedback for preference weighting."""
    recent_likes: List[FeedbackItem] = field(default_factory=list)
    recent_dislikes: List[FeedbackItem] = field(default_factory=list)


@dataclass
class UserProfileData:
    """Structured user profile from onboarding.
    
    Contains structured fields collected during the voice onboarding flow.
    Used to personalize AI DJ persona, track selection, and speech.
    """
    # Name
    display_name: Optional[str] = None
    
    # Demographics
    age_range: Optional[str] = None
    location: Optional[str] = None
    occupation: Optional[str] = None
    
    # Music preferences (lists)
    favorite_genres: List[str] = field(default_factory=list)
    favorite_artists: List[str] = field(default_factory=list)
    favorite_songs: List[str] = field(default_factory=list)
    no_go: List[str] = field(default_factory=list)  # Things to avoid
    
    # Preference enums
    explicit_lyrics: str = "ok"  # "ok" | "avoid" | "depends"
    dj_personality: str = "casual_funny"  # DJ style preference
    
    # Natural language summary
    raw_context: Optional[str] = None
    
    def allows_explicit(self) -> bool:
        """Check if user allows explicit content."""
        return self.explicit_lyrics != "avoid"
    
    def get_no_go_genres(self) -> List[str]:
        """Get list of genres/styles to avoid (lowercase)."""
        return [g.lower() for g in self.no_go if g]
    
    def get_favorite_genres_lower(self) -> List[str]:
        """Get favorite genres lowercased for matching."""
        return [g.lower() for g in self.favorite_genres if g]


@dataclass
class HistoryData:
    """Recent play history for variety and repetition avoidance."""
    recent_plays: List[str] = field(default_factory=list)  # song UUIDs
    recent_artists: List[str] = field(default_factory=list)  # artist names
    recent_tracks: List["HistoryItem"] = field(default_factory=list)  # enriched track list


@dataclass
class HistoryItem:
    """Single history entry with basic track details."""
    song_uuid: Optional[str]
    title: Optional[str]
    artist: Optional[str]


@dataclass
class PreferenceBundle:
    """Complete user preference bundle for AI agents.
    
    This is the central data structure passed to all agents during
    orchestration to personalize track selection, speech, and mixing.
    """
    user_id: str
    session_id: str
    context: ContextData
    mood: MoodData
    mood_profile: MoodProfileData
    feedback: FeedbackData
    history: HistoryData
    profile: UserProfileData  # NEW: Structured onboarding profile
    agent_settings: Dict[str, Dict[str, Any]]  # {agent_name: settings_dict}
    prompt_templates: Dict[str, str]  # {template_name: template_text}
    
    # Computed at build time
    built_at: datetime = field(default_factory=utc_now)
    
    def get_agent_setting(self, agent_name: str, key: str, default: Any = None) -> Any:
        """Get a specific agent setting with fallback."""
        settings = self.agent_settings.get(agent_name, {})
        return settings.get(key, default)
    
    def get_prompt_template(self, name: str) -> Optional[str]:
        """Get a prompt template by name."""
        return self.prompt_templates.get(name)
    
    def get_disliked_song_uuids(self) -> List[str]:
        """Get list of disliked song UUIDs for filtering."""
        return [f.song_uuid for f in self.feedback.recent_dislikes if f.song_uuid]
    
    def get_disliked_artists(self) -> List[str]:
        """Get list of disliked artists for filtering."""
        return [f.artist for f in self.feedback.recent_dislikes if f.artist]
    
    def get_liked_song_uuids(self) -> List[str]:
        """Get list of liked song UUIDs for boosting."""
        return [f.song_uuid for f in self.feedback.recent_likes if f.song_uuid]
    
    # === Profile helpers ===
    
    def get_display_name(self) -> Optional[str]:
        """Get display name from profile or context."""
        if self.profile.display_name:
            return self.profile.display_name
        # Fallback to parsed_json in context (legacy)
        if self.context.parsed_json and self.context.parsed_json.get("display_name"):
            return self.context.parsed_json["display_name"]
        return None
    
    def get_favorite_genres(self) -> List[str]:
        """Get favorite genres from profile."""
        return self.profile.favorite_genres
    
    def get_favorite_artists(self) -> List[str]:
        """Get favorite artists from profile."""
        return self.profile.favorite_artists
    
    def get_no_go_list(self) -> List[str]:
        """Get no-go genres/artists from profile (lowercase)."""
        return self.profile.get_no_go_genres()
    
    def allows_explicit(self) -> bool:
        """Check if user allows explicit lyrics."""
        return self.profile.allows_explicit()
    
    def get_dj_personality(self) -> str:
        """Get DJ personality style from profile."""
        return self.profile.dj_personality or "casual_funny"


# =============================================================================
# Cache
# =============================================================================

class PreferenceBundleCache:
    """Simple in-memory cache for PreferenceBundles.
    
    Invalidated on mood/context/feedback/settings/template changes.
    """
    _instance: Optional["PreferenceBundleCache"] = None
    
    def __init__(self, ttl_seconds: int = 300):
        self._cache: Dict[str, Tuple[PreferenceBundle, datetime]] = {}
        self._ttl = timedelta(seconds=ttl_seconds)
    
    @classmethod
    def get_instance(cls) -> "PreferenceBundleCache":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def _make_key(self, user_id: str, mood_id: Optional[str], context_name: Optional[str]) -> str:
        return f"{user_id}:{mood_id or 'default'}:{context_name or 'default'}"
    
    def get(
        self, 
        user_id: str, 
        mood_id: Optional[str], 
        context_name: Optional[str]
    ) -> Optional[PreferenceBundle]:
        """Get cached bundle if valid."""
        key = self._make_key(user_id, mood_id, context_name)
        entry = self._cache.get(key)
        if entry is None:
            return None
        
        bundle, cached_at = entry
        cached_at = ensure_utc(cached_at)
        if cached_at is None or utc_now() - cached_at > self._ttl:
            del self._cache[key]
            return None
        
        return bundle
    
    def set(
        self,
        user_id: str,
        mood_id: Optional[str],
        context_name: Optional[str],
        bundle: PreferenceBundle,
    ):
        """Cache a bundle."""
        key = self._make_key(user_id, mood_id, context_name)
        self._cache[key] = (bundle, utc_now())
    
    def invalidate(self, user_id: str):
        """Invalidate all cached bundles for a user."""
        keys_to_delete = [k for k in self._cache if k.startswith(f"{user_id}:")]
        for key in keys_to_delete:
            del self._cache[key]
        logger.debug(f"Invalidated {len(keys_to_delete)} cached bundles for user {user_id}")
    
    def clear(self):
        """Clear entire cache."""
        self._cache.clear()


def get_bundle_cache() -> PreferenceBundleCache:
    """Get the bundle cache singleton."""
    return PreferenceBundleCache.get_instance()


# =============================================================================
# Defaults
# =============================================================================

async def _get_or_create_default_context(
    db: AsyncSession, 
    user_id: str
) -> UserContext:
    """Get user's default context, creating if missing."""
    stmt = select(UserContext).where(
        and_(UserContext.user_id == user_id, UserContext.name == "default")
    )
    result = await db.execute(stmt)
    context = result.scalar_one_or_none()
    
    if context is None:
        logger.info(f"Creating default context for user {user_id}")
        context = UserContext(
            user_id=user_id,
            name="default",
            raw_text="I enjoy a variety of music. Play me something good!",
        )
        db.add(context)
        await db.flush()
    
    return context


async def _get_or_create_default_mood(
    db: AsyncSession, 
    user_id: str
) -> Mood:
    """Get user's default mood, creating if missing."""
    # First try to find existing default mood
    stmt = select(Mood).where(
        and_(Mood.user_id == user_id, Mood.is_default == True)
    ).options(selectinload(Mood.profile))
    result = await db.execute(stmt)
    mood = result.scalar_one_or_none()
    
    if mood is None:
        # Try any mood for this user
        stmt = select(Mood).where(Mood.user_id == user_id).options(selectinload(Mood.profile))
        result = await db.execute(stmt)
        mood = result.scalar_one_or_none()
    
    if mood is None:
        logger.info(f"Creating default mood for user {user_id}")
        mood = Mood(
            user_id=user_id,
            name="Default",
            color="#6366f1",
            energy_target=0.5,
            valence_target=0.5,
            genres_json=json.dumps(["pop", "rock", "indie"]),
            dj_personality="chill",
            is_default=True,
        )
        db.add(mood)
        await db.flush()
        
        # Create associated profile
        profile = MoodProfile(
            mood_id=mood.id,
            version=1,
            summary_text=None,
            weights_json=None,
        )
        db.add(profile)
        await db.flush()
        
        mood.profile = profile
    
    return mood


# =============================================================================
# Builder
# =============================================================================

async def build_preference_bundle(
    db: AsyncSession,
    user_id: str,
    session_id: str,
    mood_id: Optional[str] = None,
    context_name: Optional[str] = None,
    use_cache: bool = True,
    feedback_limit: int = 50,
    history_limit: int = 100,
) -> PreferenceBundle:
    """Build complete preference bundle from database.
    
    Args:
        db: Database session
        user_id: Authenticated user ID
        session_id: Current streaming session ID
        mood_id: Optional specific mood ID (falls back to default)
        context_name: Optional context name (falls back to "default")
        use_cache: Whether to use cached bundle if available
        feedback_limit: Max feedback events to load
        history_limit: Max history items to load
        
    Returns:
        Complete PreferenceBundle for orchestration
    """
    # Check cache first
    if use_cache:
        cache = get_bundle_cache()
        cached = cache.get(user_id, mood_id, context_name)
        if cached is not None:
            logger.debug(f"Using cached bundle for user {user_id}")
            return cached
    
    logger.debug(f"Building preference bundle for user {user_id}")
    
    # --- Load Context ---
    if context_name:
        stmt = select(UserContext).where(
            and_(UserContext.user_id == user_id, UserContext.name == context_name)
        )
        result = await db.execute(stmt)
        context_row = result.scalar_one_or_none()
    else:
        context_row = None
    
    if context_row is None:
        context_row = await _get_or_create_default_context(db, user_id)
    
    # Fix Issue #9: Safely parse context JSON to avoid crashes
    def _safe_json_loads(val: Optional[str]) -> Optional[Dict]:
        """Parse JSON string safely, return None on failure."""
        if not val:
            return None
        try:
            return json.loads(val)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse context JSON for user {user_id}: {e}")
            return None
    
    context = ContextData(
        id=context_row.id,
        name=context_row.name,
        raw_text=context_row.raw_text or "",
        parsed_json=_safe_json_loads(context_row.parsed_json),
    )
    
    # --- Load Mood ---
    if mood_id:
        stmt = select(Mood).where(
            and_(Mood.user_id == user_id, Mood.id == mood_id)
        ).options(selectinload(Mood.profile))
        result = await db.execute(stmt)
        mood_row = result.scalar_one_or_none()
    else:
        mood_row = None
    
    if mood_row is None:
        mood_row = await _get_or_create_default_mood(db, user_id)
    
    # Fix Issue #10: Helper to safely parse JSON lists for mood fields
    def _parse_json_list_safe(val: Optional[str]) -> List[str]:
        """Parse JSON string to list, return [] on failure."""
        if not val:
            return []
        try:
            parsed = json.loads(val)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
    
    genres = _parse_json_list_safe(mood_row.genres_json)
    
    mood = MoodData(
        id=mood_row.id,
        name=mood_row.name,
        genres=genres,
        energy_target=mood_row.energy_target or 0.5,
        valence_target=mood_row.valence_target or 0.5,
        dj_personality=mood_row.dj_personality or "chill",
        color=mood_row.color,
        intro_segment_path=mood_row.intro_segment_path,
        intro_song_uuid=mood_row.intro_song_uuid,
        # Fix Issue #10: Populate mood-specific personalization fields
        danceability_target=mood_row.danceability_target if hasattr(mood_row, 'danceability_target') else None,
        tempo_min=mood_row.tempo_min if hasattr(mood_row, 'tempo_min') else None,
        tempo_max=mood_row.tempo_max if hasattr(mood_row, 'tempo_max') else None,
        genre_seeds=_parse_json_list_safe(mood_row.genre_seeds_json if hasattr(mood_row, 'genre_seeds_json') else None),
        vibe_keywords=_parse_json_list_safe(mood_row.vibe_keywords_json if hasattr(mood_row, 'vibe_keywords_json') else None),
        avoid_genres=_parse_json_list_safe(mood_row.avoid_genres_json if hasattr(mood_row, 'avoid_genres_json') else None),
        example_artists=_parse_json_list_safe(mood_row.example_artists_json if hasattr(mood_row, 'example_artists_json') else None),
        intro_personality=mood_row.intro_personality if hasattr(mood_row, 'intro_personality') else None,
        era_hint=mood_row.era_hint if hasattr(mood_row, 'era_hint') else None,
    )
    
    # --- Load Mood Profile ---
    profile_row = mood_row.profile
    weights = None
    if profile_row and profile_row.weights_json:
        try:
            weights = json.loads(profile_row.weights_json)
        except json.JSONDecodeError:
            weights = None
    
    mood_profile = MoodProfileData(
        summary_text=profile_row.summary_text if profile_row else None,
        weights_json=weights,
        version=profile_row.version if profile_row else 1,
    )
    
    # --- Load Feedback ---
    stmt = (
        select(FeedbackEvent)
        .where(
            and_(
                FeedbackEvent.user_id == user_id,
                # Include global feedback (mood_id is None) or mood-specific
                (FeedbackEvent.mood_id == None) | (FeedbackEvent.mood_id == mood.id)
            )
        )
        .order_by(desc(FeedbackEvent.created_at))
        .limit(feedback_limit)
    )
    result = await db.execute(stmt)
    feedback_rows = result.scalars().all()
    
    recent_likes = []
    recent_dislikes = []
    for fb in feedback_rows:
        item = FeedbackItem(
            song_uuid=fb.song_uuid,
            title=fb.track_title,
            artist=fb.track_artist,
            reason=fb.reason_text,
        )
        if fb.value == "like":
            recent_likes.append(item)
        elif fb.value == "dislike":
            recent_dislikes.append(item)
    
    feedback = FeedbackData(
        recent_likes=recent_likes,
        recent_dislikes=recent_dislikes,
    )
    
    # --- Load History ---
    stmt = (
        select(PlayHistory)
        .where(PlayHistory.user_id == user_id)
        .order_by(desc(PlayHistory.started_at))
        .limit(history_limit)
    )
    result = await db.execute(stmt)
    history_rows = result.scalars().all()
    
    recent_plays = [h.song_uuid for h in history_rows if h.song_uuid]
    
    # Get artist/title names from songs
    recent_artists = []
    recent_tracks: List[HistoryItem] = []
    if recent_plays:
        stmt = select(Song.uuid, Song.artist, Song.title).where(Song.uuid.in_(recent_plays[:30]))
        result = await db.execute(stmt)
        song_rows = {row[0]: (row[1], row[2]) for row in result.fetchall()}
        for song_uuid in recent_plays[:30]:
            artist, title = song_rows.get(song_uuid, (None, None))
            if artist:
                recent_artists.append(artist)
            if artist or title:
                recent_tracks.append(HistoryItem(song_uuid=song_uuid, title=title, artist=artist))
    
    history = HistoryData(
        recent_plays=recent_plays,
        recent_artists=recent_artists,
        recent_tracks=recent_tracks,
    )
    
    # --- Load Agent Settings ---
    stmt = select(AgentSettings).where(AgentSettings.user_id == user_id)
    result = await db.execute(stmt)
    settings_rows = result.scalars().all()
    
    agent_settings: Dict[str, Dict[str, Any]] = {}
    for setting in settings_rows:
        if setting.settings_json:
            try:
                agent_settings[setting.agent_name] = json.loads(setting.settings_json)
            except json.JSONDecodeError:
                agent_settings[setting.agent_name] = {}
    
    # --- Load Prompt Templates ---
    # Priority: mood-scoped > global, active only
    stmt = (
        select(PromptTemplate)
        .where(
            and_(
                PromptTemplate.user_id == user_id,
                PromptTemplate.is_active == True,
                # Global or matching mood
                (PromptTemplate.scope == "global") | 
                (and_(PromptTemplate.scope == "mood", PromptTemplate.mood_id == mood.id))
            )
        )
        .order_by(
            # Mood-scoped templates override global ones
            desc(PromptTemplate.scope == "mood"),
            desc(PromptTemplate.version)
        )
    )
    result = await db.execute(stmt)
    template_rows = result.scalars().all()
    
    # Dedupe by name (first = highest priority)
    prompt_templates: Dict[str, str] = {}
    for tpl in template_rows:
        if tpl.name not in prompt_templates:
            prompt_templates[tpl.name] = tpl.template_text
    
    # --- Load User Profile (structured onboarding data) ---
    stmt = select(UserProfile).where(UserProfile.user_id == user_id)
    result = await db.execute(stmt)
    profile_row = result.scalar_one_or_none()
    
    if profile_row:
        # Parse JSON arrays
        def parse_json_list(val: Optional[str]) -> List[str]:
            if not val:
                return []
            try:
                return json.loads(val)
            except (json.JSONDecodeError, TypeError):
                return []
        
        profile = UserProfileData(
            display_name=profile_row.display_name,
            age_range=profile_row.age_range,
            location=profile_row.location,
            occupation=profile_row.occupation,
            favorite_genres=parse_json_list(profile_row.favorite_genres),
            favorite_artists=parse_json_list(profile_row.favorite_artists),
            favorite_songs=parse_json_list(profile_row.favorite_songs),
            no_go=parse_json_list(profile_row.no_go),
            explicit_lyrics=profile_row.explicit_lyrics or "ok",
            dj_personality=profile_row.dj_personality or "casual_funny",
            raw_context=profile_row.raw_context,
        )
    else:
        # Create empty profile with defaults
        profile = UserProfileData()
        
        # Try to extract from legacy context.parsed_json
        if context.parsed_json:
            pj = context.parsed_json
            profile.display_name = pj.get("display_name")
            profile.favorite_genres = pj.get("favorite_genres", [])
            profile.favorite_artists = pj.get("favorite_artists", [])
            profile.no_go = pj.get("no_go", [])
            profile.explicit_lyrics = pj.get("explicit_lyrics", "ok")
            profile.dj_personality = pj.get("dj_personality", "casual_funny")
    
    # --- Build Bundle ---
    bundle = PreferenceBundle(
        user_id=user_id,
        session_id=session_id,
        context=context,
        mood=mood,
        mood_profile=mood_profile,
        feedback=feedback,
        history=history,
        profile=profile,
        agent_settings=agent_settings,
        prompt_templates=prompt_templates,
    )
    
    # Cache for future requests
    if use_cache:
        cache = get_bundle_cache()
        cache.set(user_id, mood_id, context_name, bundle)
    
    logger.info(
        f"Built preference bundle for user {user_id}: "
        f"context={context.name}, mood={mood.name}, "
        f"likes={len(feedback.recent_likes)}, dislikes={len(feedback.recent_dislikes)}, "
        f"history={len(history.recent_plays)}"
    )
    
    return bundle


# =============================================================================
# Hard Constraints (Persona Music Rules)
# =============================================================================

def check_hard_constraints(
    song: Dict[str, Any],
    min_tempo: Optional[float] = None,
    min_energy: Optional[float] = None,
    genre_denylist: Optional[List[str]] = None,
    reject_unknown: bool = False,
) -> Tuple[bool, Optional[str]]:
    """Check if a song passes hard constraints.
    
    Returns:
        (passes, rejection_reason) - passes=True if song is allowed
    """
    from backend_v2.config import (
        DEFAULT_MIN_TEMPO_BPM,
        DEFAULT_MIN_ENERGY, 
        BALLAD_GENRE_DENYLIST,
        REJECT_UNKNOWN_FEATURES,
    )
    
    # Use defaults if not specified
    min_tempo = min_tempo if min_tempo is not None else DEFAULT_MIN_TEMPO_BPM
    min_energy = min_energy if min_energy is not None else DEFAULT_MIN_ENERGY
    genre_denylist = genre_denylist if genre_denylist is not None else BALLAD_GENRE_DENYLIST
    # Fix Issue #8: Allow reject_unknown=False to be passed through
    reject_unknown = REJECT_UNKNOWN_FEATURES if reject_unknown is None else reject_unknown
    
    features = song.get("features", {})
    
    # Check tempo
    tempo = features.get("tempo")
    if tempo is not None:
        if tempo < min_tempo:
            return False, f"tempo too low ({tempo:.0f} < {min_tempo})"
    elif reject_unknown:
        return False, "unknown tempo"
    
    # Check energy
    energy = features.get("energy")
    if energy is not None:
        if energy < min_energy:
            return False, f"energy too low ({energy:.2f} < {min_energy})"
    elif reject_unknown:
        return False, "unknown energy"
    
    # Check genre/tag denylist
    genres = song.get("genres") or []
    tags = song.get("tags") or []
    all_tags = [g.lower() for g in genres] + [t.lower() for t in tags]
    
    for tag in all_tags:
        for denied in genre_denylist:
            if denied.lower() in tag:
                return False, f"denied genre/tag: {tag}"
    
    return True, None


def apply_hard_constraints(
    songs: List[Dict[str, Any]],
    bundle: "PreferenceBundle",
    min_tempo: Optional[float] = None,
    min_energy: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """Filter songs that violate hard constraints.
    
    Should be called BEFORE scoring to remove ineligible candidates.
    
    Filters based on:
    - Tempo and energy (configurable)
    - Genre denylist (ballads, etc.)
    - User profile: explicit lyrics preference
    - User profile: no-go genres/artists
    
    Args:
        songs: List of song dicts with features
        bundle: User's preference bundle (for profile-based filtering)
        min_tempo: Override minimum tempo (uses config default if None)
        min_energy: Override minimum energy (uses config default if None)
        
    Returns:
        Filtered list of songs that pass constraints
    """
    # Get profile-based constraints
    avoid_explicit = not bundle.allows_explicit()
    no_go_list = bundle.get_no_go_list()  # lowercase list
    
    filtered = []
    rejection_counts: Dict[str, int] = {}
    
    for song in songs:
        # Check base hard constraints (tempo, energy, genre denylist)
        passes, reason = check_hard_constraints(
            song,
            min_tempo=min_tempo,
            min_energy=min_energy,
        )
        
        if not passes:
            rejection_counts[reason] = rejection_counts.get(reason, 0) + 1
            continue
        
        # Check explicit lyrics (if user wants to avoid)
        if avoid_explicit:
            is_explicit = song.get("explicit", False) or song.get("is_explicit", False)
            if is_explicit:
                rejection_counts["explicit_lyrics"] = rejection_counts.get("explicit_lyrics", 0) + 1
                continue
        
        # Check no-go list from user profile
        if no_go_list:
            artist = (song.get("artist") or "").lower()
            genres = [g.lower() for g in (song.get("genres") or [])]
            tags = [t.lower() for t in (song.get("tags") or [])]
            all_tags = genres + tags
            
            # Check if artist matches any no-go pattern
            rejected = False
            for no_go in no_go_list:
                if no_go in artist:
                    rejection_counts[f"no_go_artist:{no_go}"] = rejection_counts.get(f"no_go_artist:{no_go}", 0) + 1
                    rejected = True
                    break
                for tag in all_tags:
                    if no_go in tag:
                        rejection_counts[f"no_go_genre:{no_go}"] = rejection_counts.get(f"no_go_genre:{no_go}", 0) + 1
                        rejected = True
                        break
                if rejected:
                    break
            
            if rejected:
                continue
        
        filtered.append(song)
    
    if rejection_counts:
        logger.debug(f"Hard constraint rejections: {rejection_counts}")
    
    logger.info(f"Hard constraints: {len(songs)} -> {len(filtered)} candidates")
    return filtered


# =============================================================================
# Candidate Scoring
# =============================================================================

def score_candidate(
    song: Dict[str, Any],
    bundle: PreferenceBundle,
    prev_song: Optional[Dict[str, Any]] = None,
) -> float:
    """Score a song candidate for selection.
    
    Higher score = better match for user preferences.
    
    Args:
        song: Song dict with uuid, title, artist, and optional features
        bundle: User's preference bundle
        prev_song: Previous song for transition compatibility (optional)
        
    Returns:
        Score from -infinity to ~1.0 (negative = hard ban)
    """
    score = 0.5  # Base score
    song_uuid = song.get("uuid")
    artist = song.get("artist", "").lower()
    
    # === HARD BANS (return negative score) ===
    
    # Disliked songs are banned
    if song_uuid in bundle.get_disliked_song_uuids():
        return -1000.0
    
    # Disliked artists heavily penalized (but not if they're also a favorite artist)
    disliked_artists = [a.lower() for a in bundle.get_disliked_artists() if a]
    favorite_artists = [a.lower() for a in bundle.get_favorite_artists() if a]
    # Remove favorite artists from disliked list to prevent over-blocking
    filtered_disliked = [da for da in disliked_artists if not any(fa in da or da in fa for fa in favorite_artists)]
    if artist and any(da in artist for da in filtered_disliked):
        return -500.0
    
    # === PENALTIES ===
    
    # Recent plays penalty (heavy for very recent, lighter for older)
    if song_uuid in bundle.history.recent_plays:
        play_index = bundle.history.recent_plays.index(song_uuid)
        if play_index < 5:
            score -= 0.8  # Very recent - heavy penalty
        elif play_index < 20:
            score -= 0.4  # Recent - moderate penalty
        else:
            score -= 0.1  # Older - light penalty
    
    # Recent artist penalty (variety)
    if artist in [a.lower() for a in bundle.history.recent_artists[:10]]:
        score -= 0.3
    
    # === BOOSTS ===
    
    # Liked songs get a boost
    if song_uuid in bundle.get_liked_song_uuids():
        score += 0.3
    
    # === MOOD MATCHING (if features available) ===
    
    features = song.get("features", {})
    if features:
        # Energy distance (heavily weighted for mood differentiation)
        energy = features.get("energy")
        if energy is not None:
            energy_diff = abs(energy - bundle.mood.energy_target)
            score -= energy_diff * 0.5  # Increased from 0.2 for better mood distinction
        
        # Valence distance (heavily weighted for mood differentiation)
        valence = features.get("valence")
        if valence is not None:
            valence_diff = abs(valence - bundle.mood.valence_target)
            score -= valence_diff * 0.5  # Increased from 0.2 for better mood distinction
        
        # Apply learned weights from mood profile
        if bundle.mood_profile.weights_json:
            for feature_name, weight in bundle.mood_profile.weights_json.items():
                feature_val = features.get(feature_name)
                if feature_val is not None:
                    # Positive weight = prefer higher values
                    score += feature_val * weight * 0.1
    
    # === TRANSITION COMPATIBILITY ===
    
    if prev_song and prev_song.get("features") and features:
        prev_features = prev_song["features"]
        
        # Tempo compatibility (prefer similar or harmonic ratio)
        prev_tempo = prev_features.get("tempo")
        tempo = features.get("tempo")
        if prev_tempo and tempo:
            tempo_ratio = tempo / prev_tempo if prev_tempo > 0 else 1.0
            # Good ratios: 1.0, 0.5, 2.0 (half time, double time)
            if 0.95 <= tempo_ratio <= 1.05:
                score += 0.15  # Same tempo
            elif 0.48 <= tempo_ratio <= 0.52 or 1.95 <= tempo_ratio <= 2.05:
                score += 0.1  # Half/double time
            elif 0.8 <= tempo_ratio <= 1.2:
                score += 0.05  # Close enough
            else:
                score -= 0.1  # Big tempo jump
        
        # Key compatibility (simplified - just check if same key/mode)
        prev_key = prev_features.get("key")
        prev_mode = prev_features.get("mode")
        key = features.get("key")
        mode = features.get("mode")
        if prev_key is not None and key is not None:
            if prev_key == key and prev_mode == mode:
                score += 0.1  # Same key
            elif prev_mode == mode:
                score += 0.05  # Same mode at least
    
    return score


async def get_scored_candidates(
    db: AsyncSession,
    bundle: PreferenceBundle,
    prev_song: Optional[Dict[str, Any]] = None,
    history_ids: Optional[List[str]] = None,
    limit: int = 20,
    apply_constraints: bool = True,
) -> List[Tuple[Dict[str, Any], float]]:
    """Get song candidates with scores, sorted by score descending.
    
    Args:
        db: Database session
        bundle: User's preference bundle
        prev_song: Previous song for transition compatibility
        history_ids: List of song UUIDs to exclude (recent history)
        limit: Max candidates to return
        apply_constraints: Whether to apply hard constraints (tempo/energy)
    
    Returns:
        List of (song_dict, score) tuples
    """
    from backend_v2.models.existing import Song, SongFeatures
    from backend_v2.config import UNKNOWN_FEATURES_PENALTY
    
    # Fix Issue #6: Helper to safely parse JSON strings to lists
    def _parse_json_list_safe(val: Optional[str]) -> List[str]:
        """Parse JSON string to list, return [] on failure."""
        if not val:
            return []
        if isinstance(val, list):
            return val
        try:
            parsed = json.loads(val)
            return parsed if isinstance(parsed, list) else []
        except (json.JSONDecodeError, TypeError):
            logger.warning(f"Failed to parse JSON list: {val[:50]}...")
            return []
    
    # Defaults to bundle history if not provided
    if history_ids is None:
        history_ids = bundle.history.recent_plays

    # Get available songs with features
    stmt = (
        select(Song)
        .options(selectinload(Song.features))
        .where(
            Song.local_path.isnot(None),  # Only cached songs
            ~Song.uuid.in_(history_ids)   # Exclude recently played
        )
        .limit(200)  # Cap for performance
    )
    result = await db.execute(stmt)
    songs = result.scalars().all()
    
    # Build song dicts
    song_dicts = []
    for song in songs:
        song_dict = {
            "uuid": song.uuid,
            "title": song.title,
            "artist": song.artist,
            "local_path": song.local_path,
            "duration_sec": song.duration_sec,
            "artwork_url": song.artwork_url,
            # Fix Issue #6: Parse JSON strings to lists for genres/tags
            "genres": _parse_json_list_safe(song.genres if hasattr(song, 'genres') else None),
            "tags": _parse_json_list_safe(song.tags if hasattr(song, 'tags') else None),
            # Fix Issue #7: Include explicit field for filtering
            "explicit": bool(song.explicit) if hasattr(song, 'explicit') else False,
        }
        
        # Add features if available
        if song.features:
            song_dict["features"] = {
                "energy": song.features.energy,
                "valence": song.features.valence,
                "tempo": song.features.tempo,
                "key": song.features.key,
                "mode": song.features.mode,
                "danceability": song.features.danceability,
                "acousticness": song.features.acousticness,
                "instrumentalness": song.features.instrumentalness,
            }
        
        song_dicts.append(song_dict)
    
    # Apply hard constraints BEFORE scoring (removes slow songs, ballads etc)
    if apply_constraints:
        song_dicts = apply_hard_constraints(song_dicts, bundle)
    
    # Score remaining candidates
    scored = []
    for song_dict in song_dicts:
        score = score_candidate(song_dict, bundle, prev_song)
        
        # Skip hard-banned songs (disliked etc)
        if score < 0:
            continue
        
        # Penalize songs with unknown features
        if not song_dict.get("features"):
            score -= UNKNOWN_FEATURES_PENALTY
        
        scored.append((song_dict, score))

    
    # Sort by score descending
    scored.sort(key=lambda x: x[1], reverse=True)
    
    return scored[:limit]
