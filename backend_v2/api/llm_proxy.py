"""Custom LLM proxy for ElevenLabs Conversational AI.

This module provides an OpenAI-compatible /v1/chat/completions endpoint
that ElevenLabs Custom LLM can call. We proxy requests to OpenRouter.

Security: Protected by Bearer token (ELEVENLABS_CUSTOM_LLM_SECRET).
"""
import json
import logging
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Header, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend_v2.config import (
    OPENROUTER_API_KEY,
    ELEVENLABS_CUSTOM_LLM_SECRET,
    OPENROUTER_ONBOARD_MODEL,
)

logger = logging.getLogger("ai-dj.llm-proxy")

router = APIRouter()


# =============================================================================
# Schemas
# =============================================================================

class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    """OpenAI-compatible chat completion request."""
    messages: List[ChatMessage]
    model: Optional[str] = None
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = None
    stream: bool = False
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[Any] = None
    response_format: Optional[Dict[str, Any]] = None
    user: Optional[str] = None
    # ElevenLabs extra body fields (we extract but don't forward)
    elevenlabs_extra_body: Optional[Dict[str, Any]] = None


# =============================================================================
# Helpers
# =============================================================================

async def stream_openrouter_response(response: httpx.Response):
    """Stream SSE response from OpenRouter."""
    async for line in response.aiter_lines():
        if line:
            yield f"{line}\n"


# =============================================================================
# Endpoints
# =============================================================================

@router.post("/v1/chat/completions")
async def chat_completions_proxy(
    request: Request,
    authorization: Optional[str] = Header(None),
):
    """
    OpenAI-compatible chat completions proxy for ElevenLabs Custom LLM.
    
    This endpoint:
    1. Validates the Bearer token
    2. Extracts elevenlabs_extra_body for context (user_id, conversation_id)
    3. Forwards to OpenRouter with configured model
    4. Streams SSE response back if requested
    """
    # Validate authorization
    if not ELEVENLABS_CUSTOM_LLM_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM proxy not configured",
        )
    
    expected_auth = f"Bearer {ELEVENLABS_CUSTOM_LLM_SECRET}"
    if authorization != expected_auth:
        logger.warning("Invalid LLM proxy authorization attempt")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization",
        )
    
    if not OPENROUTER_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OpenRouter not configured",
        )
    
    # Parse request body
    try:
        body = await request.json()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid JSON: {e}",
        )
    
    # Extract elevenlabs metadata (don't forward to OpenRouter)
    elevenlabs_extra = body.pop("elevenlabs_extra_body", None) or {}
    conversation_id = elevenlabs_extra.get("conversation_id")
    el_user_id = elevenlabs_extra.get("user_id")
    
    logger.info(f"LLM proxy request: conversation={conversation_id}, user={el_user_id}")
    
    # Build OpenRouter request
    openrouter_body = {
        "messages": body.get("messages", []),
        "model": OPENROUTER_ONBOARD_MODEL,  # Force to configured model
        "temperature": body.get("temperature", 0.7),
        "stream": body.get("stream", False),
    }
    
    # Optional fields
    if body.get("max_tokens"):
        openrouter_body["max_tokens"] = body["max_tokens"]
    if body.get("tools"):
        openrouter_body["tools"] = body["tools"]
    if body.get("tool_choice"):
        openrouter_body["tool_choice"] = body["tool_choice"]
    if body.get("response_format"):
        openrouter_body["response_format"] = body["response_format"]
    
    # Use conversation_id as session_id for OpenRouter observability
    if conversation_id:
        openrouter_body["session_id"] = conversation_id
    if el_user_id:
        openrouter_body["user"] = el_user_id
    
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://jamify.app",
        "X-Title": "Jamify Voice Onboarding",
    }
    
    # Make request to OpenRouter
    if openrouter_body.get("stream"):
        # Streaming response
        async def generate():
            async with httpx.AsyncClient() as client:
                async with client.stream(
                    "POST",
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers=headers,
                    json=openrouter_body,
                    timeout=60.0,
                ) as response:
                    if response.status_code != 200:
                        error_text = await response.aread()
                        logger.error(f"OpenRouter error: {response.status_code} {error_text}")
                        yield f"data: {json.dumps({'error': str(error_text)})}\n\n"
                        return
                    
                    async for line in response.aiter_lines():
                        if line:
                            yield f"{line}\n"
                    
                    yield "data: [DONE]\n\n"
        
        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            }
        )
    else:
        # Non-streaming response
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers=headers,
                    json=openrouter_body,
                    timeout=60.0,
                )
                
                if response.status_code != 200:
                    logger.error(f"OpenRouter error: {response.status_code} {response.text}")
                    raise HTTPException(
                        status_code=response.status_code,
                        detail=f"OpenRouter error: {response.text[:200]}",
                    )
                
                return response.json()
                
        except httpx.HTTPError as e:
            logger.error(f"OpenRouter request failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="LLM backend unavailable",
            )
