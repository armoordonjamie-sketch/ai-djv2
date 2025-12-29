"""Script to create GitHub issues from docs/issues.md.

This script reads docs/issues.md and creates GitHub issues for each documented issue.

Usage:
    python scripts/create_github_issues.py

Requires:
    - GitHub personal access token with 'repo' scope
    - Set GITHUB_TOKEN environment variable
    - Or pass --token flag
"""
import os
import re
import sys
from pathlib import Path
from typing import List, Dict

try:
    import requests
except ImportError:
    print("Error: 'requests' library required. Install with: pip install requests")
    sys.exit(1)


GITHUB_REPO = "armoordonjamie-sketch/ai-djv2"
GITHUB_API = "https://api.github.com"


def parse_issues_md(file_path: Path) -> List[Dict]:
    """Parse issues.md and extract issue information."""
    content = file_path.read_text(encoding="utf-8")
    
    issues = []
    current_issue = None
    current_section = None
    
    lines = content.split("\n")
    i = 0
    
    while i < len(lines):
        line = lines[i].strip()
        
        # Detect section headers (Critical, High, Medium)
        if line.startswith("## "):
            current_section = line.replace("##", "").strip()
            i += 1
            continue
        
        # Detect issue number (e.g., "1) HistoryItem used as a dict")
        issue_match = re.match(r"^(\d+)\)\s+(.+)$", line)
        if issue_match:
            # Save previous issue if exists
            if current_issue:
                issues.append(current_issue)
            
            issue_num = issue_match.group(1)
            title = issue_match.group(2)
            current_issue = {
                "number": issue_num,
                "title": title,
                "priority": current_section or "Unknown",
                "body": [],
                "labels": []
            }
            
            # Add priority label
            if current_section:
                current_issue["labels"].append(current_section.lower())
            
            i += 1
            continue
        
        # Collect issue body
        if current_issue:
            # Detect location line
            if line.startswith("- Location:"):
                current_issue["body"].append(f"**Location:** {line.replace('- Location:', '').strip()}")
                i += 1
                continue
            
            # Detect symptom line
            if line.startswith("- Symptom:"):
                symptom = line.replace("- Symptom:", "").strip()
                current_issue["body"].append(f"\n**Symptom:**\n{symptom}")
                i += 1
                continue
            
            # Detect impact line
            if line.startswith("- Impact:"):
                impact = line.replace("- Impact:", "").strip()
                current_issue["body"].append(f"\n**Impact:**\n{impact}")
                i += 1
                continue
            
            # Detect suggested fix
            if line.startswith("- Suggested fix:"):
                current_issue["body"].append("\n**Suggested Fix:**")
                i += 1
                # Collect fix lines (indented)
                fix_lines = []
                while i < len(lines) and (lines[i].startswith("  ") or lines[i].strip() == ""):
                    if lines[i].strip():
                        fix_lines.append(lines[i].strip())
                    i += 1
                if fix_lines:
                    current_issue["body"].append("\n".join(f"  - {fl}" for fl in fix_lines))
                continue
            
            # Regular body text
            if line and not line.startswith("#"):
                current_issue["body"].append(line)
        
        i += 1
    
    # Add last issue
    if current_issue:
        issues.append(current_issue)
    
    return issues


def create_issue(token: str, issue_data: Dict) -> bool:
    """Create a GitHub issue via API."""
    url = f"{GITHUB_API}/repos/{GITHUB_REPO}/issues"
    
    # Build issue body
    body = "\n".join(issue_data["body"])
    
    # Add reference to docs
    body += f"\n\n---\n\n*See [docs/issues.md](docs/issues.md) for full details.*"
    
    payload = {
        "title": f"[{issue_data['priority']}] {issue_data['title']}",
        "body": body,
        "labels": issue_data["labels"] + ["bug", "backend"]
    }
    
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        
        issue_url = response.json()["html_url"]
        print(f"✅ Created issue #{response.json()['number']}: {issue_data['title']}")
        print(f"   {issue_url}")
        return True
    except requests.exceptions.RequestException as e:
        print(f"❌ Failed to create issue '{issue_data['title']}': {e}")
        if hasattr(e.response, 'text'):
            print(f"   Response: {e.response.text}")
        return False


def main():
    """Main entry point."""
    # Get token
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        print("Error: GITHUB_TOKEN environment variable not set.")
        print("\nTo create issues, you need a GitHub personal access token:")
        print("1. Go to https://github.com/settings/tokens")
        print("2. Generate a new token with 'repo' scope")
        print("3. Set it: $env:GITHUB_TOKEN='your_token_here'")
        print("\nOr pass --token flag (not recommended for security)")
        sys.exit(1)
    
    # Parse issues
    repo_root = Path(__file__).parent.parent
    issues_file = repo_root / "docs" / "issues.md"
    
    if not issues_file.exists():
        print(f"Error: {issues_file} not found")
        sys.exit(1)
    
    print(f"Reading {issues_file}...")
    issues = parse_issues_md(issues_file)
    
    if not issues:
        print("No issues found in issues.md")
        sys.exit(1)
    
    print(f"\nFound {len(issues)} issues to create:")
    for issue in issues:
        print(f"  {issue['number']}. [{issue['priority']}] {issue['title']}")
    
    # Confirm
    print("\n⚠️  This will create GitHub issues. Continue? (y/N): ", end="")
    response = input().strip().lower()
    if response != "y":
        print("Cancelled.")
        sys.exit(0)
    
    # Create issues
    print("\nCreating issues...\n")
    success_count = 0
    for issue in issues:
        if create_issue(token, issue):
            success_count += 1
        print()  # Blank line between issues
    
    print(f"\n✅ Created {success_count}/{len(issues)} issues successfully")


if __name__ == "__main__":
    main()

