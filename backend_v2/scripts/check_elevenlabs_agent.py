"""
ElevenLabs Agent Diagnostic Script

Checks that the agent and its tools are properly configured.
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
BACKEND_URL = os.getenv("BACKEND_URL", "https://jamify.jamiearmoordon.co.uk")
BASE_URL = "https://api.elevenlabs.io/v1"

HEADERS = {
    "xi-api-key": ELEVENLABS_API_KEY,
    "Content-Type": "application/json"
}


async def get_agent_config():
    """Fetch the agent configuration from ElevenLabs."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{BASE_URL}/convai/agents/{AGENT_ID}",
            headers=HEADERS
        )
        response.raise_for_status()
        return response.json()


async def check_webhook_url(url: str, method: str = "POST") -> dict:
    """Test if a webhook URL is reachable."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Just do an OPTIONS request to check if URL is reachable
            response = await client.options(url)
            return {
                "url": url,
                "reachable": True,
                "status": response.status_code,
                "cors": response.headers.get("Access-Control-Allow-Origin", "Not set")
            }
    except Exception as e:
        return {
            "url": url,
            "reachable": False,
            "error": str(e)
        }


def check_tool_schema(tool: dict) -> list[str]:
    """Check a tool schema for common issues."""
    issues = []
    name = tool.get("name", "unknown")
    
    # Check required fields
    if not tool.get("description"):
        issues.append(f"Tool '{name}' is missing a description")
    
    # Check webhook config for webhook tools
    if tool.get("type") == "webhook":
        webhook = tool.get("webhook", {})
        if not webhook.get("url"):
            issues.append(f"Tool '{name}' is missing webhook URL")
        if not webhook.get("method"):
            issues.append(f"Tool '{name}' is missing webhook method")
    
    # Check parameters schema
    params = tool.get("parameters", {})
    if params.get("type") != "object":
        issues.append(f"Tool '{name}' parameters should be type 'object', got '{params.get('type')}'")
    
    properties = params.get("properties", {})
    required = params.get("required", [])
    
    for req in required:
        if req not in properties:
            issues.append(f"Tool '{name}' has required param '{req}' not in properties")
    
    # Check for dynamic variables usage
    for prop_name, prop_value in properties.items():
        if "{{" in str(prop_value) and "}}" in str(prop_value):
            # Has a dynamic variable reference
            var_name = str(prop_value).split("{{")[1].split("}}")[0].strip()
            issues.append(f"Tool '{name}' param '{prop_name}' uses dynamic variable '{var_name}' (ensure it's passed)")
    
    return issues


async def main():
    print("=" * 60)
    print("ElevenLabs Agent Diagnostic Report")
    print("=" * 60)
    
    if not ELEVENLABS_API_KEY:
        print("❌ ELEVENLABS_API_KEY not set")
        return
    if not AGENT_ID:
        print("❌ ELEVENLABS_ONBOARD_AGENT_ID not set")
        return
    
    print(f"\n📋 Agent ID: {AGENT_ID}")
    print(f"📋 Backend URL: {BACKEND_URL}")
    
    # Fetch agent config
    print("\n" + "-" * 60)
    print("FETCHING AGENT CONFIGURATION...")
    print("-" * 60)
    
    try:
        config = await get_agent_config()
    except httpx.HTTPStatusError as e:
        print(f"❌ Failed to fetch agent: {e.response.status_code}")
        print(f"   {e.response.text[:500]}")
        return
    except Exception as e:
        print(f"❌ Error: {e}")
        return
    
    # Basic agent info
    print(f"\n✅ Agent Name: {config.get('name', 'N/A')}")
    
    # Check conversation config
    conv_config = config.get("conversation_config", {})
    agent_cfg = conv_config.get("agent", {})
    
    # Check language model
    llm = agent_cfg.get("llm", {})
    print(f"\n📊 LLM Model: {llm.get('model_id', 'Default')}")
    print(f"📊 Max Tokens: {llm.get('max_response_tokens', 'Default')}")
    
    # Check prompt
    prompt = agent_cfg.get("prompt", {})
    prompt_text = prompt.get("prompt", "")[:200]
    print(f"\n📝 System Prompt Preview:")
    print(f"   {prompt_text}...")
    
    # Check tools
    print("\n" + "-" * 60)
    print("CHECKING TOOLS...")
    print("-" * 60)
    
    tools = prompt.get("tools", [])
    if not tools:
        print("⚠️  No tools configured!")
    else:
        print(f"\n📋 Found {len(tools)} tools:")
        
    all_issues = []
    webhook_urls = []
    
    for i, tool in enumerate(tools, 1):
        name = tool.get("name", "unknown")
        tool_type = tool.get("type", "unknown")
        print(f"\n  [{i}] {name} ({tool_type})")
        
        # Check schema
        issues = check_tool_schema(tool)
        if issues:
            for issue in issues:
                print(f"      ⚠️  {issue}")
            all_issues.extend(issues)
        else:
            print(f"      ✅ Schema looks valid")
        
        # Collect webhook URLs
        if tool_type == "webhook":
            webhook = tool.get("webhook", {})
            url = webhook.get("url", "")
            method = webhook.get("method", "POST")
            print(f"      📡 URL: {url}")
            print(f"      📡 Method: {method}")
            
            # Check for dynamic variable issues in URL
            if "{{" in url:
                print(f"      ⚠️  URL contains dynamic variable - ensure it's passed at runtime")
            
            webhook_urls.append((url, method))
            
            # Check parameters
            params = tool.get("parameters", {})
            properties = params.get("properties", {})
            required = params.get("required", [])
            
            print(f"      📋 Parameters: {list(properties.keys())}")
            print(f"      📋 Required: {required}")
    
    # Check webhook reachability
    print("\n" + "-" * 60)
    print("CHECKING WEBHOOK ENDPOINTS...")
    print("-" * 60)
    
    for url, method in webhook_urls:
        # Replace any dynamic variables with backend URL for testing
        test_url = url
        if "{{" in test_url:
            # Can't test URLs with unresolved variables
            print(f"\n⚠️  Cannot test URL with variables: {url}")
            continue
            
        result = await check_webhook_url(test_url, method)
        if result.get("reachable"):
            print(f"\n✅ {test_url}")
            print(f"   Status: {result['status']}")
        else:
            print(f"\n❌ {test_url}")
            print(f"   Error: {result.get('error', 'Unknown')}")
    
    # Check dynamic variables
    print("\n" + "-" * 60)
    print("DYNAMIC VARIABLES...")
    print("-" * 60)
    
    # Check if agent expects dynamic variables
    expected_vars = set()
    
    # Search in tools for dynamic variable usage
    for tool in tools:
        webhook = tool.get("webhook", {})
        url = webhook.get("url", "")
        
        # Look for {{var}} patterns
        import re
        matches = re.findall(r'\{\{(\w+)\}\}', url)
        expected_vars.update(matches)
        
        # Also check in other config
        headers = webhook.get("headers", [])
        for header in headers:
            matches = re.findall(r'\{\{(\w+)\}\}', str(header.get("value", "")))
            expected_vars.update(matches)
    
    if expected_vars:
        print(f"\n📋 Expected dynamic variables: {expected_vars}")
        print("   These must be passed when starting the conversation!")
    else:
        print("\n✅ No dynamic variables expected in tool configs")
    
    # Check for common user_id requirement
    for tool in tools:
        params = tool.get("parameters", {})
        properties = params.get("properties", {})
        if "user_id" in properties:
            print(f"\n⚠️  Tool '{tool.get('name')}' expects 'user_id' parameter")
            print("   Ensure agent prompt instructs using dynamic_variables.user_id")
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    if all_issues:
        print(f"\n⚠️  Found {len(all_issues)} potential issues:")
        for issue in all_issues:
            print(f"   - {issue}")
    else:
        print("\n✅ No schema issues found")
    
    print(f"\n📊 Total tools: {len(tools)}")
    print(f"📊 Webhook tools: {len(webhook_urls)}")
    
    # Final recommendations
    print("\n" + "-" * 60)
    print("RECOMMENDATIONS")
    print("-" * 60)
    print("""
1. Ensure 'user_id' is passed as a dynamic variable when starting conversation
2. Check that webhook endpoints return within 30 seconds
3. Verify webhook responses match expected schema
4. Check ElevenLabs dashboard for tool execution logs
5. Test each webhook endpoint manually with curl/Postman
""")
    
    # Output raw config for debugging
    print("\n" + "-" * 60)
    print("RAW CONFIG (tools section)")
    print("-" * 60)
    print(json.dumps(tools, indent=2)[:5000])


if __name__ == "__main__":
    asyncio.run(main())
