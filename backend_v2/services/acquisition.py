"""Multi-provider acquisition service for obtaining audio files.

Coordinates multiple acquisition providers (local cache, YouTube, alternatives)
to obtain audio files for TrackIntents with robust fallbacks.
"""
import asyncio
import logging
import os
from datetime import datetime
from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend_v2.models.track_intent import TrackIntent, AcquisitionJob, TrackIntentStatus, AcquisitionJobStatus
from backend_v2.models.existing import Song
from backend_v2.tools.song_downloader import get_song_downloader

if TYPE_CHECKING:
    from backend_v2.catalog.providers import CatalogTrack

logger = logging.getLogger("ai-dj.acquisition")


class AcquisitionProvider:
    """Base class for acquisition providers."""
    
    @property
    def name(self) -> str:
        raise NotImplementedError
    
    async def acquire(
        self,
        intent: TrackIntent,
        timeout: int = 120,
        db: Optional[AsyncSession] = None
    ) -> Optional[str]:
        """Try to acquire audio file for intent.
        
        Args:
            intent: Track intent to acquire
            timeout: Max time to wait (seconds)
            db: Optional database session (some providers may use it)
            
        Returns:
            Song UUID if successful, None otherwise
        """
        raise NotImplementedError


class LocalCacheProvider(AcquisitionProvider):
    """Check if track already exists in local cache."""
    
    @property
    def name(self) -> str:
        return "local_cache"
    
    async def acquire(
        self,
        intent: TrackIntent,
        timeout: int = 120,
        db: Optional[AsyncSession] = None
    ) -> Optional[str]:
        """Check local cache for matching track.
        
        Args:
            intent: Track intent with artist/title
            timeout: Not used (instant check)
            db: Optional database session to use (if provided)
            
        Returns:
            Song UUID if found in cache, None otherwise
        """
        from backend_v2.db.session import get_db_session
        
        # Use provided session or create new one
        if db is None:
            from backend_v2.db.session import get_db_session
            async with get_db_session() as session:
                return await self._check_cache(session, intent)
        else:
            return await self._check_cache(db, intent)
    
    async def _check_cache(self, db: AsyncSession, intent: TrackIntent) -> Optional[str]:
        """Internal method to check cache with a database session."""
        try:
            # Normalize search terms (remove extra text like "(As featured in...)")
            artist_clean = intent.artist.strip()
            title_clean = intent.title.split("(")[0].strip()  # Remove parenthetical text
            
            logger.debug(f"Checking local cache for: {artist_clean} - {title_clean}")
            
            # Search for matching song with local file
            # Try multiple search strategies for better matching
            search_queries = [
                # Strategy 1: Exact artist + title match (cleaned)
                (Song.artist.ilike(f"{artist_clean}"), Song.title.ilike(f"{title_clean}%")),
                # Strategy 2: Fuzzy artist + title match
                (Song.artist.ilike(f"%{artist_clean}%"), Song.title.ilike(f"%{title_clean}%")),
                # Strategy 3: Original title with parenthetical
                (Song.artist.ilike(f"%{intent.artist}%"), Song.title.ilike(f"%{intent.title}%")),
            ]
            
            for artist_cond, title_cond in search_queries:
                result = await db.execute(
                    select(Song).where(
                        artist_cond,
                        title_cond,
                        Song.local_path.isnot(None)
                    ).limit(10)
                )
                songs = result.scalars().all()
                
                # Check each candidate to see if file exists
                for song in songs:
                    if song.local_path and os.path.exists(song.local_path):
                        logger.info(f"✅ Found in local cache: {song.artist} - {song.title} (uuid={song.uuid})")
                        logger.info(f"   Matched intent: {intent.artist} - {intent.title}")
                        return song.uuid
            
            logger.debug(f"Local cache: No matching song found for {intent.artist} - {intent.title}")
            
        except Exception as e:
            logger.error(f"Local cache check error: {e}")
            import traceback
            traceback.print_exc()
        
        return None


class YouTubeProvider(AcquisitionProvider):
    """Download tracks from YouTube using yt-dlp."""
    
    @property
    def name(self) -> str:
        return "youtube"
    
    async def acquire(
        self,
        intent: TrackIntent,
        timeout: int = 120,
        db: Optional[AsyncSession] = None
    ) -> Optional[str]:
        """Download track from YouTube.
        
        Args:
            intent: Track intent with artist/title
            timeout: Max download time (seconds)
            db: Not used (YouTube provider creates its own session)
            
        Returns:
            Song UUID if download successful, None otherwise
        """
        try:
            downloader = get_song_downloader()
            
            # Build search query
            query = f"{intent.artist} - {intent.title} official audio"
            
            logger.info(f"Downloading from YouTube: {query}")
            
            # Download with timeout
            result = await asyncio.wait_for(
                downloader.download_song(
                    query=query,
                    artist=intent.artist,
                    title=intent.title,
                    skip_db_storage=False
                ),
                timeout=timeout
            )
            
            if result and result.get('uuid'):
                logger.info(f"Successfully downloaded: {intent.artist} - {intent.title} (uuid={result['uuid']})")
                return result['uuid']
            
        except asyncio.TimeoutError:
            logger.warning(f"YouTube download timed out after {timeout}s: {intent.artist} - {intent.title}")
        except Exception as e:
            logger.error(f"YouTube download error: {e}")
        
        return None


class AcquisitionService:
    """Service coordinating multi-provider acquisition with fallbacks."""
    
    def __init__(self):
        # Providers in priority order
        self.providers: List[AcquisitionProvider] = [
            LocalCacheProvider(),
            YouTubeProvider(),
            # Could add more providers here (Spotify scraper, SoundCloud, etc.)
        ]
    
    async def acquire(
        self,
        db: AsyncSession,
        intent: TrackIntent,
        timeout_per_provider: int = 120
    ) -> bool:
        """Acquire audio file for intent using fallback providers.
        
        Args:
            db: Database session
            intent: Track intent to acquire
            timeout_per_provider: Timeout for each provider attempt
            
        Returns:
            True if acquired, False if all providers failed
        """
        logger.info(f"Starting acquisition for: {intent.artist} - {intent.title}")
        
        for provider in self.providers:
            try:
                # Create acquisition job
                job = AcquisitionJob(
                    track_intent_id=intent.id,
                    provider=provider.name,
                    source_url=None,  # Will be set by provider if applicable
                    status=AcquisitionJobStatus.RUNNING.value,
                    started_at=datetime.utcnow()
                )
                db.add(job)
                await db.flush()
                
                logger.info(f"Trying provider: {provider.name}")
                
                # Attempt acquisition - pass db session to all providers
                song_uuid = await provider.acquire(intent, timeout=timeout_per_provider, db=db)
                
                # Update job status
                job.completed_at = datetime.utcnow()
                job.attempt_count += 1
                
                if song_uuid:
                    # Verify song exists in database (it was created in download_song's session)
                    # We need to ensure it's visible in our session
                    await db.commit()  # Commit any pending changes first
                    
                    # Verify the song exists - retry a few times in case of session isolation
                    song = None
                    for attempt in range(3):
                        song_check = await db.execute(
                            select(Song).where(Song.uuid == song_uuid)
                        )
                        song = song_check.scalar_one_or_none()
                        if song:
                            break
                        # If not found, wait a bit and try again (session isolation)
                        if attempt < 2:
                            await asyncio.sleep(0.1)
                            await db.rollback()  # Reset session state
                    
                    if not song:
                        logger.error(f"Song {song_uuid} not found in database after download (may be session isolation issue)")
                        job.status = AcquisitionJobStatus.FAILED.value
                        job.last_error = f"Song UUID {song_uuid} not found after download"
                        await db.commit()
                        continue  # Try next provider
                    
                    # Success! Update intent with verified song UUID
                    # Ensure we're in a clean transaction state
                    try:
                        await db.rollback()  # Reset to clean state before updating
                    except Exception:
                        pass  # Ignore if already clean
                    
                    # Reload intent to ensure we have a fresh object
                    await db.refresh(intent)
                    
                    job.status = AcquisitionJobStatus.SUCCESS.value
                    job.acquired_path = f"songs.uuid={song_uuid}"
                    
                    # Update intent - song exists, so foreign key should work
                    intent.status = TrackIntentStatus.ACQUIRED.value
                    intent.acquired_song_uuid = song_uuid
                    intent.resolved_at = datetime.utcnow()
                    
                    try:
                        await db.commit()
                        logger.info(f"✅ Acquisition successful via {provider.name}: {intent.artist} - {intent.title}")
                        return True
                    except Exception as commit_err:
                        logger.error(f"Failed to commit acquisition success: {commit_err}")
                        import traceback
                        traceback.print_exc()
                        await db.rollback()
                        # Mark job as failed due to commit error
                        job.status = AcquisitionJobStatus.FAILED.value
                        job.last_error = f"Commit failed: {str(commit_err)}"
                        try:
                            await db.commit()
                        except Exception:
                            await db.rollback()
                        continue
                else:
                    # Provider failed
                    job.status = AcquisitionJobStatus.FAILED.value
                    job.last_error = f"Provider returned None"
                    await db.commit()
                    
                    logger.warning(f"Provider {provider.name} failed for: {intent.artist} - {intent.title}")
                    
            except Exception as e:
                logger.error(f"Provider {provider.name} exception: {e}")
                try:
                    await db.rollback()  # Rollback any failed transaction
                except Exception:
                    pass  # Ignore rollback errors
                
                job.status = AcquisitionJobStatus.FAILED.value
                job.last_error = str(e)
                job.completed_at = datetime.utcnow()
                
                try:
                    await db.commit()
                except Exception as commit_err:
                    logger.error(f"Failed to commit job failure: {commit_err}")
                    await db.rollback()
        
        # All providers failed
        intent.status = TrackIntentStatus.FAILED.value
        intent.failure_reason = "All acquisition providers failed"
        intent.resolved_at = datetime.utcnow()
        await db.commit()
        
        logger.error(f"❌ Acquisition failed for: {intent.artist} - {intent.title}")
        return False
    
    async def acquire_from_catalog_track(
        self,
        db: AsyncSession,
        catalog_track: "CatalogTrack",
        user_id: str,
        mood_id: Optional[str],
        session_id: str,
        timeout_per_provider: int = 120
    ) -> Optional[TrackIntent]:
        """Create intent from catalog track and acquire it.
        
        This is a convenience method that combines intent creation and acquisition.
        
        Args:
            db: Database session
            catalog_track: Track from catalog discovery
            user_id: User ID
            mood_id: Mood ID
            session_id: Session ID
            timeout_per_provider: Timeout for each provider
            
        Returns:
            TrackIntent if successful, None if acquisition failed
        """
        # Create TrackIntent
        intent = TrackIntent(
            user_id=user_id,
            mood_id=mood_id,
            session_id=session_id,
            title=catalog_track.title,
            artist=catalog_track.artist,
            album=catalog_track.album,
            spotify_id=catalog_track.provider_id if catalog_track.provider == "spotify" else None,
            apple_music_id=catalog_track.provider_id if catalog_track.provider == "apple_music" else None,
            isrc=catalog_track.isrc,
            target_energy=catalog_track.features.energy if catalog_track.features else None,
            target_valence=catalog_track.features.valence if catalog_track.features else None,
            target_tempo=catalog_track.features.tempo if catalog_track.features else None,
            target_danceability=catalog_track.features.danceability if catalog_track.features else None,
            selection_method="catalog_discovery",
            status=TrackIntentStatus.PENDING.value
        )
        db.add(intent)
        await db.flush()
        
        # Try to acquire
        success = await self.acquire(db, intent, timeout_per_provider)
        
        if success:
            return intent
        
        return None


# Singleton instance
_acquisition_service: Optional[AcquisitionService] = None


def get_acquisition_service() -> AcquisitionService:
    """Get singleton acquisition service."""
    global _acquisition_service
    if _acquisition_service is None:
        _acquisition_service = AcquisitionService()
    return _acquisition_service

