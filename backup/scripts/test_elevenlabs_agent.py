"""
ElevenLabs Agent Testing Script

Creates and runs tests for the onboarding agent using the ElevenLabs testing API.
Tests conversational responses only (tools require user_id which testing can't provide).

Reference: https://elevenlabs.io/docs/api-reference/tests/create
"""

import os
import asyncio
import json
import httpx
from dotenv import load_dotenv

load_dotenv()

# Configuration
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
AGENT_ID = os.getenv("ELEVENLABS_ONBOARD_AGENT_ID")
BASE_URL = "https://api.elevenlabs.io/v1"

HEADERS = {
    "xi-api-key": ELEVENLABS_API_KEY,
    "Content-Type": "application/json"
}


async def create_test(name: str, chat_history: list, success_condition: str, 
                      success_examples: list, failure_examples: list,
                      dynamic_variables: dict = None) -> str:
    """Create a new agent response test."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        payload = {
            "name": name,
            "chat_history": chat_history,
            "success_condition": success_condition,
            "success_examples": success_examples,
            "failure_examples": failure_examples,
        }
        # Add dynamic variables if provided (needed for tools that require user_id etc)
        if dynamic_variables:
            payload["dynamic_variables"] = dynamic_variables
            
        response = await client.post(
            f"{BASE_URL}/convai/agent-testing/create",
            headers=HEADERS,
            json=payload
        )
        if response.status_code != 200:
            print(f"❌ Failed to create test '{name}': {response.status_code}")
            print(f"   Response: {response.text[:500]}")
            return None
        result = response.json()
        print(f"✅ Created test '{name}': {result['id']}")
        return result["id"]


async def run_tests(agent_id: str, test_ids: list[str], dynamic_variables: dict = None) -> dict:
    """Run selected tests on the agent."""
    async with httpx.AsyncClient(timeout=120.0) as client:
        payload = {
            "tests": [{"test_id": tid} for tid in test_ids]
        }
        # Add dynamic variables for tool execution
        if dynamic_variables:
            payload["dynamic_variables"] = dynamic_variables
            
        response = await client.post(
            f"{BASE_URL}/convai/agents/{agent_id}/run-tests",
            headers=HEADERS,
            json=payload
        )
        response.raise_for_status()
        return response.json()


async def get_test_results(invocation_id: str) -> dict:
    """Get results of a test invocation."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{BASE_URL}/convai/test-invocations/{invocation_id}",
            headers=HEADERS
        )
        response.raise_for_status()
        return response.json()


async def main():
    if not ELEVENLABS_API_KEY:
        print("❌ ELEVENLABS_API_KEY not set in .env")
        return
    if not AGENT_ID:
        print("❌ ELEVENLABS_ONBOARD_AGENT_ID not set in .env")
        return
        
    print(f"🎯 Testing agent: {AGENT_ID}")
    print("-" * 50)
    
    # Dynamic variables required by agent tools
    # The agent's webhook tools need user_id for certain operations
    dynamic_vars = {
        "user_id": "test-user-12345"
    }
    
    test_ids = []
    
    # Test 1: Greeting Response
    test_id = await create_test(
        name="Greeting Response Test",
        chat_history=[
            {
                "role": "user",
                "time_in_call_secs": 2,
                "message": "Hello!",
                "tool_calls": [],
                "tool_results": [],
                "interrupted": False,
                "source_medium": "audio"
            }
        ],
        success_condition="'music' in response.lower() or 'artist' in response.lower() or 'song' in response.lower() or 'taste' in response.lower() or 'listen' in response.lower() or 'favorite' in response.lower()",
        success_examples=[
            {"response": "Hey! I'd love to learn about your music taste. Who are some of your favorite artists?", "type": "success"}
        ],
        failure_examples=[
            {"response": "Hello, how can I help you today?", "type": "failure"}
        ],
        dynamic_variables=dynamic_vars
    )
    if test_id:
        test_ids.append(test_id)
    
    # Test 2: Artist Mention
    test_id = await create_test(
        name="Artist Mention Response Test",
        chat_history=[
            {
                "role": "user",
                "time_in_call_secs": 5,
                "message": "I really like Avril Lavigne",
                "tool_calls": [],
                "tool_results": [],
                "interrupted": False,
                "source_medium": "audio"
            }
        ],
        success_condition="'avril' in response.lower() or 'song' in response.lower() or 'play' in response.lower() or 'great' in response.lower() or 'love' in response.lower()",
        success_examples=[
            {"response": "Avril Lavigne is great! Let me find some of her songs for you.", "type": "success"}
        ],
        failure_examples=[
            {"response": "I don't know that artist.", "type": "failure"}
        ],
        dynamic_variables=dynamic_vars
    )
    if test_id:
        test_ids.append(test_id)
    
    # Test 3: Song Request
    test_id = await create_test(
        name="Song Preview Request Test",
        chat_history=[
            {
                "role": "user",
                "time_in_call_secs": 3,
                "message": "Can you play Complicated by Avril Lavigne?",
                "tool_calls": [],
                "tool_results": [],
                "interrupted": False,
                "source_medium": "audio"
            }
        ],
        success_condition="'play' in response.lower() or 'preview' in response.lower() or 'listen' in response.lower() or 'complicated' in response.lower() or 'sure' in response.lower()",
        success_examples=[
            {"response": "Sure! Let me play a preview of Complicated for you.", "type": "success"}
        ],
        failure_examples=[
            {"response": "I can't play music.", "type": "failure"}
        ],
        dynamic_variables=dynamic_vars
    )
    if test_id:
        test_ids.append(test_id)
    
    if not test_ids:
        print("❌ No tests were created successfully")
        return
        
    print("-" * 50)
    print(f"📋 Created {len(test_ids)} tests. Running with dynamic_variables...")
    
    # Run the tests with dynamic variables
    try:
        result = await run_tests(AGENT_ID, test_ids, dynamic_vars)
        invocation_id = result.get("id") or result.get("invocation_id")
        print(f"🚀 Test invocation started: {invocation_id}")
        
        # Poll for results
        print("⏳ Waiting for results...")
        for i in range(30):  # Wait up to 5 minutes
            await asyncio.sleep(10)
            try:
                results = await get_test_results(invocation_id)
                test_runs = results.get("test_runs", [])
                
                # Count completed tests by checking for condition_result
                completed = sum(1 for run in test_runs if run.get("condition_result"))
                
                print(f"   [{i+1}/30] Completed: {completed}/{len(test_runs)}")
                
                if completed == len(test_runs) and len(test_runs) > 0:
                    print("-" * 50)
                    print("📊 RESULTS:")
                    
                    passed_count = 0
                    for run in test_runs:
                        test_name = run.get("test_name", "Unknown")
                        condition = run.get("condition_result", {})
                        result_status = condition.get("result", "unknown")
                        rationale = condition.get("rationale", {})
                        
                        is_passed = result_status == "passed" or result_status == "success"
                        if is_passed:
                            passed_count += 1
                        
                        icon = "✅" if is_passed else "❌"
                        print(f"  {icon} {test_name}")
                        print(f"      Status: {result_status}")
                        
                        # Show rationale
                        messages = rationale.get("messages", [])
                        summary = rationale.get("summary", "")
                        if summary:
                            print(f"      Summary: {summary}")
                        for msg in messages[:2]:
                            print(f"      - {msg[:150]}")
                        
                        # Show agent responses if available
                        agent_responses = run.get("agent_responses") or []
                        if agent_responses and len(agent_responses) > 0:
                            first_response = str(agent_responses[0])
                            print(f"      Agent said: {first_response[:150]}...")
                    
                    print("-" * 50)
                    print(f"   Summary: {passed_count}/{len(test_runs)} passed")
                    break
                    
            except httpx.HTTPStatusError as e:
                print(f"   Polling HTTP error: {e.response.status_code}")
            except Exception as e:
                print(f"   Polling error: {e}")
        else:
            print("⚠️ Timed out waiting for results. Showing partial results...")
            try:
                results = await get_test_results(invocation_id)
                print(json.dumps(results, indent=2, default=str)[:3000])
            except Exception:
                pass
            
    except httpx.HTTPStatusError as e:
        print(f"❌ Error running tests: {e.response.status_code}")
        print(f"   {e.response.text[:500]}")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
