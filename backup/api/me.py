"""User profile endpoint."""
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend_v2.db.session import get_async_session
from backend_v2.models.user import User
from backend_v2.schemas.auth import UserResponse
from backend_v2.auth.dependencies import get_current_user_http

router = APIRouter()


class UserUpdateRequest(BaseModel):
    """Request to update user profile."""
    display_name: Optional[str] = None


@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(
    current_user: User = Depends(get_current_user_http),
):
    """Get the current authenticated user's profile."""
    return UserResponse.model_validate(current_user)


@router.patch("/me", response_model=UserResponse)
async def update_user_profile(
    data: UserUpdateRequest,
    current_user: User = Depends(get_current_user_http),
    db: AsyncSession = Depends(get_async_session),
):
    """Update the current user's profile."""
    if data.display_name is not None:
        current_user.display_name = data.display_name
    
    await db.commit()
    await db.refresh(current_user)
    
    return UserResponse.model_validate(current_user)

