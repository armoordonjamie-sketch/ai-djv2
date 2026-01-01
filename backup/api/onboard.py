"""Onboarding API endpoints.

Provides voice-based onboarding flow using ElevenLabs Conversational AI.
- GET /status: Check if user has completed onboarding
- POST /start: Get signed URL for ElevenLabs agent conversation
- POST /submit: Called by ElevenLabs agent tool to persist onboarding data
"""
import json
import logging
from datetime import timedelta
from typing import Optional, List, Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Header, status, Request
from pydantic import BaseModel, Field, ConfigDict, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend_v2.auth.dependencies import get_current_user_http
from backend_v2.db.session import get_async_session
from backend_v2.models.user import User
from backend_v2.models.user_profile import UserProfile
from backend_v2.models.context import UserContext
from backend_v2.config import (
    ELEVENLABS_API_KEY,
    ELEVENLABS_ONBOARD_AGENT_ID,
    ONBOARD_TOOL_SECRET,
)
from backend_v2.utils.time import utc_now, ensure_utc

logger = logging.getLogger("ai-dj.onboard")

router = APIRouter()


# =============================================================================
# Enum Types
# =============================================================================

ExplicitLyricsType = Literal["ok", "avoid", "depends"]
DJPersonalityType = Literal[
    "casual_funny",
    "minimal_talk", 
    "hype_energetic",
    "light_roast",
    "more_talk_between_songs"
]


# =============================================================================
# Schemas
# =============================================================================

class OnboardStatusResponse(BaseModel):
    """Response for onboarding status check."""
    onboarded: bool
    has_profile: bool
    has_spotify: bool
    display_name: Optional[str] = None



class OnboardStartResponse(BaseModel):
    """Response for starting onboarding."""
    signed_url: str
    agent_id: str
    conversation_hint: dict


class OnboardTokenResponse(BaseModel):
    """Response for WebRTC conversation token."""
    token: str
    agent_id: str
    conversation_hint: dict


class OnboardSubmitPayload(BaseModel):
    """Payload submitted by ElevenLabs agent tool.
    
    Required: user_id
    All other fields are optional for backwards compatibility and to handle nulls from LLM.
    """
    # Required fields
    user_id: str
    display_name: Optional[str] = Field(default=None, description="User's preferred name")
    
    model_config = ConfigDict(
        # Allow extra fields for backwards compatibility
        extra="ignore",
    )
    
    # Demographics (optional)
    age_range: Optional[str] = None
    location: Optional[str] = None
    occupation: Optional[str] = None
    
    # Music preferences (optional arrays)
    favorite_genres: Optional[List[str]] = Field(default_factory=list)
    favorite_artists: Optional[List[str]] = Field(default_factory=list)
    favorite_songs: Optional[List[str]] = Field(default_factory=list)
    no_go: Optional[List[str]] = Field(default_factory=list)
    
    @field_validator('favorite_genres', 'favorite_artists', 'favorite_songs', 'no_go', mode='before')
    @classmethod
    def validate_arrays(cls, v):
        """Convert null to empty list for array fields."""
        if v is None:
            return []
        return v
    
    # Preference enums (optional with defaults)
    explicit_lyrics: Optional[ExplicitLyricsType] = "ok"
    dj_personality: Optional[DJPersonalityType] = "casual_funny"
    
    # Natural language summary
    raw_context: Optional[str] = None
    
    # NEW: Enhanced preferences from improved onboarding
    # Energy/tempo preference inferred from preview reactions
    energy_preference: Optional[Literal["high_energy", "low_energy", "mixed"]] = None
    tempo_preference: Optional[Literal["fast", "slow", "mixed"]] = None
    
    # Listening contexts when user typically listens to music
    listening_contexts: Optional[List[str]] = Field(default_factory=list)
    
    # Era preference - classics vs new releases
    era_preference: Optional[Literal["new_releases", "classics", "mixed", "no_preference"]] = "mixed"
    
    @field_validator('listening_contexts', mode='before')
    @classmethod
    def validate_listening_contexts(cls, v):
        """Convert null to empty list for listening_contexts."""
        if v is None:
            return []
        return v
    
    # Legacy fields (for backwards compatibility)
    work: Optional[str] = None  # Maps to occupation
    music_preferences: Optional[dict] = None  # Legacy nested object
    mood_presets: Optional[List[dict]] = Field(default_factory=list)
    confidence: Optional[float] = Field(default=0.8, ge=0, le=1)
    
    @field_validator('user_id')
    @classmethod
    def validate_user_id(cls, v: str) -> str:
        """Ensure user_id is not empty."""
        if not v or not v.strip():
            raise ValueError("user_id is required and cannot be empty")
        return v.strip()
    
    @field_validator('display_name', mode='before')
    @classmethod
    def validate_display_name(cls, v):
        """Convert empty strings to None."""
        if v == "":
            return None
        return v


class OnboardSubmitResponse(BaseModel):
    """Response for submit endpoint."""
    ok: bool
    message: str = "Onboarding complete"
    profile_id: Optional[str] = None
    generation_started: bool = False  # Whether mood generation was started


class GenerationStatusResponse(BaseModel):
    """Response for mood generation status."""
    status: str  # pending, generating, complete, failed
    moods_created: int
    moods_total: int
    current_step: str
    intros_ready: int
    error: Optional[str] = None


# =============================================================================
# Endpoints
# =============================================================================

@router.get("/status", response_model=OnboardStatusResponse)
async def get_onboard_status(
    current_user: User = Depends(get_current_user_http),
    db: AsyncSession = Depends(get_async_session),
):
    """Check user's onboarding status.
    
    Returns onboarded=True only if:
    1. User has connected Spotify (optional but recommended)
    2. User has completed voice onboarding (onboarded_at is set)
    3. User has a profile
    4. Mood generation is complete (user has 5 moods)
    
    This prevents the frontend from getting stuck in a polling loop.
    """
    from backend_v2.models.mood import Mood
    from backend_v2.models.spotify_context import SpotifyUserContext
    from backend_v2.services.mood_generator import get_generation_progress, GenerationStatus
    
    # Check for Spotify connection
    spotify_stmt = select(SpotifyUserContext).where(SpotifyUserContext.user_id == current_user.id)
    spotify_result = await db.execute(spotify_stmt)
    spotify_context = spotify_result.scalar_one_or_none()
    has_spotify = spotify_context is not None
    
    # Check for user profile
    stmt = select(UserProfile).where(UserProfile.user_id == current_user.id)
    result = await db.execute(stmt)
    profile = result.scalar_one_or_none()
    
    # Check if user has completed voice onboarding
    voice_onboarded = current_user.onboarded_at is not None
    
    # Check if mood generation is complete (user has 5 moods)
    mood_stmt = select(Mood).where(Mood.user_id == current_user.id)
    mood_result = await db.execute(mood_stmt)
    moods = mood_result.scalars().all()
    moods_count = len(moods)
    
    # Check generation progress
    progress = get_generation_progress(current_user.id)
    generation_complete = moods_count >= 5
    
    # User is fully onboarded only if:
    # 1. Voice onboarding done
    # 2. Profile exists  
    # 3. Mood generation is complete (user has 5 moods)
    
    fully_onboarded = False
    
    if voice_onboarded and profile:
        if generation_complete:
            # User has 5 moods - fully onboarded
            fully_onboarded = True
        elif progress:
            # Check generation status
            if progress.status == GenerationStatus.COMPLETE:
                fully_onboarded = True
            elif progress.status == GenerationStatus.FAILED:
                # Generation failed - mark as onboarded anyway (user can use app, moods can be regenerated)
                fully_onboarded = True
            elif progress.status == GenerationStatus.GENERATING:
                # Still generating - not fully onboarded yet
                fully_onboarded = False
            else:
                # PENDING - not started yet or just started
                fully_onboarded = False
        else:
            # No progress tracking - check if it's been a while since onboarding
            if current_user.onboarded_at:
                onboarded_at = ensure_utc(current_user.onboarded_at)
                if onboarded_at and utc_now() - onboarded_at > timedelta(minutes=5):
                    # Been more than 5 minutes, assume generation completed or failed
                    # If user has any moods, consider them onboarded
                    fully_onboarded = moods_count > 0
                else:
                    # Still within reasonable time window - wait for generation
                    fully_onboarded = False
            else:
                fully_onboarded = False
    
    return OnboardStatusResponse(
        onboarded=fully_onboarded,
        has_profile=profile is not None,
        has_spotify=has_spotify,
        display_name=profile.display_name if profile else current_user.display_name,
    )


@router.post("/start", response_model=OnboardStartResponse)
async def start_onboarding(
    current_user: User = Depends(get_current_user_http),
    db: AsyncSession = Depends(get_async_session),
):
    """Start onboarding conversation - returns signed URL for ElevenLabs agent."""
    if not ELEVENLABS_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ElevenLabs not configured",
        )
    
    if not ELEVENLABS_ONBOARD_AGENT_ID:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Onboarding agent not configured",
        )
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://api.elevenlabs.io/v1/convai/conversation/get-signed-url",
                params={
                    "agent_id": ELEVENLABS_ONBOARD_AGENT_ID,
                    # Increase inactivity timeout to 180s (max) to prevent disconnection
                    # during webhook tool calls which may take longer to process
                    "inactivity_timeout": 180,
                },
                headers={"xi-api-key": ELEVENLABS_API_KEY},
                timeout=10.0,
            )
            response.raise_for_status()
            data = response.json()
            signed_url = data.get("signed_url")
            
            if not signed_url:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Invalid response from ElevenLabs",
                )
                
    except httpx.HTTPError as e:
        logger.error(f"ElevenLabs signed URL request failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to get conversation URL",
        )
    
    return OnboardStartResponse(
        signed_url=signed_url,
        agent_id=ELEVENLABS_ONBOARD_AGENT_ID,
        conversation_hint={
            "user_id": current_user.id,
            "display_name": current_user.display_name,
        },
    )


@router.get("/conversation-token", response_model=OnboardTokenResponse)
async def get_conversation_token(
    current_user: User = Depends(get_current_user_http),
    db: AsyncSession = Depends(get_async_session),
):
    """Get WebRTC conversation token for ElevenLabs agent.
    
    Used for iOS PWA where WebSocket connections are unreliable.
    """
    if not ELEVENLABS_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ElevenLabs not configured",
        )
    
    if not ELEVENLABS_ONBOARD_AGENT_ID:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Onboarding agent not configured",
        )
        
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://api.elevenlabs.io/v1/convai/conversation/token",
                params={
                    "agent_id": ELEVENLABS_ONBOARD_AGENT_ID,
                },
                headers={"xi-api-key": ELEVENLABS_API_KEY},
                timeout=10.0,
            )
            response.raise_for_status()
            data = response.json()
            token = data.get("token")
            
            if not token:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Invalid response from ElevenLabs",
                )
                
    except httpx.HTTPError as e:
        logger.error(f"ElevenLabs token request failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to get conversation token",
        )
    
    return OnboardTokenResponse(
        token=token,
        agent_id=ELEVENLABS_ONBOARD_AGENT_ID,
        conversation_hint={
            "user_id": str(current_user.id),
            "display_name": current_user.display_name,
        },
    )


@router.post("/submit", response_model=OnboardSubmitResponse)
async def submit_onboarding(
    payload: OnboardSubmitPayload,
    request: Request,
    x_onboard_secret: Optional[str] = Header(None, alias="X-Onboard-Secret"),
    db: AsyncSession = Depends(get_async_session),
):
    """Submit onboarding data from ElevenLabs agent tool.
    
    Accepts both new structured payload and legacy payloads for backwards compatibility.
    """
    # Log the received payload for debugging
    logger.info(f"Received onboarding submit: user_id={payload.user_id}, display_name={payload.display_name}")
    logger.debug(f"Full payload: {payload.model_dump()}")
    
    if not ONBOARD_TOOL_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Onboard tool secret not configured",
        )
    
    if x_onboard_secret != ONBOARD_TOOL_SECRET:
        logger.warning(f"Invalid onboard secret attempt for user {payload.user_id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid onboard secret",
        )
    
    # Find the user
    stmt = select(User).where(User.id == payload.user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    # Handle backwards compatibility with legacy payload
    favorite_genres = payload.favorite_genres
    favorite_artists = payload.favorite_artists
    favorite_songs = payload.favorite_songs
    no_go = payload.no_go
    explicit_lyrics = payload.explicit_lyrics or "ok"
    
    # Extract from legacy music_preferences if present
    if payload.music_preferences:
        mp = payload.music_preferences
        if not favorite_genres and mp.get("favorite_genres"):
            favorite_genres = mp.get("favorite_genres", [])
        if not favorite_artists and mp.get("favorite_artists"):
            favorite_artists = mp.get("favorite_artists", [])
        if not no_go and mp.get("avoid"):
            no_go = mp.get("avoid", [])
        if mp.get("explicit_ok") is False:
            explicit_lyrics = "avoid"
    
    # Map legacy 'work' to 'occupation'
    occupation = payload.occupation or payload.work
    
    # Upsert user profile
    stmt = select(UserProfile).where(UserProfile.user_id == user.id)
    result = await db.execute(stmt)
    profile = result.scalar_one_or_none()
    
    # Extract new enhanced preference fields
    listening_contexts = payload.listening_contexts or []
    energy_preference = payload.energy_preference
    tempo_preference = payload.tempo_preference
    era_preference = payload.era_preference or "mixed"
    
    if profile:
        # Update existing profile
        profile.display_name = payload.display_name or profile.display_name
        profile.age_range = payload.age_range or profile.age_range
        profile.location = payload.location or profile.location
        profile.occupation = occupation or profile.occupation
        profile.favorite_genres = json.dumps(favorite_genres) if favorite_genres else profile.favorite_genres
        profile.favorite_artists = json.dumps(favorite_artists) if favorite_artists else profile.favorite_artists
        profile.favorite_songs = json.dumps(favorite_songs) if favorite_songs else profile.favorite_songs
        profile.no_go = json.dumps(no_go) if no_go else profile.no_go
        profile.explicit_lyrics = explicit_lyrics
        profile.dj_personality = payload.dj_personality or profile.dj_personality
        profile.raw_context = payload.raw_context or profile.raw_context
        # NEW: Enhanced preferences
        profile.energy_preference = energy_preference or profile.energy_preference
        profile.tempo_preference = tempo_preference or profile.tempo_preference
        profile.listening_contexts = json.dumps(listening_contexts) if listening_contexts else profile.listening_contexts
        profile.era_preference = era_preference or profile.era_preference
        profile.updated_at = utc_now()
    else:
        # Create new profile
        profile = UserProfile(
            user_id=user.id,
            display_name=payload.display_name,
            age_range=payload.age_range,
            location=payload.location,
            occupation=occupation,
            favorite_genres=json.dumps(favorite_genres) if favorite_genres else None,
            favorite_artists=json.dumps(favorite_artists) if favorite_artists else None,
            favorite_songs=json.dumps(favorite_songs) if favorite_songs else None,
            no_go=json.dumps(no_go) if no_go else None,
            explicit_lyrics=explicit_lyrics,
            dj_personality=payload.dj_personality or "casual_funny",
            raw_context=payload.raw_context,
            # NEW: Enhanced preferences
            energy_preference=energy_preference,
            tempo_preference=tempo_preference,
            listening_contexts=json.dumps(listening_contexts) if listening_contexts else None,
            era_preference=era_preference,
        )
        db.add(profile)
    
    # Also update default context for legacy compatibility
    raw_text = _build_raw_context(payload, favorite_genres, favorite_artists, no_go)
    
    stmt = select(UserContext).where(
        (UserContext.user_id == user.id) &
        (UserContext.name == "default")
    )
    result = await db.execute(stmt)
    context = result.scalar_one_or_none()
    
    if context:
        context.raw_text = raw_text
        context.parsed_json = json.dumps({
            "display_name": payload.display_name,
            "favorite_genres": favorite_genres,
            "favorite_artists": favorite_artists,
            "no_go": no_go,
            "explicit_lyrics": explicit_lyrics,
            "dj_personality": payload.dj_personality,
        })
    else:
        context = UserContext(
            user_id=user.id,
            name="default",
            raw_text=raw_text,
            parsed_json=json.dumps({
                "display_name": payload.display_name,
                "favorite_genres": favorite_genres,
                "favorite_artists": favorite_artists,
                "no_go": no_go,
                "explicit_lyrics": explicit_lyrics,
                "dj_personality": payload.dj_personality,
            }),
        )
        db.add(context)
    
    # Update user
    if payload.display_name and not user.display_name:
        user.display_name = payload.display_name
    
    user.onboarded_at = utc_now()
    
    await db.commit()
    
    logger.info(f"Onboarding complete for user {user.id}: {payload.display_name}")
    
    # Start background mood generation task
    from backend_v2.services.mood_generator import start_mood_generation
    await start_mood_generation(user.id)
    
    return OnboardSubmitResponse(
        ok=True, 
        message="Onboarding complete - creating your moods!",
        profile_id=user.id,
        generation_started=True
    )


def _build_raw_context(
    payload: OnboardSubmitPayload,
    favorite_genres: List[str],
    favorite_artists: List[str],
    no_go: List[str],
) -> str:
    """Build raw_context string from structured fields."""
    if payload.raw_context:
        return payload.raw_context
    
    parts = []
    
    if payload.display_name:
        parts.append(f"Name: {payload.display_name}")
    
    if favorite_genres:
        parts.append(f"Favorite genres: {', '.join(favorite_genres)}")
    
    if favorite_artists:
        parts.append(f"Favorite artists: {', '.join(favorite_artists)}")
    
    if payload.favorite_songs:
        parts.append(f"Favorite songs: {', '.join(payload.favorite_songs[:5])}")
    
    if no_go:
        parts.append(f"Avoid: {', '.join(no_go)}")
    
    if payload.explicit_lyrics:
        explicit_map = {"ok": "explicit OK", "avoid": "no explicit", "depends": "explicit depends on mood"}
        parts.append(explicit_map.get(payload.explicit_lyrics, ""))
    
    if payload.dj_personality:
        personality_map = {
            "casual_funny": "casual/funny DJ",
            "minimal_talk": "minimal talk DJ",
            "hype_energetic": "hype/energetic DJ", 
            "light_roast": "light roast DJ",
            "more_talk_between_songs": "chatty DJ"
        }
        parts.append(personality_map.get(payload.dj_personality, ""))
    
    # NEW: Enhanced preference fields
    if payload.energy_preference:
        energy_map = {
            "high_energy": "prefers high-energy tracks",
            "low_energy": "prefers chill/low-energy tracks",
            "mixed": "likes both high and low energy"
        }
        parts.append(energy_map.get(payload.energy_preference, ""))
    
    if payload.tempo_preference:
        tempo_map = {
            "fast": "prefers fast-paced music",
            "slow": "prefers slower tempo",
            "mixed": "likes varied tempos"
        }
        parts.append(tempo_map.get(payload.tempo_preference, ""))
    
    if payload.listening_contexts:
        parts.append(f"Listens during: {', '.join(payload.listening_contexts[:4])}")
    
    if payload.era_preference and payload.era_preference != "mixed":
        era_map = {
            "new_releases": "prefers new/recent music",
            "classics": "prefers classic hits and older music",
            "no_preference": "no era preference"
        }
        parts.append(era_map.get(payload.era_preference, ""))
    
    return ", ".join(filter(None, parts))


# =============================================================================
# Generation Status Endpoint
# =============================================================================

@router.get("/generation-status", response_model=GenerationStatusResponse)
async def get_generation_status(
    current_user: User = Depends(get_current_user_http),
):
    """Get the status of mood generation for the current user.
    
    Frontend should poll this after onboarding to show progress.
    """
    from backend_v2.services.mood_generator import get_generation_progress, GenerationStatus
    
    progress = get_generation_progress(current_user.id)
    
    if not progress:
        # No generation in progress - check if user already has moods
        return GenerationStatusResponse(
            status="complete",
            moods_created=5,
            moods_total=5,
            current_step="Ready to play!",
            intros_ready=5,
            error=None,
        )
    
    return GenerationStatusResponse(
        status=progress.status.value,
        moods_created=progress.moods_created,
        moods_total=progress.moods_total,
        current_step=progress.current_step,
        intros_ready=progress.intros_ready,
        error=progress.error,
    )

