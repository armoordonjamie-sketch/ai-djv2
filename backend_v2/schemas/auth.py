"""Pydantic schemas for authentication endpoints."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


# =============================================================================
# Request Schemas
# =============================================================================

class UserRegister(BaseModel):
    """Registration request."""
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    display_name: Optional[str] = Field(None, max_length=100)


class UserLogin(BaseModel):
    """Login request."""
    email: EmailStr
    password: str


class TokenRefresh(BaseModel):
    """Token refresh request."""
    refresh_token: str


class TokenLogout(BaseModel):
    """Logout request."""
    refresh_token: str


# =============================================================================
# Response Schemas
# =============================================================================

class UserResponse(BaseModel):
    """User profile response."""
    id: str
    email: str
    display_name: Optional[str]
    created_at: datetime
    
    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    """Token response (for API clients that need tokens in body)."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds until access token expires


class AuthResponse(BaseModel):
    """Authentication response with user and tokens."""
    user: UserResponse
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class MessageResponse(BaseModel):
    """Simple message response."""
    message: str
