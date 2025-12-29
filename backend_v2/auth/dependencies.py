"""Authentication dependencies for FastAPI routes.

Provides:
- get_current_user_http: For HTTP routes (cookie-first, Bearer fallback)
- get_current_user_ws: For WebSocket connections (cookie-first, query param in dev)
"""
import logging
from typing import Optional

from fastapi import Depends, HTTPException, status, Request, WebSocket, Query
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend_v2.db.session import get_async_session
from backend_v2.models.user import User
from backend_v2.auth.security import (
    decode_access_token,
    TokenError,
    TokenExpiredError,
    TokenInvalidError,
)
from backend_v2.config import WS_ALLOW_QUERY_TOKEN

logger = logging.getLogger("ai-dj.auth")

# OAuth2 scheme for Swagger UI compatibility
# tokenUrl is the path to the login endpoint
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


async def get_user_by_id(
    db: AsyncSession, 
    user_id: str
) -> Optional[User]:
    """Fetch a user by ID."""
    result = await db.execute(
        select(User).where(User.id == user_id, User.is_active == True)
    )
    return result.scalar_one_or_none()


async def get_current_user_http(
    request: Request,
    db: AsyncSession = Depends(get_async_session),
    bearer_token: Optional[str] = Depends(oauth2_scheme),
) -> User:
    """
    Get the current authenticated user from an HTTP request.
    
    Authentication priority:
    1. HttpOnly access_token cookie (preferred for browsers)
    2. Authorization: Bearer token (for API clients)
    
    Raises:
        HTTPException 401: If not authenticated or token invalid
    """
    token = None
    auth_method = None
    
    # Priority 1: HttpOnly cookie
    cookie_token = request.cookies.get("access_token")
    if cookie_token:
        token = cookie_token
        auth_method = "cookie"
    
    # Priority 2: Bearer token (from Authorization header)
    elif bearer_token:
        token = bearer_token
        auth_method = "bearer"
    
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Decode and verify the token
    try:
        payload = decode_access_token(token)
        user_id = payload.get("sub")
        
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
            )
        
    except TokenExpiredError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except TokenInvalidError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Fetch user from database
    user = await get_user_by_id(db, user_id)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )
    
    logger.debug(f"Authenticated user {user.id} via {auth_method}")
    return user


async def get_current_user_optional_http(
    request: Request,
    db: AsyncSession = Depends(get_async_session),
    bearer_token: Optional[str] = Depends(oauth2_scheme),
) -> Optional[User]:
    """
    Get the current user if authenticated, or None if not.
    
    Useful for endpoints that work with or without authentication.
    """
    try:
        return await get_current_user_http(request, db, bearer_token)
    except HTTPException:
        return None


async def get_current_user_ws(
    websocket: WebSocket,
    db: AsyncSession,
    token_param: Optional[str] = None,
) -> User:
    """
    Get the current authenticated user from a WebSocket connection.
    
    Authentication priority:
    1. HttpOnly access_token cookie (preferred)
    2. Query parameter token (ONLY if WS_ALLOW_QUERY_TOKEN=true, for dev)
    
    Args:
        websocket: The WebSocket connection (after accept)
        db: Database session
        token_param: Token from query parameter (if allowed)
        
    Raises:
        Exception: If not authenticated (caller should close WebSocket with 1008)
    """
    token = None
    auth_method = None
    
    # Priority 1: HttpOnly cookie
    # Note: Cookies are available from websocket.cookies AFTER accept()
    # For scope cookies, access websocket.scope.get("cookies", {})
    cookie_token = websocket.cookies.get("access_token")
    if cookie_token:
        token = cookie_token
        auth_method = "cookie"
    
    # Priority 2: Query parameter (dev only)
    elif token_param and WS_ALLOW_QUERY_TOKEN:
        token = token_param
        auth_method = "query"
        logger.warning("WebSocket authenticated via query param (dev mode only)")
    
    if not token:
        raise Exception("WebSocket authentication required")
    
    # Decode and verify the token
    try:
        payload = decode_access_token(token)
        user_id = payload.get("sub")
        
        if not user_id:
            raise Exception("Invalid token payload")
        
    except TokenError as e:
        raise Exception(f"Token error: {e}")
    
    # Fetch user from database
    user = await get_user_by_id(db, user_id)
    
    if not user:
        raise Exception("User not found or inactive")
    
    logger.debug(f"WebSocket authenticated user {user.id} via {auth_method}")
    return user
