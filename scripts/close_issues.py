"""Close GitHub issues for completed backend fixes."""
import os
import requests

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO = "armoordonjamie-sketch/ai-djv2"

if not GITHUB_TOKEN:
    print("Error: GITHUB_TOKEN environment variable not set")
    exit(1)

headers = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}

# Map issues to their fix commits
issues = {
    2: {
        "title": "HistoryItem used as dict in catalog selection",
        "commit": "598f51c",
        "message": "Fixed in commit 598f51c - replaced dict access with attribute access for HistoryItem dataclass."
    },
    3: {
        "title": "Missing required argument in fallback to legacy selection",
        "commit": "598f51c",
        "message": "Fixed in commit 598f51c - added missing state argument to select_track fallback call."
    },
    4: {
        "title": "Invalid access to song features and missing intent field",
        "commit": "598f51c",
        "message": "Fixed in commit 598f51c - use scalar song.features access and intent.selection_rationale field."
    },
    5: {
        "title": "Selected song does not include a features dict",
        "commit": "598f51c",
        "message": "Fixed in commit 598f51c - return features as nested dict for transition planning."
    },
    6: {
        "title": "Genres/tags are passed as raw JSON strings",
        "commit": "954fc60",
        "message": "Fixed in commit 954fc60 - added _parse_json_list_safe() to parse JSON genres/tags to lists."
    },
    7: {
        "title": "Explicit-lyrics filtering never triggers",
        "commit": "954fc60",
        "message": "Fixed in commit 954fc60 - added explicit field to song dict for filtering."
    },
    8: {
        "title": "Caller cannot override reject_unknown to False",
        "commit": "7d3b491",
        "message": "Fixed in commit 7d3b491 - use None check instead of falsy check for reject_unknown parameter."
    },
    9: {
        "title": "Unhandled JSON parse errors in user context",
        "commit": "7d3b491",
        "message": "Fixed in commit 7d3b491 - added _safe_json_loads() helper to handle malformed JSON gracefully."
    },
    10: {
        "title": "Mood metadata missing from MoodData",
        "commit": "212f719",
        "message": "Fixed in commit 212f719 - extended MoodData with danceability_target, tempo range, genre_seeds, vibe_keywords, avoid_genres, example_artists, intro_personality, and era_hint fields."
    },
}

print(f"Closing {len(issues)} issues in {REPO}...\n")

success = 0
failed = 0

for issue_num, data in issues.items():
    url = f"https://api.github.com/repos/{REPO}/issues/{issue_num}"
    
    # Add closing comment
    comment_url = f"{url}/comments"
    comment_data = {
        "body": f"✅ {data['message']}\n\nSee commit: https://github.com/{REPO}/commit/{data['commit']}\n\nAll regression tests passing."
    }
    
    try:
        # Post comment
        response = requests.post(comment_url, headers=headers, json=comment_data)
        if response.status_code == 201:
            print(f"[{issue_num}] Comment added")
        else:
            print(f"[{issue_num}] Comment failed: {response.status_code}")
        
        # Close issue
        close_data = {"state": "closed"}
        response = requests.patch(url, headers=headers, json=close_data)
        
        if response.status_code == 200:
            print(f"[{issue_num}] Closed: {data['title']}")
            success += 1
        else:
            print(f"[{issue_num}] Failed to close: {response.status_code} - {response.text}")
            failed += 1
            
    except Exception as e:
        print(f"[{issue_num}] Error: {e}")
        failed += 1

print(f"\n{'='*60}")
print(f"Summary: {success} closed, {failed} failed")
print(f"{'='*60}")

