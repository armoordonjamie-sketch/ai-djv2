"""
Review a specific session's LLM traces, tool usage, and track selections.
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

# Add parent directory to path and ensure we're in the right directory
script_dir = Path(__file__).parent
project_root = script_dir.parent.parent
sys.path.insert(0, str(project_root))

# Change to project root so database path resolves correctly
os.chdir(project_root)

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from backend_v2.db.session import async_session_factory
from backend_v2.models.existing import Session, LLMTrace, ToolUsageLog
from backend_v2.models.track_intent import TrackIntent
from backend_v2.models.user_profile import UserProfile
from backend_v2.models.spotify_context import SpotifyUserContext


async def get_session_details(db: AsyncSession, session_id: str) -> Optional[Dict[str, Any]]:
    """Get session details."""
    result = await db.execute(
        select(Session).where(Session.session_id == session_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        return None
    
    return {
        "session_id": session.session_id,
        "user_id": session.user_id,
        "started_at": session.started_at,
        "ended_at": session.ended_at,
        "is_active": session.is_active,
    }


async def get_llm_traces_for_session(db: AsyncSession, session_id: str, user_id: Optional[str] = None) -> List[LLMTrace]:
    """Get all LLM traces for a session, including training traces."""
    from sqlalchemy import or_, and_
    
    # Get traces with session_id
    result = await db.execute(
        select(LLMTrace)
        .where(LLMTrace.session_id == session_id)
        .order_by(LLMTrace.created_at)
    )
    traces = list(result.scalars().all())
    
    # Also get training traces for this user that happened around the same time
    # Training traces use session_id=None but have agent_name starting with "train_"
    if user_id:
        training_agents = ["train_from_like", "train_from_dislike", "train_from_skip", "train_mood_from_session"]
        
        # Get session start time to find training traces that happened after
        session_result = await db.execute(
            select(Session).where(Session.session_id == session_id)
        )
        session = session_result.scalar_one_or_none()
        
        if session:
            # Find training traces for this user that occurred during the session
            from datetime import timedelta, datetime
            training_start = session.started_at
            # Handle both datetime and string formats
            if isinstance(training_start, str):
                training_start = datetime.fromisoformat(training_start.replace('Z', '+00:00'))
            
            # Determine end time: use session ended_at if available, otherwise extend window
            if session.ended_at:
                if isinstance(session.ended_at, str):
                    training_end = datetime.fromisoformat(session.ended_at.replace('Z', '+00:00'))
                else:
                    training_end = session.ended_at
            else:
                # Session still active - extend to 30 minutes after start or current time, whichever is earlier
                from datetime import timezone
                extended_end = training_start + timedelta(minutes=30)
                current_time = datetime.now(timezone.utc)
                # Ensure both datetimes are timezone-aware for comparison
                if training_start.tzinfo is None:
                    training_start = training_start.replace(tzinfo=timezone.utc)
                training_end = extended_end if extended_end < current_time else current_time
            
            print(f"\n  Searching for training traces:")
            print(f"    User ID: {user_id}")
            print(f"    Time range: {training_start} to {training_end}")
            print(f"    Agents: {', '.join(training_agents)}")
            
            # Convert datetime to ISO string for comparison (created_at is stored as string)
            training_start_str = training_start.isoformat() if isinstance(training_start, datetime) else str(training_start)
            training_end_str = training_end.isoformat() if isinstance(training_end, datetime) else str(training_end)
            
            training_result = await db.execute(
                select(LLMTrace)
                .where(
                    and_(
                        LLMTrace.user_id == user_id,
                        LLMTrace.agent_name.in_(training_agents),
                        LLMTrace.session_id.is_(None),  # Explicitly check for NULL session_id
                        LLMTrace.created_at >= training_start_str,
                        LLMTrace.created_at <= training_end_str
                    )
                )
                .order_by(LLMTrace.created_at)
            )
            training_traces = list(training_result.scalars().all())
            print(f"    Found {len(training_traces)} training traces")
            if training_traces:
                print(f"    Trace IDs: {[t.id for t in training_traces]}")
            traces.extend(training_traces)
    
    return traces


async def get_tool_usage_for_session(db: AsyncSession, session_id: str) -> List[ToolUsageLog]:
    """Get all tool usage logs for a session."""
    result = await db.execute(
        select(ToolUsageLog)
        .where(ToolUsageLog.session_id == session_id)
        .order_by(ToolUsageLog.created_at)
    )
    return list(result.scalars().all())


async def get_track_intents_for_session(db: AsyncSession, session_id: str) -> List[TrackIntent]:
    """Get all track intents for a session."""
    result = await db.execute(
        select(TrackIntent)
        .where(TrackIntent.session_id == session_id)
        .order_by(TrackIntent.created_at)
    )
    return list(result.scalars().all())


async def get_user_context(db: AsyncSession, user_id: str) -> Dict[str, Any]:
    """Get user profile and Spotify context."""
    # Get user profile
    profile_result = await db.execute(
        select(UserProfile).where(UserProfile.user_id == user_id)
    )
    profile = profile_result.scalar_one_or_none()
    
    # Get Spotify context
    spotify_result = await db.execute(
        select(SpotifyUserContext).where(SpotifyUserContext.user_id == user_id)
    )
    spotify = spotify_result.scalar_one_or_none()
    
    return {
        "profile": {
            "favorite_genres": profile.favorite_genres if profile else None,
            "favorite_artists": profile.favorite_artists if profile else None,
            "display_name": profile.display_name if profile else None,
        } if profile else None,
        "spotify": {
            "top_artists_json": spotify.top_artists_json if spotify else None,
            "top_tracks_json": spotify.top_tracks_json if spotify else None,
        } if spotify else None,
    }


def format_trace(trace: LLMTrace) -> str:
    """Format an LLM trace for display."""
    lines = []
    lines.append(f"\n{'='*80}")
    lines.append(f"Trace ID: {trace.id}")
    lines.append(f"Agent: {trace.agent_name}")
    lines.append(f"Created: {trace.created_at}")
    lines.append(f"Model: {trace.model}")
    
    # Parse prompt (messages) and response data
    prompt_data = None
    response_data = {}
    
    if trace.prompt:
        try:
            prompt_data = json.loads(trace.prompt) if isinstance(trace.prompt, str) else trace.prompt
        except:
            prompt_data = trace.prompt[:500] if trace.prompt else None
    
    if trace.response:
        try:
            response_data = json.loads(trace.response) if isinstance(trace.response, str) else trace.response
        except:
            response_data = {"raw": trace.response[:200]}
    
    # Check for tool calls in response
    tool_calls = None
    if isinstance(response_data, dict):
        tool_calls = response_data.get('tool_calls')
        content = response_data.get('content', '')
        usage = response_data.get('usage', {})
        
        lines.append(f"Content Length: {len(content) if content else 0} chars")
        
        if tool_calls:
            lines.append(f"\nTOOL CALLS ({len(tool_calls)}):")
            for i, tc in enumerate(tool_calls, 1):
                if isinstance(tc, dict):
                    func = tc.get('function', {})
                    if isinstance(func, dict):
                        name = func.get('name', 'unknown')
                        args = func.get('arguments', '{}')
                        try:
                            args_dict = json.loads(args) if isinstance(args, str) else args
                            lines.append(f"  {i}. {name}({json.dumps(args_dict, indent=2)[:200]})")
                        except:
                            lines.append(f"  {i}. {name}({args[:100]})")
        else:
            lines.append("\nNo tool calls in response")
        
        # Show usage if available
        if usage and isinstance(usage, dict):
            lines.append(f"\nUsage: {usage.get('prompt_tokens', '?')} prompt + {usage.get('completion_tokens', '?')} completion = {usage.get('total_tokens', '?')} total")
    
    # Show prompt preview
    if prompt_data:
        if isinstance(prompt_data, list):
            # Messages format
            lines.append(f"\nPrompt (Messages): {len(prompt_data)} messages")
            if prompt_data:
                last_msg = prompt_data[-1]
                if isinstance(last_msg, dict):
                    role = last_msg.get('role', 'unknown')
                    content = last_msg.get('content', '')
                    lines.append(f"  Last message ({role}): {content[:300]}")
        else:
            lines.append(f"\nPrompt: {str(prompt_data)[:300]}")
    
    return "\n".join(lines)


def format_tool_log(log: ToolUsageLog) -> str:
    """Format a tool usage log for display."""
    lines = []
    lines.append(f"\n{'='*80}")
    lines.append(f"Tool: {log.tool_name}")
    lines.append(f"Created: {log.created_at}")
    lines.append(f"Success: {log.success}")
    if log.execution_time_ms:
        lines.append(f"Execution Time: {log.execution_time_ms:.1f}ms")
    
    if log.tool_arguments:
        try:
            args = json.loads(log.tool_arguments) if isinstance(log.tool_arguments, str) else log.tool_arguments
            lines.append(f"Args: {json.dumps(args, indent=2)[:300]}")
        except:
            lines.append(f"Args: {str(log.tool_arguments)[:200]}")
    
    if log.tool_result:
        try:
            result = json.loads(log.tool_result) if isinstance(log.tool_result, str) else log.tool_result
            if isinstance(result, list):
                lines.append(f"Result: List with {len(result)} items")
                if result:
                    lines.append(f"  First item: {json.dumps(result[0], indent=2)[:300]}")
            elif isinstance(result, dict):
                lines.append(f"Result: {json.dumps(result, indent=2)[:500]}")
            else:
                lines.append(f"Result: {str(result)[:200]}")
        except:
            lines.append(f"Result: {str(log.tool_result)[:200]}")
    
    if log.error_message:
        lines.append(f"Error: {log.error_message}")
    
    return "\n".join(lines)


async def main():
    """Main function."""
    # Get session ID from command line or use the one from logs
    session_id = sys.argv[1] if len(sys.argv) > 1 else "ac477318-962c-4b71-8f2c-7ac4eea63837"
    
    print(f"\n{'='*80}")
    print(f"SESSION REVIEW: {session_id}")
    print(f"{'='*80}\n")
    
    # Use async session factory
    async with async_session_factory() as db:
        # Get session details
        session_details = await get_session_details(db, session_id)
        if not session_details:
            print(f"ERROR: Session {session_id} not found!")
            return
        
        print("SESSION DETAILS:")
        print(f"  User ID: {session_details['user_id']}")
        print(f"  Started: {session_details['started_at']}")
        print(f"  Ended: {session_details['ended_at']}")
        print(f"  Active: {session_details['is_active']}")
        
        # Get user context
        user_context = await get_user_context(db, session_details['user_id'])
        print(f"\nUSER CONTEXT:")
        if user_context['profile']:
            print(f"  Display Name: {user_context['profile']['display_name']}")
            print(f"  Favorite Genres: {user_context['profile']['favorite_genres']}")
            print(f"  Favorite Artists: {user_context['profile']['favorite_artists']}")
        if user_context['spotify']:
            print(f"  Spotify Top Artists: {user_context['spotify']['top_artists_json'][:200] if user_context['spotify']['top_artists_json'] else 'None'}")
            print(f"  Spotify Top Tracks: {user_context['spotify']['top_tracks_json'][:200] if user_context['spotify']['top_tracks_json'] else 'None'}")
        
        # Get LLM traces (including training traces)
        traces = await get_llm_traces_for_session(db, session_id, session_details['user_id'])
        print(f"\n{'='*80}")
        print(f"LLM TRACES: {len(traces)} total")
        print(f"{'='*80}")
        
        for trace in traces:
            print(format_trace(trace))
        
        # Get tool usage logs
        tool_logs = await get_tool_usage_for_session(db, session_id)
        print(f"\n{'='*80}")
        print(f"TOOL USAGE LOGS: {len(tool_logs)} total")
        print(f"{'='*80}")
        
        # Group by tool name
        tool_counts = {}
        for log in tool_logs:
            tool_counts[log.tool_name] = tool_counts.get(log.tool_name, 0) + 1
        
        print("\nTool Usage Summary:")
        for tool_name, count in sorted(tool_counts.items(), key=lambda x: -x[1]):
            success_count = sum(1 for log in tool_logs if log.tool_name == tool_name and log.success)
            print(f"  {tool_name}: {count} calls ({success_count} successful)")
        
        print("\nDetailed Tool Logs:")
        for log in tool_logs:
            print(format_tool_log(log))
        
        # Get track intents
        intents = await get_track_intents_for_session(db, session_id)
        print(f"\n{'='*80}")
        print(f"TRACK INTENTS: {len(intents)} total")
        print(f"{'='*80}")
        
        for intent in intents:
            print(f"\n  {intent.artist} - {intent.title}")
            print(f"    Status: {intent.status}")
            print(f"    Created: {intent.created_at}")
            print(f"    Rationale: {intent.selection_rationale[:200] if intent.selection_rationale else 'N/A'}")
        
        # Analysis
        print(f"\n{'='*80}")
        print("ANALYSIS")
        print(f"{'='*80}")
        
        catalog_traces = [t for t in traces if t.agent_name == "catalog_selector"]
        print(f"\nCatalog Selection Traces: {len(catalog_traces)}")
        
        total_tool_calls = 0
        for trace in catalog_traces:
            if trace.response:
                try:
                    response_data = json.loads(trace.response) if isinstance(trace.response, str) else trace.response
                    if isinstance(response_data, dict):
                        tool_calls = response_data.get('tool_calls', [])
                        total_tool_calls += len(tool_calls)
                except:
                    pass
        
        print(f"Total tool calls made by LLM: {total_tool_calls}")
        print(f"Total tool executions logged: {len(tool_logs)}")
        
        spotify_searches = [log for log in tool_logs if log.tool_name == "search_spotify_catalog"]
        print(f"\nSpotify searches: {len(spotify_searches)}")
        if spotify_searches:
            total_results = 0
            for log in spotify_searches:
                if log.tool_result:
                    try:
                        result = json.loads(log.tool_result) if isinstance(log.tool_result, str) else log.tool_result
                        if isinstance(result, list):
                            total_results += len(result)
                    except:
                        pass
            print(f"Total tracks found: {total_results}")
        
        print(f"\nTrack selections: {len(intents)}")
        if intents:
            artists = [intent.artist for intent in intents if intent.artist]
            unique_artists = len(set(artists))
            print(f"Unique artists: {unique_artists} out of {len(artists)} selections")
            print(f"Artist variety: {unique_artists / len(artists) * 100:.1f}%")
        
        # Enhanced LLM/Tool Usage Analysis
        print(f"\n{'='*80}")
        print("ENHANCED LLM/TOOL USAGE ANALYSIS")
        print(f"{'='*80}")
        
        # Group traces by agent
        agent_traces = {}
        for trace in traces:
            agent_name = trace.agent_name or "unknown"
            if agent_name not in agent_traces:
                agent_traces[agent_name] = []
            agent_traces[agent_name].append(trace)
        
        print(f"\nAgents Used: {len(agent_traces)}")
        for agent_name, agent_trace_list in sorted(agent_traces.items(), key=lambda x: -len(x[1])):
            print(f"  {agent_name}: {len(agent_trace_list)} traces")
        
        # Analyze tool usage by agent
        print(f"\nTool Usage by Agent:")
        agent_tool_usage = {}
        for log in tool_logs:
            # Find which trace this tool call belongs to
            trace_id = None
            for trace in traces:
                if trace.response:
                    try:
                        response_data = json.loads(trace.response) if isinstance(trace.response, str) else trace.response
                        if isinstance(response_data, dict):
                            tool_calls = response_data.get('tool_calls', [])
                            for tc in tool_calls:
                                if isinstance(tc, dict):
                                    func = tc.get('function', {})
                                    if isinstance(func, dict):
                                        # Match by tool name and approximate timing
                                        if func.get('name') == log.tool_name:
                                            agent_name = trace.agent_name or "unknown"
                                            if agent_name not in agent_tool_usage:
                                                agent_tool_usage[agent_name] = {}
                                            if log.tool_name not in agent_tool_usage[agent_name]:
                                                agent_tool_usage[agent_name][log.tool_name] = 0
                                            agent_tool_usage[agent_name][log.tool_name] += 1
                                            break
                    except:
                        pass
        
        # Also try to match by timing proximity
        for log in tool_logs:
            matched = False
            for trace in traces:
                try:
                    # Handle datetime comparison - SQLAlchemy returns datetime objects
                    log_time = log.created_at
                    trace_time = trace.created_at
                    if log_time and trace_time:
                        time_diff = abs((log_time - trace_time).total_seconds())
                        if time_diff < 5:
                            agent_name = trace.agent_name or "unknown"
                            if agent_name not in agent_tool_usage:
                                agent_tool_usage[agent_name] = {}
                            if log.tool_name not in agent_tool_usage[agent_name]:
                                agent_tool_usage[agent_name][log.tool_name] = 0
                            agent_tool_usage[agent_name][log.tool_name] += 1
                            matched = True
                            break
                except Exception:
                    pass
        
        for agent_name, tools in sorted(agent_tool_usage.items()):
            print(f"\n  {agent_name}:")
            for tool_name, count in sorted(tools.items(), key=lambda x: -x[1]):
                print(f"    {tool_name}: {count} calls")
        
        # Tool efficiency analysis
        print(f"\nTool Efficiency Analysis:")
        tool_times = {}
        for log in tool_logs:
            if log.execution_time_ms:
                if log.tool_name not in tool_times:
                    tool_times[log.tool_name] = []
                tool_times[log.tool_name].append(log.execution_time_ms)
        
        for tool_name, times in sorted(tool_times.items()):
            avg_time = sum(times) / len(times)
            min_time = min(times)
            max_time = max(times)
            print(f"  {tool_name}:")
            print(f"    Avg: {avg_time:.1f}ms, Min: {min_time:.1f}ms, Max: {max_time:.1f}ms, Count: {len(times)}")
        
        # Training agent analysis
        training_agents = ["train_from_like", "train_from_dislike", "train_from_skip", "train_mood_from_session"]
        training_traces = [t for t in traces if t.agent_name and any(agent in t.agent_name for agent in training_agents)]
        if training_traces:
            print(f"\nTraining Agent Analysis:")
            print(f"  Training traces: {len(training_traces)}")
            training_tools = [log for log in tool_logs if any(agent in log.tool_name for agent in ["get_user_feedback", "get_feedback_summary", "get_play_history", "get_artist_play_count", "get_mood_profile"])]
            print(f"  Training-related tool calls: {len(training_tools)}")
            if training_tools:
                training_tool_counts = {}
                for log in training_tools:
                    training_tool_counts[log.tool_name] = training_tool_counts.get(log.tool_name, 0) + 1
                for tool_name, count in sorted(training_tool_counts.items(), key=lambda x: -x[1]):
                    print(f"    {tool_name}: {count} calls")
        
        # Training effectiveness metrics
        print(f"\nTraining Effectiveness Metrics:")
        from backend_v2.services.training_effectiveness import get_effectiveness_report
        
        try:
            effectiveness = await get_effectiveness_report(
                db=db,
                user_id=session_details['user_id'],
                days=30,
            )
            
            print(f"  Total training events: {effectiveness['total_training_events']}")
            if effectiveness['total_training_events'] > 0:
                print(f"  Average effectiveness: {effectiveness['average_effectiveness']:.2%}")
                
                if effectiveness['by_agent']:
                    print(f"\n  By Agent:")
                    for agent, stats in sorted(effectiveness['by_agent'].items(), key=lambda x: -x[1]['avg_score']):
                        print(f"    {agent}: {stats['avg_score']:.2%} ({stats['count']} events)")
                
                if effectiveness['by_feedback_type']:
                    print(f"\n  By Feedback Type:")
                    for ftype, stats in sorted(effectiveness['by_feedback_type'].items(), key=lambda x: -x[1]['avg_score']):
                        print(f"    {ftype}: {stats['avg_score']:.2%} ({stats['count']} events)")
            else:
                print(f"  No training metrics available yet")
        except Exception as e:
            print(f"  Error loading effectiveness metrics: {e}")
        
        # Catalog selector analysis
        catalog_traces = [t for t in traces if t.agent_name == "catalog_selector"]
        if catalog_traces:
            print(f"\nCatalog Selector Analysis:")
            print(f"  Total traces: {len(catalog_traces)}")
            catalog_tools = [log for log in tool_logs if log.tool_name == "search_spotify_catalog"]
            print(f"  Spotify searches: {len(catalog_tools)}")
            
            # Analyze search patterns
            search_queries = {}
            for log in catalog_tools:
                if log.tool_arguments:
                    try:
                        args = json.loads(log.tool_arguments) if isinstance(log.tool_arguments, str) else log.tool_arguments
                        query_type = "artist" if args.get("artist") else "query" if args.get("query") else "unknown"
                        query_value = args.get("artist") or args.get("query") or "unknown"
                        key = f"{query_type}:{query_value}"
                        search_queries[key] = search_queries.get(key, 0) + 1
                    except:
                        pass
            
            if search_queries:
                print(f"  Search patterns:")
                for pattern, count in sorted(search_queries.items(), key=lambda x: -x[1])[:10]:
                    print(f"    {pattern}: {count} searches")
        
        # LLM token usage analysis
        print(f"\nLLM Token Usage:")
        total_prompt_tokens = 0
        total_completion_tokens = 0
        total_tokens = 0
        for trace in traces:
            if trace.response:
                try:
                    response_data = json.loads(trace.response) if isinstance(trace.response, str) else trace.response
                    if isinstance(response_data, dict):
                        usage = response_data.get('usage', {})
                        if isinstance(usage, dict):
                            total_prompt_tokens += usage.get('prompt_tokens', 0)
                            total_completion_tokens += usage.get('completion_tokens', 0)
                            total_tokens += usage.get('total_tokens', 0)
                except:
                    pass
        
        print(f"  Total prompt tokens: {total_prompt_tokens:,}")
        print(f"  Total completion tokens: {total_completion_tokens:,}")
        print(f"  Total tokens: {total_tokens:,}")
        if len(traces) > 0:
            print(f"  Avg tokens per trace: {total_tokens // len(traces):,}")


if __name__ == "__main__":
    # Fix Windows console encoding for Unicode characters
    import sys
    if sys.platform == "win32":
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    asyncio.run(main())

