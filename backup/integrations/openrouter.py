"""OpenRouter API client for Gemini 2.5 Flash LLM calls.

Ported from backend/integrations/openrouter.py with adaptations for:
- PreferenceBundle-based personalization
- Per-user agent settings
- Prompt template injection
- LLM trace storage with user_id/mood_id
- Session-based context management via OpenRouter SDK

Evidence: Implementing Phase 4 of implementation_plan.md
"""
import json
import os
import logging
import re
import zlib
from typing import Optional, Dict, Any, List, Set, Union, TYPE_CHECKING

from openrouter import OpenRouter

from backend_v2.config import (
    OPENROUTER_API_KEY,
    THINKING_BUDGET_TRACK,
    THINKING_BUDGET_TRANSITION,
    THINKING_BUDGET_SPEECH,
)
from backend_v2.utils.time import utc_isoformat, utc_now

if TYPE_CHECKING:
    from backend_v2.services.preference_bundle import PreferenceBundle

logger = logging.getLogger("ai-dj.openrouter")


# =============================================================================
# LLM Output Validation Helpers
# =============================================================================

def validate_track_selection_response(
    parsed: Optional[Dict[str, Any]],
    valid_uuids: Optional[List[str]] = None
) -> bool:
    """Validate track selection response structure."""
    if not parsed:
        return False
    
    selected_uuid = parsed.get('selected_uuid')
    if not isinstance(selected_uuid, str) or len(selected_uuid.strip()) == 0:
        return False
    
    if valid_uuids is not None and selected_uuid not in valid_uuids:
        logger.warning(f"LLM selected UUID '{selected_uuid}' not in valid list")
        return False
    
    return True


def validate_transition_plan_response(parsed: Optional[Dict[str, Any]]) -> bool:
    """Validate transition plan response structure."""
    if not parsed or not isinstance(parsed, dict):
        return False
    
    transition_type = parsed.get('transition_type')
    if not isinstance(transition_type, str) or not transition_type:
        return False
    
    mix_length = parsed.get('mix_length_bars')
    if not isinstance(mix_length, (int, float)):
        return False
    if int(mix_length) not in {8, 16, 32}:
        return False
    
    # Validate start_position_a_seconds (NEW)
    start_a = parsed.get('start_position_a_seconds')
    if start_a is not None:  # Optional for backward compatibility
        if not isinstance(start_a, (int, float)):
            return False
        if start_a <= 0:
            return False
    
    # Validate start_position_b_seconds
    start_b = parsed.get('start_position_b_seconds')
    if not isinstance(start_b, (int, float)):
        return False
    if start_b < 5.0 or start_b > 30.0:  # NEW: stricter range
        return False
    
    # Validate transition_duration_seconds (NEW)
    duration = parsed.get('transition_duration_seconds')
    if duration is not None:  # Optional for backward compatibility
        if not isinstance(duration, (int, float)):
            return False
        if duration <= 0 or duration > 24.0:
            return False
        
        # Type-specific duration validation
        duration_bounds = {
            "quick_cut": (1.0, 2.0),
            "vinyl_stop": (2.0, 6.0),
            "bass_swap": (4.0, 8.0),
            "loop_mix": (6.0, 10.0),
            "drop_mix": (4.0, 8.0),
            "filter_sweep": (5.0, 10.0),
            "crossfade": (6.0, 12.0),
            "eq_blend": (6.0, 12.0),
        }
        bounds = duration_bounds.get(transition_type, (1.0, 24.0))
        if duration < bounds[0] or duration > bounds[1]:
            logger.warning(
                f"Transition duration {duration:.1f}s out of bounds {bounds} for type '{transition_type}'"
            )
            return False
    
    return True



# =============================================================================
# Audio Snippet & Transition Helpers
# =============================================================================

def get_track_duration_sec(track: Dict[str, Any]) -> float:
    """Resolve track duration from metadata or file.
    
    Args:
        track: Track dict with duration_sec, duration, or local_path, OR string file path
        
    Returns:
        Duration in seconds, or 180.0 as fallback
    """
    # Handle string path
    if isinstance(track, str):
        if track and os.path.exists(track):
            try:
                from backend_v2.audio.mix import get_duration
                return get_duration(track)
            except Exception:
                pass
        return 180.0

    # Try duration_sec first
    if "duration_sec" in track:
        duration = track["duration_sec"]
        if isinstance(duration, (int, float)) and duration > 0:
            return float(duration)
    
    # Try duration
    if "duration" in track:
        duration = track["duration"]
        if isinstance(duration, (int, float)) and duration > 0:
            return float(duration)
    
    # Try to get from file if local_path exists
    if "local_path" in track:
        try:
            from backend_v2.audio.mix import get_duration
            path = track["local_path"]
            if path and isinstance(path, str):
                if os.path.exists(path):
                    duration = get_duration(path)
                    if duration > 0:
                        return duration
        except Exception as e:
            logger.debug(f"Failed to get duration from file: {e}")
    
    # Fallback
    return 180.0


def build_audio_snippet(
    path: str,
    start_sec: float,
    duration_sec: float
) -> Optional[str]:
    """Extract audio snippet and return base64-encoded WAV.
    
    Uses ffmpeg to:
    - Seek to start_sec
    - Extract duration_sec of audio
    - Convert to mono, 16kHz, WAV
    - Base64 encode for OpenRouter API
    
    Args:
        path: Path to audio file
        start_sec: Start position in seconds
        duration_sec: Duration to extract in seconds
        
    Returns:
        Base64-encoded WAV string, or None on failure
    """
    import os
    import base64
    import tempfile
    
    if not path or not os.path.exists(path):
        logger.debug(f"Audio snippet: file not found: {path}")
        return None
    
    try:
        import ffmpeg
        
        # Create temporary file for snippet
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name
        
        try:
            # Extract snippet: mono, 16kHz for efficiency
            (
                ffmpeg
                .input(path, ss=start_sec)
                .output(
                    tmp_path,
                    acodec="pcm_s16le",
                    format="wav",
                    ar=16000,
                    ac=1,
                    t=duration_sec,
                )
                .overwrite_output()
                .run(capture_stdout=True, capture_stderr=True, quiet=True)
            )
            
            # Read and base64 encode
            with open(tmp_path, "rb") as f:
                wav_data = f.read()
            
            b64_data = base64.b64encode(wav_data).decode("utf-8")
            
            logger.debug(
                f"Audio snippet extracted: {os.path.basename(path)} "
                f"[{start_sec:.1f}s - {start_sec + duration_sec:.1f}s] "
                f"-> {len(b64_data)} base64 chars"
            )
            
            return b64_data
            
        finally:
            # Clean up temp file
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
                
    except Exception as e:
        logger.warning(f"Failed to build audio snippet: {e}")
        return None


def normalize_transition_plan(
    plan: Dict[str, Any],
    song_a: Dict[str, Any],
    song_b: Dict[str, Any]
) -> Dict[str, Any]:
    """Clamp and normalize transition plan values to safe ranges.
    
    Args:
        plan: Transition plan from LLM
        song_a: Current song metadata
        song_b: Next song metadata
        
    Returns:
        Normalized plan with safe values
    """
    # Get durations
    duration_a = get_track_duration_sec(song_a)
    duration_b = get_track_duration_sec(song_b)
    
    # Get transition duration
    transition_dur = plan.get("transition_duration_seconds", 10.0)
    if not isinstance(transition_dur, (int, float)) or transition_dur <= 0:
        transition_dur = 10.0
    
    # Clamp start_position_a_seconds
    # Must be in last 30s of song, with enough tail for transition
    if "start_position_a_seconds" in plan:
        min_a = max(0, duration_a - 30.0)
        max_a = max(0, duration_a - transition_dur - 5.0)  # 5s buffer
        start_a = plan["start_position_a_seconds"]
        
        if isinstance(start_a, (int, float)):
            clamped_a = max(min_a, min(start_a, max_a))
            if abs(clamped_a - start_a) > 0.1:
                logger.debug(
                    f"Clamped start_position_a from {start_a:.1f}s to {clamped_a:.1f}s "
                    f"(range: {min_a:.1f}s - {max_a:.1f}s)"
                )
            plan["start_position_a_seconds"] = clamped_a
    
    # Clamp start_position_b_seconds to 5-30s
    # Also ensure it doesn't exceed song duration
    if "start_position_b_seconds" in plan:
        start_b = plan["start_position_b_seconds"]
        max_b = min(30.0, duration_b - 30.0) if duration_b > 30.0 else max(5.0, duration_b * 0.2)
        
        if isinstance(start_b, (int, float)):
            clamped_b = max(5.0, min(start_b, max_b))
            if abs(clamped_b - start_b) > 0.1:
                logger.debug(
                    f"Clamped start_position_b from {start_b:.1f}s to {clamped_b:.1f}s "
                    f"(range: 5.0s - {max_b:.1f}s)"
                )
            plan["start_position_b_seconds"] = clamped_b
    
    # Clamp duration to type-specific bounds
    transition_type = plan.get("transition_type", "crossfade")
    bounds = {
        "quick_cut": (1.0, 2.0),
        "vinyl_stop": (2.0, 6.0),
        "bass_swap": (4.0, 8.0),
        "loop_mix": (6.0, 10.0),
        "drop_mix": (4.0, 8.0),
        "filter_sweep": (5.0, 10.0),
        "crossfade": (6.0, 12.0),
        "eq_blend": (6.0, 12.0),
    }.get(transition_type, (4.0, 12.0))
    
    if "transition_duration_seconds" in plan:
        duration = plan["transition_duration_seconds"]
        if isinstance(duration, (int, float)):
            clamped_dur = max(bounds[0], min(duration, bounds[1]))
            if abs(clamped_dur - duration) > 0.1:
                logger.debug(
                    f"Clamped transition_duration from {duration:.1f}s to {clamped_dur:.1f}s "
                    f"(bounds for {transition_type}: {bounds})"
                )
            plan["transition_duration_seconds"] = clamped_dur
    
    return plan
# =============================================================================
# Profile Context Helper
# =============================================================================

def build_profile_context(bundle: "PreferenceBundle") -> str:
    """Build a concise profile summary for LLM prompts.
    
    Extracts structured profile data from bundle.profile and formats
    it for inclusion in AI prompts.
    
    Args:
        bundle: User's preference bundle with profile
        
    Returns:
        Formatted string with user profile info
    """
    lines = []
    # Always include canonical identifiers for tool calls.
    if bundle.user_id:
        lines.append(f"USER_ID: {bundle.user_id}")
    if bundle.mood and getattr(bundle.mood, "id", None):
        lines.append(f"MOOD_ID: {bundle.mood.id}")
    
    if bundle.profile:
        # User name
        if bundle.profile.display_name:
            lines.append(f"User: {bundle.profile.display_name}")
        
        # Music preferences
        if bundle.profile.favorite_genres:
            lines.append(f"Favorite Genres: {', '.join(bundle.profile.favorite_genres[:5])}")
        
        if bundle.profile.favorite_artists:
            lines.append(f"Favorite Artists: {', '.join(bundle.profile.favorite_artists[:5])}")
        
        # ENHANCED: Better utilize favorite_songs - show more and emphasize importance
        if bundle.profile.favorite_songs:
            # Show up to 5 favorite songs for better seeding
            songs_list = bundle.profile.favorite_songs[:5]
            lines.append(f"🎵 FAVORITE SONGS (use for inspiration): {', '.join(songs_list)}")
        
        # Hard constraints
        if bundle.profile.no_go:
            lines.append(f"AVOID (user hates): {', '.join(bundle.profile.no_go)}")
        
        if not bundle.profile.allows_explicit():
            lines.append("AVOID explicit lyrics")
        
        # DJ personality preference
        personality_labels = {
            "casual_funny": "casual/funny style",
            "minimal_talk": "minimal talk preferred",
            "hype_energetic": "hype/energetic style",
            "light_roast": "light roasting welcome",
            "more_talk_between_songs": "chatty/talkative style",
        }
        if bundle.profile.dj_personality in personality_labels:
            lines.append(f"DJ Style: {personality_labels[bundle.profile.dj_personality]}")
        
        # NEW: Enhanced preference fields
        # Energy preference
        if bundle.profile.energy_preference:
            energy_labels = {
                "high_energy": "⚡ Prefers HIGH ENERGY tracks",
                "low_energy": "🧘 Prefers CHILL/relaxed tracks",
                "mixed": "Enjoys both high and low energy",
            }
            if bundle.profile.energy_preference in energy_labels:
                lines.append(energy_labels[bundle.profile.energy_preference])
        
        # Tempo preference
        if bundle.profile.tempo_preference:
            tempo_labels = {
                "fast": "🏃 Prefers FAST tempo music",
                "slow": "🐢 Prefers SLOWER tempo music",
                "mixed": "Likes varied tempos",
            }
            if bundle.profile.tempo_preference in tempo_labels:
                lines.append(tempo_labels[bundle.profile.tempo_preference])
        
        # Listening contexts
        if bundle.profile.listening_contexts:
            contexts = bundle.profile.listening_contexts[:4]
            lines.append(f"📍 Listens during: {', '.join(contexts)}")
        
        # Era preference
        if bundle.profile.era_preference and bundle.profile.era_preference != "mixed":
            era_labels = {
                "new_releases": "📅 Prefers NEW/recent music releases",
                "classics": "🎸 Prefers CLASSIC hits and older music",
                "no_preference": "No era preference",
            }
            if bundle.profile.era_preference in era_labels:
                lines.append(era_labels[bundle.profile.era_preference])
    
    # Fallback to legacy context if no profile data
    if not lines and bundle.context and bundle.context.parsed_json:
        pj = bundle.context.parsed_json
        if pj.get("display_name"):
            lines.append(f"User: {pj['display_name']}")
        if pj.get("favorite_genres"):
            lines.append(f"Favorite Genres: {', '.join(pj['favorite_genres'][:5])}")
        if pj.get("favorite_artists"):
            lines.append(f"Favorite Artists: {', '.join(pj['favorite_artists'][:5])}")
        if pj.get("no_go"):
            lines.append(f"AVOID: {', '.join(pj['no_go'])}")
    
    # NEW: Add Spotify listening data if available
    if bundle.profile.spotify_connected:
        lines.append("\n🎧 SPOTIFY LISTENING DATA:")
        
        # Top tracks with stats for DJ speech hooks
        if bundle.profile.top_tracks_with_stats:
            top_tracks = bundle.profile.top_tracks_with_stats[:5]
            track_lines = []
            for track in top_tracks:
                time_range_label = {
                    "short_term": "last month",
                    "medium_term": "last 6 months",
                    "long_term": "all time"
                }.get(track.get("time_range", ""), "recently")
                track_lines.append(f"#{track.get('rank')} {track.get('title')} by {track.get('artist')} ({time_range_label})")
            lines.append(f"Top Tracks: {'; '.join(track_lines)}")
        
        # Spotify genre analysis
        if bundle.profile.spotify_genre_analysis:
            primary_genres = bundle.profile.spotify_genre_analysis.get("primary_genres", [])
            if primary_genres:
                lines.append(f"Spotify Genres: {', '.join(primary_genres[:5])}")
        
        # Listening frequency
        if bundle.profile.listening_frequency:
            lines.append(f"Listening Frequency: {bundle.profile.listening_frequency}")
    
    # Add mood-specific training insights from MoodProfile
    if bundle.mood_profile and bundle.mood_profile.summary_text:
        lines.append(f"\n🎓 LEARNED PREFERENCES:\n{bundle.mood_profile.summary_text}")
    
    return "\n".join(lines)


# =============================================================================
# OpenRouter Client
# =============================================================================

class OpenRouterClient:
    """Async client for OpenRouter API (Gemini 2.5 Flash).
    
    Adapted for multi-user backend with:
    - PreferenceBundle integration for personalization
    - Per-user agent settings (thinking_budget, temperature)
    - Prompt template injection
    - LLM trace storage
    - Session-based context management via OpenRouter SDK
    """
    
    def __init__(self):
        self.api_key = OPENROUTER_API_KEY
        # Use Gemini 2.0 Flash (supports tools, JSON mode, structured outputs)
        # Context: 1M tokens, Max completion: 8K tokens
        # Default to environment variable if set, otherwise fallback to 001
        self.model = os.getenv("OPENROUTER_MODEL", "google/gemini-2.0-flash-001")
        # Use paid model for all tasks (free tier has rate limits)
        self.model_lite = os.getenv("OPENROUTER_MODEL", "google/gemini-2.0-flash-001")
        
        if not self.api_key:
            logger.warning("OpenRouter API key not configured")
            self.enabled = False
            self.client = None
        else:
            self.enabled = True
            # Initialize OpenRouter SDK client
            self.client = OpenRouter(api_key=self.api_key)
    
    async def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        thinking_budget: Optional[int] = None,
        json_mode: bool = False,
        search_web: bool = False,
        use_lite_model: bool = False,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = "auto",
        session_id: Optional[str] = None,
        # Logging parameters
        db: Optional["AsyncSession"] = None,
        user_id: Optional[str] = None,
        mood_id: Optional[str] = None,
        agent_name: Optional[str] = None,
        auto_log: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """Call Gemini 2.0 Flash via OpenRouter SDK with optional tool calling.
        
        Args:
            messages: List of message dicts
            temperature: Sampling temperature
            max_tokens: Max completion tokens
            thinking_budget: Max reasoning tokens (for thinking models)
            json_mode: Force JSON response format
            search_web: Enable web search
            use_lite_model: Use lite model (both are now paid due to rate limits)
            tools: List of tool definitions for function calling
            tool_choice: How to select tools ("auto", "none", or specific tool)
            session_id: Optional session ID for context management across calls
            db: Optional database session for auto-logging
            user_id: Optional user ID for auto-logging
            mood_id: Optional mood ID for auto-logging
            agent_name: Optional agent name for auto-logging
            auto_log: Whether to automatically log this call (requires db, user_id, agent_name)
        """
        if not self.enabled or not self.client:
            logger.debug("OpenRouter client disabled")
            return None
        
        try:
            model = self.model_lite if use_lite_model else self.model
            if search_web:
                model += ":online"
            
            # Prepare parameters for SDK
            params: Dict[str, Any] = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "stream": False,
            }
            
            if max_tokens:
                params["max_tokens"] = max_tokens
            
            # Note: OpenRouter SDK doesn't support max_reasoning_tokens parameter
            # The thinking_budget is still logged in traces for monitoring,
            # but cannot be passed to the SDK directly
            # if thinking_budget:
            #     params["max_reasoning_tokens"] = thinking_budget  # Not supported by SDK
            
            # CRITICAL: json_mode conflicts with tool calling
            # When tools are provided, disable json_mode to allow tool calls
            # We'll enable json_mode only after tools have been executed
            if json_mode and not tools:
                params["response_format"] = {"type": "json_object"}
                # Add JSON instruction to system message
                if messages and messages[0]["role"] == "system":
                    if isinstance(messages[0]["content"], str):
                        messages[0]["content"] += "\n\nRespond with valid JSON only."
            elif json_mode and tools:
                logger.warning("🔧 json_mode disabled because tools are provided (json_mode conflicts with tool calling)")
                # Don't set response_format when tools are present
            
            # Add tool calling if tools provided
            if tools:
                params["tools"] = tools
                if tool_choice:
                    params["tool_choice"] = tool_choice
                logger.debug(f"🔧 Passing {len(tools)} tool(s) to OpenRouter SDK: {[t.get('function', {}).get('name', 'unknown') if isinstance(t, dict) else 'unknown' for t in tools]}")
                logger.debug(f"🔧 Tool choice: {tool_choice}")
            else:
                logger.debug("🔧 No tools provided for this LLM call")
            
            # Note: OpenRouter SDK may not support session_id directly
            # Session management might be handled differently in the SDK
            # For now, we'll skip passing session_id to avoid errors
            # The session_id is still logged in traces for tracking
            # if session_id:
            #     params["session_id"] = session_id  # Not supported by SDK
            
            # Use SDK client with context manager
            # Note: SDK may be synchronous, so we run it in executor for async compatibility
            # Create a new client instance for each call to avoid thread-safety issues
            import asyncio
            loop = asyncio.get_event_loop()
            api_key = self.api_key  # Capture API key for use in executor
            
            def _call_sdk():
                # Create a new client instance for each call
                # This avoids issues with reusing the client across threads/executors
                client = OpenRouter(api_key=api_key)
                with client as open_router:
                    res = open_router.chat.send(**params)
                    
                    # Handle streaming vs non-streaming responses
                    # According to OpenRouter SDK docs:
                    # - For streaming (stream=True), res is a context manager (EventStream)
                    # - For non-streaming (stream=False), res is a ChatResponse object directly
                    is_streaming = params.get("stream", False)
                    
                    if is_streaming:
                        # Streaming response - use context manager
                        with res as event_stream:
                            # Collect all events
                            events = list(event_stream)
                            
                            if not events:
                                return None
                            
                            # Use the last event (complete response)
                            event = events[-1]
                            return _extract_response_data(event, model)
                    else:
                        # Non-streaming response - access ChatResponse directly
                        # res is a ChatResponse object with choices, model, usage, etc.
                        return _extract_response_data(res, model)
            
            def _extract_response_data(response_obj, model_name: str) -> Optional[Dict[str, Any]]:
                """Extract data from ChatResponse object (streaming or non-streaming)."""
                # Handle object-based response format (ChatResponse)
                if hasattr(response_obj, 'choices') and response_obj.choices:
                    choice = response_obj.choices[0]
                    message = choice.message if hasattr(choice, 'message') else getattr(choice, 'message', {})
                    
                    # Debug: Log message structure
                    logger.debug(f"🔧 Message type: {type(message)}, has tool_calls attr: {hasattr(message, 'tool_calls')}")
                    if hasattr(message, '__dict__'):
                        logger.debug(f"🔧 Message attributes: {list(message.__dict__.keys())}")
                    
                    # Extract content
                    if hasattr(message, 'content'):
                        content = message.content or ''
                    elif isinstance(message, dict):
                        content = message.get('content', '')
                    else:
                        content = str(message) if message else ''
                    
                    # Extract usage and convert to dict if it's an object
                    usage_obj = getattr(response_obj, 'usage', None) if hasattr(response_obj, 'usage') else None
                    usage_dict = {}
                    if usage_obj:
                        if isinstance(usage_obj, dict):
                            usage_dict = usage_obj
                        else:
                            # Convert object to dict (ChatGenerationTokenUsage)
                            usage_dict = {
                                'prompt_tokens': getattr(usage_obj, 'prompt_tokens', None),
                                'completion_tokens': getattr(usage_obj, 'completion_tokens', None),
                                'total_tokens': getattr(usage_obj, 'total_tokens', None),
                            }
                    
                    # Build result dict
                    result: Dict[str, Any] = {
                        'content': content,
                        'model': getattr(response_obj, 'model', None) or model_name,
                        'usage': usage_dict,
                        'finish_reason': getattr(choice, 'finish_reason', None),
                    }
                    
                    # Include tool_calls if present - try multiple extraction methods
                    tool_calls_extracted = None
                    
                    # Method 1: Check if message has tool_calls attribute
                    if hasattr(message, 'tool_calls') and message.tool_calls:
                        tool_calls_raw = message.tool_calls
                        logger.debug(f"🔧 Found tool_calls attribute: {type(tool_calls_raw)}, length: {len(tool_calls_raw) if tool_calls_raw else 0}")
                        
                        # Convert Pydantic models to dicts if needed
                        if tool_calls_raw:
                            tool_calls_extracted = []
                            for tc in tool_calls_raw:
                                if isinstance(tc, dict):
                                    tool_calls_extracted.append(tc)
                                elif hasattr(tc, 'model_dump'):
                                    # Pydantic v2
                                    tool_calls_extracted.append(tc.model_dump())
                                elif hasattr(tc, 'dict'):
                                    # Pydantic v1
                                    tool_calls_extracted.append(tc.dict())
                                elif hasattr(tc, '__dict__'):
                                    # Convert to dict manually
                                    tc_dict = {}
                                    if hasattr(tc, 'id'):
                                        tc_dict['id'] = getattr(tc, 'id')
                                    if hasattr(tc, 'function'):
                                        func = getattr(tc, 'function')
                                        if hasattr(func, 'name'):
                                            tc_dict['function'] = {
                                                'name': getattr(func, 'name'),
                                                'arguments': getattr(func, 'arguments', ''),
                                            }
                                        elif isinstance(func, dict):
                                            tc_dict['function'] = func
                                    tool_calls_extracted.append(tc_dict)
                                else:
                                    logger.warning(f"🔧 Unknown tool_call format: {type(tc)}")
                            
                            logger.debug(f"🔧 Extracted {len(tool_calls_extracted)} tool call(s) from response (object format)")
                    
                    # Method 2: Check if message is a dict with tool_calls
                    elif isinstance(message, dict) and message.get('tool_calls'):
                        tool_calls_extracted = message['tool_calls']
                        logger.debug(f"🔧 Extracted {len(tool_calls_extracted)} tool call(s) from response (dict format)")
                    
                    # Method 3: Check choice directly
                    elif hasattr(choice, 'message') and isinstance(choice.message, dict) and choice.message.get('tool_calls'):
                        tool_calls_extracted = choice.message['tool_calls']
                        logger.debug(f"🔧 Extracted {len(tool_calls_extracted)} tool call(s) from choice.message (dict format)")
                    
                    else:
                        logger.debug("🔧 No tool_calls found in response - checking finish_reason")
                        finish_reason = getattr(choice, 'finish_reason', None)
                        logger.debug(f"🔧 Finish reason: {finish_reason}")
                    
                    if tool_calls_extracted:
                        result['tool_calls'] = tool_calls_extracted
                        # Log tool names being called
                        tool_names = []
                        for tc in tool_calls_extracted:
                            if isinstance(tc, dict):
                                func = tc.get('function', {})
                                if isinstance(func, dict):
                                    tool_names.append(func.get('name', 'unknown'))
                                elif hasattr(func, 'name'):
                                    tool_names.append(getattr(func, 'name', 'unknown'))
                            elif hasattr(tc, 'function'):
                                func = getattr(tc, 'function')
                                if hasattr(func, 'name'):
                                    tool_names.append(getattr(func, 'name', 'unknown'))
                        logger.info(f"🔧 LLM requested tool calls: {', '.join(tool_names)}")
                    else:
                        logger.debug("🔧 No tool_calls extracted from response")
                    
                    return result
                
                # Handle dict-based response format (fallback)
                if isinstance(response_obj, dict):
                    if response_obj.get('choices') and len(response_obj['choices']) > 0:
                        choice = response_obj['choices'][0]
                        message = choice.get('message', {})
                        content = message.get('content', '')
                        
                        # Extract usage and ensure it's a dict
                        usage_obj = response_obj.get('usage', {})
                        if usage_obj and not isinstance(usage_obj, dict):
                            # Convert object to dict if needed
                            usage_obj = {
                                'prompt_tokens': getattr(usage_obj, 'prompt_tokens', None),
                                'completion_tokens': getattr(usage_obj, 'completion_tokens', None),
                                'total_tokens': getattr(usage_obj, 'total_tokens', None),
                            } if hasattr(usage_obj, '__dict__') else {}
                        
                        result = {
                            'content': content,
                            'model': response_obj.get('model', model_name),
                            'usage': usage_obj if isinstance(usage_obj, dict) else {},
                            'finish_reason': choice.get('finish_reason'),
                        }
                        
                        if message.get('tool_calls'):
                            tool_calls_extracted = message['tool_calls']
                            result['tool_calls'] = tool_calls_extracted
                            logger.debug(f"🔧 Extracted {len(tool_calls_extracted)} tool call(s) from response (fallback dict format)")
                            # Log tool names
                            tool_names = [tc.get('function', {}).get('name', 'unknown') for tc in tool_calls_extracted if isinstance(tc, dict)]
                            if tool_names:
                                logger.info(f"🔧 LLM requested tool calls: {', '.join(tool_names)}")
                        else:
                            logger.debug("🔧 No tool_calls found in response (fallback dict format)")
                        
                        return result
                
                return None
            
            # Run SDK call in executor to avoid blocking
            result = await loop.run_in_executor(None, _call_sdk)
            
            if not result:
                logger.error("No valid response from OpenRouter SDK")
                return None
            
            # Parse JSON if json_mode enabled
            if json_mode and result.get('content'):
                try:
                    # Sanitize JSON string to fix invalid escape sequences
                    sanitized_content = self._sanitize_json_string(result['content'])
                    result['parsed'] = json.loads(sanitized_content)
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse JSON: {e}")
                    logger.debug(f"Original content preview: {result['content'][:200]}")
                    # Try one more time with more aggressive sanitization
                    try:
                        # Remove markdown code blocks if present
                        content = result['content']
                        if "```json" in content:
                            start = content.find("```json") + 7
                            end = content.find("```", start)
                            content = content[start:end].strip()
                        elif "```" in content:
                            start = content.find("```") + 3
                            end = content.find("```", start)
                            content = content[start:end].strip()
                        
                        # Extract JSON object if wrapped in text
                        if "{" in content and "}" in content:
                            start = content.find("{")
                            end = content.rfind("}") + 1
                            content = content[start:end]
                        
                        sanitized_content = self._sanitize_json_string(content)
                        result['parsed'] = json.loads(sanitized_content)
                        logger.info("✅ Successfully parsed JSON after sanitization")
                    except json.JSONDecodeError as e2:
                        logger.error(f"Failed to parse JSON after sanitization: {e2}")
                        result['parsed'] = None
            
            # Auto-log this LLM call if enabled and context provided
            if auto_log and db and agent_name:
                try:
                    import time
                    start_time = time.time()
                    
                    # Extract tool calls if present
                    tool_calls = result.get('tool_calls')
                    
                    # Build parameters dict
                    params_dict = {
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                        "thinking_budget": thinking_budget,
                        "json_mode": json_mode,
                        "search_web": search_web,
                        "use_lite_model": use_lite_model,
                        "tool_choice": tool_choice,
                        "has_tools": bool(tools),
                        "tool_count": len(tools) if tools else 0,
                    }
                    
                    # Convert usage to dict if it's an object (ChatGenerationTokenUsage)
                    usage_data = result.get('usage')
                    if usage_data and not isinstance(usage_data, dict):
                        # Convert object to dict
                        if hasattr(usage_data, '__dict__'):
                            usage_data = {
                                'prompt_tokens': getattr(usage_data, 'prompt_tokens', None),
                                'completion_tokens': getattr(usage_data, 'completion_tokens', None),
                                'total_tokens': getattr(usage_data, 'total_tokens', None),
                            }
                        else:
                            # Try to convert using asdict or similar
                            try:
                                # Use module-level json import
                                usage_data = json.loads(json.dumps(usage_data, default=str))
                            except:
                                usage_data = {}
                    
                    # Store trace
                    trace_id = await store_llm_trace(
                        db=db,
                        user_id=user_id,
                        mood_id=mood_id,
                        session_id=session_id,
                        agent_name=agent_name,
                        prompt="",  # Will use messages instead
                        response=result.get('content', ''),
                        model=result.get('model', model),
                        thinking_budget=thinking_budget,
                        messages=messages,
                        parameters=params_dict,
                        tool_calls=tool_calls,
                        usage=usage_data,
                    )
                    
                    execution_time = (time.time() - start_time) * 1000
                    logger.debug(f"📊 Logged LLM call: {agent_name} (trace_id={trace_id}, {execution_time:.1f}ms)")
                except Exception as e:
                    logger.warning(f"Failed to auto-log LLM call: {e}")
            
            return result
        
        except Exception as e:
            logger.error(f"OpenRouter API error: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return None
    
    async def generate_intro_speech(
        self,
        mood_name: str,
        user_name: Optional[str],
        personality: str,
        first_song_artist: Optional[str],
        first_song_title: Optional[str],
    ) -> Optional[str]:
        """Generate intro speech script."""
        system_prompt = f"""You are a professional Radio DJ with a {personality} personality.
Your goal is to welcome the listener and introduce the first track.
Keep it brief (under 15 seconds speaking time).
Do not include [Sound Effects] or other stage directions.
Just the spoken words."""
        
        user_prompt = f"Mood: {mood_name}\\n"
        if user_name:
            user_prompt += f"Listener: {user_name}\\n"
        if first_song_artist and first_song_title:
            user_prompt += f"First Track: {first_song_title} by {first_song_artist}\\n"
            
        user_prompt += "\\nWrite a short intro script."
        
        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
            
            response = await self.chat_completion(
                messages=messages,
                temperature=0.7,
                max_tokens=150,
            )
            
            if response and response.get("content"):
                return response["content"]
            
        except Exception as e:
            logger.error(f"Intro generation failed: {e}")
            
        return None

    async def generate_transition_speech(
        self,
        song_a_artist: Optional[str],
        song_a_title: Optional[str],
        song_b_artist: Optional[str],
        song_b_title: Optional[str],
        transition_type: str,
        personality: str,
        persona_addendum: str = "",
    ) -> Optional[str]:
        """Generate transition speech script."""
        system_prompt = f"""You are a professional Radio DJ with a {personality} personality.
Your goal is to bridge the gap between two songs with a short voiceover.
Keep it brief (under 10 seconds).
Do not include [Sound Effects].
Just the spoken words.
{persona_addendum}"""

        user_prompt = f"""Incoming Track: {song_b_title} by {song_b_artist}
Outgoing Track: {song_a_title} by {song_a_artist}
Transition: {transition_type}

Write a short transition script/hook."""

        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
            
            response = await self.chat_completion(
                messages=messages,
                temperature=0.7,
                max_tokens=100,
            )
            
            if response and response.get("content"):
                return response["content"]
                
        except Exception as e:
            logger.error(f"Transition speech generation failed: {e}")
            
        return None

    async def generate_transition_plan(
        self,
        song_a: Dict[str, Any],
        song_b: Dict[str, Any],
        recent_transition_types: List[str] = None,
        bundle: Optional["PreferenceBundle"] = None,
    ) -> Optional[Dict[str, Any]]:
        """Generate transition plan between two songs."""
        # Build profile context if bundle available
        profile_context = ""
        if bundle:
            # We can use the standalone function defined in this module
            try:
                profile_context = build_profile_context(bundle)
            except Exception:
                pass

        system_prompt = """You are an expert audio engineer and DJ.
Your task is to plan the perfect transition between two tracks.
Analyze the BPM, energy, and genre to decide the best mix technique.

Available Transition Types:
- crossfade: Standard smooth blend
- quick_cut: Immediate switch (good for high energy or tempo mismatch)
- vinyl_stop: Gradual slow down of outgoing track
- bass_swap: Swap basslines (good for house/techno)
- loop_mix: Loop outgoing beat while bringing in incoming
- drop_mix: Build up A, drop into B
- filter_sweep: Low/High pass filter sweep
- eq_blend: Gradual EQ frequency swap

Output JSON:
{
    "transition_type": "crossfade",
    "transition_duration_seconds": 8.0,
    "start_position_a_seconds": 180.0,  # Where to start transition in Song A (relative to start)
    "start_position_b_seconds": 0.0,    # Where to start Song B
    "mix_length_bars": 16,
    "rationale": "Explanation..."
}"""

        user_prompt = f"""Song A (Outgoing):
Title: {song_a.get('title')}
Artist: {song_a.get('artist')}
BPM: {song_a.get('bpm', 'Unknown')}
Energy: {song_a.get('energy', 'Unknown')}
Duration: {song_a.get('duration_sec', '180')}s

Song B (Incoming):
Title: {song_b.get('title')}
Artist: {song_b.get('artist')}
BPM: {song_b.get('bpm', 'Unknown')}
Energy: {song_b.get('energy', 'Unknown')}

{profile_context}

Recommend the best transition."""

        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
            
            response = await self.chat_completion(
                messages=messages,
                temperature=0.4,
                json_mode=True,
            )
            
            if response and response.get("parsed"):
                return response["parsed"]
                
        except Exception as e:
            logger.error(f"Transition planning failed: {e}")
            
        return None

    async def estimate_song_features(
        self,
        artist: str,
        title: str,
        genres: List[str]
    ) -> Optional[Dict[str, float]]:
        """Estimate audio features (energy, valence) using LLM knowledge."""
        system_prompt = """You are an audio analysis expert.
Estimate the audio features for the given song on a scale of 0.0 to 1.0.

Features:
- Energy: Intensity and activity (0.0=calm, 1.0=intense)
- Valence: Musical positiveness (0.0=sad/depressed, 1.0=happy/euphoric)
- Danceability: Suitability for dancing (0.0=concerto, 1.0=club banger)
- Acousticness: 1.0 = purely acoustic, 0.0 = electronic/amplified

Also estimate Tempo (BPM).

Respond with JSON only:
{
  "energy": 0.8,
  "valence": 0.5,
  "danceability": 0.7,
  "acousticness": 0.1,
  "tempo": 120
}"""

        user_prompt = f"Song: {title} by {artist}\nGenres: {', '.join(genres)}"
        
        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
            response = await self.chat_completion(
                messages=messages,
                temperature=0.1,
                json_mode=True,
                session_id=None,  # Standalone call, no session context needed
            )

            if not response:
                return None

            if response.get("parsed"):
                data = response["parsed"]
                return {
                    "energy": float(data.get("energy", 0.5)),
                    "valence": float(data.get("valence", 0.5)),
                    "danceability": float(data.get("danceability", 0.5)),
                    "acousticness": float(data.get("acousticness", 0.5)),
                    "tempo": float(data.get("tempo", 120)),
                }

            content = response.get("content", "")
            if content:
                import re
                # Use module-level json import

                match = re.search(r"\{.*\}", content, re.DOTALL)
                if match:
                    data = json.loads(match.group(0))
                    return {
                        "energy": float(data.get("energy", 0.5)),
                        "valence": float(data.get("valence", 0.5)),
                        "danceability": float(data.get("danceability", 0.5)),
                        "acousticness": float(data.get("acousticness", 0.5)),
                        "tempo": float(data.get("tempo", 120)),
                    }
        except Exception as e:
            logger.error(f"Feature estimation failed: {e}")

        return None

    async def generate_song_suggestion(
        self,
        bundle: "PreferenceBundle",
        prev_song: Optional[Dict[str, Any]] = None,
        # Logging parameters
        db: Optional["AsyncSession"] = None,
        agent_name: Optional[str] = "track_selector",
        auto_log: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """Generate a song suggestion to acquire (when library is insufficient).
        
        Args:
            bundle: User's preference bundle
            prev_song: Previous song context
            
        Returns:
            Dict with artist, title, rationale
        """
        # Get agent settings
        thinking_budget = bundle.get_agent_setting(
            "track_selector", "thinking_budget", THINKING_BUDGET_TRACK
        )
        temperature = bundle.get_agent_setting(
            "track_selector", "temperature", 0.9  # Higher temp for creative suggestions
        )
        
        # Build profile context from structured onboarding data
        profile_context = build_profile_context(bundle)
        
        # Build history + feedback context
        # INCREASED from 5 to 15 to prevent AI from suggesting recently played songs
        recent_tracks = [
            f"{h.artist} - {h.title}"
            for h in bundle.history.recent_tracks[:15]  # Increased for better variety
            if h.artist and h.title
        ]
        recent_artists = [a for a in bundle.history.recent_artists[:15] if a]  # Increased for variety

        likes_section = ""
        if bundle.feedback.recent_likes[:3]:
            likes_examples = "\n".join([
                f"- {l.artist} - {l.title}" + (f" ({l.reason})" if l.reason else "")
                for l in bundle.feedback.recent_likes[:3]
                if l.artist and l.title
            ])
            if likes_examples:
                likes_section = f"USER LIKES (lean toward these vibes):\n{likes_examples}\n"

        dislikes_section = ""
        if bundle.feedback.recent_dislikes[:3]:
            dislikes_examples = "\n".join([
                f"- {d.artist} - {d.title}" + (f" ({d.reason})" if d.reason else "")
                for d in bundle.feedback.recent_dislikes[:3]
                if d.artist and d.title
            ])
            if dislikes_examples:
                dislikes_section = f"USER DISLIKES (avoid these and similar):\n{dislikes_examples}\n"

        history_section = ""
        if recent_tracks:
            history_section = f"RECENTLY PLAYED (DO NOT SUGGEST THESE OR SIMILAR SONGS BY SAME ARTIST):\n- " + "\n- ".join(recent_tracks) + "\n"

        recent_artists_section = ""
        if recent_artists:
            recent_artists_section = f"RECENT ARTISTS (prefer variety):\n- " + "\n- ".join(recent_artists) + "\n"
        
        # Log the context being used
        logger.info(
            f"Song suggestion using profile: {profile_context[:100]}... "
            f"History tracks: {len(recent_tracks)}, artists: {len(recent_artists)}"
        )
        
        system_prompt = f"""You are an expert DJ building a setlist.

Target Mood: {bundle.mood.name} (Energy: {bundle.mood.energy_target:.1f}, Valence: {bundle.mood.valence_target:.1f})
Genres: {', '.join(bundle.mood.genres)}

{profile_context}
{likes_section}{dislikes_section}{history_section}{recent_artists_section}
Suggest ONE real song that fits this vibe perfectly.
It can be a classic hit, a deep cut, or a new release.
You are NOT restricted to any library. Pick the best song in the world for this moment.
Prefer a fresh, adventurous pick (deep cut, emerging artist, or adjacent-genre gem) over obvious staples unless the user's likes indicate otherwise.

Respond with JSON:
{{
  "artist": "Artist Name",
  "title": "Song Title",
  "rationale": "Reason for choice"
}}"""

        prev_section = ""
        if prev_song:
            prev_section = f"Previous Song: {prev_song.get('artist')} - {prev_song.get('title')}\n"
            
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"{prev_section}Suggest the perfect next track to download."}
        ]
        
        result = await self.chat_completion(
            messages=messages,
            temperature=temperature,
            thinking_budget=thinking_budget,
            json_mode=True,
            search_web=True, # Allow web search to verify song exists
            session_id=bundle.session_id,
            db=db,
            user_id=bundle.user_id,
            mood_id=bundle.mood.id if bundle.mood else None,
            agent_name=agent_name,
            auto_log=auto_log,
        )
        
        if result and result.get('parsed'):
            parsed = result['parsed']
            if parsed.get('artist') and parsed.get('title'):
                return parsed
        
        return None

    async def generate_catalog_selection(
        self,
        bundle: "PreferenceBundle",
        candidates: List[Dict[str, Any]],
        prev_song: Optional[Dict[str, Any]] = None,
        recent_artists: Optional[List[str]] = None,
        # Logging parameters
        db: Optional["AsyncSession"] = None,
        agent_name: Optional[str] = "catalog_selector",
        auto_log: bool = True,
        # Tool calling
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Generate track selection from catalog candidates - AI DJ makes the creative choice!
        
        This is where the AI DJ personality shines. The catalog gives us diverse options,
        but the AI decides which one will create the best musical journey.
        
        Args:
            bundle: User's preference bundle
            candidates: Catalog tracks with scores (pre-filtered for diversity)
            prev_song: Previous song for flow context
            recent_artists: Recently played artists (for variety)
            
        Returns:
            Dict with selected_index, rationale, or None
        """
        # Get agent settings
        thinking_budget = bundle.get_agent_setting(
            "track_selector", "thinking_budget", THINKING_BUDGET_TRACK
        )
        temperature = bundle.get_agent_setting(
            "track_selector", "temperature", 0.85  # Higher temp for creative DJ choices
        )
        
        # Build personalization context
        profile_context = build_profile_context(bundle)
        
        # Feedback context
        likes_section = ""
        if bundle.feedback.recent_likes[:3]:
            likes_examples = "\n".join([
                f"- {l.artist} - {l.title}"
                for l in bundle.feedback.recent_likes[:3]
                if l.artist and l.title
            ])
            if likes_examples:
                likes_section = f"\nUSER LOVES (lean toward these vibes):\n{likes_examples}\n"
        
        dislikes_section = ""
        if bundle.feedback.recent_dislikes[:5]:  # Show more dislikes
            dislikes_examples = "\n".join([
                f"- {d.artist} - {d.title}"
                for d in bundle.feedback.recent_dislikes[:5]
                if d.artist and d.title
            ])
            if dislikes_examples:
                dislikes_section = f"\n⚠️ **HARD RULE - NEVER SELECT THESE TRACKS:**\n{dislikes_examples}\nThe user explicitly disliked these. Selecting any of them is a FAILURE.\n"
        
        # Recent artists context for variety (cooldown guidance)
        recent_artists_section = ""
        if recent_artists:
            cooldown_default = 3
            try:
                artist_cooldown = int(
                    bundle.get_agent_setting("track_selector", "artist_cooldown_tracks", cooldown_default)
                )
            except (TypeError, ValueError):
                artist_cooldown = cooldown_default
            artist_cooldown = max(0, artist_cooldown)
            recent_list = [a for a in recent_artists if a]
            cooldown_list = recent_list[:max(1, artist_cooldown)] if artist_cooldown else recent_list[:3]
            if cooldown_list:
                recent_artists_section = (
                    "\n**AVOID RECENT ARTISTS (cooldown):**\n- "
                    + "\n- ".join(cooldown_list)
                    + "\nDo NOT pick these unless there are no strong alternatives.\n"
                )
        
        # Previous song context
        prev_section = ""
        if prev_song:
            prev_features = prev_song.get("features") or {}
            prev_section = f"""
PREVIOUS TRACK (just played):
- Artist: {prev_song.get('artist', 'Unknown')}
- Title: {prev_song.get('title', 'Unknown')}
- Energy: {prev_features.get('energy', 'N/A')}
- Tempo: {prev_features.get('tempo', 'N/A')} BPM

"""
        
        system_prompt = f"""You are an expert AI DJ curating the perfect music journey for your listener.

YOUR ROLE:
- You're not just matching mood - you're creating a JOURNEY
- Be adventurous! Deep cuts, emerging artists, and hidden gems are ENCOURAGED
- Balance familiarity with discovery
- Think like a real DJ: flow, energy, surprise, delight

TARGET MOOD: {bundle.mood.name}
- Energy: {bundle.mood.energy_target:.1f} (0=calm, 1=energetic)
- Vibe: {bundle.mood.valence_target:.1f} (0=melancholic, 1=euphoric)
- Genres: {', '.join(bundle.mood.genres)}

{profile_context}
{likes_section}{dislikes_section}{recent_artists_section}

SELECTION PHILOSOPHY (in priority order):
1. **Musical Flow** - Does this track flow naturally from the previous one?
2. **User Taste** - Match their vibe and preferences.
3. **Variety** - Prefer different artists when possible, but don't avoid great tracks just for variety.
4. **Discovery** - Introduce artists the user hasn't heard, balanced with familiar favorites.
5. **Energy Arc** - Are we building, sustaining, or bringing it down intentionally?
6. **Song Selection** - Avoid exact duplicates from the current session, but covers/remixes are fine.

ENCOURAGED BEHAVIORS:
- Pick different artists when possible for variety
- Pick deep cuts and emerging artists over obvious hits
- Create a natural musical flow
- Surprise the listener with excellence from unexpected sources

The candidates are PRE-SCORED for basic fit. Your job is to pick the BEST track considering flow, taste, and variety."""

        # Format candidates compactly (using module-level json import)
        candidates_text = json.dumps(candidates, separators=(',', ':'))
        
        user_prompt = f"""{prev_section}
AVAILABLE TRACKS (all are good fits - you decide which is BEST):
{candidates_text}

Select the track that will create the best musical moment right now.
Consider flow, variety, adventure, and user taste.

Respond with JSON:
{{
  "selected_index": 3,
  "rationale": "Why this track creates the perfect moment"
}}"""
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        
        # Handle tool calling loop if tools are provided
        max_tool_iterations = 5
        iteration = 0
        
        while iteration < max_tool_iterations:
            result = await self.chat_completion(
                messages=messages,
                temperature=temperature,
                thinking_budget=thinking_budget,
                json_mode=True,
                session_id=bundle.session_id,
                db=db,
                user_id=bundle.user_id,
                mood_id=bundle.mood.id if bundle.mood else None,
                agent_name=agent_name,
                auto_log=auto_log,
                tools=tools if iteration == 0 else None,  # Only pass tools on first call
                tool_choice="auto" if tools else None,
            )
            
            if not result:
                break
            
            # Check if LLM wants to call tools
            tool_calls = result.get('tool_calls')
            if not tool_calls or result.get('finish_reason') == 'stop':
                # No more tool calls, validate and return
                if result.get('parsed'):
                    parsed = result['parsed']
                    selected_index = parsed.get('selected_index')
                    if isinstance(selected_index, int) and selected_index >= 1:
                        return result
                    else:
                        logger.warning(f"Invalid catalog selection response: {parsed}")
                return result
            
            # Execute tool calls and add results to conversation
            from backend_v2.integrations.db_tools import execute_tool
            
            # Add assistant message with tool calls
            assistant_message = {
                "role": "assistant",
                "content": result.get('content', ''),
                "tool_calls": tool_calls,
            }
            messages.append(assistant_message)
            
            # Execute each tool call
            for tool_call in tool_calls:
                tool_name = tool_call['function']['name']
                tool_args = json_lib.loads(tool_call['function']['arguments'])
                tool_id = tool_call['id']
                
                if tool_name in history_tools:
                    history_tool_called = True

                logger.info(f"🔧 LLM calling tool: {tool_name} with args: {tool_args}")
                
                try:
                    tool_result = await execute_tool(
                        tool_name,
                        tool_args,
                        db,
                        session_id=bundle.session_id,
                        user_id=bundle.user_id,
                        mood_id=bundle.mood.id if bundle.mood else None,
                        agent_name=agent_name,
                        auto_log=True,
                    )
                    result_str = json_lib.dumps(tool_result, default=str)
                    
                    # Add tool result to conversation
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_id,
                        "name": tool_name,
                        "content": result_str,
                    })
                    
                    logger.info(f"✅ Tool {tool_name} result: {result_str[:200]}")
                except Exception as e:
                    logger.error(f"❌ Tool execution failed: {e}")
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_id,
                        "name": tool_name,
                        "content": json_lib.dumps({"error": str(e)}),
                    })
            
            iteration += 1
        
        if iteration >= max_tool_iterations:
            logger.warning(f"Reached max tool iterations ({max_tool_iterations}), using final result")
        
        return result
    
    async def generate_track_selection_with_search(
        self,
        bundle: "PreferenceBundle",
        prev_song: Optional[Dict[str, Any]] = None,
        excluded_titles: Optional[Set[str]] = None,
        excluded_normalized_titles: Optional[Set[str]] = None,
        recent_artists: Optional[List[str]] = None,
        excluded_artists: Optional[List[str]] = None,
        # Logging parameters
        db: Optional["AsyncSession"] = None,
        agent_name: Optional[str] = "catalog_selector",
        auto_log: bool = True,
        # Tool calling
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Generate track selection by letting LLM search Spotify and select.
        
        Unlike generate_catalog_selection, this method doesn't receive pre-searched
        candidates. Instead, the LLM uses tools to search Spotify and selects from
        the search results.
        
        Args:
            bundle: User's preference bundle
            prev_song: Previous song for transition context
            excluded_titles: Set of track titles to exclude (already played)
            excluded_normalized_titles: Set of normalized titles to exclude
            recent_artists: List of recently played artists (for variety)
            excluded_artists: List of artist names to avoid for this selection
            db: Database session for logging
            agent_name: Agent name for logging
            auto_log: Whether to auto-log this call
            tools: List of tools to pass to LLM (should include search_spotify_catalog)
            
        Returns:
            Dict with artist, title, rationale, or None
        """
        # Get agent settings
        thinking_budget = bundle.get_agent_setting(
            "track_selector", "thinking_budget", THINKING_BUDGET_TRACK
        )
        temperature = bundle.get_agent_setting(
            "track_selector", "temperature", 0.85  # Higher temp for creative DJ choices
        )
        
        # Build personalization context
        profile_context = build_profile_context(bundle)
        
        # Feedback context
        likes_section = ""
        if bundle.feedback.recent_likes[:3]:
            likes_examples = "\n".join([
                f"- {l.artist} - {l.title}"
                for l in bundle.feedback.recent_likes[:3]
                if l.artist and l.title
            ])
            if likes_examples:
                likes_section = f"\nUSER LOVES (lean toward these vibes):\n{likes_examples}\n"
        
        dislikes_section = ""
        if bundle.feedback.recent_dislikes[:5]:
            dislikes_examples = "\n".join([
                f"- {d.artist} - {d.title}"
                for d in bundle.feedback.recent_dislikes[:5]
                if d.artist and d.title
            ])
            if dislikes_examples:
                dislikes_section = f"\n⚠️ **HARD RULE - NEVER SELECT THESE TRACKS:**\n{dislikes_examples}\nThe user explicitly disliked these. Selecting any of them is a FAILURE.\n"
        
        excluded_artists_section = ""
        if excluded_artists:
            deduped = []
            seen = set()
            for artist in excluded_artists:
                if not artist:
                    continue
                normalized = artist.strip().lower()
                if not normalized or normalized in seen:
                    continue
                seen.add(normalized)
                deduped.append(artist.strip())
            if deduped:
                display_limit = min(12, len(deduped))
                formatted = deduped[:display_limit]
                excluded_artists_section = (
                    "\n**HARD RULE - DO NOT SELECT THESE ARTISTS:**\n- "
                    + "\n- ".join(formatted)
                    + "\n"
                )
                if len(deduped) > display_limit:
                    excluded_artists_section += f"(+{len(deduped) - display_limit} more excluded artists)\n"

        # Recent artists context for variety (softened)
        recent_artists_section = ""
        if recent_artists:
            recent_artists_section = (
                f"\n**For variety, consider different artists:**\n- "
                + "\n- ".join(recent_artists[:5])
                + "\nThese artists were recently played. Prefer variety when possible, but don't avoid them if they're the perfect fit.\n"
            )
        
        # Exclusion context (informational only)
        excluded_section = ""
        if excluded_titles:
            excluded_count = len(excluded_titles)
            display_limit = min(30, excluded_count)
            formatted = []
            for item in sorted(excluded_titles)[:display_limit]:
                if "|" in item:
                    artist, title = item.split("|", 1)
                    formatted.append(f"{artist.strip()} - {title.strip()}")
                else:
                    formatted.append(item.strip())
            excluded_section = (
                "\n**HARD RULE - DO NOT SELECT THESE TRACKS:**\n- "
                + "\n- ".join(formatted)
                + "\n"
            )
            if excluded_count > display_limit:
                excluded_section += f"(+{excluded_count - display_limit} more excluded tracks)\n"
        
        # Previous song context
        prev_section = ""
        if prev_song:
            prev_features = prev_song.get("features") or {}
            prev_section = f"""
PREVIOUS TRACK (just played):
- Artist: {prev_song.get('artist', 'Unknown')}
- Title: {prev_song.get('title', 'Unknown')}
- Energy: {prev_features.get('energy', 'N/A')}
- Tempo: {prev_features.get('tempo', 'N/A')} BPM

"""
        
        system_prompt = f"""You are an expert AI DJ curating the perfect music journey for your listener.

YOUR ROLE:
- You're not just matching mood - you're creating a JOURNEY
- Be adventurous! Deep cuts, emerging artists, and hidden gems are ENCOURAGED
- Balance familiarity with discovery
- Think like a real DJ: flow, energy, surprise, delight

TARGET MOOD: {bundle.mood.name}
- Energy: {bundle.mood.energy_target:.1f} (0=calm, 1=energetic)
- Vibe: {bundle.mood.valence_target:.1f} (0=melancholic, 1=euphoric)
- Genres: {', '.join(bundle.mood.genres)}

{profile_context}
{likes_section}{dislikes_section}{excluded_artists_section}{recent_artists_section}{excluded_section}

SELECTION PHILOSOPHY (in priority order):
1. **Musical Flow** - Does this track flow naturally from the previous one?
2. **User Taste** - Match their vibe and preferences.
3. **Variety** - Prefer different artists when possible, but don't avoid great tracks just for variety.
4. **Discovery** - Introduce artists the user hasn't heard, balanced with familiar favorites.
5. **Energy Arc** - Are we building, sustaining, or bringing it down intentionally?
6. **Song Selection** - Avoid exact duplicates from the current session, but covers/remixes are fine.

HOW TO SEARCH (YOU MUST USE TOOLS):
**STEP 0: CHECK HISTORY** - Call get_play_history to review recent plays before searching.
- Use USER_ID from context with limit 20 (optional MOOD_ID) to avoid repeats
- If an artist looks overplayed, you can call get_artist_play_count
**STEP 1: SEARCH FIRST** - You MUST use the search_spotify_catalog tool to find tracks. Do NOT respond with a selection yet.
- Call search_spotify_catalog multiple times with different queries (artists, genres, song titles)
- Search for artists from the mood's example artists, user's favorite artists, or genres
- Collect at least 10-20 tracks before selecting
- You can search by artist name using the "artist" parameter, or by genre/query using the "query" parameter

**STEP 2: SELECT AFTER SEARCHING** - Only after you have collected search results, select the BEST track from all results
- Consider variety when selecting, but prioritize musical fit
- Respond with JSON only after you have search results

ENCOURAGED BEHAVIORS:
- Pick different artists when possible for variety
- Pick deep cuts and emerging artists over obvious hits
- Create a natural musical flow
- Surprise the listener with excellence from unexpected sources

**IMPORTANT**: You MUST call search_spotify_catalog tool(s) FIRST before selecting a track. Do not respond with JSON until you have search results.

After searching and collecting results, select the BEST track and respond with JSON:
{{
  "artist": "Artist Name",
  "title": "Song Title",
  "rationale": "Why this track creates the perfect moment"
}}"""
        
        user_prompt = f"""{prev_section}
**TASK**: Search Spotify for tracks matching the mood "{bundle.mood.name}" and select the best one.

**ACTION REQUIRED**: You MUST call get_play_history FIRST, then use search_spotify_catalog. Do not respond with a selection until you have search results.

**SEARCH STEPS**:
0. Call get_play_history first (USER_ID, limit 20, optional MOOD_ID) to avoid repeats
1. Search for tracks by artists from the mood's example artists (use artist parameter)
2. Search for tracks matching the mood's genres (use query parameter)
3. Search for tracks by the user's favorite artists if available (use artist parameter)
4. Make multiple searches to collect 10-20+ tracks total
5. After collecting results, select the BEST track considering variety, flow, and user taste

**SELECTION GUIDELINES**:
- Prefer variety in artists when possible, but don't avoid great tracks just for variety
- Avoid exact duplicates from the current session
- Match the mood's energy and vibe
- Create a natural musical flow

**REMEMBER**: Call search_spotify_catalog tool(s) FIRST, then respond with JSON after you have results:
{{
  "artist": "Artist Name",
  "title": "Song Title",
  "rationale": "Why this track creates the perfect moment"
}}"""
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        
        # Import json_lib at function level to avoid scoping issues
        import json as json_lib
        
        # Handle tool calling loop
        max_tool_iterations = 10  # Allow more iterations for search + selection
        iteration = 0
        all_search_results = []  # Accumulate search results across iterations
        tool_calls_required = bool(tools)
        tool_calls_made = False
        tool_retry_needed = False
        history_tool_called = False
        history_tool_retry_needed = False
        history_tools = {"get_play_history", "get_artist_play_count"}
        
        while iteration < max_tool_iterations:
            tools_to_pass = tools if (iteration == 0 or tool_retry_needed) else None
            if tool_retry_needed:
                tool_retry_needed = False
            if tools_to_pass:
                logger.info(f"🔧 Iteration {iteration + 1}: Passing {len(tools_to_pass)} tool(s) to LLM")
                tool_names = [t.get('function', {}).get('name', 'unknown') if isinstance(t, dict) else 'unknown' for t in tools_to_pass]
                logger.debug(f"🔧 Tool names: {', '.join(tool_names)}")
            else:
                logger.debug(f"🔧 Iteration {iteration + 1}: No tools (iteration > 0 or no tools provided)")
            
            # Only enable json_mode if we're not expecting tool calls
            # json_mode conflicts with tool calling, so disable it when tools are present
            # We want JSON mode for final selection, but not when tools are being called
            use_json_mode = not tools_to_pass  # Enable json_mode only after tools are done
            
            result = await self.chat_completion(
                messages=messages,
                temperature=temperature,
                thinking_budget=thinking_budget,
                json_mode=use_json_mode,
                session_id=bundle.session_id,
                db=db,
                user_id=bundle.user_id,
                mood_id=bundle.mood.id if bundle.mood else None,
                agent_name=agent_name,
                auto_log=auto_log,
                tools=tools_to_pass,
                tool_choice="auto" if tools_to_pass else None,
            )
            
            if not result:
                logger.warning(f"⚠️ No result returned from LLM on iteration {iteration + 1}")
                break
            
            # Check if LLM wants to call tools
            tool_calls = result.get('tool_calls')
            finish_reason = result.get('finish_reason')
            content = result.get('content', '')
            
            if tool_calls:
                tool_calls_made = True
            
            logger.debug(f"🔧 Iteration {iteration + 1}: tool_calls={bool(tool_calls)}, finish_reason={finish_reason}, content_length={len(content) if content else 0}, search_results={len(all_search_results)}")
            
            # If tools were expected but not called, log warning
            if tools_to_pass and not tool_calls and iteration == 0:
                logger.warning(f"⚠️ LLM did not call tools on first iteration despite {len(tools_to_pass)} tools being available")
                logger.warning(f"⚠️ Response content preview: {content[:300] if content else 'empty'}")
            
            if tools_to_pass and not tool_calls and iteration == 0 and tool_calls_required and not tool_calls_made:
                messages.append({
                    "role": "user",
                    "content": "You must call get_play_history and search_spotify_catalog at least once before selecting a track. "
                               "Call those tools now and then continue.",
                })
                tool_retry_needed = True
                history_tool_retry_needed = True
                iteration += 1
                continue

            if not tool_calls or finish_reason == 'stop':
                if tool_calls_required and not history_tool_called and not history_tool_retry_needed:
                    messages.append({
                        "role": "user",
                        "content": "Before selecting, call get_play_history to review recent plays "
                                   "(user_id, limit 20, optional mood_id), then continue searching.",
                    })
                    tool_retry_needed = True
                    history_tool_retry_needed = True
                    iteration += 1
                    continue
                # No more tool calls, check if we have a selection
                # If we have search results, prompt for final selection with json_mode
                if all_search_results and not tool_calls:
                    selection_prompt = f"""
  You have collected {len(all_search_results)} tracks from Spotify searches. 

Now select the BEST track from these results:
{json_lib.dumps(all_search_results[:50], indent=2)}

Consider variety, flow, and user taste. Respond with JSON:
{{
  "artist": "Artist Name",
  "title": "Song Title",
  "rationale": "Why this track creates the perfect moment"
}}"""
                    messages.append({"role": "user", "content": selection_prompt})
                    # Now enable json_mode for final selection
                    final_result = await self.chat_completion(
                        messages=messages,
                        temperature=temperature,
                        thinking_budget=thinking_budget,
                        json_mode=True,  # Enable json_mode for final selection
                        session_id=bundle.session_id,
                        db=db,
                        user_id=bundle.user_id,
                        mood_id=bundle.mood.id if bundle.mood else None,
                        agent_name=agent_name,
                        auto_log=auto_log,
                        tools=None,  # No tools for final selection
                    )
                    if final_result and final_result.get('parsed'):
                        parsed = final_result['parsed']
                        artist = parsed.get('artist')
                        title = parsed.get('title')
                        if artist and title:
                            return final_result
                
                # Try to parse JSON from content if json_mode wasn't used
                if result.get('content'):
                    try:
                        # Sanitize JSON string to fix invalid escape sequences
                        sanitized_content = self._sanitize_json_string(result['content'])
                        parsed = json_lib.loads(sanitized_content)
                        artist = parsed.get('artist')
                        title = parsed.get('title')
                        if artist and title:
                            logger.info(f"✅ Parsed selection from content: {artist} - {title}")
                            result['parsed'] = parsed
                            return result
                    except json_lib.JSONDecodeError as e:
                        logger.debug(f"⚠️ Failed to parse JSON from content: {e}")
                        logger.debug(f"⚠️ Content preview: {content[:200]}")
                        # Try one more time with more aggressive sanitization
                        try:
                            # Remove markdown code blocks if present
                            content_to_parse = result['content']
                            if "```json" in content_to_parse:
                                start = content_to_parse.find("```json") + 7
                                end = content_to_parse.find("```", start)
                                content_to_parse = content_to_parse[start:end].strip()
                            elif "```" in content_to_parse:
                                start = content_to_parse.find("```") + 3
                                end = content_to_parse.find("```", start)
                                content_to_parse = content_to_parse[start:end].strip()
                            
                            # Extract JSON object if wrapped in text
                            if "{" in content_to_parse and "}" in content_to_parse:
                                start = content_to_parse.find("{")
                                end = content_to_parse.rfind("}") + 1
                                content_to_parse = content_to_parse[start:end]
                            
                            sanitized_content = self._sanitize_json_string(content_to_parse)
                            parsed = json_lib.loads(sanitized_content)
                            artist = parsed.get('artist')
                            title = parsed.get('title')
                            if artist and title:
                                logger.info(f"✅ Parsed selection from content after sanitization: {artist} - {title}")
                                result['parsed'] = parsed
                                return result
                        except json_lib.JSONDecodeError as e2:
                            logger.debug(f"⚠️ Failed to parse JSON after sanitization: {e2}")
                
                # If we have no search results and no parsed selection, log warning
                if not all_search_results and not result.get('parsed'):
                    logger.warning(f"⚠️ Iteration {iteration + 1}: No tool calls, no search results, and no valid selection. Content: {content[:200] if content else 'empty'}")
                
                # Return result even if not parsed - caller will handle fallback
                return result
            
            # Execute tool calls and add results to conversation
            from backend_v2.integrations.db_tools import execute_tool
            
            # Add assistant message with tool calls
            assistant_message = {
                "role": "assistant",
                "content": result.get('content', ''),
                "tool_calls": tool_calls,
            }
            messages.append(assistant_message)
            
            # Execute each tool call
            for tool_call in tool_calls:
                tool_name = tool_call['function']['name']
                tool_args = json_lib.loads(tool_call['function']['arguments'])
                tool_id = tool_call['id']
                
                logger.info(f"🔧 LLM calling tool: {tool_name} with args: {tool_args}")
                
                try:
                    tool_result = await execute_tool(
                        tool_name,
                        tool_args,
                        db,
                        session_id=bundle.session_id,
                        user_id=bundle.user_id,
                        mood_id=bundle.mood.id if bundle.mood else None,
                        agent_name=agent_name,
                        auto_log=True,
                    )
                    
                    # Accumulate search results
                    if tool_name == "search_spotify_catalog" and isinstance(tool_result, list):
                        all_search_results.extend(tool_result)
                        logger.info(f"📊 Accumulated {len(all_search_results)} total search results")
                    
                    result_str = json_lib.dumps(tool_result, default=str)
                    
                    # Add tool result to conversation
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_id,
                        "name": tool_name,
                        "content": result_str,
                    })
                    
                    logger.info(f"✅ Tool {tool_name} result: {len(result_str)} chars")
                except Exception as e:
                    logger.error(f"❌ Tool execution failed: {e}")
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_id,
                        "name": tool_name,
                        "content": json_lib.dumps({"error": str(e)}),
                    })
            
            # Note: Selection prompt is handled above when no tool_calls are returned
            # Continue to next iteration to let LLM process tool results
            iteration += 1
        
        if iteration >= max_tool_iterations:
            logger.warning(f"Reached max tool iterations ({max_tool_iterations}), using final result")
        
        return result
    
    async def generate_track_selection(
        self,
        bundle: "PreferenceBundle",
        candidates: List[Dict[str, Any]],
        prev_song: Optional[Dict[str, Any]] = None,
        # Logging parameters
        db: Optional["AsyncSession"] = None,
        agent_name: Optional[str] = "track_selector",
        auto_log: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """Generate track selection using PreferenceBundle personalization.
        
        Args:
            bundle: User's preference bundle
            candidates: Pre-scored candidate songs (top N from deterministic scoring)
            prev_song: Previous song for transition context
            
        Returns:
            Dict with selected_uuid, rationale, or None
        """
        # Get agent settings
        thinking_budget = bundle.get_agent_setting(
            "track_selector", "thinking_budget", THINKING_BUDGET_TRACK
        )
        temperature = bundle.get_agent_setting(
            "track_selector", "temperature", 0.7
        )
        
        # Build personalization context
        persona_section = ""
        if bundle.mood_profile.summary_text:
            persona_section = f"\nLEARNED USER PREFERENCES:\n{bundle.mood_profile.summary_text}\n"
        
        # Few-shot examples from feedback
        likes_section = ""
        if bundle.feedback.recent_likes[:3]:
            likes_examples = "\n".join([
                f"- {l.artist} - {l.title}" + (f" ({l.reason})" if l.reason else "")
                for l in bundle.feedback.recent_likes[:3]
                if l.artist and l.title
            ])
            likes_section = f"\nUSER LIKES (prefer similar):\n{likes_examples}\n"
        
        dislikes_section = ""
        if bundle.feedback.recent_dislikes[:3]:
            dislikes_examples = "\n".join([
                f"- {d.artist} - {d.title}" + (f" ({d.reason})" if d.reason else "")
                for d in bundle.feedback.recent_dislikes[:3]
                if d.artist and d.title
            ])
            dislikes_section = f"\nUSER DISLIKES (avoid these and similar):\n{dislikes_examples}\n"
        
        # Build history context
        recent_section = ""
        recent_tracks = [
            f"{h.artist} - {h.title}"
            for h in bundle.history.recent_tracks[:10]
            if h.artist and h.title
        ]
        if recent_tracks:
            recent_section = f"\nRECENT PLAYS (STRICTLY AVOID REPEATING THESE):\n- " + "\n- ".join(recent_tracks) + "\n"
        elif bundle.history.recent_plays[:10]:
            # Fallback to UUIDs if no titles available
            recent_section = f"\nRECENT PLAYS (avoid repeating IDs):\n{bundle.history.recent_plays[:10]}\n"

        recent_artists_section = ""
        if bundle.history.recent_artists[:10]:
            recent_artists_section = (
                "\nRECENT ARTISTS (prefer variety):\n- "
                + "\n- ".join(bundle.history.recent_artists[:10])
                + "\n"
            )
        
        # Apply prompt template if exists
        base_system = bundle.get_prompt_template("track_selection_system")
        if not base_system:
            base_system = """You are an expert DJ selecting the perfect next track.

SELECTION CRITERIA (priority order):
1. Musical compatibility: tempo (±10 BPM preferred), energy flow
2. User personalization: respect mood targets, genre preferences
3. Lyrical/thematic coherence with previous track
4. Avoid recently played songs
5. Emotional arc: manage energy intentionally
6. Novelty: if candidates are close, favor a less obvious or more adventurous pick"""
        
        system_prompt = f"""{base_system}

TARGET MOOD: {bundle.mood.name}
- Energy target: {bundle.mood.energy_target:.1f} (0=calm, 1=energetic)
- Valence target: {bundle.mood.valence_target:.1f} (0=sad, 1=happy)
- Preferred genres: {', '.join(bundle.mood.genres)}
{persona_section}{likes_section}{dislikes_section}{recent_section}{recent_artists_section}
USER CONTEXT:
{bundle.context.raw_text[:500]}"""

        # Format candidates (compact JSON for token efficiency)
        candidates_text = json.dumps([
            {
                "uuid": c.get("uuid"),
                "artist": c.get("artist"),
                "title": c.get("title"),
                "score": round(c.get("score", 0.5), 2),
                "energy": round(c.get("features", {}).get("energy") or 0, 2),
                "tempo": int(c.get("features", {}).get("tempo") or 0),
            }
            for c in candidates[:10]  # Reduced from 15 for token efficiency
        ], separators=(',', ':'))  # Compact JSON
        
        prev_section = ""
        if prev_song:
            prev_section = f"""
Previous Song (just played):
- Artist: {prev_song.get('artist', 'Unknown')}
- Title: {prev_song.get('title', 'Unknown')}
- Energy: {prev_song.get('features', {}).get('energy', 'N/A')}
- Tempo: {prev_song.get('features', {}).get('tempo', 'N/A')} BPM
"""
        
        user_prompt = f"""{prev_section}
Available Candidates (pre-scored, higher = better fit):
{candidates_text}

Select the best next track. Respond with JSON:
{{
  "selected_uuid": "uuid-here",
  "rationale": "Why this track fits the vibe and user preferences"
}}"""
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        
        result = await self.chat_completion(
            messages=messages,
            temperature=temperature,
            thinking_budget=thinking_budget,
            json_mode=True,
            session_id=bundle.session_id,
            db=db,
            user_id=bundle.user_id,
            mood_id=bundle.mood.id if bundle.mood else None,
            agent_name=agent_name,
            auto_log=auto_log,
        )
        
        # Validate response
        if result and result.get('parsed'):
            valid_uuids = [c.get('uuid') for c in candidates]
            if validate_track_selection_response(result['parsed'], valid_uuids):
                return result
            else:
                logger.warning("Invalid track selection response, falling back to top candidate")
        
        return result
    
    async def generate_transition_plan(
        self,
        bundle: "PreferenceBundle",
        song_a: Dict[str, Any],
        song_b: Dict[str, Any],
        recent_transition_types: Optional[List[str]] = None,
        # Logging parameters
        db: Optional["AsyncSession"] = None,
        agent_name: Optional[str] = "transition_planner",
        auto_log: bool = True,
        # Tool calling
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Generate transition plan between two songs with audio context.
        
        Args:
            bundle: User's preference bundle
            song_a: Current song with features and local_path
            song_b: Next song with features and local_path
            recent_transition_types: Recent transition types to avoid
            
        Returns:
            Dict with transition_type, start_position_a_seconds,
            start_position_b_seconds, transition_duration_seconds, mix_length_bars
        """
        thinking_budget = bundle.get_agent_setting(
            "transition_planner", "thinking_budget", THINKING_BUDGET_TRANSITION
        )
        temperature = bundle.get_agent_setting(
            "transition_planner", "temperature", 0.4
        )

        # Get durations
        song_a_duration = get_track_duration_sec(song_a)
        song_b_duration = get_track_duration_sec(song_b)
        
        # Extract audio snippets (non-fatal on failure)
        import os
        audio_snippets_enabled = os.environ.get("DISABLE_AUDIO_SNIPPETS", "0") != "1"
        audio_a_b64 = None
        audio_b_b64 = None
        
        if audio_snippets_enabled:
            # Last 30s of Song A
            song_a_path = song_a.get("local_path")
            if song_a_path and isinstance(song_a_path, str):
                snippet_a_start = max(0, song_a_duration - 30.0)
                audio_a_b64 = build_audio_snippet(song_a_path, snippet_a_start, 30.0)
            
            # First 30s of Song B
            song_b_path = song_b.get("local_path")
            if song_b_path and isinstance(song_b_path, str):
                audio_b_b64 = build_audio_snippet(song_b_path, 0.0, 30.0)
        
        # Build enhanced system prompt
        system_prompt = """You are an expert DJ creating smooth radio transitions.

You have access to:
1. Audio snippets: Last 30s of Song A, First 30s of Song B (when available)
2. Metadata: BPM, energy, key, duration for both songs
3. Recent transition history (avoid repetition)

REQUIRED OUTPUT (JSON only, no markdown, no code fences):
{
  "transition_type": "crossfade",
  "start_position_a_seconds": 142.5,
  "start_position_b_seconds": 12.0,
  "transition_duration_seconds": 8.0,
  "mix_length_bars": 16,
  "rationale": "Explanation of your choice"
}

TRANSITION TYPES & DURATION RANGES:
- quick_cut: 1-2s (large BPM gaps >20)
- vinyl_stop: 2-6s (creative effect, use sparingly)
- bass_swap: 4-8s (tight BPM match <3)
- loop_mix: 6-10s (looping effect)
- drop_mix: 4-8s (energy drop)
- filter_sweep: 5-10s (energy changes)
- crossfade: 6-12s (smooth blend)
- eq_blend: 6-12s (professional sound)

CRITICAL RULES:
1. **Listen to the audio**: Use the snippets to find natural transition points
2. **start_position_a_seconds**: Where in Song A to START the transition
   - Must be in the last 20-30s of Song A
   - Find a natural ending phrase or energy suitable for transition
   - Leave enough tail for crossfade + buffer
3. **start_position_b_seconds**: Where in Song B to START playback (5-30s range)
   - MUST be 5-30s, NEVER 0 or close to 0
   - Skip intros, silence, or build-ups
   - Start at a strong beat or musical phrase
   - VARY this value - don't always use 8s or 12s
4. **transition_duration_seconds**: Crossfade duration matching the type
   - Must fall within type-specific duration ranges
   - Consider BPM gap (larger gap = shorter transition usually)
   - Consider energy levels (similar = longer transition possible)
5. **Vary your choices**: Don't repeat the same type or timing patterns
6. **mix_length_bars**: Musical phrase length (8, 16, or 32 bars)
   - 8 bars = quick transition
   - 16 bars = standard transition
   - 32 bars = extended blend"""

        # Get features for metadata
        features_a = song_a.get('features') or {}
        features_b = song_b.get('features') or {}
        
        # Build user prompt text
        prompt_text = f"""Song A (current):
  Title: {song_a.get('title', 'Unknown')}
  Artist: {song_a.get('artist', 'Unknown')}
  Duration: {song_a_duration:.1f}s
  BPM: {features_a.get('tempo', 'N/A')}
  Energy: {features_a.get('energy', 'N/A')}
  Key: {features_a.get('key', 'N/A')}
  Danceability: {features_a.get('danceability', 'N/A')}
  Valence: {features_a.get('valence', 'N/A')}

Song B (next):
  Title: {song_b.get('title', 'Unknown')}
  Artist: {song_b.get('artist', 'Unknown')}
  Duration: {song_b_duration:.1f}s
  BPM: {features_b.get('tempo', 'N/A')}
  Energy: {features_b.get('energy', 'N/A')}
  Key: {features_b.get('key', 'N/A')}
  Danceability: {features_b.get('danceability', 'N/A')}
  Valence: {features_b.get('valence', 'N/A')}"""

        if recent_transition_types:
            prompt_text += f"\n\nRecent transitions (avoid these types): {', '.join(recent_transition_types[-3:])}"
        
        prompt_text += "\n\nGenerate the transition plan:"
        
        # Build messages with audio snippets if available
        user_content = []
        
        # Always add text prompt
        user_content.append({
            "type": "text",
            "text": prompt_text
        })
        
        # Add audio snippets if available
        if audio_a_b64:
            user_content.append({
                "type": "input_audio",
                "input_audio": {
                    "data": audio_a_b64,
                    "format": "wav"
                }
            })
            logger.info(f"🎵 Audio snippet A included: last 30s of {song_a.get('title', 'Song A')}")
        
        if audio_b_b64:
            user_content.append({
                "type": "input_audio",
                "input_audio": {
                    "data": audio_b_b64,
                    "format": "wav"
                }
            })
            logger.info(f"🎵 Audio snippet B included: first 30s of {song_b.get('title', 'Song B')}")
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content if len(user_content) > 1 else prompt_text},
        ]
        
        result = await self.chat_completion(
            messages=messages,
            temperature=temperature,
            thinking_budget=thinking_budget,
            json_mode=not tools,  # Disable json_mode if using tools
            session_id=bundle.session_id,
            db=db,
            user_id=bundle.user_id,
            mood_id=bundle.mood.id if bundle.mood else None,
            agent_name=agent_name,
            auto_log=auto_log,
            tools=tools,  # Pass tools for LLM to use
            tool_choice="auto" if tools else None,
        )

        # Parse response if needed
        if result and not result.get("parsed") and result.get("content"):
            try:
                content = result["content"]
                if "```json" in content:
                    start = content.find("```json") + 7
                    end = content.find("```", start)
                    content = content[start:end].strip()
                elif "```" in content:
                    start = content.find("```") + 3
                    end = content.find("```", start)
                    content = content[start:end].strip()

                if "{" in content and "}" in content:
                    start = content.find("{")
                    end = content.rfind("}") + 1
                    content = content[start:end]

                sanitized_content = self._sanitize_json_string(content)
                result["parsed"] = json.loads(sanitized_content)
            except Exception as e:
                logger.debug("Transition plan parse fallback failed: %s", e)
        
        # Validate and normalize response
        if result and result.get('parsed'):
            if validate_transition_plan_response(result['parsed']):
                # Normalize values to safe ranges
                normalized = normalize_transition_plan(
                    result['parsed'],
                    song_a,
                    song_b
                )
                result['parsed'] = normalized
                
                logger.info(
                    f"✅ Transition plan: type={normalized.get('transition_type')}, "
                    f"start_a={normalized.get('start_position_a_seconds', 'N/A'):.1f}s, "
                    f"start_b={normalized.get('start_position_b_seconds'):.1f}s, "
                    f"duration={normalized.get('transition_duration_seconds', 'N/A'):.1f}s"
                )
                return result
            else:
                # Provide default fallback with new fields
                logger.warning("Invalid transition plan, using fallback with defaults")
                result['parsed'] = {
                    "transition_type": "crossfade",
                    "mix_length_bars": 16,
                    "start_position_a_seconds": max(0, song_a_duration - 20.0),
                    "start_position_b_seconds": max(5.0, min(8.0, song_b_duration * 0.1)),
                    "transition_duration_seconds": 8.0,
                    "rationale": "Default crossfade fallback"
                }
        
        return result
    
    
    async def generate_dj_intro_speech(
        self,
        bundle: "PreferenceBundle",
        song_info: Dict[str, Any],
        banter_history: Optional[List[str]] = None,
        # Logging parameters
        db: Optional["AsyncSession"] = None,
        agent_name: Optional[str] = "speech_writer_intro",
        auto_log: bool = True,
        # Tool calling
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Generate DJ intro speech for set opening.
        
        Args:
            bundle: User's preference bundle
            song_info: First song info (title, artist)
            banter_history: Recent DJ speeches to avoid repetition
            
        Returns:
            Dict with text, tone
        """
        thinking_budget = bundle.get_agent_setting(
            "speech_writer", "thinking_budget", THINKING_BUDGET_SPEECH
        )
        temperature = bundle.get_agent_setting(
            "speech_writer", "temperature", 0.9
        )
        
        # Build history avoidance
        history_section = ""
        if banter_history:
            history_section = f"\nRECENT BANTER (don't repeat):\n- " + "\n- ".join(banter_history[-5:])
        
        # Extract mood-specific context for unique intros
        mood_keywords = bundle.mood.vibe_keywords or []
        example_artists = bundle.mood.example_artists or []
        intro_style = bundle.mood.intro_personality or bundle.mood.dj_personality
        
        # Build mood context section
        mood_context = f"""
MOOD: {bundle.mood.name}
MOOD ENERGY: {bundle.mood.energy_target:.1f} (0=calm, 1=intense)
MOOD VIBE: {bundle.mood.valence_target:.1f} (0=melancholic, 1=euphoric)"""
        
        if mood_keywords:
            mood_context += f"\nMOOD KEYWORDS: {', '.join(mood_keywords[:4])}"
        
        if example_artists:
            mood_context += f"\nEXAMPLE ARTISTS FOR THIS MOOD: {', '.join(example_artists[:3])}"
        
        # Map intro personalities to speech styles
        intro_style_map = {
            "upbeat_welcoming": "Warm and upbeat. Make the listener feel energized and ready for the day.",
            "hyped_energetic": "HYPED and PUMPED! Get them FIRED UP! Use exclamation marks and energy!",
            "calm_soothing": "Calm, gentle, and soothing. Like a warm embrace. Speak softly.",
            "celebratory_wild": "Celebratory and WILD! This is a PARTY! Let's GO! Maximum enthusiasm!",
            "mysterious_intimate": "Mysterious and intimate. Whisper-like. Create an atmosphere of late-night introspection.",
            "minimal": "Brief and understated. 1-2 sentences max.",
            "chill": "Relaxed and friendly. 2-3 sentences.",
            "chatty": "Engaging and energetic. 2-4 sentences with personality.",
        }
        intro_style_desc = intro_style_map.get(intro_style, intro_style_map["chill"])
        
        # Use mood personality
        personality_map = {
            "minimal": "Brief and understated. 1-2 sentences max.",
            "chill": "Relaxed and friendly. 2-3 sentences.",
            "chatty": "Engaging and energetic. 2-4 sentences with personality.",
        }
        personality_desc = personality_map.get(
            bundle.mood.dj_personality, 
            personality_map["chill"]
        )
        
        # Apply prompt template if exists
        base_system = bundle.get_prompt_template("dj_intro_system")
        if not base_system:
            base_system = f"""You are a witty, personable DJ starting a new set.

PERSONALITY STYLE: {bundle.mood.dj_personality.upper()}
{personality_desc}

{mood_context}

INTRO STYLE FOR THIS MOOD: {intro_style_desc}

USER CONTEXT:
{bundle.context.raw_text[:300]}
{history_section}

GUIDELINES:
- Warm greeting, set the mood
- Reference the first song naturally
- Emphasize the mood's unique vibe ({bundle.mood.name})
- Match the intro style for this specific mood
- Avoid cheesy radio clichés
- Don't use technical jargon (BPM, key, etc.)
- Make this intro sound DIFFERENT from other moods"""
        
        user_prompt = f"""
First Song:
- Title: {song_info.get('title', 'Unknown')}
- Artist: {song_info.get('artist', 'Unknown')}

Generate a DJ intro. Respond with JSON:
{{
  "text": "Your intro speech here",
  "tone": "excited"
}}"""
        
        messages = [
            {"role": "system", "content": base_system},
            {"role": "user", "content": user_prompt},
        ]
        
        # Import json_lib at function level
        import json as json_lib
        
        # Handle tool calling loop if tools are provided
        max_tool_iterations = 5
        iteration = 0
        
        while iteration < max_tool_iterations:
            # Only enable json_mode if we're not expecting tool calls
            # json_mode conflicts with tool calling, so disable it when tools are present
            tools_to_pass = tools if iteration == 0 else None
            use_json_mode = not tools_to_pass  # Enable json_mode only after tools are done
            
            result = await self.chat_completion(
                messages=messages,
                temperature=temperature,
                thinking_budget=thinking_budget,
                json_mode=use_json_mode,
                session_id=bundle.session_id,
                db=db,
                user_id=bundle.user_id,
                mood_id=bundle.mood.id if bundle.mood else None,
                agent_name=agent_name,
                auto_log=auto_log,
                tools=tools_to_pass,
                tool_choice="auto" if tools_to_pass else None,
            )
            
            if not result:
                break
            
            # Check if LLM wants to call tools
            tool_calls = result.get('tool_calls')
            if not tool_calls or result.get('finish_reason') == 'stop':
                # No more tool calls, we're done
                # If we had tools but no tool calls and no parsed result, retry with json_mode
                if tools and iteration == 0 and not result.get('parsed'):
                    logger.debug("🔧 No tool calls on first iteration, retrying with json_mode enabled")
                    result = await self.chat_completion(
                        messages=messages,
                        temperature=temperature,
                        thinking_budget=thinking_budget,
                        json_mode=True,  # Enable json_mode for final response
                        session_id=bundle.session_id,
                        db=db,
                        user_id=bundle.user_id,
                        mood_id=bundle.mood.id if bundle.mood else None,
                        agent_name=agent_name,
                        auto_log=auto_log,
                        tools=None,  # No tools for final response
                    )
                break
            
            # Execute tool calls and add results to conversation
            from backend_v2.integrations.db_tools import execute_tool
            
            # Add assistant message with tool calls
            assistant_message = {
                "role": "assistant",
                "content": result.get('content', ''),
                "tool_calls": tool_calls,
            }
            messages.append(assistant_message)
            
            # Execute each tool call
            for tool_call in tool_calls:
                tool_name = tool_call['function']['name']
                tool_args = json_lib.loads(tool_call['function']['arguments'])
                tool_id = tool_call['id']
                
                logger.info(f"🔧 LLM calling tool: {tool_name} with args: {tool_args}")
                
                try:
                    tool_result = await execute_tool(
                        tool_name,
                        tool_args,
                        db,
                        session_id=bundle.session_id,
                        user_id=bundle.user_id,
                        mood_id=bundle.mood.id if bundle.mood else None,
                        agent_name=agent_name,
                        auto_log=True,
                    )
                    result_str = json_lib.dumps(tool_result, default=str)
                    
                    # Add tool result to conversation
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_id,
                        "name": tool_name,
                        "content": result_str,
                    })
                    
                    logger.info(f"✅ Tool {tool_name} result: {result_str[:200]}")
                except Exception as e:
                    logger.error(f"❌ Tool execution failed: {e}")
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_id,
                        "name": tool_name,
                        "content": json_lib.dumps({"error": str(e)}),
                    })
            
            iteration += 1
        
        if iteration >= max_tool_iterations:
            logger.warning(f"Reached max tool iterations ({max_tool_iterations}), using final result")
        
        # Post-process to sanitize
        if result and result.get('parsed') and result['parsed'].get('text'):
            result['parsed']['text'] = self._sanitize_tts_output(result['parsed']['text'])
        
        return result
    
    async def generate_dj_speech(
        self,
        bundle: "PreferenceBundle",
        context: Dict[str, Any],
        banter_history: Optional[List[str]] = None,
        # Logging parameters
        db: Optional["AsyncSession"] = None,
        agent_name: Optional[str] = "speech_writer",
        auto_log: bool = True,
        # Tool calling
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Generate transition DJ speech.
        
        Args:
            bundle: User's preference bundle  
            context: Current context (prev_song, next_song, transition_type)
            banter_history: Recent speeches to avoid repetition
            
        Returns:
            Dict with text, tone
        """
        thinking_budget = bundle.get_agent_setting(
            "speech_writer", "thinking_budget", THINKING_BUDGET_SPEECH
        )
        temperature = bundle.get_agent_setting(
            "speech_writer", "temperature", 0.9
        )
        
        history_section = ""
        if banter_history:
            history_section = f"\nRECENT BANTER (don't repeat):\n- " + "\n- ".join(banter_history[-5:])
        
        # Use profile data for DJ personality
        dj_style = bundle.get_dj_personality()
        display_name = bundle.get_display_name()
        
        # Build profile context for additional personalization
        profile_context = build_profile_context(bundle)
        
        # Map personality styles to speech guidance
        personality_map = {
            "minimal_talk": "Very brief. 1 sentence max.",
            "chill": "Relaxed. 1-2 sentences.",
            "chatty": "Engaging. 2-3 sentences with personality.",
            "casual_funny": "Casual and funny. 2-3 witty sentences.",
            "calm_radio": "Calm radio host style. 1-2 sentences.",
            "hype_energetic": "Energetic! Hyped up! 2-3 punchy sentences.",
            "light_roast": "Witty with light roasting. 2-3 sentences.",
            "more_talk_between_songs": "Chatty and conversational. 3-4 sentences.",
        }
        personality_desc = personality_map.get(dj_style, personality_map["casual_funny"])
        
        # Roast guidance based on personality
        roast_guidance = ""
        if dj_style == "light_roast" and display_name:
            roast_guidance = f"\nFeel free to playfully roast {display_name} occasionally."
        
        # Spotify hook guidance
        spotify_guidance = ""
        if context.get('spotify_hook'):
            hook = context['spotify_hook']
            time_range_label = {
                "short_term": "last month",
                "medium_term": "last 6 months",
                "long_term": "all time"
            }.get(hook.get('time_range', ''), 'recently')
            spotify_guidance = f"\n\n🎵 SPOTIFY HOOK: This track is #{hook.get('rank')} in {display_name}'s {time_range_label} top tracks! Feel free to mention this naturally (e.g., 'I see you had this on repeat last month!' or 'This was your #{hook.get('rank')} most played track recently'). Don't overuse - sprinkle it naturally."
        
        # DJ history guidance
        dj_history_guidance = ""
        if bundle.dj_history.topics_mentioned:
            recent_topics = bundle.dj_history.topics_mentioned[:5]
            dj_history_guidance = f"\n\nRECENT TOPICS MENTIONED: {', '.join(recent_topics)}\nAvoid repeating these topics too soon."
        
        base_system = bundle.get_prompt_template("dj_speech_system")
        if not base_system:
            listener_line = f"Listener: {display_name}\n" if display_name else ""
            base_system = f"""You are a witty DJ creating short spoken transitions.

PERSONALITY: {dj_style.upper()}
{personality_desc}{roast_guidance}{spotify_guidance}{dj_history_guidance}
{listener_line}{history_section}

{profile_context}

GUIDELINES:
- Natural, conversational
- Reference songs by name/artist
- No technical jargon (BPM, key, crossfade, etc.)
- Don't be cheesy"""
        
        # Sanitize context to remove technical fields
        safe_context = self._sanitize_speech_context(context)
        
        user_prompt = f"""
Context:
{json.dumps(safe_context, indent=2)}

Generate DJ speech. Respond with JSON:
{{
  "text": "Your speech here",
  "tone": "humorous"
}}"""
        
        messages = [
            {"role": "system", "content": base_system},
            {"role": "user", "content": user_prompt},
        ]
        
        # Import json_lib at function level
        import json as json_lib
        
        # Handle tool calling loop if tools are provided
        max_tool_iterations = 5
        iteration = 0
        
        while iteration < max_tool_iterations:
            # Only enable json_mode if we're not expecting tool calls
            # json_mode conflicts with tool calling, so disable it when tools are present
            tools_to_pass = tools if iteration == 0 else None
            use_json_mode = not tools_to_pass  # Enable json_mode only after tools are done
            
            result = await self.chat_completion(
                messages=messages,
                temperature=temperature,
                thinking_budget=thinking_budget,
                json_mode=use_json_mode,
                session_id=bundle.session_id,
                db=db,
                user_id=bundle.user_id,
                mood_id=bundle.mood.id if bundle.mood else None,
                agent_name=agent_name,
                auto_log=auto_log,
                tools=tools_to_pass,
                tool_choice="auto" if tools_to_pass else None,
            )
            
            if not result:
                break
            
            # Check if LLM wants to call tools
            tool_calls = result.get('tool_calls')
            if not tool_calls or result.get('finish_reason') == 'stop':
                # No more tool calls, we're done
                # If we had tools but no tool calls and no parsed result, retry with json_mode
                if tools and iteration == 0 and not result.get('parsed'):
                    logger.debug("🔧 No tool calls on first iteration, retrying with json_mode enabled")
                    result = await self.chat_completion(
                        messages=messages,
                        temperature=temperature,
                        thinking_budget=thinking_budget,
                        json_mode=True,  # Enable json_mode for final response
                        session_id=bundle.session_id,
                        db=db,
                        user_id=bundle.user_id,
                        mood_id=bundle.mood.id if bundle.mood else None,
                        agent_name=agent_name,
                        auto_log=auto_log,
                        tools=None,  # No tools for final response
                    )
                break
            
            # Execute tool calls and add results to conversation
            from backend_v2.integrations.db_tools import execute_tool
            
            # Add assistant message with tool calls
            assistant_message = {
                "role": "assistant",
                "content": result.get('content', ''),
                "tool_calls": tool_calls,
            }
            messages.append(assistant_message)
            
            # Execute each tool call
            for tool_call in tool_calls:
                tool_name = tool_call['function']['name']
                tool_args = json_lib.loads(tool_call['function']['arguments'])
                tool_id = tool_call['id']
                
                logger.info(f"🔧 LLM calling tool: {tool_name} with args: {tool_args}")
                
                try:
                    tool_result = await execute_tool(
                        tool_name,
                        tool_args,
                        db,
                        session_id=bundle.session_id,
                        user_id=bundle.user_id,
                        mood_id=bundle.mood.id if bundle.mood else None,
                        agent_name=agent_name,
                        auto_log=True,
                    )
                    result_str = json_lib.dumps(tool_result, default=str)
                    
                    # Add tool result to conversation
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_id,
                        "name": tool_name,
                        "content": result_str,
                    })
                    
                    logger.info(f"✅ Tool {tool_name} result: {result_str[:200]}")
                except Exception as e:
                    logger.error(f"❌ Tool execution failed: {e}")
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_id,
                        "name": tool_name,
                        "content": json_lib.dumps({"error": str(e)}),
                    })
            
            iteration += 1
        
        if iteration >= max_tool_iterations:
            logger.warning(f"Reached max tool iterations ({max_tool_iterations}), using final result")
        
        if result and result.get('parsed') and result['parsed'].get('text'):
            result['parsed']['text'] = self._sanitize_tts_output(result['parsed']['text'])
        
        return result
    
    def _sanitize_speech_context(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Remove technical metadata from context."""
        technical_fields = {
            'tempo', 'bpm', 'key', 'camelot_code', 'energy', 'danceability',
            'valence', 'beats', 'downbeats', 'cue_in_seconds', 'cue_out_seconds',
            'duration_seconds', 'loudness', 'ffmpeg_filter', 'mix_length_bars',
            'start_position_b_seconds', 'song_a_start_sec', 'song_b_start_sec',
            'features', 'score'
        }
        
        def clean_dict(d: Dict) -> Dict:
            return {k: v for k, v in d.items() if k.lower() not in technical_fields}
        
        sanitized = {}
        for key, value in context.items():
            if key.lower() in technical_fields:
                continue
            if isinstance(value, dict):
                sanitized[key] = clean_dict(value)
            else:
                sanitized[key] = value
        
        return sanitized
    
    def _sanitize_json_string(self, json_str: str) -> str:
        r"""Sanitize JSON string to fix invalid escape sequences.
        
        Fixes common issues:
        - Invalid escape sequences (e.g., \c, \x without hex, etc.)
        - Extracts JSON from markdown code blocks
        
        Args:
            json_str: Raw JSON string that may contain invalid escapes
            
        Returns:
            Sanitized JSON string safe for parsing
        """
        import re
        
        # Remove markdown code blocks if present
        result = json_str.strip()
        if "```json" in result:
            start = result.find("```json") + 7
            end = result.find("```", start)
            if end > start:
                result = result[start:end].strip()
        elif "```" in result:
            start = result.find("```") + 3
            end = result.find("```", start)
            if end > start:
                result = result[start:end].strip()
        
        # Extract JSON object if wrapped in text
        if "{" in result and "}" in result:
            start = result.find("{")
            end = result.rfind("}") + 1
            if end > start:
                result = result[start:end]
        
        # Fix invalid escape sequences by replacing them with escaped backslashes
        # Valid JSON escapes: \\, \", \/, \b, \f, \n, \r, \t, \uXXXX
        # Invalid escapes like \c, \x, etc. should become \\c, \\x
        
        # Use a simple approach: replace backslashes that aren't part of valid escapes
        # We'll process character by character to avoid breaking valid sequences
        chars = list(result)
        i = 0
        while i < len(chars):
            if chars[i] == '\\' and i + 1 < len(chars):
                next_char = chars[i + 1]
                # Check if this is a valid escape sequence
                valid_escapes = ['\\', '"', '/', 'b', 'f', 'n', 'r', 't', 'u']
                is_valid = next_char in valid_escapes
                
                # Check for \uXXXX pattern
                if next_char == 'u' and i + 5 < len(chars):
                    # Check if followed by 4 hex digits
                    hex_chars = chars[i+2:i+6]
                    if all(c in '0123456789abcdefABCDEF' for c in hex_chars):
                        is_valid = True
                        i += 6  # Skip the entire \uXXXX sequence
                        continue
                
                if not is_valid:
                    # Invalid escape - escape the backslash
                    chars.insert(i, '\\')
                    i += 2
                else:
                    i += 2  # Skip valid escape
            else:
                i += 1
        
        return ''.join(chars)
    
    def _sanitize_tts_output(self, text: str) -> str:
        """Remove technical terms from TTS output."""
        forbidden_patterns = [
            r'\b\d{2,3}\s*(bpm|beats?\s*per\s*minute)\b',
            r'\b(bpm|beats?\s*per\s*minute)\s*of?\s*\d{2,3}\b',
            r'\b(key\s+of\s+)?[A-G](#|b)?\s*(major|minor|m)\b',
            r'\b\d{1,2}[AB]\b',
            r'\bcamelot\s*(wheel|code|key)?\b',
            r'\b(crossfade|eq[_\s]?blend|bass[_\s]?swap|filter[_\s]?sweep|echo[_\s]?out|vinyl[_\s]?stop|quick[_\s]?cut|loop[_\s]?mix|drop[_\s]?mix|filtergraph|ffmpeg|atrim)\b',
            r'\benergy\s*(score|level|rating)?\s*:?\s*\d+(\.\d+)?\b',
            r'\b(danceability|valence)\s*:?\s*\d+(\.\d+)?\b',
            r'\b\d+(\.\d+)?\s*(db|decibels?|lufs)\b',
        ]
        
        result = text
        for pattern in forbidden_patterns:
            result = re.sub(pattern, '', result, flags=re.IGNORECASE)
        
        # Clean up artifacts
        result = re.sub(r'\s{2,}', ' ', result)
        result = re.sub(r',\s*,', ',', result)
        result = re.sub(r',\s*\.', '.', result)
        result = result.strip()
        
        return result


# =============================================================================
# LLM Trace Storage
# =============================================================================

def redact_audio_payloads(data: Any) -> Any:
    """Recursively redact base64 audio data from request/response.
    
    Prevents database bloat by replacing large base64 audio strings with
    size placeholders while preserving structure and metadata.
    
    Args:
        data: Request/response data (dict, list, or primitive)
        
    Returns:
        Redacted copy of data
    """
    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            if key == "data" and isinstance(value, str) and len(value) > 1000:
                # Likely base64 audio - redact but keep size info
                result[key] = f"<redacted_audio:{len(value)}_bytes>"
            elif key == "input_audio" and isinstance(value, dict):
                # Preserve format/metadata, redact data
                result[key] = {
                    "format": value.get("format"),
                    "data": f"<redacted_audio:{len(value.get('data', ''))}_bytes>" if "data" in value else None
                }
            else:
                result[key] = redact_audio_payloads(value)
        return result
    elif isinstance(data, list):
        return [redact_audio_payloads(item) for item in data]
    else:
        return data


async def store_llm_trace(
    db,  # AsyncSession
    user_id: Optional[str],
    mood_id: Optional[str],
    session_id: Optional[str],
    agent_name: str,
    prompt: str,
    response: str,
    model: str,
    thinking_budget: Optional[int] = None,
    messages: Optional[List[Dict[str, Any]]] = None,
    parameters: Optional[Dict[str, Any]] = None,
    tool_calls: Optional[List[Dict[str, Any]]] = None,
    usage: Optional[Dict[str, Any]] = None,
) -> Optional[int]:
    """Store LLM interaction trace in database.
    
    Args:
        db: Database session
        user_id: User ID (optional)
        mood_id: Mood ID (optional)
        session_id: Session ID (optional)
        agent_name: Name of the agent making the call
        prompt: User prompt (deprecated, use messages instead)
        response: LLM response content
        model: Model name
        thinking_budget: Thinking budget used
        messages: Full message history (preferred over prompt)
        parameters: Request parameters (temperature, max_tokens, etc.)
        tool_calls: Tool calls made by the LLM
        usage: Token usage information
        
    Returns:
        Trace ID if successful, None otherwise
    """
    from backend_v2.models.existing import LLMTrace
    
    try:
        # NEW: Redact audio payloads before storage
        messages_safe = redact_audio_payloads(messages) if messages else None
        
        # Build comprehensive prompt from messages if available
        if messages_safe:
            # Format messages for storage (now redacted)
            messages_str = json.dumps(messages_safe, indent=2)
            full_prompt = messages_str[:10000]  # Truncate for storage
        else:
            full_prompt = prompt[:10000] if prompt else ""
        
        # Build comprehensive response with tool calls (also redact)
        response_data = {
            "content": response[:10000] if response else "",
        }
        if tool_calls:
            response_data["tool_calls"] = tool_calls
        if usage:
            response_data["usage"] = usage
        
        # NEW: Redact response data as well (in case it contains audio)
        response_data_safe = redact_audio_payloads(response_data)
        response_str = json.dumps(response_data_safe, indent=2)[:10000]
        
        trace = LLMTrace(
            session_id=session_id,
            user_id=user_id,
            mood_id=mood_id,
            agent_name=agent_name,
            prompt=full_prompt,
            response=response_str,
            model=model,
            thinking_budget=thinking_budget,
            created_at=utc_isoformat(utc_now()),
        )
        db.add(trace)
        await db.flush()
        
        logger.info(f"📝 Stored LLM trace for {agent_name} (trace_id={trace.id}, session={session_id})")
        return trace.id
    except Exception as e:
        logger.error(f"Failed to store LLM trace: {e}")
        return None


async def store_tool_usage_log(
    db: "AsyncSession",
    tool_name: str,
    tool_arguments: Dict[str, Any],
    tool_result: Any,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    mood_id: Optional[str] = None,
    llm_trace_id: Optional[int] = None,
    agent_name: Optional[str] = None,
    execution_time_ms: Optional[float] = None,
    success: bool = True,
    error_message: Optional[str] = None,
) -> Optional[int]:
    """Store tool usage log in database.
    
    Args:
        db: Database session
        tool_name: Name of the tool executed
        tool_arguments: Arguments passed to the tool
        tool_result: Result returned by the tool
        session_id: Session ID (optional)
        user_id: User ID (optional)
        mood_id: Mood ID (optional)
        llm_trace_id: Associated LLM trace ID (optional)
        agent_name: Name of the agent using the tool
        execution_time_ms: Execution time in milliseconds
        success: Whether execution was successful
        error_message: Error message if execution failed
        
    Returns:
        Log ID if successful, None otherwise
    """
    from backend_v2.models.existing import ToolUsageLog
    
    try:
        # Serialize arguments and result to JSON
        args_json = json.dumps(tool_arguments, default=str)[:50000]  # Truncate if needed
        result_json = json.dumps(tool_result, default=str)[:50000] if tool_result is not None else None
        
        log = ToolUsageLog(
            session_id=session_id,
            user_id=user_id,
            mood_id=mood_id,
            llm_trace_id=llm_trace_id,
            agent_name=agent_name,
            tool_name=tool_name,
            tool_arguments=args_json,
            tool_result=result_json,
            execution_time_ms=execution_time_ms,
            success=1 if success else 0,
            error_message=error_message[:5000] if error_message else None,
            created_at=utc_isoformat(utc_now()),
        )
        db.add(log)
        await db.flush()
        
        logger.info(f"🔧 Stored tool usage log: {tool_name} (log_id={log.id}, success={success})")
        return log.id
    except Exception as e:
        logger.error(f"Failed to store tool usage log: {e}")
        import traceback
        logger.debug(traceback.format_exc())
        return None


# =============================================================================
# Singleton
# =============================================================================

_openrouter_client: Optional[OpenRouterClient] = None


def get_openrouter_client() -> OpenRouterClient:
    """Get or create global OpenRouter client."""
    global _openrouter_client
    if _openrouter_client is None:
        _openrouter_client = OpenRouterClient()
    return _openrouter_client
