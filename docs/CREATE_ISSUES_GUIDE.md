# How to Create GitHub Issues

The issues documented in `docs/issues.md` need to be created on GitHub. Here are three ways to do it:

## Method 1: Automated Script (Recommended)

### Step 1: Get a GitHub Personal Access Token

1. Go to https://github.com/settings/tokens
2. Click **"Generate new token (classic)"**
3. Give it a name: `Create Issues`
4. Select scope: **`repo`** (full control of private repositories)
5. Click **"Generate token"**
6. **Copy the token immediately** (you won't see it again!)

### Step 2: Run the Script

**Option A: Using environment variable (PowerShell)**
```powershell
cd C:\Users\JamiePC\Desktop\ai-djv2
$env:GITHUB_TOKEN="your_token_here"
python scripts/create_issues_from_env.py
```

**Option B: Interactive script**
```powershell
cd C:\Users\JamiePC\Desktop\ai-djv2
python scripts/create_issues_simple.py
# Paste your token when prompted
```

The script will create all 9 issues automatically with proper labels and formatting.

---

## Method 2: Manual Creation (If Script Doesn't Work)

1. Go to: https://github.com/armoordonjamie-sketch/ai-djv2/issues/new

2. For each issue, copy from `docs/github-issues.md`:
   - The **Title**
   - The **Body** (everything in the code block)
   - Add **Labels**: `bug`, `backend`, and the priority (`critical`, `high`, or `medium`)

3. Click **"Submit new issue"**

4. Repeat for all 9 issues.

---

## Method 3: Bulk Import (Advanced)

If you have many repositories or want to automate this regularly, you can use the GitHub CLI:

```powershell
# Install GitHub CLI first: https://cli.github.com/
gh auth login
gh issue create --title "[Critical] HistoryItem used as dict..." --body "..." --label "bug,backend,critical"
```

---

## Issues to Create

1. ✅ [Critical] HistoryItem used as dict in catalog selection
2. ✅ [Critical] Missing required argument in fallback to legacy selection
3. ✅ [Critical] Invalid access to song features and missing intent field
4. ✅ [High] Selected song does not include a `features` dict
5. ✅ [High] Genres/tags are passed as raw JSON strings
6. ✅ [High] Explicit-lyrics filtering never triggers
7. ✅ [Medium] Caller cannot override `reject_unknown` to False
8. ✅ [Medium] Unhandled JSON parse errors in user context
9. ✅ [Medium] Mood metadata missing from MoodData

---

## Troubleshooting

**"Authentication failed"**
- Make sure your token has the `repo` scope
- Check that the token hasn't expired
- Verify you have write access to the repository

**"Not found" or "404"**
- Verify the repository name: `armoordonjamie-sketch/ai-djv2`
- Make sure you're authenticated with the correct GitHub account

**"Labels don't exist"**
- The script will create labels automatically if they don't exist
- If manual creation fails, create the labels first:
  - Go to: https://github.com/armoordonjamie-sketch/ai-djv2/labels
  - Create: `critical`, `high`, `medium` (if they don't exist)

---

## After Creating Issues

Once all issues are created, you can:
- View them at: https://github.com/armoordonjamie-sketch/ai-djv2/issues
- Organize them into a project board
- Assign them to team members
- Link them to pull requests when fixing

