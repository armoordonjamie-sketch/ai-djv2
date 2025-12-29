"""CSRF protection middleware and utilities.

Implements the "double-submit" pattern:
1. On login/register/refresh, set a non-HttpOnly csrf_token cookie
2. For state-changing requests (POST/PUT/PATCH/DELETE), require X-CSRF-Token header
3. Verify header matches cookie value

WebSocket connections are exempt (rely on origin check + cookie auth).
"""
import logging
from typing import Optional

from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response, JSONResponse

from backend_v2.config import CSRF_ENABLED

logger = logging.getLogger("ai-dj.csrf")

# Methods that require CSRF protection
PROTECTED_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# Paths exempt from CSRF (e.g., public API, login/register which set the token)
CSRF_EXEMPT_PATHS = {
    "/api/v1/auth/login",
    "/api/v1/auth/register",
    "/api/v1/auth/refresh",
    "/health",
    "/docs",
    "/openapi.json",
    "/redoc",
}


class CSRFMiddleware(BaseHTTPMiddleware):
    """
    CSRF protection middleware using double-submit pattern.
    
    Skips:
    - Non-protected methods (GET, HEAD, OPTIONS)
    - Exempt paths (login, register, etc.)
    - Requests without credentials (no cookies)
    - WebSocket upgrade requests
    """
    
    async def dispatch(self, request: Request, call_next) -> Response:
        # Skip if CSRF is disabled
        if not CSRF_ENABLED:
            return await call_next(request)
        
        # Skip non-protected methods
        if request.method not in PROTECTED_METHODS:
            return await call_next(request)
        
        # Skip exempt paths
        if request.url.path in CSRF_EXEMPT_PATHS:
            return await call_next(request)
        
        # Skip if path starts with exempt patterns
        for exempt_path in CSRF_EXEMPT_PATHS:
            if request.url.path.startswith(exempt_path):
                return await call_next(request)
        
        # Skip WebSocket upgrade requests
        if request.headers.get("upgrade", "").lower() == "websocket":
            return await call_next(request)
        
        # Get CSRF token from cookie
        csrf_cookie = request.cookies.get("csrf_token")
        
        # Get CSRF token from header
        csrf_header = request.headers.get("X-CSRF-Token")
        
        # If no CSRF cookie, the request likely hasn't authenticated yet
        # Let the auth middleware handle it
        if not csrf_cookie:
            return await call_next(request)
        
        # Verify CSRF token
        if not csrf_header:
            logger.warning(f"CSRF token missing in header for {request.method} {request.url.path}")
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": "CSRF token missing. Include X-CSRF-Token header."},
            )
        
        if csrf_cookie != csrf_header:
            logger.warning(f"CSRF token mismatch for {request.method} {request.url.path}")
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": "CSRF token mismatch."},
            )
        
        return await call_next(request)


def set_csrf_cookie(response: Response, csrf_token: str) -> None:
    """
    Set the CSRF token cookie on a response.
    
    This cookie is NOT HttpOnly so JavaScript can read it and include
    it in the X-CSRF-Token header.
    """
    from backend_v2.config import COOKIE_SECURE, COOKIE_SAMESITE, COOKIE_DOMAIN
    
    response.set_cookie(
        key="csrf_token",
        value=csrf_token,
        httponly=False,  # Must be readable by JavaScript
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        domain=COOKIE_DOMAIN,
        path="/",
    )


def validate_csrf_token(request: Request) -> bool:
    """
    Manually validate CSRF token for a request.
    
    Useful for WebSocket or other contexts where middleware doesn't apply.
    
    Returns:
        True if valid or CSRF disabled, False otherwise
    """
    if not CSRF_ENABLED:
        return True
    
    csrf_cookie = request.cookies.get("csrf_token")
    csrf_header = request.headers.get("X-CSRF-Token")
    
    if not csrf_cookie or not csrf_header:
        return False
    
    return csrf_cookie == csrf_header
