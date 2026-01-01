"""
Tool-Based Track Selector

Uses OpenRouter's tool calling feature to give the AI direct database access
for more intelligent song selection.

The AI can query play history, analyze patterns, check artist frequency,
and search the library before making a selection.
"""

import json
import logging
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from backend_v2.integrations.openrouter import get_openrouter_client, store_llm_trace
from backend_v2.integrations.db_tools import DB_TOOLS, execute_tool
from backend_v2.services.preference_bundle import PreferenceBundle
from backend_v2.orchestration.state import DJState

logger = logging.getLogger("ai-dj.tool-selector")


async def select_track_with_tools(
    db: AsyncSession,
    bundle: PreferenceBundle,
    state: DJState,
    prev_song: Optional[Dict[str, Any]] = None,
    max_iterations: int = 5,
) -> Optional[Dict[str, Any]]:
    """Select track using AI with database tool access.
    
    The AI can use tools to:
    - Query play history
    - Check artist frequency
    - Search the local library
    - Analyze listening patterns
    - Get user feedback
    - Access Spotify context
    
    Args:
        db: Database session
        bundle: User's preference bundle
        state: Current DJ state
        prev_song: Previous song for context
        max_iterations: Max tool calling iterations
        
    Returns:
        Selected song dict or None
    """
    client = get_openrouter_client()
    if not client.enabled:
        logger.warning("OpenRouter disabled, cannot use tool-based selection")
        return None
    
    # Build system prompt
    system_prompt = _build_system_prompt(bundle, prev_song)
    
    # Build user request
    user_prompt = _build_user_prompt(bundle, prev_song)
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    
    iteration = 0
    tool_calls_made = False
    tool_call_retry = False
    
    while iteration < max_iterations:
        iteration += 1
        logger.info(f"🤖 Tool-based selection iteration {iteration}/{max_iterations}")
        
        try:
            # Call LLM with tools
            session_id = state.get("session_id") if state else None
            response = await client.chat_completion(
                messages=messages,
                tools=DB_TOOLS,
                tool_choice="auto",
                temperature=0.7,
                max_tokens=2000,
                session_id=session_id,
                # Enable auto-logging
                db=db,
                user_id=bundle.user_id,
                mood_id=bundle.mood.id if bundle.mood else None,
                agent_name="tool_based_selector",
                auto_log=True,
            )
            
            if not response:
                logger.error("No response from LLM")
                return None
            
            finish_reason = response.get('finish_reason')
            tool_calls = response.get('tool_calls', [])
            if tool_calls:
                tool_calls_made = True
            
            # Add assistant message to conversation
            assistant_message = {
                "role": "assistant",
                "content": response.get('content'),
            }
            if tool_calls:
                assistant_message["tool_calls"] = tool_calls
            messages.append(assistant_message)
            
            # If no tool calls, AI has made final decision
            if not tool_calls or finish_reason == "stop":
                if not tool_calls and not tool_calls_made and not tool_call_retry:
                    messages.append({
                        "role": "assistant",
                        "content": response.get('content', ''),
                    })
                    messages.append({
                        "role": "user",
                        "content": "You must call at least one tool before selecting a song. "
                                   "Use the tools now and then return the final JSON selection.",
                    })
                    tool_call_retry = True
                    continue

                content = response.get('content', '')
                logger.info(f"🎵 AI final response: {content[:200]}")
                
                # Parse final selection from content
                song_selection = _parse_song_selection(content)
                if song_selection:
                    # Note: LLM call is already auto-logged by chat_completion
                    # This explicit log is redundant but kept for backward compatibility
                    await store_llm_trace(
                        db=db,
                        user_id=bundle.user_id,
                        mood_id=bundle.mood.id if bundle.mood else None,
                        session_id=state.get("session_id"),
                        agent_name="tool_based_selector",
                        prompt=user_prompt,
                        response=content,
                        model=response.get('model', 'unknown'),
                        messages=messages,  # Include full conversation
                        tool_calls=response.get('tool_calls'),
                        usage=response.get('usage'),
                    )
                    return song_selection
                else:
                    logger.warning("AI finished but no song selection found in response")
                    return None
            
            # Execute tool calls
            # Get trace ID from last LLM call for linking (if available)
            llm_trace_id = None  # Will be set if we can get it from the response
            
            for tool_call in tool_calls:
                tool_name = tool_call['function']['name']
                tool_args = json.loads(tool_call['function']['arguments'])
                tool_id = tool_call['id']
                
                logger.info(f"🔧 Executing tool: {tool_name} with args: {tool_args}")
                
                try:
                    tool_result = await execute_tool(
                        tool_name, 
                        tool_args, 
                        db,
                        # Pass logging context
                        session_id=session_id,
                        user_id=bundle.user_id,
                        mood_id=bundle.mood.id if bundle.mood else None,
                        llm_trace_id=llm_trace_id,  # Link to LLM trace if available
                        agent_name="tool_based_selector",
                        auto_log=True,
                    )
                    result_str = json.dumps(tool_result, default=str)
                    
                    # Add tool result to conversation
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_id,
                        "name": tool_name,
                        "content": result_str,
                    })
                    
                    logger.info(f"✅ Tool result: {result_str[:200]}")
                
                except Exception as e:
                    logger.error(f"❌ Tool execution failed: {e}")
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_id,
                        "name": tool_name,
                        "content": json.dumps({"error": str(e)}),
                    })
        
        except Exception as e:
            logger.error(f"Error in tool-based selection: {e}")
            return None
    
    logger.warning(f"Max iterations ({max_iterations}) reached without selection")
    return None


def _build_system_prompt(bundle: PreferenceBundle, prev_song: Optional[Dict[str, Any]]) -> str:
    """Build system prompt for tool-based selection."""
    mood_name = bundle.mood.name if bundle.mood else "Unknown"
    mood_desc = bundle.mood.description if bundle.mood else ""
    
    return f"""You are an expert AI DJ with direct access to the user's music database.

**Your Task**: Select the perfect next song for the user based on their mood, preferences, and listening history.

**Current Context**:
- Mood: {mood_name}
- Mood Description: {mood_desc}
- Previous Song: {prev_song.get('artist') if prev_song else 'None'} - {prev_song.get('title') if prev_song else 'N/A'}
- User ID: {bundle.user_id}

**Available Tools**:
You have access to database tools to help you make an informed decision:

1. **get_play_history**: Query recent plays, filter by mood/artist/time
2. **get_artist_play_count**: Check how often an artist has been played recently
3. **search_songs_in_library**: Find songs by artist, title, genre, duration
4. **get_user_feedback**: See what songs the user liked/disliked
5. **get_spotify_context**: Access user's Spotify top artists and genres
6. **analyze_listening_patterns**: Get insights on listening habits

**Selection Strategy**:
1. First, use tools to understand the user's preferences and recent history
2. Check if any artists are overplayed (use get_artist_play_count)
3. Search for appropriate songs in the library (use search_songs_in_library)
4. Consider the mood and previous song for flow
5. Make your final selection

**CRITICAL RULES**:
- You MUST call at least one tool before making your final selection
- DO NOT select artists that appear 3+ times in the last 10 tracks
- Ensure variety - avoid repetitive artist selection
- Match the mood's energy and vibe
- Consider the transition from the previous song
- Only select songs that exist in the library (verify with search_songs_in_library)

**Output Format**:
When you've made your final decision, respond with JSON:
```json
{{
  "artist": "Artist Name",
  "title": "Song Title",
  "rationale": "Brief explanation of why this song was selected"
}}
```

Use the tools wisely to make an informed, personalized selection!"""


def _build_user_prompt(bundle: PreferenceBundle, prev_song: Optional[Dict[str, Any]]) -> str:
    """Build user prompt for track selection."""
    mood_name = bundle.mood.name if bundle.mood else "Unknown"
    
    prompt = f"Select the next song for mood '{mood_name}'."
    
    if prev_song:
        prompt += f" The previous song was '{prev_song.get('artist')} - {prev_song.get('title')}'."
    
    prompt += "\n\nUse the available tools to analyze the user's preferences and make an informed selection."
    prompt += "\n\nIMPORTANT: Avoid overplayed artists and ensure variety!"
    
    return prompt


def _parse_song_selection(content: str) -> Optional[Dict[str, Any]]:
    """Parse song selection from AI response.
    
    Expects JSON format:
    {
      "artist": "Artist Name",
      "title": "Song Title",
      "rationale": "..."
    }
    """
    try:
        # Try to parse as JSON
        if "{" in content and "}" in content:
            # Extract JSON from markdown code blocks if present
            if "```json" in content:
                start = content.find("```json") + 7
                end = content.find("```", start)
                json_str = content[start:end].strip()
            elif "```" in content:
                start = content.find("```") + 3
                end = content.find("```", start)
                json_str = content[start:end].strip()
            else:
                # Find JSON object
                start = content.find("{")
                end = content.rfind("}") + 1
                json_str = content[start:end]
            
            data = json.loads(json_str)
            
            if "artist" in data and "title" in data:
                return {
                    "artist": data["artist"],
                    "title": data["title"],
                    "rationale": data.get("rationale", "AI selection"),
                    "selection_method": "tool_based_ai",
                }
    
    except Exception as e:
        logger.error(f"Failed to parse song selection: {e}")
    
    return None
