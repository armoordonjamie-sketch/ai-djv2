"""Script to manually test the onboarding submit endpoint.

This script posts a test payload to /api/v1/onboard/submit to debug issues.

Usage:
    python backend_v2/scripts/test_onboard_submit.py [--local]

Options:
    --local    Test against localhost:8000 instead of production

Requires:
    - ONBOARD_TOOL_SECRET in .env
    - BACKEND_BASE_URL in .env (or defaults to https://jamify.jamiearmoordon.co.uk)
"""
import os
import sys
import json
import httpx
from dotenv import load_dotenv

load_dotenv()

# Check for --local flag
USE_LOCAL = "--local" in sys.argv or "-l" in sys.argv

# Configuration
if USE_LOCAL:
    BACKEND_BASE_URL = "http://localhost:8000"
    print("🏠 Using localhost:8000")
else:
    BACKEND_BASE_URL = os.getenv("BACKEND_BASE_URL", "https://jamify.jamiearmoordon.co.uk")
    print(f"🌐 Using production: {BACKEND_BASE_URL}")

ONBOARD_TOOL_SECRET = os.getenv("ONBOARD_TOOL_SECRET")

if not ONBOARD_TOOL_SECRET:
    print("❌ ONBOARD_TOOL_SECRET not set in .env")
    sys.exit(1)

# User ID from the failed attempt
USER_ID = "a33fad8a-779a-47ac-9c07-0038399a2dd8"

# Test payload based on the conversation
# User said: Christmas music, Ariana Grande, UK Top 40, energetic/funny DJ
payload = {
    "user_id": USER_ID,
    "display_name": "Jamie",
    "favorite_genres": ["pop", "christmas"],
    "favorite_artists": ["Ariana Grande"],
    "favorite_songs": [],
    "no_go": [],
    "explicit_lyrics": "ok",
    "dj_personality": "hype_energetic",  # energetic + funny -> hype_energetic
    "raw_context": "Christmas music mix with Ariana Grande Christmas music and UK Top 40 hits. Energetic and funny DJ personality with jokes about Ace the dog eating treats on Christmas day."
}

# First, check if server is up
health_url = f"{BACKEND_BASE_URL}/health"
print(f"🏥 Checking server health: {health_url}")
try:
    health_response = httpx.get(health_url, timeout=5.0)
    if health_response.status_code == 200:
        print("✅ Server is up and responding")
    else:
        print(f"⚠️  Server returned status {health_response.status_code}")
except httpx.RequestError as e:
    print(f"❌ Cannot reach server: {e}")
    print(f"   Make sure the backend is running at {BACKEND_BASE_URL}")
    if not USE_LOCAL:
        print(f"   Try running with --local flag to test against localhost:8000")
    sys.exit(1)
except Exception as e:
    print(f"⚠️  Health check failed: {e}")
    print("   Continuing anyway...")

print()

url = f"{BACKEND_BASE_URL}/api/v1/onboard/submit"
headers = {
    "Content-Type": "application/json",
    "X-Onboard-Secret": ONBOARD_TOOL_SECRET
}

print(f"🧪 Testing onboarding submit for user: {USER_ID}")
print(f"📍 URL: {url}")
print(f"📦 Payload:")
print(json.dumps(payload, indent=2))
print()

try:
    response = httpx.post(url, json=payload, headers=headers, timeout=30.0)
    
    print(f"📊 Response Status: {response.status_code}")
    print(f"📋 Response Headers:")
    for key, value in response.headers.items():
        print(f"   {key}: {value}")
    print()
    
    try:
        response_json = response.json()
        print(f"📄 Response Body:")
        print(json.dumps(response_json, indent=2))
    except:
        print(f"📄 Response Body (raw):")
        print(response.text)
    
    if response.status_code == 200:
        print("\n✅ Success! Onboarding submitted successfully.")
    elif response.status_code == 502:
        print(f"\n❌ 502 Bad Gateway - The backend server is down or unreachable.")
        print(f"   This usually means:")
        print(f"   - The backend process is not running")
        print(f"   - The server crashed or is restarting")
        print(f"   - There's a network issue between Cloudflare and the origin server")
        if not USE_LOCAL:
            print(f"\n   💡 Try testing locally first:")
            print(f"      python backend_v2/scripts/test_onboard_submit.py --local")
        sys.exit(1)
    elif response.status_code == 422:
        print(f"\n❌ 422 Unprocessable Entity - Validation error")
        print(f"   Check the response body above for validation details")
        sys.exit(1)
    else:
        print(f"\n❌ Failed with status {response.status_code}")
        sys.exit(1)
        
except httpx.HTTPError as e:
    print(f"❌ HTTP Error: {e}")
    sys.exit(1)
except Exception as e:
    print(f"❌ Error: {e}")
    sys.exit(1)

