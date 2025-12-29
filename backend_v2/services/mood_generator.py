"""Mood generator service for post-onboarding personalization.

Generates 5 personalized moods based on user's onboarding data:
- Flow (balanced, default)
- Energy (high energy, workout)
- Chill (relaxed, focus)
- Party (high energy, positive)
- Late Night (low energy, moody)

Each mood inherits the user's genres, artists, and DJ personality.
"""
import asyncio
import json
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from enum import Enum

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend_v2.db.session import async_session_factory
from backend_v2.models.user import User
from backend_v2.models.user_profile import UserProfile
from backend_v2.models.mood import Mood, MoodProfile
from backend_v2.orchestration.events import get_event_emitter
from backend_v2.schemas.status_events import StatusCategory, StatusStep
from backend_v2.utils.time import utc_now

logger = logging.getLogger("ai-dj.mood-generator")


class GenerationStatus(str, Enum):
    """Status of mood generation."""
    PENDING = "pending"
    GENERATING = "generating"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass
class MoodTemplate:
    """Template for generating a mood."""
    name: str
    color: str
    energy_target: float
    valence_target: float
    danceability_target: float
    tempo_range: tuple
    genre_seeds: List[str]
    era_hint: Optional[str]
    vibe_keywords: List[str]
    avoid_genres: List[str]
    example_artists: List[str]
    intro_personality: str
    description: str


@dataclass
class GenerationProgress:
    """Progress tracking for mood generation."""
    user_id: str
    status: GenerationStatus = GenerationStatus.PENDING
    moods_created: int = 0
    moods_total: int = 5
    current_step: str = "Starting..."
    intros_ready: int = 0
    error: Optional[str] = None
    started_at: datetime = field(default_factory=utc_now)
    completed_at: Optional[datetime] = None
    created_mood_ids: List[str] = field(default_factory=list)


# In-memory progress tracking (use Redis in production for multi-instance)
_generation_progress: Dict[str, GenerationProgress] = {}


# Mood templates based on common listening scenarios
# Designed with enforced spread (min pairwise energy distance > 0.15)
MOOD_TEMPLATES = [
    MoodTemplate(
        name="Flow",
        color="#ec4899",  # Pink
        energy_target=0.6,
        valence_target=0.6,
        danceability_target=0.7,
        tempo_range=(100, 130),
        genre_seeds=["pop", "indie pop", "alt-pop", "synth-pop"],
        era_hint="modern",
        vibe_keywords=["smooth", "balanced", "flowing", "steady groove"],
        avoid_genres=["hardcore", "death metal", "noise"],
        example_artists=["Dua Lipa", "The Weeknd", "Billie Eilish", "Doja Cat"],
        intro_personality="upbeat_welcoming",
        description="Balanced vibes for everyday listening"
    ),
    MoodTemplate(
        name="Energy",
        color="#f59e0b",  # Orange
        energy_target=0.85,
        valence_target=0.70,  # Lowered from 0.75 to increase distance from Party (0.85)
        danceability_target=0.85,
        tempo_range=(120, 150),
        genre_seeds=["edm", "dance", "house", "electro", "hip-hop", "rock"],
        era_hint="modern",
        vibe_keywords=["powerful", "driving", "intense", "pumped", "motivating"],
        avoid_genres=["ballad", "ambient", "lo-fi", "jazz"],
        example_artists=["Calvin Harris", "Marshmello", "Drake", "Imagine Dragons"],
        intro_personality="hyped_energetic",
        description="High energy for workouts and motivation"
    ),
    MoodTemplate(
        name="Chill",
        color="#06b6d4",  # Cyan
        energy_target=0.35,
        valence_target=0.55,
        danceability_target=0.45,
        tempo_range=(70, 100),
        genre_seeds=["lo-fi", "indie", "acoustic", "folk", "chillhop", "ambient"],
        era_hint="any",
        vibe_keywords=["mellow", "relaxed", "dreamy", "soft", "peaceful"],
        avoid_genres=["metal", "hardcore", "dubstep", "trap"],
        example_artists=["Bon Iver", "Sufjan Stevens", "Phoebe Bridgers", "Lofi Girl"],
        intro_personality="calm_soothing",
        description="Relaxed vibes for focus and unwinding"
    ),
    MoodTemplate(
        name="Party",
        color="#8b5cf6",  # Purple
        energy_target=0.9,
        valence_target=0.85,
        danceability_target=0.9,
        tempo_range=(115, 135),
        genre_seeds=["dance pop", "party", "club", "funk", "disco", "upbeat"],
        era_hint="any",
        vibe_keywords=["euphoric", "celebratory", "explosive", "wild", "unstoppable"],
        avoid_genres=["sad", "emo", "slow", "ballad"],
        example_artists=["Daft Punk", "Lizzo", "Mark Ronson", "Bruno Mars"],
        intro_personality="celebratory_wild",
        description="High energy and positive for celebrations"
    ),
    MoodTemplate(
        name="Late Night",
        color="#1e293b",  # Slate
        energy_target=0.45,
        valence_target=0.4,
        danceability_target=0.55,
        tempo_range=(85, 110),
        genre_seeds=["r&b", "alternative", "indie", "dark pop", "trip-hop"],
        era_hint="any",
        vibe_keywords=["moody", "introspective", "atmospheric", "sultry", "nocturnal"],
        avoid_genres=["upbeat pop", "happy", "children"],
        example_artists=["The Weeknd", "FKA twigs", "James Blake", "Frank Ocean"],
        intro_personality="mysterious_intimate",
        description="Low energy, moody vibes for late nights"
    ),
]


def euclidean_distance(point1: Tuple[float, float], point2: Tuple[float, float]) -> float:
    """Calculate Euclidean distance between two 2D points."""
    return math.sqrt((point1[0] - point2[0])**2 + (point1[1] - point2[1])**2)


def validate_mood_spread(moods: List[MoodTemplate], min_distance: float = 0.15) -> bool:
    """Ensure minimum pairwise distance between mood target vectors.
    
    Args:
        moods: List of mood templates to validate
        min_distance: Minimum required distance between any two moods
        
    Returns:
        True if all moods are sufficiently spread out, False otherwise
    """
    for i, m1 in enumerate(moods):
        for m2 in moods[i+1:]:
            dist = euclidean_distance(
                (m1.energy_target, m1.valence_target),
                (m2.energy_target, m2.valence_target)
            )
            if dist < min_distance:
                logger.warning(
                    f"Mood spread validation failed: {m1.name} and {m2.name} "
                    f"are too close (distance={dist:.3f}, required={min_distance})"
                )
                return False
    return True


def calculate_mood_distinctness(moods: List[MoodTemplate]) -> float:
    """Calculate average pairwise distance between mood vectors.
    
    This metric quantifies how spread out the moods are in energy-valence space.
    Higher values indicate more distinct moods.
    
    Args:
        moods: List of mood templates
        
    Returns:
        Average pairwise Euclidean distance
    """
    if len(moods) < 2:
        return 0.0
    
    distances = []
    for i, m1 in enumerate(moods):
        for m2 in moods[i+1:]:
            dist = euclidean_distance(
                (m1.energy_target, m1.valence_target),
                (m2.energy_target, m2.valence_target)
            )
            distances.append(dist)
    
    return sum(distances) / len(distances) if distances else 0.0


def _calculate_mood_spread(moods: List[MoodTemplate]) -> float:
    """Backward-compatible alias for calculating mood distinctness."""
    return calculate_mood_distinctness(moods)


# Validate templates at module load time
if not validate_mood_spread(MOOD_TEMPLATES):
    logger.error("MOOD_TEMPLATES failed spread validation! Moods may be too similar.")
else:
    distinctness = calculate_mood_distinctness(MOOD_TEMPLATES)
    logger.info(f"Mood templates validated. Average distinctness: {distinctness:.3f}")


def get_generation_progress(user_id: str) -> Optional[GenerationProgress]:
    """Get the current generation progress for a user."""
    return _generation_progress.get(user_id)


def clear_generation_progress(user_id: str) -> None:
    """Clear generation progress after completion."""
    if user_id in _generation_progress:
        del _generation_progress[user_id]


async def generate_personalized_moods(user_id: str) -> None:
    """Generate 5 personalized moods for a user based on their onboarding data.
    
    This runs as a background task after onboarding completes.
    Progress is tracked in _generation_progress for the frontend to poll.
    """
    # Initialize progress
    progress = GenerationProgress(user_id=user_id)
    _generation_progress[user_id] = progress
    
    logger.info(f"Starting mood generation for user {user_id}")
    
    try:
        progress.status = GenerationStatus.GENERATING
        
        # Emit status for onboarding
        emitter = get_event_emitter()
        await emitter.emit_status(
            user_id=user_id,
            category=StatusCategory.ONBOARDING,
            step=StatusStep.MOOD_CREATING,
            user_message="Creating your personalized moods...",
            progress=0.0,
        )
        
        async with async_session_factory() as db:
            # Get user profile for personalization
            result = await db.execute(
                select(UserProfile).where(UserProfile.user_id == user_id)
            )
            profile = result.scalar_one_or_none()
            
            if not profile:
                logger.warning(f"No profile found for user {user_id}, using defaults")
            
            # Get user's preferences from profile
            genres = []
            if profile and profile.favorite_genres:
                try:
                    genres = json.loads(profile.favorite_genres)
                except json.JSONDecodeError:
                    pass
            
            dj_personality = profile.dj_personality if profile else "casual_funny"
            
            # Delete existing moods (fresh start)
            existing = await db.execute(
                select(Mood).where(Mood.user_id == user_id)
            )
            for mood in existing.scalars():
                await db.delete(mood)
            await db.flush()
            
            # Generate each mood
            for i, template in enumerate(MOOD_TEMPLATES):
                progress.current_step = f"Creating {template.name} mood..."
                progress.moods_created = i
                
                # Merge user genres with mood-specific genre seeds
                # User genres are still respected, but mood adds its own flavor
                mood_genres = list(set((genres or []) + template.genre_seeds))
                
                # Create the mood
                mood = Mood(
                    user_id=user_id,
                    name=template.name,
                    color=template.color,
                    energy_target=template.energy_target,
                    valence_target=template.valence_target,
                    danceability_target=template.danceability_target,
                    tempo_min=template.tempo_range[0],
                    tempo_max=template.tempo_range[1],
                    genres_json=json.dumps(mood_genres),
                    genre_seeds_json=json.dumps(template.genre_seeds),
                    vibe_keywords_json=json.dumps(template.vibe_keywords),
                    avoid_genres_json=json.dumps(template.avoid_genres),
                    example_artists_json=json.dumps(template.example_artists),
                    intro_personality=template.intro_personality,
                    era_hint=template.era_hint,
                    dj_personality=dj_personality,
                    is_default=(i == 0),  # First mood is default
                )
                db.add(mood)
                await db.flush()
                
                # Create mood profile
                mood_profile = MoodProfile(
                    mood_id=mood.id,
                    summary_text=template.description,
                )
                db.add(mood_profile)
                
                progress.created_mood_ids.append(mood.id)
                
                logger.info(f"Created mood: {template.name} for user {user_id}")
                
                # Small delay to show progress (and be nice to the DB)
                await asyncio.sleep(0.5)
            
            await db.commit()
            
            progress.moods_created = len(MOOD_TEMPLATES)
            progress.current_step = "Generating intros..."
            
            # Emit progress update
            await emitter.emit_status(
                user_id=user_id,
                category=StatusCategory.ONBOARDING,
                step=StatusStep.INTRO_GENERATING,
                user_message="Preparing your intros...",
                progress=0.7,
            )
            
            # Pre-generate intros SEQUENTIALLY (not parallel) to avoid:
            # 1. Download concurrency lock contention
            # 2. YouTube rate limiting
            # 3. Duplicate song selection
            from backend_v2.orchestration.generation import generate_mood_intro
            from sqlalchemy import update
            
            for idx, mood_id in enumerate(progress.created_mood_ids):
                try:
                    # Get mood name for status message
                    mood_result = await db.execute(
                        select(Mood).where(Mood.id == mood_id)
                    )
                    mood = mood_result.scalar_one_or_none()
                    mood_name = mood.name if mood else f"Mood {idx+1}"
                    
                    logger.info(f"Generating intro {idx+1}/{len(progress.created_mood_ids)} for {mood_name}")
                    
                    # Emit status for this specific intro
                    await emitter.emit_status(
                        user_id=user_id,
                        category=StatusCategory.ONBOARDING,
                        step=StatusStep.INTRO_GENERATING,
                        user_message=f"Creating {mood_name} intro ({idx+1}/{len(progress.created_mood_ids)})...",
                        progress=0.7 + (0.3 * (idx / len(progress.created_mood_ids))),
                    )
                    
                    # Create dedicated session for this task
                    async with async_session_factory() as session:
                        result = await generate_mood_intro(session, user_id, mood_id)
                        
                        if result:
                            # Save path to DB
                            await session.execute(
                                update(Mood)
                                .where(Mood.id == mood_id)
                                .values(
                                    intro_segment_path=result['path'],
                                    intro_song_uuid=result['song_uuid']
                                )
                            )
                            await session.commit()
                            
                            progress.intros_ready += 1
                            logger.info(f"Intro ready for {mood_name} (song: {result['song_uuid']})")
                            
                            # Emit completion for this intro
                            await emitter.emit_status(
                                user_id=user_id,
                                category=StatusCategory.ONBOARDING,
                                step=StatusStep.INTRO_GENERATING,
                                user_message=f"{mood_name} intro ready! ({idx+1}/{len(progress.created_mood_ids)})",
                                progress=0.7 + (0.3 * ((idx + 1) / len(progress.created_mood_ids))),
                            )
                        else:
                            logger.warning(f"Intro generation returned None for {mood_name}")
                            
                except Exception as e:
                    logger.error(f"Intro generation failed for mood {mood_id}: {e}")
                    import traceback
                    traceback.print_exc()
            
            progress.status = GenerationStatus.COMPLETE
            progress.completed_at = utc_now()
            
            # Emit completion status
            await emitter.emit_status(
                user_id=user_id,
                category=StatusCategory.ONBOARDING,
                step=StatusStep.ONBOARDING_COMPLETE,
                user_message="Your AI DJ is ready!",
                progress=1.0,
            )
            
            logger.info(f"Mood generation complete for user {user_id}. Intros ready: {progress.intros_ready}")
    
    except Exception as e:
        logger.error(f"Mood generation failed for user {user_id}: {e}")
        import traceback
        traceback.print_exc()
        
        progress.status = GenerationStatus.FAILED
        progress.error = str(e)
        progress.current_step = f"Failed: {str(e)[:50]}"


async def start_mood_generation(user_id: str) -> None:
    """Start mood generation as a background task.
    
    This is non-blocking - the calling code can return immediately.
    """
    # Check if already generating
    existing = get_generation_progress(user_id)
    if existing and existing.status == GenerationStatus.GENERATING:
        logger.info(f"Mood generation already in progress for user {user_id}")
        return
    
    # Start background task
    asyncio.create_task(generate_personalized_moods(user_id))
    logger.info(f"Mood generation task started for user {user_id}")
