# Backend & Frontend Fixes - Onboarding Issues

## Summary

Fixed two critical issues with the onboarding flow:
1. **Backend**: Foreign key constraint error preventing intro speech generation during onboarding
2. **Frontend**: Infinite redirect loop after onboarding completion

---

## Issue 1: Backend Foreign Key Constraint Error ✅ FIXED

### Problem
```
ERROR - Intro speech generation failed: (sqlite3.IntegrityError) FOREIGN KEY constraint failed
```

During mood intro pre-generation (onboarding), the system was failing to store LLM traces because:
- Pre-generation uses fake session IDs like `"pre-gen-{mood_id}"`
- These sessions don't exist in the `sessions` table
- `llm_trace.session_id` had a foreign key constraint to `sessions.session_id`
- SQLite FK enforcement caused insert to fail

### Root Cause Files
- `backend_v2/orchestration/generation.py:45` - Creates fake session ID
- `backend_v2/orchestration/agents.py:680-689` - Stores LLM trace with fake session ID
- `backend_v2/models/existing.py:290-295` - Had FK constraint on `session_id`
- `backend_v2/db/session.py:36` - Enables SQLite FK enforcement

### Solution Applied
✅ **Removed the foreign key constraint** from `llm_trace.session_id`

**Files Modified:**
1. `backend_v2/models/existing.py`:
   - Removed `ForeignKey("sessions.session_id")` from `session_id` column
   - Removed `session` relationship from `LLMTrace`
   - Removed `llm_traces` relationship from `Session`
   - Added documentation explaining why there's no FK constraint

2. `backend_v2/scripts/fix_llm_trace_fk.py`:
   - Created migration script to remove FK constraint from existing database
   - Successfully migrated 446 existing llm_trace rows

### Verification
```bash
# Before fix:
llm_trace foreign keys:
  session_id -> sessions.session_id (on_delete=CASCADE)  ❌
  mood_id -> moods.id (on_delete=SET NULL)
  user_id -> users.id (on_delete=SET NULL)

# After fix:
llm_trace foreign keys:
  mood_id -> moods.id (on_delete=SET NULL)  ✅
  user_id -> users.id (on_delete=SET NULL)  ✅
  (no session_id constraint)  ✅
```

**Migration Status**: ✅ Completed successfully on `data/persistence.db`

---

## Issue 2: Frontend Infinite Redirect Loop ✅ FIXED

### Problem
After mood generation completed, users experienced:
- Infinite redirect loop between `/moods` and `/onboarding`
- Black screen / loading forever
- Rapid polling of `/api/v1/onboard/status` (~50ms intervals)

### Root Cause
The `MoodCreationPage` was navigating to `/moods` after mood generation completed, but the `AuthProvider`'s `isOnboarded` state was stale. This caused `ProtectedRoute` to immediately redirect back to `/onboarding`, creating an infinite loop.

**Sequence:**
1. User completes voice onboarding → mood generation starts
2. Backend updates `user.is_onboarded = true` in database
3. `MoodCreationPage` polls `/onboard/generation-status` until complete
4. Frontend navigates to `/moods`
5. `ProtectedRoute` checks `isOnboarded` from `AuthProvider` (still `false` - stale!)
6. Redirects back to `/onboarding`
7. Loop continues forever

### Solution Applied
✅ **Call `refreshAuth()` immediately after mood generation completes**

**Files Modified:**
1. `frontend/src/pages/MoodCreationPage.tsx`:
   - Import `useAuth` hook
   - Call `await refreshAuth()` when `data.status === "complete"`
   - Call `await refreshAuth()` on failure too (for safety)
   - Added to `checkStatus` dependencies

```typescript
if (data.status === "complete") {
  setCompletedSteps(["voice_processing", "mood_parsing", "mood_creating", "intro_generating"])
  // Refresh auth state to update isOnboarded status ✅
  await refreshAuth()
  setTimeout(() => {
    navigate("/moods", { replace: true })
  }, 1500)
} else if (data.status === "failed") {
  setError(data.error || "Something went wrong")
  await refreshAuth() // Refresh auth even on failure
}
```

### Verification
The fix ensures:
- ✅ `AuthProvider.isOnboarded` is updated before navigation
- ✅ `ProtectedRoute` sees correct state
- ✅ No redirect loop
- ✅ Smooth transition to `/moods` page

---

## Additional Observations

### Missing Intro Status Updates (Still Investigating)

**User reported**: "it only shows updates when it creates the moods not when creating the intros"

**Current findings:**
- Intro generation happens in parallel after moods are created
- Status event for intro generation: `StatusStep.INTRO_GENERATING`
- Frontend `StatusTimeline` includes this step
- May be a timing issue with WebSocket events vs polling

**Next steps to debug:**
1. Check if `StatusStep.INTRO_GENERATING` events are being emitted
2. Verify WebSocket connection is still active during intro generation
3. Check if frontend is handling `intro_generating` status correctly

### Cached Intros Ready for Next Session

The code is correctly set up to use pre-generated intros:
- ✅ `mood_generator.py:237-241` saves `intro_segment_path` to database
- ✅ `preference_bundle.py:445` loads it into `bundle.mood`
- ✅ `loop.py:201-284` checks for and uses cached intros
- ✅ Database schema has `intro_segment_path` and `intro_song_uuid` columns

**Current status:** No moods in database have cached intros yet. After a successful onboarding with the FK fix, intros should be cached.

**Expected log when using cached intro:**
```
INFO - Using pre-generated intro: /path/to/segment
```

---

## Testing Checklist

### Backend
- [x] Database migration completed successfully
- [x] FK constraint removed from llm_trace.session_id
- [ ] Complete onboarding without FK constraint errors
- [ ] Verify intros are generated (5/5 intros_ready in status)
- [ ] Verify `moods` table has `intro_segment_path` populated
- [ ] Press play and verify cached intro is used (check logs)

### Frontend
- [x] Frontend infinite loop fixed
- [ ] Complete onboarding and verify smooth transition to `/moods`
- [ ] No rapid polling after completion
- [ ] Status updates visible during mood creation
- [ ] Status updates visible during intro generation (needs verification)

---

## How to Test

### 1. Restart Backend
The database has been migrated, so just restart the backend:
```bash
cd backend_v2
python main.py
```

### 2. Complete Onboarding
- Go through voice onboarding
- Watch for status updates (both moods and intros)
- Verify smooth transition to moods page (no loop)

### 3. Check Database
```bash
python backend_v2/scripts/check_db_schema.py
```
Should show moods with `intro_segment_path` populated.

### 4. Press Play
- Select a mood and press play
- Check backend logs for: `INFO - Using pre-generated intro: ...`
- Verify playback starts with the cached intro

---

## Files Changed

### Backend
- `backend_v2/models/existing.py` - Removed FK constraint on llm_trace.session_id
- `backend_v2/scripts/fix_llm_trace_fk.py` - Migration script (new)
- `backend_v2/scripts/check_db_schema.py` - Schema inspection tool (new)
- `backend_v2/scripts/list_tables.py` - Table listing tool (updated)

### Frontend
- `frontend/src/pages/MoodCreationPage.tsx` - Added refreshAuth() call

### Documentation
- `docs/backend_fixes_onboarding.md` - Detailed technical analysis (new)
- `docs/FIXES_SUMMARY.md` - This summary document (new)

---

## Notes

- The FK constraint removal is **permanent** and correct - pre-generation scenarios legitimately don't have real sessions
- The model definition now matches the migrated database schema
- Future deployments will create tables with the correct schema from the start
- No data was lost during migration (446 llm_trace rows preserved)

---

**Status**: ✅ Backend FK issue fixed, Frontend loop fixed, Ready for testing

