#!/usr/bin/env python3
"""
Cleanup script to delete all ElevenLabs agents and tools.
"""
import os
import httpx
from dotenv import load_dotenv

load_dotenv()

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
API_BASE = "https://api.elevenlabs.io"

headers = {
    "xi-api-key": ELEVENLABS_API_KEY,
    "Content-Type": "application/json"
}


def list_agents():
    """List all agents."""
    response = httpx.get(
        f"{API_BASE}/v1/convai/agents",
        headers=headers,
        timeout=30.0
    )
    if response.status_code == 200:
        return response.json().get("agents", [])
    return []


def delete_agent(agent_id: str):
    """Delete an agent."""
    response = httpx.delete(
        f"{API_BASE}/v1/convai/agents/{agent_id}",
        headers=headers,
        timeout=30.0
    )
    return response.status_code == 200


def list_tools():
    """List all tools."""
    response = httpx.get(
        f"{API_BASE}/v1/convai/tools",
        headers=headers,
        timeout=30.0
    )
    if response.status_code == 200:
        return response.json().get("tools", [])
    return []


def delete_tool(tool_id: str):
    """Delete a tool."""
    response = httpx.delete(
        f"{API_BASE}/v1/convai/tools/{tool_id}",
        headers=headers,
        timeout=30.0
    )
    return response.status_code == 200


def main():
    print("=" * 60)
    print("🧹 ElevenLabs Cleanup")
    print("=" * 60)
    
    # Delete all agents
    print("\n📍 Listing agents...")
    agents = list_agents()
    print(f"   Found {len(agents)} agent(s)")
    
    for agent in agents:
        agent_id = agent["agent_id"]
        name = agent.get("name", "Unnamed")
        print(f"   🗑️  Deleting agent: {name} ({agent_id})...")
        if delete_agent(agent_id):
            print(f"      ✅ Deleted")
        else:
            print(f"      ❌ Failed to delete")
    
    # Delete all tools
    print("\n📍 Listing tools...")
    tools = list_tools()
    print(f"   Found {len(tools)} tool(s)")
    
    for tool in tools:
        tool_id = tool["id"]
        name = tool.get("name", "Unnamed")
        print(f"   🗑️  Deleting tool: {name} ({tool_id})...")
        if delete_tool(tool_id):
            print(f"      ✅ Deleted")
        else:
            print(f"      ❌ Failed to delete")
    
    print("\n" + "=" * 60)
    print("✅ Cleanup complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
