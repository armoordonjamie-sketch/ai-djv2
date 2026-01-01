"""Authentication API router.

Endpoints:
- POST /register: Create new user account
- POST /login: Authenticate and get tokens
- POST /refresh: Rotate refresh token
- POST /logout: Revoke refresh token

All token endpoints set HttpOnly cookies for browser clients
and also return tokens in response body for API clients.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, status, Response, Form, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend_v2.db.session import get_async_session
from backend_v2.models.user import User, RefreshToken
from backend_v2.schemas.auth import (
    UserRegister,
    UserLogin,
    TokenRefresh,
    TokenLogout,
    AuthResponse,
    TokenResponse,
    MessageResponse,
    UserResponse,
)
from backend_v2.auth.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    hash_token,
    generate_csrf_token,
    TokenError,
)
from backend_v2.auth.csrf import set_csrf_cookie
from backend_v2.config import (
    ACCESS_TOKEN_EXPIRES_MIN,
    COOKIE_SECURE,
    COOKIE_SAMESITE,
    COOKIE_DOMAIN,
)
from backend_v2.utils.time import utc_now, ensure_utc

logger = logging.getLogger("ai-dj.auth")

router = APIRouter()


def set_auth_cookies(
    response: Response,
    access_token: str,
    refresh_token: str,
    csrf_token: str,
) -> None:
    """Set authentication cookies on response."""
    # Access token cookie
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        domain=COOKIE_DOMAIN,
        path="/",
        max_age=ACCESS_TOKEN_EXPIRES_MIN * 60,
    )
    
    # Refresh token cookie (restricted path)
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        domain=COOKIE_DOMAIN,
        path="/",
        max_age=7 * 24 * 60 * 60,  # 7 days
    )
    
    # CSRF token cookie (readable by JavaScript)
    set_csrf_cookie(response, csrf_token)


def clear_auth_cookies(response: Response) -> None:
    """Clear all authentication cookies."""
    response.delete_cookie(key="access_token", path="/")
    response.delete_cookie(key="refresh_token", path="/")
    response.delete_cookie(key="csrf_token", path="/")


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(
    response: Response,
    data: UserRegister,
    db: AsyncSession = Depends(get_async_session),
):
    """
    Register a new user account.
    
    Creates user, generates tokens, and sets HttpOnly cookies.
    Also returns tokens in response body for API clients.
    """
    # Check if email already exists
    result = await db.execute(
        select(User).where(User.email == data.email)
    )
    existing_user = result.scalar_one_or_none()
    
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )
    
    # Create new user
    user = User(
        email=data.email,
        password_hash=hash_password(data.password),
        display_name=data.display_name,
    )
    db.add(user)
    await db.flush()  # Get the user ID
    
    # Generate tokens
    access_token = create_access_token(user.id)
    refresh_jwt, token_hash, expires_at = create_refresh_token(user.id)
    
    # Store refresh token hash
    refresh_token_record = RefreshToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expires_at,
    )
    db.add(refresh_token_record)
    
    await db.commit()
    await db.refresh(user)
    
    # Generate CSRF token
    csrf_token = generate_csrf_token()
    
    # Set cookies
    set_auth_cookies(response, access_token, refresh_jwt, csrf_token)
    
    logger.info(f"New user registered: {user.email}")
    
    return AuthResponse(
        user=UserResponse.model_validate(user),
        access_token=access_token,
        refresh_token=refresh_jwt,
        expires_in=ACCESS_TOKEN_EXPIRES_MIN * 60,
    )


@router.post("/login", response_model=AuthResponse)
async def login(
    response: Response,
    data: UserLogin,
    db: AsyncSession = Depends(get_async_session),
):
    """
    Authenticate user and get tokens.
    
    Sets HttpOnly cookies and returns tokens in response body.
    """
    # Find user by email
    result = await db.execute(
        select(User).where(User.email == data.email, User.is_active == True)
    )
    user = result.scalar_one_or_none()
    
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    
    # Generate tokens
    access_token = create_access_token(user.id)
    refresh_jwt, token_hash, expires_at = create_refresh_token(user.id)
    
    # Store refresh token hash
    refresh_token_record = RefreshToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expires_at,
    )
    db.add(refresh_token_record)
    await db.commit()
    
    # Generate CSRF token
    csrf_token = generate_csrf_token()
    
    # Set cookies
    set_auth_cookies(response, access_token, refresh_jwt, csrf_token)
    
    logger.info(f"User logged in: {user.email}")
    
    return AuthResponse(
        user=UserResponse.model_validate(user),
        access_token=access_token,
        refresh_token=refresh_jwt,
        expires_in=ACCESS_TOKEN_EXPIRES_MIN * 60,
    )


@router.post("/login/form", response_model=TokenResponse, include_in_schema=False)
async def login_form(
    response: Response,
    username: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_async_session),
):
    """
    OAuth2 password flow for Swagger UI compatibility.
    
    Same as /login but accepts form data instead of JSON.
    """
    # Find user by email (username field)
    result = await db.execute(
        select(User).where(User.email == username, User.is_active == True)
    )
    user = result.scalar_one_or_none()
    
    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    
    # Generate tokens
    access_token = create_access_token(user.id)
    refresh_jwt, token_hash, expires_at = create_refresh_token(user.id)
    
    # Store refresh token hash
    refresh_token_record = RefreshToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expires_at,
    )
    db.add(refresh_token_record)
    await db.commit()
    
    # Generate CSRF token
    csrf_token = generate_csrf_token()
    
    # Set cookies
    set_auth_cookies(response, access_token, refresh_jwt, csrf_token)
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_jwt,
        expires_in=ACCESS_TOKEN_EXPIRES_MIN * 60,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_tokens(
    request: Request,
    response: Response,
    data: TokenRefresh = None,
    db: AsyncSession = Depends(get_async_session),
):
    """
    Refresh access token using refresh token.
    
    Implements token rotation: old refresh token is revoked,
    new tokens are issued.
    
    Accepts refresh token from:
    1. Request body (API clients)
    2. HttpOnly cookie (browsers)
    """
    # Get refresh token from body or cookie (cookie is preferred for browsers)
    refresh_jwt = None
    if data and data.refresh_token:
        refresh_jwt = data.refresh_token
    else:
        refresh_jwt = request.cookies.get("refresh_token")

    if not refresh_jwt:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Refresh token required",
        )
    
    try:
        user_id, raw_token = decode_refresh_token(refresh_jwt)
    except TokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        )
    
    # Find the refresh token in database
    token_hash = hash_token(raw_token)
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.user_id == user_id,
            RefreshToken.revoked_at == None,
        )
    )
    token_record = result.scalar_one_or_none()
    
    if not token_record:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or revoked refresh token",
        )
    
    # Check if expired
    expires_at = ensure_utc(token_record.expires_at)
    if expires_at is None or utc_now() > expires_at:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token expired",
        )
    
    # Revoke old token (rotation)
    token_record.revoked_at = utc_now()
    
    # Generate new tokens
    access_token = create_access_token(user_id)
    new_refresh_jwt, new_token_hash, new_expires_at = create_refresh_token(user_id)
    
    # Store new refresh token
    new_token_record = RefreshToken(
        user_id=user_id,
        token_hash=new_token_hash,
        expires_at=new_expires_at,
    )
    db.add(new_token_record)
    await db.commit()
    
    # Generate new CSRF token
    csrf_token = generate_csrf_token()
    
    # Set cookies
    set_auth_cookies(response, access_token, new_refresh_jwt, csrf_token)
    
    logger.info(f"Tokens refreshed for user {user_id}")
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_jwt,
        expires_in=ACCESS_TOKEN_EXPIRES_MIN * 60,
    )


@router.post("/logout", response_model=MessageResponse)
async def logout(
    response: Response,
    data: TokenLogout = None,
    db: AsyncSession = Depends(get_async_session),
):
    """
    Logout user by revoking refresh token.
    
    Clears all authentication cookies.
    """
    if data and data.refresh_token:
        try:
            user_id, raw_token = decode_refresh_token(data.refresh_token)
            token_hash = hash_token(raw_token)
            
            # Find and revoke the token
            result = await db.execute(
                select(RefreshToken).where(
                    RefreshToken.token_hash == token_hash,
                    RefreshToken.revoked_at == None,
                )
            )
            token_record = result.scalar_one_or_none()
            
            if token_record:
                token_record.revoked_at = utc_now()
                await db.commit()
                logger.info(f"User {user_id} logged out")
        except TokenError:
            # Token invalid, but we still clear cookies
            pass
    
    # Clear cookies
    clear_auth_cookies(response)
    
    return MessageResponse(message="Logged out successfully")
