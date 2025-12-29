"""Smoke test for prod-like frontend serving.

Verifies that the backend correctly serves the built Vite frontend.

Usage:
    python -m backend_v2.scripts.smoke_test_prod

Prerequisites:
    1. Build frontend: cd frontend && npm run build
    2. Start backend: SERVE_FRONTEND=true uvicorn backend_v2.main:app --port 5173
"""
import sys
import urllib.request
import urllib.error
from pathlib import Path


BASE_URL = "http://localhost:5173"

# ANSI colors for terminal output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"


def check(name: str, passed: bool, detail: str = ""):
    """Print check result."""
    icon = f"{GREEN}✓{RESET}" if passed else f"{RED}✗{RESET}"
    msg = f"{icon} {name}"
    if detail:
        msg += f" ({detail})"
    print(msg)
    return passed


def fetch(path: str, timeout: int = 5) -> tuple[int, str, dict]:
    """Fetch URL and return (status_code, body, headers)."""
    url = f"{BASE_URL}{path}"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            # Normalize header keys to lowercase for consistent access
            headers = {k.lower(): v for k, v in resp.headers.items()}
            return resp.status, resp.read().decode("utf-8", errors="ignore"), headers
    except urllib.error.HTTPError as e:
        return e.code, "", {}
    except urllib.error.URLError as e:
        return 0, str(e.reason), {}


def find_js_asset() -> str:
    """Find a JS asset filename from dist/assets."""
    dist_assets = Path(__file__).parent.parent.parent / "frontend" / "dist" / "assets"
    if dist_assets.exists():
        for f in dist_assets.iterdir():
            if f.suffix == ".js":
                return f.name
    return "index-DEkxOjHe.js"  # fallback


def main():
    print(f"\n{YELLOW}=== Prod-Like Smoke Test ==={RESET}\n")
    print(f"Target: {BASE_URL}\n")
    
    all_passed = True
    
    # Test 1: Root returns HTML
    status, body, headers = fetch("/")
    passed = status == 200 and '<div id="root">' in body
    all_passed &= check("GET / returns index.html", passed, f"status={status}")
    
    # Test 2: JS asset loads
    js_file = find_js_asset()
    status, body, headers = fetch(f"/assets/{js_file}")
    passed = status == 200 and len(body) > 1000
    cache_header = headers.get("cache-control", "")
    has_cache = "max-age" in cache_header
    all_passed &= check(f"GET /assets/{js_file[:20]}... returns JS", passed, f"cached={has_cache}")
    
    # Test 3: SPA fallback for /moods
    status, body, headers = fetch("/moods")
    passed = status == 200 and '<div id="root">' in body
    all_passed &= check("GET /moods returns index.html (SPA fallback)", passed, f"status={status}")
    
    # Test 4: API health endpoint still works
    status, body, headers = fetch("/health")
    passed = status == 200 and '"status":"ok"' in body
    all_passed &= check("GET /health returns JSON", passed, f"status={status}")
    
    # Test 5: index.html has no-cache header
    status, body, headers = fetch("/")
    cache_header = headers.get("cache-control", "")
    passed = "no-cache" in cache_header
    all_passed &= check("index.html has no-cache header", passed, f"Cache-Control: {cache_header}")
    
    # Summary
    print()
    if all_passed:
        print(f"{GREEN}All checks passed!{RESET}")
        return 0
    else:
        print(f"{RED}Some checks failed. Is the backend running with SERVE_FRONTEND=true?{RESET}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
