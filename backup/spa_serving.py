"""SPA Static File Serving Middleware.

Serves built Vite frontend with proper SPA fallback and cache headers.
"""
import os
from pathlib import Path
from typing import Optional

from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, FileResponse
from starlette.types import ASGIApp


# Paths that should NOT be handled by SPA (API, WebSocket, etc.)
API_PATH_PREFIXES = (
    "/api/",
    "/ws/",
    "/health",
    "/metrics",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/audio/",
    "/llm/",
    "/static/",
)


class SPAStaticFilesMiddleware(BaseHTTPMiddleware):
    """Middleware to serve SPA with proper fallback and cache headers.
    
    Features:
    - Serves static files from dist directory
    - Returns index.html for SPA routes (client-side routing)
    - Applies cache headers (long for hashed assets, no-cache for index.html)
    - Preserves API routes (doesn't intercept them)
    """
    
    def __init__(self, app: ASGIApp, dist_dir: str):
        super().__init__(app)
        self.dist_dir = Path(dist_dir)
        self.index_html = self.dist_dir / "index.html"
        
        if not self.index_html.exists():
            raise FileNotFoundError(
                f"Frontend dist not found at {self.dist_dir}. "
                "Run 'npm run build' in the frontend directory first."
            )
    
    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        
        # Skip API and special routes - let them pass through to FastAPI
        # Check for exact matches or prefix matches
        for api_path in API_PATH_PREFIXES:
            if api_path.endswith("/"):
                # Prefix match (e.g., "/api/")
                if path.startswith(api_path):
                    return await call_next(request)
            else:
                # Exact match or prefix match (e.g., "/health" matches "/health" and "/health/")
                if path == api_path or path.startswith(api_path + "/"):
                    return await call_next(request)
        
        # Try to serve static file
        file_path = self._get_static_file_path(path)
        
        if file_path and file_path.is_file():
            # If serving index.html from root path, use /index.html for cache logic
            effective_path = "/index.html" if path == "/" else path
            return self._file_response(file_path, effective_path)
        
        # For non-file paths (SPA routes), return index.html
        # This handles /moods, /player, /settings, etc.
        if not self._has_file_extension(path):
            return self._file_response(self.index_html, "/index.html")
        
        # File not found - let FastAPI handle 404
        return await call_next(request)
    
    def _get_static_file_path(self, url_path: str) -> Optional[Path]:
        """Get the file system path for a URL path."""
        # Remove leading slash and normalize
        clean_path = url_path.lstrip("/")
        if not clean_path:
            clean_path = "index.html"
        
        # Prevent directory traversal
        try:
            file_path = (self.dist_dir / clean_path).resolve()
            if not str(file_path).startswith(str(self.dist_dir.resolve())):
                return None
            return file_path
        except (ValueError, OSError):
            return None
    
    def _has_file_extension(self, path: str) -> bool:
        """Check if path looks like a file (has extension)."""
        basename = os.path.basename(path)
        return "." in basename and not basename.startswith(".")
    
    def _file_response(self, file_path: Path, url_path: str) -> FileResponse:
        """Create FileResponse with appropriate cache headers."""
        headers = {}
        
        # Hashed assets get long cache
        if "/assets/" in url_path or url_path.startswith("/assets/"):
            headers["Cache-Control"] = "public, max-age=31536000, immutable"
        # SW and manifest need revalidation
        elif url_path in ("/sw.js", "/manifest.webmanifest", "/registerSW.js"):
            headers["Cache-Control"] = "no-cache, must-revalidate"
        # index.html and other root files - no cache
        elif url_path == "/" or url_path == "/index.html":
            headers["Cache-Control"] = "no-cache, must-revalidate"
        else:
            # Default for other static files (icons, etc.)
            headers["Cache-Control"] = "public, max-age=86400"
        
        return FileResponse(file_path, headers=headers)


def mount_spa_serving(app, dist_dir: str) -> None:
    """Mount SPA static file serving middleware on FastAPI app.
    
    This should be called AFTER all API routes are registered.
    """
    app.add_middleware(SPAStaticFilesMiddleware, dist_dir=dist_dir)
