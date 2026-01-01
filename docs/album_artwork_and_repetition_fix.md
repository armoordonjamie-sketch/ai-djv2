# Album Artwork & Song Repetition Fix

**Date:** 2025-12-29  
**Issues:** Album artwork not displaying on frontend, songs repeating despite being in play history

## Issues Found

### Issue 1: Missing Album Artwork
**Symptom:** Album artwork was being fetched and enriched (visible in logs), but not showing on the frontend.

**Root Cause:** The `select_track_via_catalog()` function in `backend_v2/orchestration/agents.py` was not including `artwork_url` in its return dictionary, even though:
- The Song model has the field
- The metadata enrichment was working correctly
- The frontend was expecting it

**Location:** `backend_v2/orchestration/agents.py:631-651`

**Fix:** Added `"artwork_url": song.artwork_url` to the return dictionary.

```python
return {
    "uuid": song.uuid,
    "title": song.title,
    "artist": song.artist,
    "local_path": song.local_path,
    "artwork_url": song.artwork_url,  # ✅ Added this line
    "features": { ... },
    "rationale": intent.selection_rationale or "Catalog selection",
    "selection_method": "catalog_intent",
}
```

### Issue 2: Songs Repeating
**Symptom:** Songs like "The Fate of Ophelia" and "Opalite" were played multiple times in the same session.

**Root Cause:** The `select_track_via_catalog()` function was only using the last 10 tracks from `bundle.history.recent_tracks` for diversity filtering, completely ignoring the full `history_ids` list passed as a parameter.

**Location:** `backend_v2/orchestration/agents.py:536-555`

**Before:**
```python
# Convert recent history to CatalogTrack format for diversity
recent_catalog_tracks = []
for hist_item in bundle.history.recent_tracks[:10]:  # ❌ Only last 10!
    if hist_item.artist and hist_item.title:
        recent_catalog_tracks.append(CatalogTrack(...))
```

**After:**
```python
# Convert ALL history_ids to CatalogTrack format for proper diversity filtering
recent_catalog_tracks = []
if history_ids:
    # Query database for all songs in history
    result = await db.execute(
        select(Song).where(Song.uuid.in_(history_ids))
    )
    history_songs = result.scalars().all()
    
    # Convert to CatalogTrack format
    for song in history_songs:
        if song.artist and song.title:
            recent_catalog_tracks.append(CatalogTrack(...))

logger.info(f"🚫 Excluding {len(recent_catalog_tracks)} previously played tracks from selection")
```

## Data Flow

### Album Artwork Flow
1. **Metadata Enrichment** (`backend_v2/tools/song_downloader.py`) → Fetches artwork from Apple Music/MusicBrainz
2. **Song Model** (`backend_v2/models/existing.py`) → Stores `artwork_url` field
3. **Track Selection** (`backend_v2/orchestration/agents.py`) → Returns song dict with `artwork_url` ✅
4. **Loop Queuing** (`backend_v2/orchestration/loop.py`) → Includes `artwork_url` in segment metadata
5. **Pipeline Emission** (`backend_v2/streaming/pipeline.py`) → Emits `now_playing` event with `artwork_url`
6. **WebSocket** → Sends to frontend
7. **PlayerProvider** (`frontend/src/providers/PlayerProvider.tsx`) → Updates `currentTrack.artworkUrl`
8. **NowPlaying Component** (`frontend/src/components/player/NowPlaying.tsx`) → Displays artwork

### Song Repetition Prevention Flow
1. **DJLoop** (`backend_v2/orchestration/loop.py`) → Passes `history_ids=self.songs_played + self.failed_song_uuids`
2. **Track Selection** (`backend_v2/orchestration/agents.py`) → Queries DB for ALL songs in `history_ids` ✅
3. **Catalog Selector** (`backend_v2/catalog/selector.py`) → Filters out tracks matching history
4. **MMR Selection** → Applies diversity ranking to remaining candidates

## Testing

### Album Artwork
1. Start a new stream
2. Wait for first track to play
3. Check frontend - artwork should now display (if available in metadata)
4. Check browser console for `now_playing` event - should include `artwork_url`

### Song Repetition
1. Start a stream and let it play 15+ songs
2. Check play history - no song should repeat
3. Backend logs should show: `🚫 Excluding N previously played tracks from selection`

## Notes

- **Apify Limit Exceeded:** During testing, the Apple Music API (via Apify) hit its monthly limit. This is why some songs like "Ruin The Friendship" and "The Life of a Showgirl" don't have artwork. The fix is still valid - it will work once the API limit resets.

- **Archive.org Unavailable:** MusicBrainz's Cover Art Archive was returning 503 errors during testing. This is a temporary external service issue.

- **Deezer Fallback:** The metadata enrichment correctly falls back to Deezer when Apple Music fails, but Deezer doesn't always have artwork URLs.

## Related Files

**Backend:**
- `backend_v2/orchestration/agents.py` (main fix)
- `backend_v2/orchestration/loop.py` (passes history_ids)
- `backend_v2/streaming/pipeline.py` (emits now_playing)
- `backend_v2/orchestration/events.py` (event emitter)
- `backend_v2/catalog/selector.py` (diversity filtering)

**Frontend:**
- `frontend/src/providers/PlayerProvider.tsx` (receives artwork_url)
- `frontend/src/components/player/NowPlaying.tsx` (displays artwork)

## Impact

- ✅ Album artwork will now display when available
- ✅ Songs will not repeat within a session
- ✅ Better diversity in track selection
- ✅ More professional user experience

