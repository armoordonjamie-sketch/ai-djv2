"""
Track Selection Graph - Select next track using tool-calling + optional RAG.

This subgraph handles:
1. Optional RAG retrieval for candidate tracks
2. LLM-based selection with database tools
3. Guardrails (cooldowns, duplicates, blocked artists)
4. Fallback to deterministic selection
"""
import logging
import json
from typing import Any, Dict, List, Optional

from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

from backend_v2.langgraph_v3.state import (
    DJStateV3,
    add_debug_event,
    check_artist_cooldown,
    add_artist_cooldown,
)

logger = logging.getLogger("ai-dj.graph.track-selection")


# =============================================================================
# Routing Functions
# =============================================================================

def should_retrieve(state: DJStateV3) -> str:
    """
    Decide if RAG retrieval is needed.
    
    Returns "retrieve" or "select" node name.
    """
    # Skip retrieval if disabled
    import os
    if os.environ.get("LANGGRAPH_RAG_ENABLED", "true").lower() != "true":
        return "select"
    
    # Skip if we already have candidates
    if state.get("candidate_tracks"):
        return "select"
    
    # Skip for initial segment (use Spotify context directly)
    if state.get("is_initial_segment", True):
        return "select"
    
    # Retrieve every 3rd segment for variety
    segment_index = state.get("segment_index", 0)
    if segment_index > 0 and segment_index % 3 == 0:
        return "retrieve"
    
    return "select"


def should_continue_tools(state: DJStateV3) -> str:
    """
    Decide if we should continue tool calling or finalize.
    
    Returns "tools", "finalize", or "fallback".
    """
    messages = state.get("messages", [])
    
    if not messages:
        return "fallback"
    
    last_message = messages[-1]
    
    # Check if last message has tool calls
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    
    # Check if we have a selection
    if state.get("selected_track"):
        return "finalize"
    
    # Try to parse selection from message content
    content = ""
    if hasattr(last_message, "content"):
        content = last_message.content
    elif isinstance(last_message, dict):
        content = last_message.get("content", "")
    
    if content and _contains_selection(content):
        return "finalize"
    
    # Check iteration count
    # Look for special key or count messages
    tool_messages = [m for m in messages if hasattr(m, "type") and m.type == "tool"]
    if len(tool_messages) >= 10:  # Max 10 tool calls
        logger.warning("Max tool calls reached, falling back")
        return "fallback"
    
    logger.info(f"No tools or selection found in message. Content preview: {content[:100] if content else 'Empty'}")
    return "fallback"


def _contains_selection(content: str) -> bool:
    """Check if content contains a track selection."""
    selection = _parse_selection(content)
    if selection:
        return "artist" in selection and "title" in selection
    return False


# =============================================================================
# Nodes
# =============================================================================

async def retrieve_node(state: DJStateV3) -> Dict[str, Any]:
    """
    Retrieve candidate tracks using RAG.
    """
    logger.debug("Retrieving tracks via RAG")
    
    try:
        from backend_v2.langgraph_v3.rag.retriever import retrieve_tracks
        
        retrieved = await retrieve_tracks(state, k=8)
        
        if retrieved:
            logger.info(f"Retrieved {len(retrieved)} candidate tracks via RAG")
            return {
                "retrieved_docs": retrieved,
                "should_retrieve": False,
            }
    except ImportError:
        logger.debug("RAG retriever not available")
    except Exception as e:
        logger.warning(f"RAG retrieval failed: {e}")
    
    return {"should_retrieve": False}


async def select_node(state: DJStateV3) -> Dict[str, Any]:
    """
    Use LLM with tools to select a track.
    """
    import os
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import SystemMessage, HumanMessage
    
    logger.debug("Selecting track with LLM")
    
    # Build LLM
    llm = ChatOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.environ.get("OPENROUTER_API_KEY"),
        model=os.environ.get("OPENROUTER_MODEL", "google/gemini-2.0-flash-001"),
        temperature=0.7,
        default_headers={
            "HTTP-Referer": "https://ai-dj.app",
            "X-Title": "AI DJ v3 Track Selection",
        },
    )
    
    # Get tools
    tools = _get_selection_tools()
    llm_with_tools = llm.bind_tools(tools)
    
    # Build prompt
    system_prompt = _build_selection_system_prompt(state)
    user_prompt = _build_selection_user_prompt(state)
    
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]
    
    # Invoke LLM
    try:
        response = await llm_with_tools.ainvoke(messages)
        
        # Debug logging
        logger.info(f"LLM Response type: {type(response)}")
        logger.info(f"LLM Content: {response.content[:500] if hasattr(response, 'content') else 'No content'}")
        if hasattr(response, "tool_calls"):
            logger.info(f"LLM Tool Calls: {len(response.tool_calls)} - {response.tool_calls}")
        else:
            logger.info("No tool_calls attribute on response")

        # Add response to messages
        return {"messages": [response]}
        
    except Exception as e:
        logger.error(f"LLM selection failed: {e}")
        return {"last_error": str(e)}


async def tools_node(state: DJStateV3) -> Dict[str, Any]:
    """
    Execute tool calls from the LLM.
    """
    from backend_v2.db.session import get_db_session
    from backend_v2.integrations.db_tools import execute_tool
    from langchain_core.messages import ToolMessage
    
    messages = state.get("messages", [])
    if not messages:
        return {}
    
    last_message = messages[-1]
    if not hasattr(last_message, "tool_calls") or not last_message.tool_calls:
        return {}
    
    tool_messages = []
    user_id = state.get("user_id")
    mood_id = state.get("mood_id")
    
    async with get_db_session() as db:
        for tool_call in last_message.tool_calls:
            tool_name = tool_call.get("name", "")
            args = tool_call.get("args", {})
            tool_id = tool_call.get("id", "")
            
            logger.debug(f"Executing tool: {tool_name}")
            
            try:
                # Inject user_id if not provided
                if "user_id" not in args and user_id:
                    args["user_id"] = user_id
                # Only inject mood_id for tools that support/need it
                mood_aware_tools = [
                    "get_play_history",
                    "get_user_feedback",
                    "get_track_intents",
                    "get_feedback_summary",
                    "get_mood_details",
                ]
                
                if "mood_id" not in args and mood_id and tool_name in mood_aware_tools:
                    args["mood_id"] = mood_id
                
                result = await execute_tool(tool_name, args, db)
                
                tool_messages.append(
                    ToolMessage(
                        content=json.dumps(result, default=str),
                        tool_call_id=tool_id,
                        name=tool_name,
                    )
                )
            except Exception as e:
                logger.error(f"Tool execution failed: {tool_name}: {e}")
                tool_messages.append(
                    ToolMessage(
                        content=json.dumps({"error": str(e)}),
                        tool_call_id=tool_id,
                        name=tool_name,
                    )
                )
    
    return {"messages": tool_messages}


async def finalize_node(state: DJStateV3) -> Dict[str, Any]:
    """
    Parse LLM response and extract selected track.
    """
    messages = state.get("messages", [])
    
    # Find last AI message with content
    for message in reversed(messages):
        content = ""
        if hasattr(message, "content"):
            content = message.content
        elif isinstance(message, dict):
            content = message.get("content", "")
        
        if not content:
            continue
        
        # Try to parse JSON selection
        selection = _parse_selection(content)
        if selection:
            # Validate against guardrails
            is_valid, rejection_reason = _validate_selection(state, selection)
            
            if is_valid:
                logger.info(f"Selected track: {selection.get('artist')} - {selection.get('title')}")
                return {
                    "selected_track": selection,
                    "selection_rationale": selection.get("rationale", ""),
                    "selection_source": "llm",
                }
            else:
                logger.warning(f"Selection rejected: {rejection_reason}")
                # Try to get another selection (could loop back)
    
    logger.warning("Could not extract valid selection from LLM response")
    return {}


async def fallback_node(state: DJStateV3) -> Dict[str, Any]:
    """
    Fallback to deterministic track selection from local library.
    """
    from backend_v2.db.session import get_db_session
    from backend_v2.integrations.db_tools import search_songs_in_library
    
    logger.info("Using fallback library-based selection")
    
    mood_targets = state.get("mood_targets") or {}
    songs_played = state.get("songs_played", [])
    disliked_uuids = state.get("disliked_uuids", [])
    
    try:
        async with get_db_session() as db:
            # Try to search by genre from mood
            genres = mood_targets.get("genres", [])
            genre = genres[0] if genres else None
            
            songs = await search_songs_in_library(
                db=db,
                genre=genre,
                limit=20,
            )
            
            # Filter out played and disliked songs
            available = [
                s for s in songs
                if s.get("uuid") not in songs_played
                and s.get("uuid") not in disliked_uuids
            ]
            
            if available:
                track = available[0]
                logger.info(f"Fallback selected: {track.get('artist')} - {track.get('title')}")
                return {
                    "selected_track": {
                        "uuid": track.get("uuid"),
                        "title": track.get("title"),
                        "artist": track.get("artist"),
                        "duration_sec": track.get("duration_sec"),
                        "local_path": track.get("local_path"),
                        "artwork_url": track.get("artwork_url"),
                    },
                    "selection_source": "fallback",
                    "selection_rationale": "Library search fallback",
                }
            
            # If no genre match, try without genre filter
            if genre:
                songs = await search_songs_in_library(
                    db=db,
                    limit=20,
                )
                
                available = [
                    s for s in songs
                    if s.get("uuid") not in songs_played
                    and s.get("uuid") not in disliked_uuids
                ]
                
                if available:
                    track = available[0]
                    logger.info(f"Fallback selected (no genre): {track.get('artist')} - {track.get('title')}")
                    return {
                        "selected_track": {
                            "uuid": track.get("uuid"),
                            "title": track.get("title"),
                            "artist": track.get("artist"),
                            "duration_sec": track.get("duration_sec"),
                            "local_path": track.get("local_path"),
                            "artwork_url": track.get("artwork_url"),
                        },
                        "selection_source": "fallback",
                        "selection_rationale": "Library search fallback (any genre)",
                    }
                
    except Exception as e:
        logger.error(f"Fallback selection failed: {e}")
    
    return {"last_error": "No tracks available for selection"}


async def validate_node(state: DJStateV3) -> Dict[str, Any]:
    """
    Final validation of selected track.
    """
    track = state.get("selected_track")
    if not track:
        return {}
    
    # Add artist cooldown
    artist = track.get("artist")
    if artist:
        return add_artist_cooldown(state, artist, segments=5)
    
    return {}


# =============================================================================
# Helper Functions
# =============================================================================

def _get_selection_tools() -> List[Dict[str, Any]]:
    """Get tool definitions for track selection."""
    from backend_v2.integrations.db_tools import DB_TOOLS
    
    # Filter to selection-relevant tools
    selection_tools = [
        "get_play_history",
        "get_artist_play_count",
        "search_songs_in_library",
        "get_user_feedback",
        "get_spotify_context",
        "get_mood_details",
        "search_spotify_catalog",
    ]
    
    return [
        tool for tool in DB_TOOLS
        if tool.get("function", {}).get("name") in selection_tools
    ]


def _build_selection_system_prompt(state: DJStateV3) -> str:
    """Build system prompt for track selection."""
    mood_targets = state.get("mood_targets") or {}
    
    return f"""You are an expert AI DJ selecting the next track for a personalized radio session.

## Current Mood: {mood_targets.get('mood_name', 'Unknown')}
- Energy Target: {mood_targets.get('energy_target', 0.5)}
- Valence Target: {mood_targets.get('valence_target', 0.5)}
- Genres: {', '.join(mood_targets.get('genres', [])[:5])}
- Example Artists: {', '.join(mood_targets.get('example_artists', [])[:5])}

## Your Task
1. Use the available tools to understand the user's preferences and history
2. Select a track that matches the mood and won't repeat recently played content
3. Ensure variety - avoid playing the same artist within 5 tracks

## Output Format
After your analysis, output a JSON object:
```json
{{
    "artist": "Artist Name",
    "title": "Track Title",
    "rationale": "Brief explanation of why this track fits"
}}
```

## Rules
- You MUST use at least one tool before making your selection
- Never select a track that was played in the last 10 songs
- Never select a disliked track
- Prefer tracks from the user's Spotify top artists when appropriate
- Balance familiarity with discovery
"""


def _build_selection_user_prompt(state: DJStateV3) -> str:
    """Build user prompt for track selection."""
    last_song = state.get("last_song") or {}
    songs_played = state.get("songs_played", [])[-10:]
    spotify_artists = state.get("spotify_top_artists", [])[:5]
    
    parts = ["Select the next track for this DJ session."]
    
    if last_song:
        parts.append(f"\nLast played: {last_song.get('artist', 'Unknown')} - {last_song.get('title', 'Unknown')}")
    
    if songs_played:
        parts.append(f"\nRecently played ({len(songs_played)} tracks) - avoid repeating these.")
    
    if spotify_artists:
        artist_names = [a.get("name") for a in spotify_artists if a.get("name")]
        parts.append(f"\nUser's top Spotify artists: {', '.join(artist_names)}")
    
    parts.append("\n\nUse the tools to gather more context, then make your selection.")
    
    return "\n".join(parts)


def _parse_selection(content: str) -> Optional[Dict[str, Any]]:
    """Parse track selection from LLM content."""
    # Try to extract JSON from content
    import re
    
    # Look for JSON block
    json_match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass
    
    # Try parsing raw JSON
    try:
        # Find JSON object in content
        json_match = re.search(r'\{[^{}]*"artist"[^{}]*\}', content)
        if json_match:
            return json.loads(json_match.group(0))
    except json.JSONDecodeError:
        pass
    
    # Try full content as JSON
    try:
        data = json.loads(content)
        if isinstance(data, dict) and "artist" in data:
            return data
    except json.JSONDecodeError:
        pass
    
    return None


def _validate_selection(state: DJStateV3, selection: Dict[str, Any]) -> tuple[bool, str]:
    """Validate track selection against guardrails."""
    artist = selection.get("artist", "").lower()
    title = selection.get("title", "").lower()
    
    if not artist or not title:
        return False, "Missing artist or title"
    
    # Check blocked artists
    blocked = [a.lower() for a in state.get("blocked_artists", [])]
    if artist in blocked:
        return False, f"Artist '{artist}' is blocked"
    
    # Check cooldown
    if not check_artist_cooldown(state, artist):
        return False, f"Artist '{artist}' is on cooldown"
    
    # Check recent plays
    recent_artists = [a.lower() for a in state.get("recent_artists", [])[-5:]]
    if artist in recent_artists:
        return False, f"Artist '{artist}' was played recently"
    
    return True, ""


# =============================================================================
# Graph Builder
# =============================================================================

def build_track_selection_graph() -> StateGraph:
    """
    Build the TrackSelectionGraph subgraph.
    
    Flow:
    1. Route: retrieve or select
    2. retrieve (optional) - RAG retrieval
    3. select - LLM with tools
    4. tools - Execute tool calls (loops back to select)
    5. finalize - Extract selection
    6. fallback - Deterministic fallback
    7. validate - Final validation
    """
    graph = StateGraph(DJStateV3)
    
    # Add nodes
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("select", select_node)
    graph.add_node("tools", tools_node)
    graph.add_node("finalize", finalize_node)
    graph.add_node("fallback", fallback_node)
    graph.add_node("validate", validate_node)
    
    # Set entry point with conditional routing
    graph.set_conditional_entry_point(
        should_retrieve,
        {
            "retrieve": "retrieve",
            "select": "select",
        }
    )
    
    # Retrieve -> Select
    graph.add_edge("retrieve", "select")
    
    # Select -> conditional routing
    graph.add_conditional_edges(
        "select",
        should_continue_tools,
        {
            "tools": "tools",
            "finalize": "finalize",
            "fallback": "fallback",
        }
    )
    
    # Tools -> Select (loop)
    graph.add_edge("tools", "select")
    
    # Finalize/Fallback -> Validate
    graph.add_edge("finalize", "validate")
    graph.add_edge("fallback", "validate")
    
    # Validate -> END
    graph.add_edge("validate", END)
    
    return graph


def get_track_selection_subgraph():
    """Get compiled track selection subgraph."""
    return build_track_selection_graph().compile()
