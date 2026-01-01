"""Moods API router."""
import json
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend_v2.db.session import get_async_session
from backend_v2.models.user import User
from backend_v2.models.mood import Mood, MoodProfile
from backend_v2.schemas.mood import MoodCreate, MoodUpdate, MoodResponse
from backend_v2.schemas.auth import MessageResponse
from backend_v2.auth.dependencies import get_current_user_http

router = APIRouter()


@router.get("", response_model=List[MoodResponse])
async def list_moods(
    current_user: User = Depends(get_current_user_http),
    db: AsyncSession = Depends(get_async_session),
):
    """List all moods for the current user."""
    result = await db.execute(
        select(Mood)
        .options(selectinload(Mood.profile))
        .where(Mood.user_id == current_user.id)
        .order_by(Mood.is_default.desc(), Mood.name)
    )
    return result.scalars().all()


@router.post("", response_model=MoodResponse, status_code=status.HTTP_201_CREATED)
async def create_mood(
    data: MoodCreate,
    current_user: User = Depends(get_current_user_http),
    db: AsyncSession = Depends(get_async_session),
):
    """Create a new mood for the current user."""
    # If this is set as default, unset other defaults
    if data.is_default:
        await db.execute(
            select(Mood)
            .where(Mood.user_id == current_user.id, Mood.is_default == True)
        )
        result = await db.execute(
            select(Mood).where(Mood.user_id == current_user.id, Mood.is_default == True)
        )
        for existing_default in result.scalars():
            existing_default.is_default = False
    
    mood = Mood(
        user_id=current_user.id,
        name=data.name,
        color=data.color,
        energy_target=data.energy_target,
        valence_target=data.valence_target,
        genres_json=json.dumps(data.genres) if data.genres else None,
        dj_personality=data.dj_personality,
        is_default=data.is_default,
    )
    db.add(mood)
    await db.flush()
    
    # Create empty profile
    profile = MoodProfile(mood_id=mood.id)
    db.add(profile)
    
    await db.commit()
    
    # Trigger LLM enrichment in background to generate personalized similar artists
    import asyncio
    from backend_v2.services.mood_enrichment import enrich_mood_with_llm
    from backend_v2.models.user_profile import UserProfile
    
    async def enrich_task():
        from backend_v2.db.session import get_db_session
        async with get_db_session() as enrich_db:
            # Get user profile for context
            profile_result = await enrich_db.execute(
                select(UserProfile).where(UserProfile.user_id == current_user.id)
            )
            user_profile = profile_result.scalar_one_or_none()
            
            # Get the mood
            mood_result = await enrich_db.execute(select(Mood).where(Mood.id == mood.id))
            mood_to_enrich = mood_result.scalar_one_or_none()
            
            if mood_to_enrich:
                await enrich_mood_with_llm(enrich_db, mood_to_enrich, user_profile)
                await enrich_db.commit()
    
    asyncio.create_task(enrich_task())
    
    # Reload with profile
    result = await db.execute(
        select(Mood)
        .options(selectinload(Mood.profile))
        .where(Mood.id == mood.id)
    )
    return result.scalar_one()


@router.get("/{mood_id}", response_model=MoodResponse)
async def get_mood(
    mood_id: str,
    current_user: User = Depends(get_current_user_http),
    db: AsyncSession = Depends(get_async_session),
):
    """Get a specific mood by ID."""
    result = await db.execute(
        select(Mood)
        .options(selectinload(Mood.profile))
        .where(Mood.id == mood_id, Mood.user_id == current_user.id)
    )
    mood = result.scalar_one_or_none()
    
    if not mood:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mood not found",
        )
    
    return mood


@router.patch("/{mood_id}", response_model=MoodResponse)
async def update_mood(
    mood_id: str,
    data: MoodUpdate,
    current_user: User = Depends(get_current_user_http),
    db: AsyncSession = Depends(get_async_session),
):
    """Partially update a mood."""
    result = await db.execute(
        select(Mood)
        .options(selectinload(Mood.profile))
        .where(Mood.id == mood_id, Mood.user_id == current_user.id)
    )
    mood = result.scalar_one_or_none()
    
    if not mood:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mood not found",
        )
    
    if data.name is not None:
        mood.name = data.name
    if data.color is not None:
        mood.color = data.color
    if data.energy_target is not None:
        mood.energy_target = data.energy_target
    if data.valence_target is not None:
        mood.valence_target = data.valence_target
    if data.genres is not None:
        mood.genres_json = json.dumps(data.genres)
    if data.dj_personality is not None:
        mood.dj_personality = data.dj_personality
    
    await db.commit()
    await db.refresh(mood)
    
    return mood


@router.delete("/{mood_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mood(
    mood_id: str,
    current_user: User = Depends(get_current_user_http),
    db: AsyncSession = Depends(get_async_session),
):
    """Delete a mood."""
    result = await db.execute(
        select(Mood).where(Mood.id == mood_id, Mood.user_id == current_user.id)
    )
    mood = result.scalar_one_or_none()
    
    if not mood:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mood not found",
        )
    
    await db.delete(mood)
    await db.commit()


@router.post("/{mood_id}/set-default", response_model=MoodResponse)
async def set_default_mood(
    mood_id: str,
    current_user: User = Depends(get_current_user_http),
    db: AsyncSession = Depends(get_async_session),
):
    """Set a mood as the default."""
    result = await db.execute(
        select(Mood)
        .options(selectinload(Mood.profile))
        .where(Mood.id == mood_id, Mood.user_id == current_user.id)
    )
    mood = result.scalar_one_or_none()
    
    if not mood:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mood not found",
        )
    
    # Unset other defaults
    other_defaults = await db.execute(
        select(Mood).where(
            Mood.user_id == current_user.id,
            Mood.is_default == True,
            Mood.id != mood_id,
        )
    )
    for other in other_defaults.scalars():
        other.is_default = False
    
    mood.is_default = True
    await db.commit()
    await db.refresh(mood)
    
    return mood
