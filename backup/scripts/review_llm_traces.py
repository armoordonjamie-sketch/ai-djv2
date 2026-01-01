"""Review LLM traces for the last 3 streams to analyze song selection.

This script reviews LLM traces to understand:
1. Whether Spotify data is being included in prompts
2. Whether user onboarding context is being used
3. What tools are being called
4. What prompts are being sent to the LLM
"""
import asyncio
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any

# Add parent directory to path and ensure we're in the right directory
script_dir = Path(__file__).parent
project_root = script_dir.parent.parent
sys.path.insert(0, str(project_root))

# Change to project root so database path resolves correctly
os.chdir(project_root)

from sqlalchemy import select, desc, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend_v2.db.session import async_session_factory
from backend_v2.models.existing import LLMTrace, ToolUsageLog, Session
from backend_v2.models.user_profile import UserProfile
from backend_v2.models.spotify_context import SpotifyUserContext
from backend_v2.models.mood import Mood


async def get_recent_sessions(db: AsyncSession, limit: int = 3) -> List[Session]:
    """Get the most recent streaming sessions."""
    stmt = (
        select(Session)
        .where(Session.is_active == 0)  # Completed sessions
        .order_by(desc(Session.started_at))
        .limit(limit)
    )
    result = await db.execute(stmt)
    return result.scalars().all()


async def get_llm_traces_for_session(
    db: AsyncSession, 
    session_id: str,
    agent_name: Optional[str] = None
) -> List[LLMTrace]:
    """Get all LLM traces for a session."""
    stmt = select(LLMTrace).where(
        LLMTrace.session_id == session_id
    )
    if agent_name:
        stmt = stmt.where(LLMTrace.agent_name == agent_name)
    stmt = stmt.order_by(LLMTrace.created_at)
    result = await db.execute(stmt)
    return result.scalars().all()


async def get_tool_logs_for_trace(
    db: AsyncSession,
    llm_trace_id: int
) -> List[ToolUsageLog]:
    """Get tool usage logs for an LLM trace."""
    stmt = select(ToolUsageLog).where(
        ToolUsageLog.llm_trace_id == llm_trace_id
    ).order_by(ToolUsageLog.created_at)
    result = await db.execute(stmt)
    return result.scalars().all()


async def get_user_profile(db: AsyncSession, user_id: str) -> Optional[UserProfile]:
    """Get user profile."""
    stmt = select(UserProfile).where(UserProfile.user_id == user_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_spotify_context(db: AsyncSession, user_id: str) -> Optional[SpotifyUserContext]:
    """Get Spotify context."""
    stmt = select(SpotifyUserContext).where(SpotifyUserContext.user_id == user_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


def analyze_prompt_for_spotify_data(prompt: str) -> Dict[str, Any]:
    """Analyze prompt to see if Spotify data is included."""
    analysis = {
        "has_spotify_mention": False,
        "has_top_tracks": False,
        "has_top_artists": False,
        "has_genre_analysis": False,
        "has_listening_data": False,
        "spotify_keywords_found": [],
    }
    
    prompt_lower = prompt.lower()
    
    # Check for Spotify mentions
    if "spotify" in prompt_lower:
        analysis["has_spotify_mention"] = True
        analysis["spotify_keywords_found"].append("spotify")
    
    # Check for top tracks
    if "top track" in prompt_lower or "favorite track" in prompt_lower:
        analysis["has_top_tracks"] = True
        analysis["spotify_keywords_found"].append("top_tracks")
    
    # Check for top artists
    if "top artist" in prompt_lower or "favorite artist" in prompt_lower:
        analysis["has_top_artists"] = True
        analysis["spotify_keywords_found"].append("top_artists")
    
    # Check for genre analysis
    if "genre analysis" in prompt_lower or "spotify genre" in prompt_lower:
        analysis["has_genre_analysis"] = True
        analysis["spotify_keywords_found"].append("genre_analysis")
    
    # Check for listening data
    if "listening data" in prompt_lower or "listening habit" in prompt_lower:
        analysis["has_listening_data"] = True
        analysis["spotify_keywords_found"].append("listening_data")
    
    return analysis


def analyze_prompt_for_user_context(prompt: str) -> Dict[str, Any]:
    """Analyze prompt to see if user onboarding context is included."""
    analysis = {
        "has_display_name": False,
        "has_favorite_genres": False,
        "has_favorite_artists": False,
        "has_favorite_songs": False,
        "has_no_go": False,
        "has_energy_preference": False,
        "has_tempo_preference": False,
        "has_listening_contexts": False,
        "has_era_preference": False,
        "has_dj_personality": False,
        "context_keywords_found": [],
    }
    
    prompt_lower = prompt.lower()
    
    # Check for display name
    if "user:" in prompt_lower or "display name" in prompt_lower:
        analysis["has_display_name"] = True
        analysis["context_keywords_found"].append("display_name")
    
    # Check for favorite genres
    if "favorite genre" in prompt_lower:
        analysis["has_favorite_genres"] = True
        analysis["context_keywords_found"].append("favorite_genres")
    
    # Check for favorite artists
    if "favorite artist" in prompt_lower:
        analysis["has_favorite_artists"] = True
        analysis["context_keywords_found"].append("favorite_artists")
    
    # Check for favorite songs
    if "favorite song" in prompt_lower or "favorite track" in prompt_lower:
        analysis["has_favorite_songs"] = True
        analysis["context_keywords_found"].append("favorite_songs")
    
    # Check for no-go
    if "avoid" in prompt_lower or "no-go" in prompt_lower or "hates" in prompt_lower:
        analysis["has_no_go"] = True
        analysis["context_keywords_found"].append("no_go")
    
    # Check for energy preference
    if "energy preference" in prompt_lower or "high energy" in prompt_lower or "low energy" in prompt_lower:
        analysis["has_energy_preference"] = True
        analysis["context_keywords_found"].append("energy_preference")
    
    # Check for tempo preference
    if "tempo preference" in prompt_lower or "fast tempo" in prompt_lower or "slow tempo" in prompt_lower:
        analysis["has_tempo_preference"] = True
        analysis["context_keywords_found"].append("tempo_preference")
    
    # Check for listening contexts
    if "listening context" in prompt_lower or "listens during" in prompt_lower:
        analysis["has_listening_contexts"] = True
        analysis["context_keywords_found"].append("listening_contexts")
    
    # Check for era preference
    if "era preference" in prompt_lower or "new release" in prompt_lower or "classic" in prompt_lower:
        analysis["has_era_preference"] = True
        analysis["context_keywords_found"].append("era_preference")
    
    # Check for DJ personality
    if "dj style" in prompt_lower or "dj personality" in prompt_lower or "personality" in prompt_lower:
        analysis["has_dj_personality"] = True
        analysis["context_keywords_found"].append("dj_personality")
    
    return analysis


def format_trace(trace: LLMTrace, tools: List[ToolUsageLog]) -> Dict[str, Any]:
    """Format an LLM trace for display."""
    prompt = trace.prompt or ""
    response = trace.response or ""
    
    spotify_analysis = analyze_prompt_for_spotify_data(prompt)
    context_analysis = analyze_prompt_for_user_context(prompt)
    
    # Parse response JSON to check for tool_calls
    response_tool_calls = None
    response_data = {}
    try:
        response_data = json.loads(response) if response else {}
        response_tool_calls = response_data.get('tool_calls')
    except json.JSONDecodeError:
        pass
    
    return {
        "trace_id": trace.id,
        "agent_name": trace.agent_name,
        "model": trace.model,
        "created_at": trace.created_at,
        "user_id": trace.user_id,
        "mood_id": trace.mood_id,
        "prompt_length": len(prompt),
        "response_length": len(response),
        "spotify_analysis": spotify_analysis,
        "context_analysis": context_analysis,
        "response_tool_calls": response_tool_calls,
        "response_has_tool_calls": bool(response_tool_calls),
        "tools_called": [
            {
                "name": tool.tool_name,
                "arguments": tool.tool_arguments,
                "success": bool(tool.success),
                "execution_time_ms": tool.execution_time_ms,
            }
            for tool in tools
        ],
        "prompt_preview": prompt[:500] + "..." if len(prompt) > 500 else prompt,
        "response_preview": response[:500] + "..." if len(response) > 500 else response,
        "response_data": response_data,
    }


async def main():
    """Main review function."""
    print("=" * 80)
    print("LLM TRACE REVIEW - Last 3 Streams")
    print("=" * 80)
    print()
    
    async with async_session_factory() as db:
        # Get recent sessions (including active ones)
        stmt = (
            select(Session)
            .order_by(desc(Session.started_at))
            .limit(3)
        )
        result = await db.execute(stmt)
        sessions = result.scalars().all()
        
        if not sessions:
            print("❌ No completed sessions found.")
            return
        
        print(f"Found {len(sessions)} recent session(s)\n")
        
        for i, session in enumerate(sessions, 1):
            print("=" * 80)
            print(f"SESSION {i}: {session.session_id}")
            print(f"User: {session.user_id}")
            print(f"Started: {session.started_at}")
            print(f"Ended: {session.ended_at}")
            print("=" * 80)
            print()
            
            # Get user profile and Spotify context
            if session.user_id:
                profile = await get_user_profile(db, session.user_id)
                spotify_context = await get_spotify_context(db, session.user_id)
                
                print("USER PROFILE:")
                if profile:
                    print(f"  [OK] Profile exists")
                    print(f"  - Display Name: {profile.display_name}")
                    print(f"  - Favorite Genres: {profile.favorite_genres}")
                    print(f"  - Favorite Artists: {profile.favorite_artists}")
                    print(f"  - Favorite Songs: {profile.favorite_songs}")
                    print(f"  - Energy Preference: {profile.energy_preference}")
                    print(f"  - Tempo Preference: {profile.tempo_preference}")
                    print(f"  - Listening Contexts: {profile.listening_contexts}")
                    print(f"  - Era Preference: {profile.era_preference}")
                    print(f"  - DJ Personality: {profile.dj_personality}")
                else:
                    print("  [X] No profile found")
                
                print()
                print("SPOTIFY CONTEXT:")
                if spotify_context:
                    print(f"  [OK] Spotify connected")
                    print(f"  - Has top artists: {bool(spotify_context.top_artists_json)}")
                    print(f"  - Has favorite tracks: {bool(spotify_context.favorite_tracks_with_stats_json)}")
                    print(f"  - Has genre analysis: {bool(spotify_context.genres_analysis_json)}")
                    print(f"  - Has mood analysis: {bool(spotify_context.mood_analysis_json)}")
                    print(f"  - Has listening habits: {bool(spotify_context.listening_habits_json)}")
                else:
                    print("  [X] No Spotify context found")
                
                print()
            
            # Get LLM traces for catalog selection
            traces = await get_llm_traces_for_session(
                db, 
                session.session_id,
                agent_name="catalog_selector"
            )
            
            if not traces:
                # Try without agent filter
                traces = await get_llm_traces_for_session(db, session.session_id)
            
            print(f"LLM TRACES: {len(traces)} trace(s) found")
            print()
            
            for trace in traces:
                tools = await get_tool_logs_for_trace(db, trace.id)
                formatted = format_trace(trace, tools)
                
                print(f"  Trace #{formatted['trace_id']} ({formatted['agent_name']})")
                print(f"  Model: {formatted['model']}")
                print(f"  Created: {formatted['created_at']}")
                print(f"  Prompt length: {formatted['prompt_length']} chars")
                print(f"  Response length: {formatted['response_length']} chars")
                print()
                
                # Spotify analysis
                spotify = formatted['spotify_analysis']
                print("  SPOTIFY DATA IN PROMPT:")
                if spotify['has_spotify_mention']:
                    print(f"    [OK] Spotify mentioned")
                    print(f"    Keywords found: {', '.join(spotify['spotify_keywords_found'])}")
                else:
                    print("    [X] No Spotify data found in prompt")
                print()
                
                # Context analysis
                context = formatted['context_analysis']
                print("  USER CONTEXT IN PROMPT:")
                found_contexts = [k for k, v in context.items() if v and k.startswith('has_')]
                if found_contexts:
                    print(f"    [OK] Found: {', '.join([k.replace('has_', '') for k in found_contexts])}")
                else:
                    print("    [X] No user context found in prompt")
                print()
                
                # Check if tool_calls are in response
                print("  TOOL CALLS IN RESPONSE:")
                if formatted['response_has_tool_calls']:
                    print(f"    [OK] Found {len(formatted['response_tool_calls'])} tool call(s) in response")
                    for tc in formatted['response_tool_calls']:
                        if isinstance(tc, dict):
                            func = tc.get('function', {})
                            if isinstance(func, dict):
                                print(f"      - {func.get('name', 'unknown')}: {func.get('arguments', '')[:100]}")
                else:
                    print("    [X] No tool_calls found in stored response")
                    # Check response structure
                    if formatted['response_data']:
                        print(f"    Response keys: {list(formatted['response_data'].keys())}")
                        if 'content' in formatted['response_data']:
                            content_preview = formatted['response_data']['content'][:200]
                            print(f"    Content preview: {content_preview}...")
                print()
                
                # Tools actually executed
                if formatted['tools_called']:
                    print("  TOOLS EXECUTED:")
                    for tool in formatted['tools_called']:
                        status = "[OK]" if tool['success'] else "[X]"
                        print(f"    {status} {tool['name']} ({tool['execution_time_ms']}ms)")
                        if tool['arguments']:
                            try:
                                args = json.loads(tool['arguments'])
                                print(f"      Args: {json.dumps(args, indent=8)}")
                            except:
                                print(f"      Args: {tool['arguments'][:100]}")
                else:
                    print("  TOOLS EXECUTED: None")
                print()
                
                # Prompt preview - check for tools in stored messages
                print("  PROMPT ANALYSIS:")
                prompt_text = formatted['prompt_preview']
                
                # Try to parse as JSON to see structure
                try:
                    prompt_data = json.loads(prompt_text)
                    if isinstance(prompt_data, list):
                        # Check if tools are in the messages structure
                        # Tools should be at the top level of the request, not in messages
                        # But let's check if search_spotify_catalog is mentioned
                        full_prompt_str = prompt_text.lower()
                        if "search_spotify" in full_prompt_str or "spotify" in full_prompt_str:
                            print("    [OK] Spotify search mentioned in prompt")
                        else:
                            print("    [X] No Spotify search mentioned")
                        
                        # Check if tool instructions are in system message
                        if prompt_data:
                            system_msg = next((m for m in prompt_data if m.get('role') == 'system'), None)
                            if system_msg:
                                content = system_msg.get('content', '').lower()
                                if "search_spotify" in content or "tool" in content:
                                    print("    [OK] Tool instructions found in system message")
                                else:
                                    print("    [X] No tool instructions in system message")
                                    
                            user_msg = next((m for m in prompt_data if m.get('role') == 'user'), None)
                            if user_msg:
                                content = user_msg.get('content', '').lower()
                                if "search_spotify" in content or "use the" in content:
                                    print("    [OK] Tool usage instructions in user message")
                                    
                        # Show message count
                        print(f"    Messages in conversation: {len(prompt_data)}")
                        
                except json.JSONDecodeError:
                    # Not JSON, show as text
                    print("    [WARN] Prompt is not valid JSON")
                    if "search_spotify" in prompt_text.lower():
                        print("    [OK] Spotify mentioned in prompt text")
                print()
                
                print("-" * 80)
                print()
            
            print()
        
        # Summary report
        print("=" * 80)
        print("SUMMARY REPORT")
        print("=" * 80)
        print()
        
        total_traces = 0
        total_with_tools = 0
        total_without_tools = 0
        
        for session in sessions:
            traces = await get_llm_traces_for_session(db, session.session_id, agent_name="catalog_selector")
            if not traces:
                traces = await get_llm_traces_for_session(db, session.session_id)
            
            total_traces += len(traces)
            for trace in traces:
                tools = await get_tool_logs_for_trace(db, trace.id)
                if tools:
                    total_with_tools += 1
                else:
                    total_without_tools += 1
        
        print(f"Total traces reviewed: {total_traces}")
        print(f"Traces with tool calls: {total_with_tools}")
        print(f"Traces without tool calls: {total_without_tools}")
        print()
        
        if total_without_tools > 0:
            print("ISSUE DETECTED:")
            print("  The LLM is not calling tools even though:")
            print("  1. Spotify data IS being included in prompts")
            print("  2. User context IS being included in prompts")
            print("  3. Tools should be available (search_spotify_catalog)")
            print()
            print("RECOMMENDATIONS:")
            print("  1. Verify tools are being passed to chat_completion()")
            print("  2. Check if tool_choice parameter is set correctly")
            print("  3. Verify tool definitions match OpenRouter format")
            print("  4. Check LLM response for tool_calls field")
        else:
            print("All traces show tool usage - system working correctly!")
        print()


if __name__ == "__main__":
    asyncio.run(main())
