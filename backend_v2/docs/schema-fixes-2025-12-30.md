# Database Schema Fixes - December 30, 2025

## Issues Fixed

### 1. Duplicate Index Error on Startup

**Error**: `sqlite3.OperationalError: index ix_spotify_user_context_user_id already exists`

**Root Cause**: 
- In `backend_v2/models/spotify_context.py`, indexes were defined twice:
  - Column definitions had `index=True` parameter (auto-creates indexes)
  - Explicit `Index()` declarations at the bottom of the file tried to create the same indexes again

**Solution**:
- Removed redundant explicit index declarations:
  - `Index("ix_spotify_user_context_user_id", SpotifyUserContext.user_id)` (line 131)
  - `Index("ix_dj_speech_history_created_at", DJSpeechHistory.created_at)` (line 133)
- Kept the composite index `ix_dj_speech_history_user_session` as it's unique
- Added comment explaining that single-column indexes are auto-created by `index=True`
- Manually dropped duplicate indexes from existing database using SQLite

**Files Modified**:
- `backend_v2/models/spotify_context.py`

---

### 2. Missing Column Error

**Error**: `sqlite3.OperationalError: no such column: users.spotify_connected_at`

**Root Cause**:
- The `User` model was updated to include a `spotify_connected_at` column
- The application uses `Base.metadata.create_all()` for database initialization
- `create_all()` only creates new tables, it doesn't add columns to existing tables
- Migration file `002_spotify_and_dj_history.py` existed but wasn't being run

**Solution**:
- Manually added the missing column to the `users` table using SQLite `ALTER TABLE`:
  ```sql
  ALTER TABLE users ADD COLUMN spotify_connected_at TEXT
  ```
- Column is nullable (defaults to NULL) for existing users

**Files Modified**:
- Database: `data/persistence.db` (added column to `users` table)

---

## Prevention

### For Future Schema Changes

1. **Option A: Proper Migration System**
   - Set up Alembic properly to run migrations on startup
   - Create migration files for all schema changes
   - Run `alembic upgrade head` during deployment

2. **Option B: Manual Migration Scripts**
   - Create migration scripts in `backend_v2/scripts/`
   - Document required migrations in deployment docs
   - Run scripts before starting new version

3. **Option C: Fresh Database**
   - For development, delete `data/persistence.db` and let `create_all()` recreate it
   - Not suitable for production with existing data

### Best Practices

1. **Index Definitions**: Choose ONE method:
   - Use `index=True` on column definitions for simple indexes
   - Use explicit `Index()` for composite indexes or custom index options
   - Never use both for the same column

2. **Schema Changes**: 
   - Always create migration files when adding/removing columns
   - Test migrations on a copy of production database
   - Document breaking changes in migration notes

---

## Verification

After fixes:
- ✅ Server starts without errors
- ✅ Database tables properly initialized
- ✅ All workers started successfully
- ✅ No duplicate index errors
- ✅ User registration endpoint works (queries `users` table successfully)

Server running on: `http://0.0.0.0:8000`

