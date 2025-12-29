"""Prompt templates API router."""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend_v2.db.session import get_async_session
from backend_v2.models.user import User
from backend_v2.models.settings import PromptTemplate
from backend_v2.schemas.settings import PromptTemplateCreate, PromptTemplateResponse
from backend_v2.schemas.auth import MessageResponse
from backend_v2.auth.dependencies import get_current_user_http

router = APIRouter()


@router.get("", response_model=List[PromptTemplateResponse])
async def list_prompt_templates(
    active_only: bool = Query(True),
    current_user: User = Depends(get_current_user_http),
    db: AsyncSession = Depends(get_async_session),
):
    """List all prompt templates for the current user."""
    query = select(PromptTemplate).where(PromptTemplate.user_id == current_user.id)
    
    if active_only:
        query = query.where(PromptTemplate.is_active == True)
    
    query = query.order_by(PromptTemplate.name, PromptTemplate.version.desc())
    
    result = await db.execute(query)
    return result.scalars().all()


@router.put("/{name}", response_model=PromptTemplateResponse)
async def upsert_prompt_template(
    name: str,
    data: PromptTemplateCreate,
    current_user: User = Depends(get_current_user_http),
    db: AsyncSession = Depends(get_async_session),
):
    """Create or update a prompt template (creates new version)."""
    # Get current max version for this template name
    result = await db.execute(
        select(PromptTemplate)
        .where(
            PromptTemplate.user_id == current_user.id,
            PromptTemplate.name == name,
        )
        .order_by(PromptTemplate.version.desc())
        .limit(1)
    )
    existing = result.scalar_one_or_none()
    
    new_version = (existing.version + 1) if existing else 1
    
    # Deactivate old versions
    if existing:
        deactivate_result = await db.execute(
            select(PromptTemplate).where(
                PromptTemplate.user_id == current_user.id,
                PromptTemplate.name == name,
                PromptTemplate.is_active == True,
            )
        )
        for old_template in deactivate_result.scalars():
            old_template.is_active = False
    
    # Create new version
    template = PromptTemplate(
        user_id=current_user.id,
        name=name,
        scope=data.scope,
        mood_id=data.mood_id,
        role=data.role,
        template_text=data.template_text,
        version=new_version,
        is_active=True,
    )
    db.add(template)
    await db.commit()
    await db.refresh(template)
    
    return template


@router.post("/{name}/activate", response_model=PromptTemplateResponse)
async def activate_prompt_template(
    name: str,
    version: int = Query(..., ge=1),
    current_user: User = Depends(get_current_user_http),
    db: AsyncSession = Depends(get_async_session),
):
    """Activate a specific version of a prompt template."""
    result = await db.execute(
        select(PromptTemplate).where(
            PromptTemplate.user_id == current_user.id,
            PromptTemplate.name == name,
            PromptTemplate.version == version,
        )
    )
    template = result.scalar_one_or_none()
    
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template '{name}' version {version} not found",
        )
    
    # Deactivate all other versions
    deactivate_result = await db.execute(
        select(PromptTemplate).where(
            PromptTemplate.user_id == current_user.id,
            PromptTemplate.name == name,
            PromptTemplate.version != version,
            PromptTemplate.is_active == True,
        )
    )
    for other in deactivate_result.scalars():
        other.is_active = False
    
    template.is_active = True
    await db.commit()
    await db.refresh(template)
    
    return template
