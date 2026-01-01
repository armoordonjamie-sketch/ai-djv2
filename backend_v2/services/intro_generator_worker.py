"""Background worker for pre-generating mood intro segments.

Pre-generates intro audio for all user moods so playback is instant
when users select a mood. Uses ElevenLabs TTS for DJ speech.

This runs as a background task polling for moods that don't have intros.
"""
import asyncio
import logging
import os
from datetime import datetime, timedelta
from typing import Optional, Set

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend_v2.db.session import get_db_session
from backend_v2.models.mood import Mood
from backend_v2.models.user import User
from backend_v2.orchestration.generation import generate_mood_intro
from backend_v2.utils.time import utc_now

logger = logging.getLogger("ai-dj.intro-generator")


class IntroGeneratorWorker:
    """Background worker for pre-generating mood intros.
    
    Polls for moods without intro_segment_path and generates them.
    Ensures instant playback when users select a mood.
    
    NOTE: max_concurrent should be 1 for SQLite to avoid "database is locked" errors.
    SQLite has limited concurrent write support. For PostgreSQL, increase to 2-3.
    """
    
    def __init__(
        self, 
        poll_interval: int = 60, 
        max_concurrent: int = 1,  # Keep at 1 for SQLite compatibility
        regenerate_after_days: int = 7,
    ):
        """Initialize worker.
        
        Args:
            poll_interval: How often to check for moods needing intros (seconds)
            max_concurrent: Max concurrent intro generations
            regenerate_after_days: Regenerate intros older than this (for freshness)
        """
        self.poll_interval = poll_interval
        self.max_concurrent = max_concurrent
        self.regenerate_after_days = regenerate_after_days
        self.is_running = False
        self._task: Optional[asyncio.Task] = None
        self._active_jobs = 0
        self._processing_mood_ids: Set[str] = set()  # Prevent duplicate processing
    
    async def start(self):
        """Start the background worker."""
        if self.is_running:
            logger.warning("Intro generator worker already running")
            return
        
        self.is_running = True
        self._task = asyncio.create_task(self._run())
        logger.info("Intro generator worker started")
    
    async def stop(self):
        """Stop the background worker."""
        logger.info("Stopping intro generator worker...")
        self.is_running = False
        
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        logger.info("Intro generator worker stopped")
    
    async def _run(self):
        """Main worker loop."""
        logger.info("Intro generator worker loop started")
        
        # Initial delay to let app fully start
        await asyncio.sleep(10)
        
        while self.is_running:
            try:
                # Process moods needing intros
                if self._active_jobs < self.max_concurrent:
                    await self._process_moods_needing_intros()
                
                # Sleep before next poll
                await asyncio.sleep(self.poll_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Intro generator worker error: {e}")
                import traceback
                traceback.print_exc()
                await asyncio.sleep(30)  # Longer delay on error
    
    async def _process_moods_needing_intros(self):
        """Find and process moods that need intro generation."""
        try:
            async with get_db_session() as db:
                # Calculate cutoff for stale intros
                stale_cutoff = utc_now() - timedelta(days=self.regenerate_after_days)
                
                # Find moods without intros or with stale/missing files
                result = await db.execute(
                    select(Mood)
                    .options(selectinload(Mood.user))
                    .where(
                        or_(
                            # No intro path set
                            Mood.intro_segment_path.is_(None),
                            # Or intro was generated too long ago (updated_at is proxy)
                            Mood.updated_at < stale_cutoff
                        )
                    )
                    .limit(self.max_concurrent * 2)  # Fetch extras in case some are processing
                )
                moods = result.scalars().all()
                
                if not moods:
                    return
                
                # Filter out moods already being processed
                moods_to_process = [
                    m for m in moods 
                    if m.id not in self._processing_mood_ids
                ][:self.max_concurrent - self._active_jobs]
                
                if not moods_to_process:
                    return
                
                logger.info(f"Found {len(moods_to_process)} moods needing intro generation")
                
                # Process in parallel
                tasks = []
                for mood in moods_to_process:
                    self._processing_mood_ids.add(mood.id)
                    task = asyncio.create_task(
                        self._generate_intro_for_mood(mood.id, mood.user_id)
                    )
                    tasks.append(task)
                
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
                    
        except Exception as e:
            error_str = str(e)
            if "no such table" in error_str.lower() or "moods" in error_str.lower():
                logger.debug("Moods table not yet created, skipping poll")
                return
            raise
    
    async def _generate_intro_for_mood(self, mood_id: str, user_id: str):
        """Generate intro for a specific mood.
        
        Args:
            mood_id: Mood ID
            user_id: User ID
        """
        self._active_jobs += 1
        
        try:
            async with get_db_session() as db:
                # Load mood to verify it still needs an intro
                result = await db.execute(
                    select(Mood).where(Mood.id == mood_id)
                )
                mood = result.scalar_one_or_none()
                
                if not mood:
                    logger.warning(f"Mood {mood_id} not found")
                    return
                
                # Check if intro file exists (if path is set)
                if mood.intro_segment_path and os.path.exists(mood.intro_segment_path):
                    # Check if it's stale (based on file mtime)
                    stale_cutoff = utc_now() - timedelta(days=self.regenerate_after_days)
                    try:
                        file_mtime = datetime.fromtimestamp(
                            os.path.getmtime(mood.intro_segment_path)
                        )
                        if file_mtime.timestamp() > stale_cutoff.timestamp():
                            logger.debug(f"Mood {mood_id} intro still fresh, skipping")
                            return
                    except OSError:
                        pass  # File might be gone, regenerate
                
                logger.info(f"Generating intro for mood {mood_id} (user {user_id}, name: {mood.name})")
                
                # Generate intro
                result = await generate_mood_intro(db, user_id, mood_id)
                
                if result:
                    # Refresh mood object in case it was detached during acquisition
                    await db.refresh(mood)
                    
                    # Update mood with intro path
                    mood.intro_segment_path = result["path"]
                    mood.intro_song_uuid = result["song_uuid"]
                    await db.commit()
                    
                    logger.info(
                        f"✅ Generated intro for mood '{mood.name}' "
                        f"(user {user_id}): {result['path']}"
                    )
                else:
                    logger.warning(f"Failed to generate intro for mood {mood_id}")
                    
        except Exception as e:
            logger.error(f"Error generating intro for mood {mood_id}: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self._active_jobs -= 1
            self._processing_mood_ids.discard(mood_id)
    
    async def generate_for_user(self, user_id: str):
        """Generate intro for only the DEFAULT mood of a specific user.
        
        Useful to call after onboarding completes.
        Only generates for the main mood to speed up onboarding.
        Other moods will get fresh intros on first play.
        
        Args:
            user_id: User ID
        """
        try:
            async with get_db_session() as db:
                # Only generate for the default/main mood
                result = await db.execute(
                    select(Mood)
                    .where(Mood.user_id == user_id, Mood.is_default == True)
                )
                default_mood = result.scalar_one_or_none()
                
                if not default_mood:
                    # Fallback: get first mood if no default
                    result = await db.execute(
                        select(Mood)
                        .where(Mood.user_id == user_id)
                        .limit(1)
                    )
                    default_mood = result.scalar_one_or_none()
                
                if default_mood and default_mood.id not in self._processing_mood_ids:
                    logger.info(f"Generating intro for default mood '{default_mood.name}' (user {user_id})")
                    # Await this one so onboarding flow knows when it's ready
                    await self._generate_intro_for_mood(default_mood.id, user_id)
                else:
                    logger.info(f"No default mood found for user {user_id} or already processing")
                        
        except Exception as e:
            logger.error(f"Error scheduling intros for user {user_id}: {e}")


# =============================================================================
# Global Worker Instance
# =============================================================================

_worker: Optional[IntroGeneratorWorker] = None


async def start_intro_generator_worker(
    poll_interval: int = 60,
    max_concurrent: int = 2,
    regenerate_after_days: int = 7,
):
    """Start the global intro generator worker.
    
    Args:
        poll_interval: Poll interval in seconds
        max_concurrent: Max concurrent generations
        regenerate_after_days: Regenerate intros older than this
    """
    global _worker
    if _worker is None:
        _worker = IntroGeneratorWorker(
            poll_interval=poll_interval,
            max_concurrent=max_concurrent,
            regenerate_after_days=regenerate_after_days,
        )
    
    await _worker.start()


async def stop_intro_generator_worker():
    """Stop the global intro generator worker."""
    global _worker
    if _worker:
        await _worker.stop()


def get_intro_generator_worker() -> Optional[IntroGeneratorWorker]:
    """Get the global intro generator worker instance."""
    return _worker


async def trigger_intro_generation_for_user(user_id: str):
    """Trigger intro generation for a specific user.
    
    Call this after onboarding completes or when new moods are created.
    
    Args:
        user_id: User ID
    """
    worker = get_intro_generator_worker()
    if worker and worker.is_running:
        await worker.generate_for_user(user_id)
    else:
        logger.warning("Intro generator worker not running, cannot trigger generation")

