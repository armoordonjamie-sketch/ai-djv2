"""User contexts API router."""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend_v2.db.session import get_async_session
from backend_v2.models.user import User
from backend_v2.models.context import UserContext
from backend_v2.schemas.context import ContextCreate, ContextUpdate, ContextResponse
from backend_v2.auth.dependencies import get_current_user_http

router = APIRouter()


@router.get("", response_model=List[ContextResponse])
async def list_contexts(
    current_user: User = Depends(get_current_user_http),
    db: AsyncSession = Depends(get_async_session),
):
    """List all contexts for the current user."""
    result = await db.execute(
        select(UserContext)
        .where(UserContext.user_id == current_user.id)
        .order_by(UserContext.name)
    )
    return result.scalars().all()


@router.post("", response_model=ContextResponse, status_code=status.HTTP_201_CREATED)
async def create_context(
    data: ContextCreate,
    current_user: User = Depends(get_current_user_http),
    db: AsyncSession = Depends(get_async_session),
):
    """Create a new context for the current user."""
    # Check if name already exists for this user
    result = await db.execute(
        select(UserContext).where(
            UserContext.user_id == current_user.id,
            UserContext.name == data.name,
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Context '{data.name}' already exists",
        )
    
    context = UserContext(
        user_id=current_user.id,
        name=data.name,
        raw_text=data.raw_text,
    )
    db.add(context)
    await db.commit()
    await db.refresh(context)
    
    return context


@router.get("/{name}", response_model=ContextResponse)
async def get_context(
    name: str,
    current_user: User = Depends(get_current_user_http),
    db: AsyncSession = Depends(get_async_session),
):
    """Get a specific context by name."""
    result = await db.execute(
        select(UserContext).where(
            UserContext.user_id == current_user.id,
            UserContext.name == name,
        )
    )
    context = result.scalar_one_or_none()
    
    if not context:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Context '{name}' not found",
        )
    
    return context


@router.put("/{name}", response_model=ContextResponse)
async def update_context(
    name: str,
    data: ContextUpdate,
    current_user: User = Depends(get_current_user_http),
    db: AsyncSession = Depends(get_async_session),
):
    """Update a context by name."""
    result = await db.execute(
        select(UserContext).where(
            UserContext.user_id == current_user.id,
            UserContext.name == name,
        )
    )
    context = result.scalar_one_or_none()
    
    if not context:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Context '{name}' not found",
        )
    
    if data.raw_text is not None:
        context.raw_text = data.raw_text
    if data.parsed_json is not None:
        context.parsed_json = data.parsed_json
    
    await db.commit()
    await db.refresh(context)
    
    return context


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_context(
    name: str,
    current_user: User = Depends(get_current_user_http),
    db: AsyncSession = Depends(get_async_session),
):
    """Delete a context by name."""
    result = await db.execute(
        select(UserContext).where(
            UserContext.user_id == current_user.id,
            UserContext.name == name,
        )
    )
    context = result.scalar_one_or_none()
    
    if not context:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Context '{name}' not found",
        )
    
    await db.delete(context)
    await db.commit()
