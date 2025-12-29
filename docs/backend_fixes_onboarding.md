# Backend Fixes - Onboarding Loop & Intro Generation

## Issues Fixed

### 1. Foreign Key Constraint Error During Intro Generation

**Problem:**
```
ERROR - Intro speech generation failed: (sqlite3.IntegrityError) FOREIGN KEY constraint failed
```

During mood intro pre-generation (onboarding), the `store_llm_trace` function was trying to insert records with `session_id=f"pre-gen-{mood_id}"`. However, the `llm_trace` table had a foreign key constraint on `session_id` referencing the `sessions` table, and these pre-generation "sessions" didn't actually exist in the database.

**Root Cause:**
- `backend_v2/orchestration/generation.py:45` creates a mock session ID for pre-generation: `session_id=f"pre-gen-{mood_id}"`
- `backend_v2/orchestration/agents.py:680-689` stores LLM traces with this session ID
- `backend_v2/models/existing.py:290-295` defined `session_id` with `ForeignKey("sessions.session_id", ondelete="CASCADE")`
- SQLite FK constraints are enabled in `backend_v2/db/session.py:36`

**Solution:**
Removed the foreign key constraint from `LLMTrace.session_id` to support pre-generation scenarios where no real session exists.

**Changed Files:**
- `backend_v2/models/existing.py`:
  - Removed `ForeignKey` constraint from `LLMTrace.session_id`
  - Removed `LLMTrace.session` relationship
  - Updated `Session.llm_traces` relationship (removed)
  - Added documentation explaining the rationale

**Migration:**
For existing databases, the tables will need to be recreated. The safest approach:
1. Backup your data
2. Delete `data/ai_dj.db`
3. Restart backend (tables will be created with new schema)

Or use `backend_v2/scripts/fix_llm_trace_fk.py` to migrate (not tested yet since DB was empty).

### 2. Cached Intros Not Being Used on Play

**Problem:**
User reported that when pressing "play", the pre-generated intro segments (created during onboarding) were not being used. The logs show a new session starting but not using the cached `intro_segment_path`.

**Investigation Needed:**
The code in `backend_v2/orchestration/loop.py:201-240` appears to correctly check for pre-generated intros:
```python
if bundle.mood and bundle.mood.intro_segment_path:
    intro_path = bundle.mood.intro_segment_path
    if os.path.exists(intro_path):
        logger.info(f"Using pre-generated intro: {intro_path}")
```

Need to check:
1. Is `intro_segment_path` being saved to the database correctly during onboarding?
2. Is the path still valid when playback starts?
3. Are there any error logs preventing the cached intro from being used?

**Next Steps:**
1. Check backend logs for "Using pre-generated intro" message
2. Verify `moods` table has `intro_segment_path` populated
3. Verify the file path exists and is accessible

---

## Testing Checklist

- [ ] Backend starts without errors (tables created)
- [ ] Can complete onboarding without FK constraint errors
- [ ] Intros are generated during onboarding (status updates visible)
- [ ] After onboarding, `moods` table has `intro_segment_path` populated
- [ ] Pressing "play" uses the cached intro (check logs for "Using pre-generated intro")
- [ ] No infinite redirect loop after onboarding completes

---

## Related Frontend Fix

The infinite redirect loop issue was fixed in the frontend by calling `refreshAuth()` in `MoodCreationPage.tsx` after mood generation completes. This ensures the `isOnboarded` flag is updated immediately, preventing `ProtectedRoute` from redirecting back to `/onboarding`.

See `frontend/src/pages/MoodCreationPage.tsx:241` for the fix.

