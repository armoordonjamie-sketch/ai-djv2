"""
Test webhook endpoints directly to verify they work correctly.
"""

import os
import asyncio
import time
import json
import httpx
from dotenv import load_dotenv

load_dotenv()

BACKEND_URL = os.getenv("BACKEND_URL", "https://jamify.jamiearmoordon.co.uk")
ONBOARD_SECRET = os.getenv("ONBOARD_TOOL_SECRET")

HEADERS = {
    "Content-Type": "application/json",
    "X-Onboard-Secret": ONBOARD_SECRET
}


async def test_endpoint(name: str, url: str, payload: dict):
    """Test a single endpoint and measure timing."""
    print(f"\n{'='*60}")
    print(f"Testing: {name}")
    print(f"URL: {url}")
    print(f"{'='*60}")
    
    try:
        start = time.time()
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=HEADERS, json=payload)
            elapsed = time.time() - start
            
            print(f"Status: {response.status_code}")
            print(f"Time: {elapsed:.2f}s")
            
            if response.status_code == 200:
                data = response.json()
                print(f"Response size: {len(json.dumps(data))} bytes")
                print(f"Response preview: {json.dumps(data, indent=2)[:1000]}")
                return True, elapsed
            else:
                print(f"Error: {response.text[:500]}")
                return False, elapsed
                
    except Exception as e:
        print(f"Error: {e}")
        return False, 0


async def main():
    print("Testing Webhook Endpoints")
    print("=" * 60)
    print(f"Backend URL: {BACKEND_URL}")
    print(f"Secret configured: {'Yes' if ONBOARD_SECRET else 'No'}")
    
    if not ONBOARD_SECRET:
        print("\n❌ ONBOARD_TOOL_SECRET not set in .env!")
        return
    
    results = []
    
    # Test 1: Artist Search
    success, time_taken = await test_endpoint(
        "Artist Search",
        f"{BACKEND_URL}/api/v1/deezer/artist-search",
        {"artist_name": "Taylor Swift"}
    )
    results.append(("Artist Search", success, time_taken))
    
    # Test 2: Related Artists
    success, time_taken = await test_endpoint(
        "Related Artists (by name)",
        f"{BACKEND_URL}/api/v1/deezer/related-artists",
        {"artist_name": "Taylor Swift"}
    )
    results.append(("Related Artists", success, time_taken))
    
    # Test 3: Track Search
    success, time_taken = await test_endpoint(
        "Track Search",
        f"{BACKEND_URL}/api/v1/deezer/search-tracks",
        {"query": "Taylor Swift", "limit": 3}
    )
    results.append(("Track Search", success, time_taken))
    
    # Test 4: Play Preview
    success, time_taken = await test_endpoint(
        "Play Preview",
        f"{BACKEND_URL}/api/v1/deezer/play-preview",
        {"artist_name": "Taylor Swift", "track_title": "Shake It Off"}
    )
    results.append(("Play Preview", success, time_taken))
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    for name, success, time_taken in results:
        icon = "✅" if success else "❌"
        print(f"{icon} {name}: {time_taken:.2f}s")
    
    # Check for slow endpoints
    slow = [r for r in results if r[2] > 15]
    if slow:
        print("\n⚠️  WARNING: Some endpoints took >15 seconds!")
        print("   This may cause ElevenLabs agent timeouts.")
        print("   Consider optimizing or increasing response_timeout_secs.")


if __name__ == "__main__":
    asyncio.run(main())
