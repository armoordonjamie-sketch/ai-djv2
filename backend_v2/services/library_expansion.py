"""Library expansion service for auto-downloading new songs.

Runs as a background task to expand the song library when the
candidate pool is small or repetitive.
"""
import asyncio
import logging
from typing import Optional, List, Set
from datetime import datetime, timedelta

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend_v2.models.existing import Song
from backend_v2.config import MAX_CONCURRENT_DOWNLOADS
from backend_v2.utils.time import utc_now, ensure_utc

logger = logging.getLogger("ai-dj.library_expansion")


class LibraryExpansionService:
    """Background service for library expansion."""
    
    def __init__(self):
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._pending_queries: Set[str] = set()
        self._active_downloads = 0
        self._last_expansion = ensure_utc(datetime.min)
        self._cooldown = timedelta(minutes=5)  # Min time between expansions
    
    async def start(self):
        """Start the library expansion service."""
        if self._running:
            return
        
        self._running = True
        logger.info("Library expansion service started")
    
    async def stop(self):
        """Stop the library expansion service."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Library expansion service stopped")
    
    async def expand_if_needed(
        self,
        db: AsyncSession,
        bundle: "PreferenceBundle",
        persona: Optional["DJPersona"] = None,
        min_candidates: int = 10,
    ) -> int:
        """Check if library needs expansion and trigger if so.
        
        Returns number of new downloads enqueued.
        """
        from backend_v2.services.preference_bundle import PreferenceBundle
        from backend_v2.services.persona import DJPersona
        
        # Check cooldown
        last_expansion = ensure_utc(self._last_expansion) or utc_now()
        if utc_now() - last_expansion < self._cooldown:
            return 0
        
        # Count available songs
        result = await db.execute(
            select(func.count(Song.uuid)).where(Song.local_path.isnot(None))
        )
        song_count = result.scalar() or 0
        
        if song_count >= min_candidates:
            return 0
        
        logger.info(f"Library has {song_count} songs, expanding...")
        
        # Generate search queries
        from backend_v2.integrations.search_queries import generate_search_queries
        
        queries = await generate_search_queries(
            bundle=bundle,
            persona=persona,
            count=5,
        )
        
        # Enqueue downloads (respecting concurrency limit)
        enqueued = 0
        for query in queries:
            if query.lower() in self._pending_queries:
                continue
            
            if self._active_downloads >= MAX_CONCURRENT_DOWNLOADS:
                break
            
            # Parse "Artist - Title" format
            if " - " not in query:
                continue
            
            parts = query.split(" - ", 1)
            if len(parts) != 2:
                continue
            
            artist, title = parts
            self._pending_queries.add(query.lower())
            
            # Start async download (fire and forget)
            asyncio.create_task(self._download_song(db, artist.strip(), title.strip(), query))
            enqueued += 1
        
        self._last_expansion = utc_now()
        logger.info(f"Enqueued {enqueued} downloads for library expansion")
        return enqueued
    
    async def _download_song(self, db: AsyncSession, artist: str, title: str, query: str):
        """Download a single song in the background."""
        from backend_v2.orchestration.agents import acquire_song_by_name
        
        self._active_downloads += 1
        try:
            result = await acquire_song_by_name(db, artist, title)
            if result:
                logger.info(f"Library expansion: Downloaded {artist} - {title}")
            else:
                logger.warning(f"Library expansion: Failed {artist} - {title}")
        except Exception as e:
            logger.error(f"Library expansion download error: {e}")
        finally:
            self._active_downloads -= 1
            self._pending_queries.discard(query.lower())


# Singleton
_service: Optional[LibraryExpansionService] = None


def get_library_expansion_service() -> LibraryExpansionService:
    """Get the library expansion service singleton."""
    global _service
    if _service is None:
        _service = LibraryExpansionService()
    return _service
