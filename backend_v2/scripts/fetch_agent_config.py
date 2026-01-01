#!/usr/bin/env python3
"""
Fetch current ElevenLabs agent configuration for analysis.
This script retrieves the full agent config and saves it to a JSON file.
"""

import os
import sys
import json
from datetime import datetime

import httpx
from dotenv import load_dotenv

load_dotenv()

# =============================================================================
# Configuration
# =============================================================================
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_ONBOARD_AGENT_ID = os.getenv("ELEVENLABS_ONBOARD_AGENT_ID")

if not ELEVENLABS_API_KEY:
    print("❌ ELEVENLABS_API_KEY not set in .env")
    sys.exit(1)

if not ELEVENLABS_ONBOARD_AGENT_ID:
    print("❌ ELEVENLABS_ONBOARD_AGENT_ID not set in .env")
    sys.exit(1)

API_BASE = "https://api.elevenlabs.io"


# =============================================================================
# Fetch Agent
# =============================================================================

def fetch_agent():
    """Fetch the current agent configuration."""
    response = httpx.get(
        f"{API_BASE}/v1/convai/agents/{ELEVENLABS_ONBOARD_AGENT_ID}",
        headers={
            "xi-api-key": ELEVENLABS_API_KEY,
        },
        timeout=30.0
    )
    
    if response.status_code != 200:
        print(f"❌ Failed to fetch agent: {response.status_code}")
        print(response.text)
        sys.exit(1)
    
    return response.json()


def main():
    print("=" * 60)
    print("🔍 Fetching Jamify Onboarding Agent Configuration")
    print("=" * 60)
    print(f"\n📍 Agent ID: {ELEVENLABS_ONBOARD_AGENT_ID}")
    
    # Fetch agent config
    agent_config = fetch_agent()
    
    # Save to file
    output_dir = os.path.dirname(__file__)
    output_path = os.path.join(output_dir, "current_agent_config.json")
    
    with open(output_path, "w") as f:
        json.dump(agent_config, f, indent=2)
    
    print(f"\n✅ Agent config saved to: {output_path}")
    
    # Print summary
    print("\n" + "=" * 60)
    print("📊 Agent Summary")
    print("=" * 60)
    
    print(f"\n📛 Name: {agent_config.get('name', 'Unknown')}")
    
    conv_config = agent_config.get("conversation_config", {})
    agent = conv_config.get("agent", {})
    prompt_config = agent.get("prompt", {})
    
    print(f"🎙️ First Message: {agent.get('first_message', 'N/A')[:80]}...")
    print(f"🧠 LLM: {prompt_config.get('llm', 'Unknown')}")
    print(f"🌡️ Temperature: {prompt_config.get('temperature', 'Unknown')}")
    
    # List tools
    tools = prompt_config.get("tools", [])
    print(f"\n🔧 Tools ({len(tools)}):")
    for tool in tools:
        tool_type = tool.get("type", "unknown")
        name = tool.get("name", "unnamed")
        desc = tool.get("description", "")[:60]
        print(f"   - [{tool_type}] {name}: {desc}...")
    
    # Print system prompt
    system_prompt = prompt_config.get("prompt", "")
    print(f"\n📝 System Prompt Length: {len(system_prompt)} chars")
    
    # Print first 500 chars of prompt
    print("\n" + "=" * 60)
    print("📝 System Prompt Preview (first 1000 chars)")
    print("=" * 60)
    print(system_prompt[:1000] + "..." if len(system_prompt) > 1000 else system_prompt)
    
    # TTS config
    tts = conv_config.get("tts", {})
    print("\n" + "=" * 60)
    print("🎤 TTS Configuration")
    print("=" * 60)
    print(f"   Voice ID: {tts.get('voice_id', 'Unknown')}")
    print(f"   Model: {tts.get('model_id', 'Unknown')}")
    print(f"   Stability: {tts.get('stability', 'Unknown')}")
    print(f"   Speed: {tts.get('speed', 'Unknown')}")
    
    print("\n" + "=" * 60)
    print("✅ Analysis Complete!")
    print("=" * 60)
    print(f"\n🔗 ElevenLabs Dashboard:")
    print(f"   https://elevenlabs.io/app/agents/{ELEVENLABS_ONBOARD_AGENT_ID}")


if __name__ == "__main__":
    main()
