"""Create GitHub issues using GITHUB_TOKEN environment variable.

Usage:
    $env:GITHUB_TOKEN="your_token_here"
    python scripts/create_issues_from_env.py
"""
import os
import sys
from typing import Dict, Any, Optional, Tuple
import requests

REPO = "armoordonjamie-sketch/ai-djv2"
API_URL = f"https://api.github.com/repos/{REPO}/issues"

# Same issues as create_issues_simple.py
ISSUES = [
    {
        "title": "[Critical] HistoryItem used as dict in catalog selection",
        "body": """## Location
`backend_v2/orchestration/agents.py:543-552`

## Symptom
`HistoryItem` is a dataclass, but the code calls `hist_item.get(...)`, which raises `AttributeError` once history is non-empty.

## Impact
Catalog selection flow crashes during recent-track conversion, causing fallback failures or a stalled loop.

## Suggested Fix
- Replace dict access with attributes: `hist_item.artist`, `hist_item.title`.
- If features are required for MMR, either extend `HistoryItem` to include features or query the DB for features by `song_uuid` before building `CatalogTrack`.

## Reference
See [docs/issues.md](docs/issues.md) for full details.""",
        "labels": ["bug", "backend", "critical"]
    },
    {
        "title": "[Critical] Missing required argument in fallback to legacy selection",
        "body": """## Location
`backend_v2/orchestration/agents.py:582`

## Symptom
`select_track(db, bundle, prev_song)` omits the required `state` argument.

## Impact
Raises a `TypeError` at runtime when catalog flow falls back.

## Suggested Fix
- Call `select_track(db, bundle, state, prev_song, history_ids)` with the correct signature.

## Reference
See [docs/issues.md](docs/issues.md) for full details.""",
        "labels": ["bug", "backend", "critical"]
    },
    {
        "title": "[Critical] Invalid access to song features and missing intent field",
        "body": """## Location
`backend_v2/orchestration/agents.py:630-633`

## Symptom
- `song.features[0]` is used, but `Song.features` is `uselist=False` and should be accessed as `song.features`.
- `intent.rationale` does not exist; the column is `selection_rationale`.

## Impact
Crash immediately after successful acquisition, preventing playback.

## Suggested Fix
- Use `song.features.energy` / `song.features.valence` / `song.features.tempo`.
- Use `intent.selection_rationale` (or fallback to a default string).

## Reference
See [docs/issues.md](docs/issues.md) for full details.""",
        "labels": ["bug", "backend", "critical"]
    },
    {
        "title": "[High] Selected song does not include a `features` dict",
        "body": """## Location
`backend_v2/orchestration/agents.py:625-635`

## Symptom
The returned dict puts `energy`, `valence`, and `tempo` at top level instead of under `features`.

## Impact
Transition planning and mixing logic expect `song['features']`, so they lose feature data and fall back to generic transitions.

## Suggested Fix
- Return a `features` dict consistent with `select_track` and `get_scored_candidates` outputs.

## Reference
See [docs/issues.md](docs/issues.md) for full details.""",
        "labels": ["bug", "backend", "high"]
    },
    {
        "title": "[High] Genres/tags are passed as raw JSON strings",
        "body": """## Location
`backend_v2/services/preference_bundle.py:952-960`

## Symptom
`song.genres` and `song.tags` are stored as JSON strings, but `apply_hard_constraints` treats them as lists and lowercases each element.

## Impact
Denylist/no-go checks operate on characters, so genre filtering silently fails.

## Suggested Fix
- Parse JSON strings to lists when building `song_dict`.
- If parsing fails, fall back to an empty list and log a warning.

## Reference
See [docs/issues.md](docs/issues.md) for full details.""",
        "labels": ["bug", "backend", "high"]
    },
    {
        "title": "[High] Explicit-lyrics filtering never triggers",
        "body": """## Location
`backend_v2/services/preference_bundle.py:747-753`

## Symptom
`apply_hard_constraints` checks `song['explicit']`, but the song dict never includes it.

## Impact
Users who set explicit_lyrics=avoid still get explicit tracks.

## Suggested Fix
- Add `explicit` from `Song.explicit` into each song dict.
- Normalize to boolean when checking (SQLite uses 0/1).

## Reference
See [docs/issues.md](docs/issues.md) for full details.""",
        "labels": ["bug", "backend", "high"]
    },
    {
        "title": "[Medium] Caller cannot override `reject_unknown` to False",
        "body": """## Location
`backend_v2/services/preference_bundle.py:670`

## Symptom
`reject_unknown = reject_unknown if reject_unknown else REJECT_UNKNOWN_FEATURES` forces the config default when `reject_unknown` is `False`.

## Impact
Callers cannot disable unknown-feature rejection.

## Suggested Fix
- Use `reject_unknown = REJECT_UNKNOWN_FEATURES if reject_unknown is None else reject_unknown`.

## Reference
See [docs/issues.md](docs/issues.md) for full details.""",
        "labels": ["bug", "backend", "medium"]
    },
    {
        "title": "[Medium] Unhandled JSON parse errors in user context",
        "body": """## Location
`backend_v2/services/preference_bundle.py:414`

## Symptom
`json.loads(context_row.parsed_json)` is unguarded.

## Impact
A single malformed context record crashes bundle construction and the DJ loop.

## Suggested Fix
- Wrap in try/except, log the parse error, and set `parsed_json` to `None`.

## Reference
See [docs/issues.md](docs/issues.md) for full details.""",
        "labels": ["bug", "backend", "medium"]
    },
    {
        "title": "[Medium] Mood metadata missing from MoodData",
        "body": """## Location
`backend_v2/services/preference_bundle.py:43` (MoodData definition) and `build_preference_bundle`

## Symptom
MoodData does not carry `danceability_target`, `genre_seeds_json`, `vibe_keywords_json`, `intro_personality`, or `era_hint`.

## Impact
Prompt generation and catalog scoring that look for these fields always see them as missing, so mood-specific personalization is not applied.

## Suggested Fix
- Extend `MoodData` and populate these fields in `build_preference_bundle`.
- Update usages to reference the structured fields directly instead of `hasattr` checks.

## Reference
See [docs/issues.md](docs/issues.md) for full details.""",
        "labels": ["bug", "backend", "medium"]
    }
]


def create_issue(token: str, issue_data: Dict[str, Any]) -> Tuple[Optional[int], Optional[str]]:
    """Create a single GitHub issue."""
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    payload = {
        "title": issue_data["title"],
        "body": issue_data["body"],
        "labels": issue_data["labels"]
    }
    
    try:
        response = requests.post(API_URL, json=payload, headers=headers)
        response.raise_for_status()
        result = response.json()
        return result["number"], result["html_url"]
    except requests.exceptions.RequestException as e:
        print(f"Error: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response: {e.response.text}")
        return None, None


def main():
    token = os.getenv("GITHUB_TOKEN")
    
    if not token:
        print("Error: GITHUB_TOKEN environment variable not set.")
        print()
        print("To create issues, you need a GitHub Personal Access Token:")
        print("1. Go to: https://github.com/settings/tokens")
        print("2. Click 'Generate new token (classic)'")
        print("3. Name it 'Create Issues'")
        print("4. Select scope: 'repo' (full control of private repositories)")
        print("5. Generate and copy the token")
        print()
        print("Then set it in PowerShell:")
        print('  $env:GITHUB_TOKEN="your_token_here"')
        print()
        print("Or run the interactive script:")
        print("  python scripts/create_issues_simple.py")
        sys.exit(1)
    
    print(f"Creating {len(ISSUES)} issues in {REPO}...")
    print()
    
    created = 0
    failed = 0
    
    for i, issue in enumerate(ISSUES, 1):
        print(f"[{i}/{len(ISSUES)}] {issue['title']}...", end=" ")
        number, url = create_issue(token, issue)
        
        if number:
            print(f"[OK] #{number}")
            print(f"   {url}")
            created += 1
        else:
            print("[FAILED]")
            failed += 1
        print()
    
    print("=" * 60)
    print(f"Summary: {created} created, {failed} failed")
    print("=" * 60)


if __name__ == "__main__":
    main()

