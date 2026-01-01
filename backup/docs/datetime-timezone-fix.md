# DateTime Timezone Comparison Fix - December 30, 2025

## Issue
The `/api/v1/spotify/fetch` endpoint was failing with:
```
TypeError: can't compare offset-naive and offset-aware datetimes
```

## Root Cause
When comparing `utc_now()` (timezone-aware) with `spotify_context.token_expires_at` (potentially timezone-naive from database), Python raises an error because it can't compare datetimes with different timezone information.

```python
# This fails if token_expires_at is naive:
if utc_now() >= spotify_context.token_expires_at:
```

## Solution
Use `ensure_utc()` utility function to convert the database datetime to timezone-aware before comparison:

```python
from backend_v2.utils.time import utc_now, ensure_utc

# Convert to timezone-aware before comparison:
token_expires_at = ensure_utc(spotify_context.token_expires_at)
if utc_now() >= token_expires_at:
```

## Why This Happens
- SQLAlchemy stores datetimes in SQLite as strings
- When retrieving them, they may lose timezone information
- Python's datetime comparison requires both to be either naive or aware
- Our `utc_now()` always returns timezone-aware datetimes
- Our `ensure_utc()` safely converts any datetime to timezone-aware UTC

## Files Modified
- `backend_v2/api/spotify.py` - Fixed token expiration check in `/fetch` endpoint

## Prevention
Always use `ensure_utc()` when comparing datetimes retrieved from the database with `utc_now()`:

```python
# ❌ BAD: May fail
if utc_now() >= db_datetime:

# ✅ GOOD: Always works
if utc_now() >= ensure_utc(db_datetime):
```

