#!/usr/bin/env python
"""
AI DJ v3 LangGraph Smoke Test

This script tests the LangGraph v3 orchestration system end-to-end.
It generates test segments and validates the output.

Usage:
    python scripts/run_v3_smoketest.py
    
Or with specific user/session:
    python scripts/run_v3_smoketest.py --user-id test-user --session-id test-session
"""
import asyncio
import argparse
import logging
import os
import sys

# Add project root to path for imports
# scripts/ is inside backend_v2/, so we need to go up two levels
script_dir = os.path.dirname(os.path.abspath(__file__))
backend_v2_dir = os.path.dirname(script_dir)
project_root = os.path.dirname(backend_v2_dir)
sys.path.insert(0, project_root)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("smoke-test")


async def run_smoke_test(
    user_id: str = "test-user-v3",
    session_id: str = "test-session-v3",
    mood_id: str = None,
    num_segments: int = 2,
) -> bool:
    """
    Run the smoke test.
    
    Returns True if all tests pass.
    """
    print("=" * 60)
    print("🎵 AI DJ v3 LangGraph Smoke Test")
    print("=" * 60)
    print(f"User ID:    {user_id}")
    print(f"Session ID: {session_id}")
    print(f"Mood ID:    {mood_id or '(default)'}")
    print(f"Segments:   {num_segments}")
    print("=" * 60)
    
    # Check runtime health
    print("\n📊 Checking runtime health...")
    try:
        from backend_v2.langgraph_v3.runtime import check_runtime_health
        health = check_runtime_health()
        
        print(f"  Checkpointer:     {health.get('checkpointer', 'unknown')}")
        print(f"  Store:            {health.get('store', 'unknown')}")
        print(f"  Supervisor Graph: {health.get('supervisor_graph', 'unknown')}")
        
        if not health.get("healthy"):
            print(f"  ❌ Runtime unhealthy: {health.get('error', 'unknown error')}")
            return False
        
        print("  ✅ Runtime healthy!")
        
    except Exception as e:
        print(f"  ❌ Health check failed: {e}")
        return False
    
    # Generate segments
    print(f"\n📀 Generating {num_segments} segment(s)...")
    
    from backend_v2.langgraph_v3.runtime import invoke_segment, get_thread_state
    
    segments = []
    for i in range(num_segments):
        print(f"\n  Segment {i + 1}/{num_segments}:")
        
        try:
            segment = await invoke_segment(
                user_id=user_id,
                session_id=session_id,
                mood_id=mood_id,
            )
            
            if segment:
                print(f"    ✅ Generated!")
                print(f"    🎤 Artist:   {segment.get('artist', 'Unknown')}")
                print(f"    🎵 Title:    {segment.get('title', 'Unknown')}")
                print(f"    ⏱️  Duration: {segment.get('duration', 0):.1f}s")
                print(f"    📁 Path:     {segment.get('path', 'N/A')}")
                
                # Check file exists
                path = segment.get("path")
                if path and os.path.exists(path):
                    size_mb = os.path.getsize(path) / 1024 / 1024
                    print(f"    📦 Size:     {size_mb:.2f} MB")
                else:
                    print(f"    ⚠️  File not found!")
                
                segments.append(segment)
            else:
                print(f"    ❌ Generation failed (no segment returned)")
                
        except Exception as e:
            print(f"    ❌ Exception: {e}")
            logger.exception("Segment generation failed")
    
    # Check state persistence
    print("\n💾 Checking state persistence...")
    try:
        state = await get_thread_state(session_id)
        
        if state:
            print(f"  Segment Index: {state.get('segment_index', 0)}")
            print(f"  Songs Played:  {len(state.get('songs_played', []))}")
            print(f"  ✅ State persisted correctly!")
        else:
            print("  ⚠️  No state found (may be expected for first run)")
            
    except Exception as e:
        print(f"  ❌ State check failed: {e}")
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 Summary")
    print("=" * 60)
    print(f"  Segments generated: {len(segments)}/{num_segments}")
    
    if len(segments) == num_segments:
        print("  ✨ All tests passed!")
        return True
    else:
        print("  ❌ Some tests failed")
        return False


async def test_training(
    user_id: str,
    mood_id: str,
) -> bool:
    """
    Test the feedback training graph.
    """
    print("\n📚 Testing feedback training...")
    
    from backend_v2.langgraph_v3.runtime import process_feedback
    
    test_cases = [
        ("like", "Daft Punk", "Get Lucky"),
        ("dislike", "Test Artist", "Bad Song"),
        ("skip", "Another Artist", "Skipped Track"),
    ]
    
    success = True
    for feedback_type, artist, title in test_cases:
        print(f"  Testing {feedback_type} for {artist} - {title}...")
        try:
            result = await process_feedback(
                user_id=user_id,
                session_id="test-training-session",
                mood_id=mood_id or "test-mood",
                feedback_type=feedback_type,
                track_artist=artist,
                track_title=title,
            )
            
            if result.get("success"):
                print(f"    ✅ {feedback_type.upper()} training succeeded")
            else:
                print(f"    ❌ {feedback_type.upper()} training failed: {result.get('error')}")
                success = False
                
        except Exception as e:
            print(f"    ❌ Exception: {e}")
            success = False
    
    return success


async def test_memory(user_id: str) -> bool:
    """
    Test long-term memory operations.
    """
    print("\n🧠 Testing long-term memory...")
    
    from backend_v2.langgraph_v3.memory.store import (
        load_user_memory,
        update_taste_preferences,
        update_banter_constraints,
    )
    
    try:
        # Update preferences
        print("  Updating taste preferences...")
        prefs = await update_taste_preferences(
            user_id=user_id,
            updates={"test_preference": 0.5, "another_pref": -0.2},
        )
        print(f"    ✅ Updated {len(prefs)} preferences")
        
        # Update banter
        print("  Updating banter constraints...")
        banter = await update_banter_constraints(
            user_id=user_id,
            topics_used=["test_topic", "another_topic"],
        )
        print(f"    ✅ Updated banter (topics: {len(banter.get('roast_topics_used', []))})")
        
        # Load memory
        print("  Loading user memory...")
        memory = await load_user_memory(user_id)
        print(f"    Taste keys: {len(memory.get('taste', {}))}")
        print(f"    Sessions:   {len(memory.get('session_summaries', []))}")
        print(f"    ✅ Memory operations succeeded!")
        
        return True
        
    except Exception as e:
        print(f"  ❌ Memory test failed: {e}")
        return False


async def main():
    parser = argparse.ArgumentParser(description="AI DJ v3 Smoke Test")
    parser.add_argument("--user-id", default="test-user-v3", help="User ID")
    parser.add_argument("--session-id", default="test-session-v3", help="Session ID")
    parser.add_argument("--mood-id", default=None, help="Mood ID (optional)")
    parser.add_argument("--segments", type=int, default=1, help="Number of segments")
    parser.add_argument("--skip-segments", action="store_true", help="Skip segment generation")
    parser.add_argument("--test-training", action="store_true", help="Test training")
    parser.add_argument("--test-memory", action="store_true", help="Test memory")
    parser.add_argument("--all", action="store_true", help="Run all tests")
    
    args = parser.parse_args()
    
    # Set environment for test
    os.environ.setdefault("LANGGRAPH_CHECKPOINTER", "memory")
    os.environ.setdefault("LANGGRAPH_STORE", "memory")
    
    all_passed = True
    
    # Run segment test
    if not args.skip_segments or args.all:
        passed = await run_smoke_test(
            user_id=args.user_id,
            session_id=args.session_id,
            mood_id=args.mood_id,
            num_segments=args.segments,
        )
        all_passed = all_passed and passed
    
    # Run training test
    if args.test_training or args.all:
        passed = await test_training(args.user_id, args.mood_id)
        all_passed = all_passed and passed
    
    # Run memory test
    if args.test_memory or args.all:
        passed = await test_memory(args.user_id)
        all_passed = all_passed and passed
    
    # Exit code
    print("\n" + "=" * 60)
    if all_passed:
        print("✨ All tests passed!")
        sys.exit(0)
    else:
        print("❌ Some tests failed")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
