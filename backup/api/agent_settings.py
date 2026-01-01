"""Agent settings API router."""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend_v2.db.session import get_async_session
from backend_v2.models.user import User
from backend_v2.models.settings import AgentSettings
from backend_v2.schemas.settings import AgentSettingsUpdate, AgentSettingsResponse
from backend_v2.auth.dependencies import get_current_user_http

router = APIRouter()


@router.get("", response_model=List[AgentSettingsResponse])
async def list_agent_settings(
    current_user: User = Depends(get_current_user_http),
    db: AsyncSession = Depends(get_async_session),
):
    """List all agent settings for the current user."""
    result = await db.execute(
        select(AgentSettings)
        .where(AgentSettings.user_id == current_user.id)
        .order_by(AgentSettings.agent_name)
    )
    return result.scalars().all()


@router.put("/{agent_name}", response_model=AgentSettingsResponse)
async def upsert_agent_settings(
    agent_name: str,
    data: AgentSettingsUpdate,
    current_user: User = Depends(get_current_user_http),
    db: AsyncSession = Depends(get_async_session),
):
    """Create or update settings for an agent."""
    # Valid agent names
    valid_agents = {"track_selector", "transition_planner", "speech_writer", "download_planner"}
    if agent_name not in valid_agents:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid agent name. Must be one of: {', '.join(valid_agents)}",
        )
    
    result = await db.execute(
        select(AgentSettings).where(
            AgentSettings.user_id == current_user.id,
            AgentSettings.agent_name == agent_name,
        )
    )
    settings = result.scalar_one_or_none()
    
    if settings:
        settings.settings_json = data.settings_json
    else:
        settings = AgentSettings(
            user_id=current_user.id,
            agent_name=agent_name,
            settings_json=data.settings_json,
        )
        db.add(settings)
    
    await db.commit()
    await db.refresh(settings)
    
    return settings
