"""Custom LLM proxy for ElevenLabs Conversational AI.

This module provides an OpenAI-compatible /v1/chat/completions endpoint
that ElevenLabs Custom LLM can call. We proxy requests to OpenRouter using SDK.

Security: Protected by Bearer token (ELEVENLABS_CUSTOM_LLM_SECRET).
"""
import json
import logging
import asyncio
import time
from typing import Any, Dict, List, Optional

from openrouter import OpenRouter
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

# Initialize OpenRouter SDK client (singleton)
_openrouter_client: Optional[OpenRouter] = None

def get_openrouter_sdk_client() -> Optional[OpenRouter]:
    """Get or create OpenRouter SDK client."""
    global _openrouter_client
    if not OPENROUTER_API_KEY:
        return None
    if _openrouter_client is None:
        _openrouter_client = OpenRouter(api_key=OPENROUTER_API_KEY)
    return _openrouter_client


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
    
    # Use conversation_id as session_id for OpenRouter context management
    session_id = conversation_id if conversation_id else None
    user_id = el_user_id if el_user_id else None
    
    # Get SDK client
    client = get_openrouter_sdk_client()
    if not client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OpenRouter SDK client not available",
        )
    
    # Prepare SDK parameters
    sdk_params: Dict[str, Any] = {
        "model": OPENROUTER_ONBOARD_MODEL,
        "messages": openrouter_body["messages"],
        "temperature": openrouter_body.get("temperature", 0.7),
        "stream": openrouter_body.get("stream", False),
    }
    
    if openrouter_body.get("max_tokens"):
        sdk_params["max_tokens"] = openrouter_body["max_tokens"]
    if openrouter_body.get("tools"):
        sdk_params["tools"] = openrouter_body["tools"]
    if openrouter_body.get("tool_choice"):
        sdk_params["tool_choice"] = openrouter_body["tool_choice"]
    if openrouter_body.get("response_format"):
        sdk_params["response_format"] = openrouter_body["response_format"]
    if session_id:
        sdk_params["session_id"] = session_id
    if user_id:
        sdk_params["user"] = user_id
    
    # Make request to OpenRouter via SDK
    if sdk_params.get("stream"):
        # Streaming response
        async def generate():
            try:
                loop = asyncio.get_event_loop()
                
                def _stream_sdk():
                    with client as open_router:
                        res = open_router.chat.send(**sdk_params)
                        with res as event_stream:
                            for event in event_stream:
                                # Convert SDK event to SSE format
                                # SDK events need to be converted to OpenAI-compatible SSE
                                if hasattr(event, '__dict__'):
                                    # Convert object to dict for JSON serialization
                                    event_dict = {}
                                    if hasattr(event, 'choices') and event.choices:
                                        event_dict['choices'] = [{
                                            'delta': {'content': getattr(event.choices[0], 'content', '')},
                                            'finish_reason': getattr(event.choices[0], 'finish_reason', None)
                                        }]
                                    if hasattr(event, 'model'):
                                        event_dict['model'] = event.model
                                    yield json.dumps(event_dict)
                                elif isinstance(event, dict):
                                    yield json.dumps(event)
                                else:
                                    yield json.dumps({'data': str(event)})
                
                # Run SDK streaming in executor
                stream_gen = await loop.run_in_executor(None, _stream_sdk)
                for chunk in stream_gen:
                    yield f"data: {chunk}\n\n"
                
                yield "data: [DONE]\n\n"
            except Exception as e:
                logger.error(f"OpenRouter streaming error: {e}")
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
        
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
            loop = asyncio.get_event_loop()
            
            def _call_sdk():
                with client as open_router:
                    res = open_router.chat.send(**sdk_params)
                    with res as event_stream:
                        # For non-streaming, collect all events and return the last one
                        events = list(event_stream)
                        if not events:
                            return None
                        
                        # Get the final event (complete response)
                        event = events[-1]
                        
                        # Convert SDK response to OpenAI-compatible format
                        if hasattr(event, 'choices') and event.choices:
                            choice = event.choices[0]
                            message = choice.message if hasattr(choice, 'message') else getattr(choice, 'message', {})
                            
                            content = message.content if hasattr(message, 'content') else (message.get('content', '') if isinstance(message, dict) else '')
                            
                            result = {
                                'id': f"chatcmpl-{conversation_id[:8]}" if conversation_id else "chatcmpl-unknown",
                                'object': 'chat.completion',
                                'created': int(time.time()),
                                'model': getattr(event, 'model', OPENROUTER_ONBOARD_MODEL),
                                'choices': [{
                                    'index': 0,
                                    'message': {
                                        'role': 'assistant',
                                        'content': content,
                                    },
                                    'finish_reason': getattr(choice, 'finish_reason', 'stop'),
                                }],
                                'usage': getattr(event, 'usage', {}) if hasattr(event, 'usage') else {},
                            }
                            
                            # Add tool_calls if present
                            if hasattr(message, 'tool_calls') and message.tool_calls:
                                result['choices'][0]['message']['tool_calls'] = message.tool_calls
                            elif isinstance(message, dict) and message.get('tool_calls'):
                                result['choices'][0]['message']['tool_calls'] = message['tool_calls']
                            
                            return result
                        
                        # Fallback for dict format
                        if isinstance(event, dict):
                            return event
                        
                        return None
            
            response_data = await loop.run_in_executor(None, _call_sdk)
            
            if not response_data:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="OpenRouter returned empty response",
                )
            
            return response_data
                
        except Exception as e:
            logger.error(f"OpenRouter request failed: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"LLM backend unavailable: {str(e)}",
            )
