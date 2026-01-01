"""Agentic training agents with dynamic tool calling.

Similar to tool_based_selector.py, but for training.
Agents can decide which tools to use based on feedback context.
"""
import json
import logging
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from backend_v2.integrations.openrouter import get_openrouter_client
from backend_v2.integrations.db_tools import DB_TOOLS, execute_tool
from backend_v2.models.mood import Mood
from backend_v2.orchestration.events import get_event_emitter
from backend_v2.schemas.status_events import StatusCategory, StatusStep

logger = logging.getLogger("ai-dj.agentic-trainer")


async def train_with_tools(
    db: AsyncSession,
    mood_id: str,
    user_id: str,
    feedback_type: str,  # "like", "dislike", "skip"
    track_artist: str,
    track_title: str,
    max_iterations: int = 5,
    require_tool_calls: bool = True,
) -> Dict[str, Any]:
    """Train mood using agentic tool calling.
    
    The AI can dynamically decide which tools to use:
    - get_play_history: Check if artist is overplayed
    - get_artist_play_count: Count recent plays
    - get_user_feedback: See past feedback patterns
    - get_deezer_related_artists: Find similar artists (NEW)
    - get_spotify_context: Access user's Spotify preferences
    - analyze_listening_patterns: Understand user habits
    
    Returns:
        Dict with training results including:
        - artists_added: List of artists added
        - artists_removed: List of artists removed
        - reasoning: LLM explanation
        - tool_calls: Number of tools used
    """
    client = get_openrouter_client()
    if not client.enabled:
        logger.warning("OpenRouter disabled, cannot use agentic training")
        return {"success": False, "error": "OpenRouter disabled"}
    
    # Get mood
    from sqlalchemy import select
    result = await db.execute(select(Mood).where(Mood.id == mood_id))
    mood = result.scalar_one_or_none()
    if not mood:
        return {"success": False, "error": "Mood not found"}
    
    # Build system prompt with tool descriptions
    system_prompt = _build_training_system_prompt(mood, feedback_type)
    
    # Build user prompt with context
    user_prompt = _build_training_user_prompt(
        mood, feedback_type, track_artist, track_title
    )
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    
    # Add Deezer similarity tool to available tools
    training_tools = DB_TOOLS + [DEEZER_RELATED_ARTISTS_TOOL]
    
    # Emit training started status
    emitter = get_event_emitter()
    await emitter.emit_status(
        user_id=user_id,
        category=StatusCategory.TRAINING,
        step=StatusStep.TRAINING_STARTED,
        user_message=f"Learning from your {feedback_type}...",
        debug_message=f"Training mood with agentic tools for {track_artist} - {track_title}",
    )
    
    iteration = 0
    tool_calls_count = 0
    tool_calls_made = False
    tool_call_retry = False
    
    while iteration < max_iterations:
        iteration += 1
        logger.debug(f"Training iteration {iteration}/{max_iterations}")
        
        # Call LLM with tools
        result = await client.chat_completion(
            messages=messages,
            temperature=0.7,
            tools=training_tools,
            tool_choice="auto",
            session_id=None,
            db=db,
            user_id=user_id,
            mood_id=mood_id,
            agent_name=f"train_from_{feedback_type}_agentic",
        )
        
        if not result:
            return {"success": False, "error": "LLM call failed"}
        
        tool_calls = result.get("tool_calls", [])
        content = result.get("content", "")
        
        if tool_calls:
            tool_calls_made = True
        
        # If no tool calls, LLM is done - parse final decision
        if not tool_calls:
            if require_tool_calls and not tool_calls_made and not tool_call_retry:
                messages.append({"role": "assistant", "content": content})
                messages.append({
                    "role": "user",
                    "content": "You must call at least one tool before making a final decision. "
                               "Use the tools now and then respond with the final JSON decision.",
                })
                tool_call_retry = True
                continue

            decision = _parse_training_decision(content)
            
            # Check for valid decision keys
            valid_keys = ["artists_to_add", "artists_to_remove", "artists_to_demote", "reasoning"]
            has_decision = decision.get("final_decision") or any(k in decision for k in valid_keys)
            
            if has_decision:
                logger.info(f"Training complete after {iteration} iterations, {tool_calls_count} tools")
                
                # Emit training complete status
                await emitter.emit_status(
                    user_id=user_id,
                    category=StatusCategory.TRAINING,
                    step=StatusStep.TRAINING_COMPLETE,
                    user_message="Updated your preferences",
                    debug_message=f"Training applied after {iteration} iterations, {tool_calls_count} tools",
                )
                
                return {
                    "success": True,
                    "decision": decision,
                    "tool_calls": tool_calls_count,
                    "iterations": iteration,
                }
            else:
                logger.warning(f"No final decision from LLM. Content: {content[:200]}...")
                await emitter.emit_status(
                    user_id=user_id,
                    category=StatusCategory.TRAINING,
                    step=StatusStep.TRAINING_COMPLETE,
                    user_message="No changes applied",
                    debug_message="Training skipped: no final decision from LLM",
                )
                return {
                    "success": True,
                    "decision": {
                        "final_decision": True,
                        "artists_to_add": [],
                        "artists_to_remove": [],
                        "artists_to_demote": [],
                        "genres_to_add": [],
                        "genres_to_avoid": [],
                        "reasoning": "No final decision from LLM; no changes applied.",
                    },
                    "tool_calls": tool_calls_count,
                    "iterations": iteration,
                    "fallback": True,
                }
        
        # Execute tool calls
        tool_results = []
        for tool_call in tool_calls:
            tool_calls_count += 1
            function_name = tool_call.get("function", {}).get("name")
            arguments_str = tool_call.get("function", {}).get("arguments", "{}")
            
            try:
                arguments = json.loads(arguments_str) if isinstance(arguments_str, str) else arguments_str
            except json.JSONDecodeError:
                arguments = {}
            
            logger.debug(f"Executing tool: {function_name}({arguments})")
            
            # Execute tool
            if function_name == "get_deezer_related_artists":
                tool_result = await execute_deezer_related_artists(
                    arguments, db, user_id, mood_id, f"train_from_{feedback_type}_agentic"
                )
            else:
                tool_result = await execute_tool(
                    function_name, arguments, db,
                    user_id=user_id, mood_id=mood_id,
                    agent_name=f"train_from_{feedback_type}_agentic",
                    auto_log=True  # NOW ENABLED
                )
            
            tool_results.append({
                "tool_call_id": tool_call.get("id"),
                "role": "tool",
                "name": function_name,
                "content": json.dumps(tool_result),
            })
        
        # Add assistant message with tool calls to conversation
        assistant_message = {
            "role": "assistant",
            "content": content,
            "tool_calls": tool_calls,
        }
        messages.append(assistant_message)
        messages.extend(tool_results)

        if iteration >= max_iterations - 1:
            # Force a final decision without further tool calls.
            messages.append({
                "role": "user",
                "content": "Based on the tool results above, provide the final JSON decision now. "
                           "Do not call tools.",
            })
            final_result = await client.chat_completion(
                messages=messages,
                temperature=0.3,
                json_mode=True,
                tools=None,
                tool_choice=None,
                session_id=None,
                db=db,
                user_id=user_id,
                mood_id=mood_id,
                agent_name=f"train_from_{feedback_type}_agentic",
                auto_log=True,
            )
            if final_result:
                decision = final_result.get("parsed") or _parse_training_decision(
                    final_result.get("content", "")
                )
                valid_keys = ["artists_to_add", "artists_to_remove", "artists_to_demote", "reasoning"]
                has_decision = decision.get("final_decision") or any(k in decision for k in valid_keys)
                if has_decision:
                    logger.info(f"Training complete after {iteration + 1} iterations, {tool_calls_count} tools")
                    await emitter.emit_status(
                        user_id=user_id,
                        category=StatusCategory.TRAINING,
                        step=StatusStep.TRAINING_COMPLETE,
                        user_message="Updated your preferences",
                        debug_message=f"Training applied after {iteration + 1} iterations, {tool_calls_count} tools",
                    )
                    return {
                        "success": True,
                        "decision": decision,
                        "tool_calls": tool_calls_count,
                        "iterations": iteration + 1,
                    }
            
            logger.warning("Forced finalization failed to produce a valid decision")
            await emitter.emit_status(
                user_id=user_id,
                category=StatusCategory.TRAINING,
                step=StatusStep.TRAINING_COMPLETE,
                user_message="No changes applied",
                debug_message="Training skipped: forced finalization had no valid decision",
            )
            return {
                "success": True,
                "decision": {
                    "final_decision": True,
                    "artists_to_add": [],
                    "artists_to_remove": [],
                    "artists_to_demote": [],
                    "genres_to_add": [],
                    "genres_to_avoid": [],
                    "reasoning": "Forced finalization returned no valid decision; no changes applied.",
                },
                "tool_calls": tool_calls_count,
                "iterations": iteration + 1,
                "fallback": True,
            }
        
        # Continue loop for next LLM call
    
    logger.warning(f"Max iterations ({max_iterations}) reached without final decision")
    await emitter.emit_status(
        user_id=user_id,
        category=StatusCategory.TRAINING,
        step=StatusStep.TRAINING_COMPLETE,
        user_message="No changes applied",
        debug_message="Training skipped: max iterations reached without decision",
    )
    return {
        "success": True,
        "decision": {
            "final_decision": True,
            "artists_to_add": [],
            "artists_to_remove": [],
            "artists_to_demote": [],
            "genres_to_add": [],
            "genres_to_avoid": [],
            "reasoning": "Max iterations reached without a decision; no changes applied.",
        },
        "tool_calls": tool_calls_count,
        "iterations": max_iterations,
        "fallback": True,
    }


def _build_training_system_prompt(mood: Mood, feedback_type: str) -> str:
    """Build system prompt for agentic training."""
    feedback_guidance = {
        "like": """The user LIKED a track. This is a POSITIVE signal.
Your job:
1. Use tools to understand WHY they liked it (check their history, preferences)
2. Find similar artists to add to the mood
3. Strengthen the mood's alignment with this preference
4. Be bold - add 3-5 similar artists if appropriate""",
        
        "dislike": """The user DISLIKED a track. This is a NEGATIVE signal.
Your job:
1. Remove or demote this artist from the mood
2. Find alternative artists with similar energy but different style
3. Add genres to avoid list if appropriate
4. Be decisive - strongly demote disliked content""",
        
        "skip": """The user SKIPPED a track. This is a WEAK/AMBIGUOUS signal.
Skips can mean:
- Not in the mood right now (timing)
- Heard it too recently (check play history!)
- Wrong energy/vibe for this mood
- Artist is overplayed (check frequency!)

Your job:
1. Use tools to understand WHY (play count, recent history, feedback)
2. Only demote if there's clear evidence (multiple skips, overplayed, etc.)
3. Soft adjustments - move to end of list rather than remove
4. Don't overreact to a single skip"""
    }
    
    # Build mood description from available fields
    mood_desc_parts = []
    if mood.vibe_keywords_json:
        try:
            keywords = json.loads(mood.vibe_keywords_json) or []
            if keywords:
                mood_desc_parts.append(f"Keywords: {', '.join(keywords[:5])}")
        except:
            pass
    
    mood_description = "\n".join(mood_desc_parts) if mood_desc_parts else "No additional description"
    
    return f"""You are an expert music training AI with access to database tools.

{feedback_guidance.get(feedback_type, "")}

**Current Mood**: {mood.name}
- Energy: {mood.energy_target}
- Valence: {mood.valence_target}
- {mood_description}

**Available Tools**:
1. get_play_history - Query recent plays (filter by artist, time)
2. get_artist_play_count - Check if artist is overplayed
3. get_user_feedback - See past likes/dislikes
4. get_deezer_related_artists - Find similar artists (NEW!)
5. get_spotify_context - Access Spotify preferences
6. analyze_listening_patterns - Understand habits

**Process**:
1. First, use tools to gather context
2. Analyze the feedback in context of user's history
3. Make informed decisions about mood adjustments
4. Respond with final JSON decision

**Final Decision Format**:
You MUST respond with this JSON format when you are done using tools:
```json
{{
  "final_decision": true,
  "artists_to_add": ["Artist 1"],
  "artists_to_remove": [],
  "artists_to_demote": [],
  "genres_to_add": [],
  "genres_to_avoid": [],
  "reasoning": "Reasoning here"
}}
```

You MUST call at least one tool before outputting the final decision JSON."""


def _build_training_user_prompt(
    mood: Mood,
    feedback_type: str,
    track_artist: str,
    track_title: str
) -> str:
    """Build user prompt with feedback context."""
    emoji = {"like": "❤️", "dislike": "👎", "skip": "⏭️"}.get(feedback_type, "🎵")
    
    existing_artists = []
    if mood.example_artists_json:
        try:
            existing_artists = json.loads(mood.example_artists_json) or []
        except:
            pass
    
    return f"""User feedback: {emoji} {feedback_type.upper()}
Track: {track_artist} - {track_title}

Current mood artists ({len(existing_artists)}):
{', '.join(existing_artists[:10])}{"..." if len(existing_artists) > 10 else ""}

Use your tools to analyze this feedback and decide how to update the mood."""


def _parse_training_decision(content: str) -> Dict[str, Any]:
    """Parse LLM's final decision from content."""
    try:
        # Try to extract JSON from content
        if "```json" in content:
            start = content.find("```json") + 7
            end = content.find("```", start)
            json_str = content[start:end].strip()
        elif "```" in content:
            start = content.find("```") + 3
            end = content.find("```", start)
            json_str = content[start:end].strip()
        else:
            json_str = content.strip()
        
        return json.loads(json_str)
    except:
        logger.warning(f"Failed to parse decision from: {content[:200]}")
        return {}


# Deezer similarity tool definition (added to DB_TOOLS for training)
DEEZER_RELATED_ARTISTS_TOOL = {
    "type": "function",
    "function": {
        "name": "get_deezer_related_artists",
        "description": "Get related/similar artists from Deezer for music discovery. Returns artists with similar style/genre.",
        "parameters": {
            "type": "object",
            "properties": {
                "artist_name": {
                    "type": "string",
                    "description": "Artist name to find similar artists for"
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results to return (default 5, max 20)",
                    "default": 5
                }
            },
            "required": ["artist_name"]
        }
    }
}


async def execute_deezer_related_artists(
    arguments: Dict[str, Any],
    db: AsyncSession,
    user_id: str,
    mood_id: str,
    agent_name: str,
) -> List[Dict[str, Any]]:
    """Execute Deezer related artists lookup with logging."""
    from backend_v2.integrations.deezer import get_deezer_client
    from backend_v2.models.existing import ToolUsageLog
    import time
    
    start_time = time.time()
    artist_name = arguments.get("artist_name", "")
    limit = min(arguments.get("limit", 5), 20)
    
    try:
        client = get_deezer_client()
        # Search for artist
        search_result = await client.search_artist(artist_name)
        
        if not search_result or not search_result.get("data"):
            return []
        
        artist_id = search_result["data"][0]["id"]
        
        # Get related artists
        related = await client.get_related_artists(artist_id, limit=limit)
        
        if not related or not related.get("data"):
            return []
        
        result = [
            {"name": artist["name"], "id": artist["id"]}
            for artist in related["data"]
        ]
        
        # Log tool usage
        execution_time = (time.time() - start_time) * 1000
        tool_log = ToolUsageLog(
            tool_name="get_deezer_related_artists",
            tool_arguments=json.dumps(arguments),
            tool_result=json.dumps(result),
            success=True,
            execution_time_ms=execution_time,
            session_id=None,
            user_id=user_id,
        )
        db.add(tool_log)
        await db.flush()
        
        logger.debug(f"Found {len(result)} related artists for {artist_name}")
        return result
        
    except Exception as e:
        logger.error(f"Deezer related artists error: {e}")
        
        # Log failure
        execution_time = (time.time() - start_time) * 1000
        tool_log = ToolUsageLog(
            tool_name="get_deezer_related_artists",
            tool_arguments=json.dumps(arguments),
            tool_result=None,
            success=False,
            error_message=str(e),
            execution_time_ms=execution_time,
            session_id=None,
            user_id=user_id,
        )
        db.add(tool_log)
        await db.flush()
        
        return []


async def apply_training_decision_with_metrics(
    db: AsyncSession,
    mood_id: str,
    user_id: str,
    decision: Dict[str, Any],
    feedback_type: str,
    track_artist: str,
    track_title: str,
    tool_calls_made: int,
    llm_tokens: int,
) -> bool:
    """Apply training decision to mood and track metrics.
    
    Args:
        db: Database session
        mood_id: Mood ID
        user_id: User ID
        decision: LLM decision dict with artists_to_add, artists_to_remove, etc.
        feedback_type: like, dislike, skip, batch
        track_artist: Track artist
        track_title: Track title
        tool_calls_made: Number of tools used
        llm_tokens: LLM tokens consumed
        
    Returns:
        True if successful
    """
    from sqlalchemy import select
    from backend_v2.models.mood import Mood
    from backend_v2.models.training_metrics import TrainingMetrics
    
    # Get mood
    mood_result = await db.execute(select(Mood).where(Mood.id == mood_id))
    mood = mood_result.scalar_one_or_none()
    if not mood:
        return False
    
    # Get existing artists before changes
    existing_artists_before = []
    if mood.example_artists_json:
        try:
            existing_artists_before = json.loads(mood.example_artists_json) or []
        except:
            pass
    
    # Apply artists_to_add
    artists_to_add = decision.get("artists_to_add", [])
    existing_artists = existing_artists_before.copy()
    added_count = 0
    
    for artist in artists_to_add:
        if artist and artist not in existing_artists:
            existing_artists.insert(0, artist)
            added_count += 1
    
    # Apply artists_to_remove
    artists_to_remove = decision.get("artists_to_remove", [])
    removed_count = 0
    
    for artist in artists_to_remove:
        if artist:
            before_len = len(existing_artists)
            existing_artists = [a for a in existing_artists if a.lower() != artist.lower()]
            removed_count += (before_len - len(existing_artists))
    
    # Apply artists_to_demote (move to end of list)
    artists_to_demote = decision.get("artists_to_demote", [])
    demoted_count = 0
    
    for artist in artists_to_demote:
        if artist and artist in existing_artists:
            existing_artists.remove(artist)
            existing_artists.append(artist)
            demoted_count += 1
    
    # Update mood
    mood.example_artists_json = json.dumps(existing_artists[:25])
    
    # Update genres
    genres_to_add = decision.get("genres_to_add", [])
    if genres_to_add:
        existing_genres = []
        if mood.genre_seeds_json:
            try:
                existing_genres = json.loads(mood.genre_seeds_json) or []
            except:
                pass
        
        for genre in genres_to_add:
            if genre and genre not in existing_genres:
                existing_genres.insert(0, genre)
        
        mood.genre_seeds_json = json.dumps(existing_genres[:10])
    
    # Track metrics
    agent_name = f"train_from_{feedback_type}_agentic"
    metrics = TrainingMetrics(
        mood_id=mood_id,
        user_id=user_id,
        agent_name=agent_name,
        feedback_type=feedback_type,
        track_artist=track_artist,
        track_title=track_title,
        artists_before=json.dumps(existing_artists_before[:25]),
        artists_after=json.dumps(existing_artists[:25]),
        artists_added=added_count,
        artists_removed=removed_count,
        artists_demoted=demoted_count,
        llm_reasoning=decision.get("reasoning", ""),
        tool_calls_made=tool_calls_made,
        llm_tokens=llm_tokens,
    )
    db.add(metrics)
    
    await db.commit()
    
    # Invalidate cache
    from backend_v2.services.preference_bundle import get_bundle_cache
    cache = get_bundle_cache()
    cache.invalidate(user_id)
    
    logger.info(f"🎓 Applied training decision: +{added_count} -{removed_count} ↓{demoted_count} artists")
    
    return True
