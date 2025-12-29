"""Password hashing and JWT token utilities.

Security features:
- bcrypt password hashing
- JWT access/refresh token creation and verification
- Refresh token hash storage (never store raw tokens)
"""
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional, Tuple

import bcrypt
from jose import jwt, JWTError

from backend_v2.config import (
    JWT_SECRET,
    JWT_ALG,
    ACCESS_TOKEN_EXPIRES_MIN,
    REFRESH_TOKEN_EXPIRES_DAYS,
)


# =============================================================================
# Password Hashing (using bcrypt directly for Python 3.13 compatibility)
# =============================================================================

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return bcrypt.checkpw(
        plain_password.encode('utf-8'), 
        hashed_password.encode('utf-8')
    )


def hash_password(password: str) -> str:
    """Hash a password for storage."""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')


# =============================================================================
# JWT Token Creation
# =============================================================================

def create_access_token(
    user_id: str, 
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Create a JWT access token.
    
    Args:
        user_id: The user's ID to encode in the token
        expires_delta: Optional custom expiration time
        
    Returns:
        Encoded JWT string
    """
    if not JWT_SECRET:
        raise ValueError("JWT_SECRET not configured")
    
    if expires_delta is None:
        expires_delta = timedelta(minutes=ACCESS_TOKEN_EXPIRES_MIN)
    
    expire = datetime.utcnow() + expires_delta
    
    payload = {
        "sub": user_id,
        "type": "access",
        "exp": expire,
        "iat": datetime.utcnow(),
    }
    
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


def create_refresh_token(user_id: str) -> Tuple[str, str, datetime]:
    """
    Create a refresh token.
    
    Returns a tuple of (raw_token, token_hash, expires_at).
    Store only the hash in the database!
    
    Args:
        user_id: The user's ID
        
    Returns:
        Tuple of (raw_token, token_hash, expires_at)
    """
    if not JWT_SECRET:
        raise ValueError("JWT_SECRET not configured")
    
    expires_delta = timedelta(days=REFRESH_TOKEN_EXPIRES_DAYS)
    expire = datetime.utcnow() + expires_delta
    
    # Generate a secure random token
    raw_token = secrets.token_urlsafe(32)
    
    # Hash for storage (we never store the raw token)
    token_hash = hash_token(raw_token)
    
    # Also encode user info in a JWT for the client
    # This allows the client to know the user_id without a DB lookup
    payload = {
        "sub": user_id,
        "type": "refresh",
        "jti": raw_token,  # The actual refresh token
        "exp": expire,
        "iat": datetime.utcnow(),
    }
    
    jwt_token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)
    
    return jwt_token, token_hash, expire


def hash_token(token: str) -> str:
    """Hash a token for secure storage."""
    return hashlib.sha256(token.encode()).hexdigest()


# =============================================================================
# JWT Token Verification
# =============================================================================

class TokenError(Exception):
    """Base exception for token errors."""
    pass


class TokenExpiredError(TokenError):
    """Token has expired."""
    pass


class TokenInvalidError(TokenError):
    """Token is invalid."""
    pass


def decode_access_token(token: str) -> dict:
    """
    Decode and verify an access token.
    
    Args:
        token: The JWT token string
        
    Returns:
        Decoded payload dict with 'sub' (user_id) and other claims
        
    Raises:
        TokenExpiredError: If token has expired
        TokenInvalidError: If token is invalid
    """
    if not JWT_SECRET:
        raise TokenInvalidError("JWT_SECRET not configured")
    
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
        
        # Verify it's an access token
        if payload.get("type") != "access":
            raise TokenInvalidError("Invalid token type")
        
        return payload
        
    except jwt.ExpiredSignatureError:
        raise TokenExpiredError("Token has expired")
    except JWTError as e:
        raise TokenInvalidError(f"Invalid token: {e}")


def decode_refresh_token(token: str) -> Tuple[str, str]:
    """
    Decode and verify a refresh token.
    
    Args:
        token: The JWT refresh token string
        
    Returns:
        Tuple of (user_id, raw_token_from_jti)
        
    Raises:
        TokenExpiredError: If token has expired
        TokenInvalidError: If token is invalid
    """
    if not JWT_SECRET:
        raise TokenInvalidError("JWT_SECRET not configured")
    
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
        
        # Verify it's a refresh token
        if payload.get("type") != "refresh":
            raise TokenInvalidError("Invalid token type")
        
        user_id = payload.get("sub")
        raw_token = payload.get("jti")
        
        if not user_id or not raw_token:
            raise TokenInvalidError("Missing token claims")
        
        return user_id, raw_token
        
    except jwt.ExpiredSignatureError:
        raise TokenExpiredError("Refresh token has expired")
    except JWTError as e:
        raise TokenInvalidError(f"Invalid token: {e}")


# =============================================================================
# CSRF Token Generation
# =============================================================================

def generate_csrf_token() -> str:
    """Generate a random CSRF token."""
    return secrets.token_urlsafe(32)
