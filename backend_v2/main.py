"""AI-DJ Backend v2 - FastAPI Application Entry Point.

This is the main entry point for the multi-user authenticated AI-DJ backend.

Dev mode (API only, frontend via Vite dev server):
    uvicorn backend_v2.main:app --reload --port 8000

Prod-like mode (serve built frontend + API from same origin):
    SERVE_FRONTEND=true uvicorn backend_v2.main:app --port 5173
"""
import os
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from backend_v2.config import (
    CORS_ALLOWED_ORIGINS,
    ENABLE_DEMO_MODE,
    SEGMENT_DIR,
    SONG_CACHE_DIR,
    CSRF_ENABLED,
    SERVE_FRONTEND,
    FRONTEND_DIST_DIR,
    validate_config,
)
from backend_v2.db.session import close_db
from backend_v2.auth.csrf import CSRFMiddleware

# Import routers
from backend_v2.api.auth import router as auth_router
from backend_v2.api.me import router as me_router
from backend_v2.api.contexts import router as contexts_router
from backend_v2.api.moods import router as moods_router
from backend_v2.api.feedback import router as feedback_router
from backend_v2.api.agent_settings import router as agent_settings_router
from backend_v2.api.prompts import router as prompts_router
from backend_v2.api.stream import router as stream_router
from backend_v2.api.ws import router as ws_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("ai-dj-v2")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage application lifecycle - startup and shutdown."""
    # Startup
    logger.info("🚀 AI-DJ Backend v2 starting up...")
    
    # Validate configuration
    warnings = validate_config()
    for warning in warnings:
        logger.warning(f"⚠️  {warning}")
    
    # Log CORS configuration
    logger.info(f"🌐 CORS allowed origins: {CORS_ALLOWED_ORIGINS}")
    
    # Ensure data directories exist
    os.makedirs(SEGMENT_DIR, exist_ok=True)
    os.makedirs(SONG_CACHE_DIR, exist_ok=True)
    os.makedirs("data", exist_ok=True)  # Ensure data dir exists for SQLite
    
    # Initialize database (create tables if they don't exist)
    # NOTE: In production, use Alembic migrations instead
    from backend_v2.db.session import init_db
    await init_db()
    
    # Start acquisition worker for background track downloads
    try:
        from backend_v2.services.acquisition_worker import start_acquisition_worker
        await start_acquisition_worker(poll_interval=5, max_concurrent=2)
        logger.info("✅ Acquisition worker started")
    except Exception as e:
        logger.warning(f"⚠️  Failed to start acquisition worker: {e}")
    
    # Log initial metrics summary
    try:
        from backend_v2.monitoring.metrics import get_metrics
        metrics = get_metrics()
        logger.info("📊 Metrics collector initialized")
    except Exception as e:
        logger.warning(f"⚠️  Failed to initialize metrics: {e}")
    
    logger.info("✅ AI-DJ Backend v2 ready")
    
    yield
    
    # Shutdown
    logger.info("🛑 AI-DJ Backend v2 shutting down...")
    
    # Stop acquisition worker
    try:
        from backend_v2.services.acquisition_worker import stop_acquisition_worker
        await stop_acquisition_worker()
        logger.info("✅ Acquisition worker stopped")
    except Exception as e:
        logger.warning(f"⚠️  Error stopping acquisition worker: {e}")
    
    # Log final metrics summary
    try:
        from backend_v2.monitoring.metrics import get_metrics
        metrics = get_metrics()
        metrics.log_summary()
    except Exception as e:
        logger.warning(f"⚠️  Error logging metrics: {e}")
    
    await close_db()
    logger.info("👋 Shutdown complete")


# Create FastAPI application
app = FastAPI(
    title="AI-DJ Backend v2",
    description="Multi-user authenticated AI-DJ service with per-user contexts, moods, and streaming",
    version="2.0.0",
    lifespan=lifespan,
)


# =============================================================================
# Middleware
# =============================================================================

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,
    allow_credentials=True,  # Required for cookies
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*", "X-CSRF-Token"],
    expose_headers=["X-CSRF-Token"],
)

# CSRF Middleware (must be after CORS)
if CSRF_ENABLED:
    app.add_middleware(CSRFMiddleware)
    logger.info("🔒 CSRF protection enabled")


# =============================================================================
# Exception Handlers
# =============================================================================

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Log validation errors with request body for debugging."""
    body = await request.body()
    try:
        import json
        body_json = json.loads(body) if body else None
    except:
        body_json = body.decode('utf-8', errors='ignore') if body else None
    
    logger.error(
        f"Validation error on {request.method} {request.url.path}: {exc.errors()}\n"
        f"Request body: {body_json}\n"
        f"Headers: {dict(request.headers)}"
    )
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": exc.errors(),
            "body": body_json,
        },
    )


# =============================================================================
# API v1 Routers
# =============================================================================
app.include_router(auth_router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(me_router, prefix="/api/v1", tags=["user"])
app.include_router(contexts_router, prefix="/api/v1/contexts", tags=["contexts"])
app.include_router(moods_router, prefix="/api/v1/moods", tags=["moods"])
app.include_router(feedback_router, prefix="/api/v1/feedback", tags=["feedback"])
app.include_router(agent_settings_router, prefix="/api/v1/agent-settings", tags=["settings"])
app.include_router(prompts_router, prefix="/api/v1/prompts", tags=["prompts"])
app.include_router(stream_router, prefix="/api/v1/stream", tags=["stream"])
app.include_router(ws_router, prefix="/api/v1/ws", tags=["websocket"])

# Onboarding router
from backend_v2.api.onboard import router as onboard_router
app.include_router(onboard_router, prefix="/api/v1/onboard", tags=["onboarding"])

# LLM proxy for ElevenLabs Custom LLM (root-level path)
from backend_v2.api.llm_proxy import router as llm_proxy_router
app.include_router(llm_proxy_router, tags=["llm-proxy"])

# Deezer tools for ElevenLabs onboarding agent
from backend_v2.api.deezer_tools import router as deezer_tools_router
app.include_router(deezer_tools_router, prefix="/api/v1/deezer", tags=["deezer"])

# History endpoint
from backend_v2.api.history import router as history_router
app.include_router(history_router, prefix="/api/v1/history", tags=["history"])


# =============================================================================
# Health & Root Endpoints
# =============================================================================
@app.get("/health")
async def health_check():
    """Health check endpoint for load balancers and monitoring."""
    return {"status": "ok", "service": "ai-dj-backend-v2", "version": "2.0.0"}


@app.get("/metrics")
async def metrics():
    """Metrics endpoint returning acquisition and mood distinctness metrics."""
    from backend_v2.monitoring.metrics import get_metrics
    
    metrics_collector = get_metrics()
    summary = metrics_collector.get_summary()
    
    return {
        "status": "ok",
        "metrics": summary,
    }


@app.get("/")
async def root():
    """Root endpoint with API information."""
    return JSONResponse(
        content={
            "message": "Welcome to AI-DJ Backend v2",
            "version": "2.0.0",
            "docs": "/docs",
            "health": "/health",
            "demo_mode": ENABLE_DEMO_MODE,
        }
    )


# =============================================================================
# Demo Mode Endpoints (Legacy Compatibility)
# =============================================================================
if ENABLE_DEMO_MODE:
    logger.info("📻 Demo mode enabled - legacy endpoints available at /demo/*")
    
    @app.get("/demo/status")
    async def demo_status():
        """Check demo mode status."""
        return {
            "demo_mode": True,
            "message": "Demo mode is enabled. Use /api/v1/* for authenticated endpoints.",
        }


# =============================================================================
# Static File Mounts (for audio serving)
# =============================================================================
if os.path.exists(SEGMENT_DIR):
    app.mount("/audio/segments", StaticFiles(directory=SEGMENT_DIR), name="segments")

if os.path.exists(SONG_CACHE_DIR):
    app.mount("/audio/songs", StaticFiles(directory=SONG_CACHE_DIR), name="songs")

# Mount test page for manual verification
_static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(_static_dir):
    app.mount("/static", StaticFiles(directory=_static_dir, html=True), name="static")


# =============================================================================
# SPA Frontend Serving (Prod-like mode)
# =============================================================================
if SERVE_FRONTEND:
    from backend_v2.spa_serving import mount_spa_serving
    
    if os.path.exists(FRONTEND_DIST_DIR):
        mount_spa_serving(app, FRONTEND_DIST_DIR)
        logger.info(f"🌐 Serving built frontend from {FRONTEND_DIST_DIR}")
    else:
        logger.warning(
            f"⚠️  SERVE_FRONTEND=true but dist not found at {FRONTEND_DIST_DIR}. "
            "Run 'npm run build' in the frontend directory first."
        )

