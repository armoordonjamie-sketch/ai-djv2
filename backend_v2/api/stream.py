"""Stream API router with authenticated endpoints.

Provides endpoints for:
- POST /start - Start a streaming session
- GET /status - Get current stream status
- POST /stop - Stop the streaming session
- GET / - Stream continuous MP3 audio

All endpoints require authentication via HttpOnly cookie or Bearer token.
"""
import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend_v2.db.session import get_async_session
from backend_v2.models.user import User
from backend_v2.models.context import UserContext
from backend_v2.schemas.stream import StreamStartRequest, StreamStartResponse, StreamStatusResponse
from backend_v2.schemas.auth import MessageResponse
from backend_v2.auth.dependencies import get_current_user_http
from backend_v2.streaming.pipeline import (
    get_user_pipeline,
    stop_user_pipeline,
    get_pipeline_count,
)
from backend_v2.orchestration.events import get_event_emitter
from backend_v2.config import MAX_SESSIONS_TOTAL

logger = logging.getLogger("ai-dj.stream")

router = APIRouter()


@router.post("/start", response_model=StreamStartResponse)
async def start_stream(
    data: StreamStartRequest,
    current_user: User = Depends(get_current_user_http),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Start or resume a streaming session.
    
    Idempotent: returns existing session if active.
    Enforces MAX_SESSIONS_PER_USER (1) and MAX_SESSIONS_TOTAL.
    """
    from datetime import datetime
    from backend_v2.models.existing import Session
    
    # Gate: Require onboarding before streaming
    if current_user.onboarded_at is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "onboarding_required",
                "message": "Please complete onboarding before streaming",
                "next": "/api/v1/onboard/start",
            },
        )
    
    context_id = None
    
    # Resolve context name to ID if provided
    if data.context_name:
        result = await db.execute(
            select(UserContext).where(
                UserContext.user_id == current_user.id,
                UserContext.name == data.context_name,
            )
        )
        context = result.scalar_one_or_none()
        if context:
            context_id = context.id
    
    try:
        # Generate session ID
        import uuid
        session_id = str(uuid.uuid4())
        
        # Create Session row in database (required for foreign key constraints)
        db_session = Session(
            session_id=session_id,
            user_id=current_user.id,
            context_id=context_id,
            mood_id=data.mood_id,
            started_at=datetime.utcnow().isoformat() + "Z",
            mode="autonomous",
        )
        db.add(db_session)
        await db.commit()
        logger.info(f"Created session {session_id} for user {current_user.id}")
        
        # Get or create per-user pipeline
        pipeline = await get_user_pipeline(
            user_id=current_user.id,
            session_id=session_id,
            create_if_missing=True
        )
        
        # Emit stream_status event via WebSocket
        emitter = get_event_emitter()
        await emitter.emit_stream_status(
            user_id=current_user.id,
            status="started",
            session_id=pipeline.session_id
        )
        
        # Emit structured StatusEvent for UI
        from backend_v2.schemas.status_events import StatusCategory, StatusStep
        await emitter.emit_status(
            user_id=current_user.id,
            category=StatusCategory.PLAYBACK,
            step=StatusStep.STARTING,
            user_message="Starting your stream...",
            session_id=pipeline.session_id,
        )
        
        return StreamStartResponse(
            session_id=pipeline.session_id,
            stream_url="/api/v1/stream",
            ws_url="/api/v1/ws",
            now_playing=pipeline.now_playing,
        )
    
    except ValueError as e:
        # Session limit exceeded
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        )


@router.get("/status", response_model=StreamStatusResponse)
async def get_stream_status(
    current_user: User = Depends(get_current_user_http),
):
    """Get the current user's stream status."""
    pipeline = await get_user_pipeline(
        user_id=current_user.id,
        session_id="",
        create_if_missing=False
    )
    
    if not pipeline:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active stream. Call POST /stream/start first.",
        )
    
    return StreamStatusResponse(
        session_id=pipeline.session_id,
        active=pipeline.is_running,
        mood_id=None,  # TODO: Add mood tracking in Batch 3
        context_id=None,  # TODO: Add context tracking in Batch 3
        started_at=pipeline.created_at,
        now_playing=pipeline.now_playing,
    )


@router.post("/stop", response_model=MessageResponse)
async def stop_stream(
    current_user: User = Depends(get_current_user_http),
):
    """Stop the current user's streaming session."""
    stopped = await stop_user_pipeline(current_user.id)
    
    if not stopped:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active stream to stop.",
        )
    
    # Emit stream_status event
    emitter = get_event_emitter()
    await emitter.emit_stream_status(
        user_id=current_user.id,
        status="stopped"
    )
    
    # Emit structured StatusEvent
    from backend_v2.schemas.status_events import StatusCategory, StatusStep
    await emitter.emit_status(
        user_id=current_user.id,
        category=StatusCategory.PLAYBACK,
        step=StatusStep.STOPPED,
        user_message="Stream stopped",
    )
    
    return MessageResponse(message="Stream stopped")


@router.post("/skip", response_model=MessageResponse)
async def skip_track(
    current_user: User = Depends(get_current_user_http),
):
    """Skip the currently playing track.
    
    This signals the DJ loop to move to the next segment/track.
    """
    pipeline = await get_user_pipeline(
        user_id=current_user.id,
        session_id="",
        create_if_missing=False
    )
    
    if not pipeline or not pipeline.is_running:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active stream. Start a stream first.",
        )
    
    # Signal skip to the pipeline
    try:
        await pipeline.skip_current()
        logger.info(f"User {current_user.id} skipped current track")
    except AttributeError:
        # If pipeline doesn't support skip, just log
        logger.warning(f"Skip not supported by pipeline for user {current_user.id}")
    
    # Emit skip event via WebSocket
    emitter = get_event_emitter()
    await emitter.emit_stream_status(
        user_id=current_user.id,
        status="skipped"
    )
    
    # Emit structured StatusEvent
    from backend_v2.schemas.status_events import StatusCategory, StatusStep
    await emitter.emit_status(
        user_id=current_user.id,
        category=StatusCategory.PLAYBACK,
        step=StatusStep.SKIPPING,
        user_message="Skipping to next track...",
        session_id=pipeline.session_id,
    )
    
    return MessageResponse(message="Track skipped")


@router.get("")
async def stream_audio(
    request: Request,
    current_user: User = Depends(get_current_user_http),
):
    """
    Stream the user's audio session.
    
    Authenticated via HttpOnly cookie (browser) or Bearer token (API clients).
    Returns continuous MP3 stream.
    
    The stream uses a per-user FFmpeg encoder pipeline that:
    1. Receives audio segments (or dummy audio for testing)
    2. Encodes to MP3 in real-time
    3. Streams to the client
    """
    pipeline = await get_user_pipeline(
        user_id=current_user.id,
        session_id="",
        create_if_missing=False
    )
    
    if not pipeline or not pipeline.is_running:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active stream. Call POST /stream/start first.",
        )
    
    return StreamingResponse(
        pipeline.stream_audio(),
        media_type="audio/mpeg",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Accept-Ranges": "none",
        },
    )


@router.get("/debug")
async def debug_streams(
    current_user: User = Depends(get_current_user_http),
):
    """Debug endpoint to get pipeline state."""
    pipeline = await get_user_pipeline(
        user_id=current_user.id,
        session_id="",
        create_if_missing=False
    )
    
    return {
        "total_pipelines": get_pipeline_count(),
        "max_pipelines": MAX_SESSIONS_TOTAL,
        "your_pipeline": pipeline.get_state() if pipeline else None,
        "ws_connections": get_event_emitter().get_user_connection_count(current_user.id),
    }
