"""Background acquisition worker for processing acquisition jobs asynchronously.

This worker runs as a background task and processes QUEUED acquisition jobs,
allowing the main DJLoop to continue without blocking on downloads.

For now, this is a simple implementation. In production, consider using:
- Celery for distributed task processing
- Redis for job queue
- Multiple worker processes for parallelism
"""
import asyncio
import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend_v2.db.session import get_db_session
from backend_v2.models.track_intent import AcquisitionJob, TrackIntent, AcquisitionJobStatus
from backend_v2.services.acquisition import get_acquisition_service
from backend_v2.utils.time import utc_now

logger = logging.getLogger("ai-dj.acquisition-worker")


class AcquisitionWorker:
    """Background worker for processing acquisition jobs."""
    
    def __init__(self, poll_interval: int = 5, max_concurrent: int = 2):
        """Initialize worker.
        
        Args:
            poll_interval: How often to check for new jobs (seconds)
            max_concurrent: Max concurrent acquisitions
        """
        self.poll_interval = poll_interval
        self.max_concurrent = max_concurrent
        self.is_running = False
        self._task: Optional[asyncio.Task] = None
        self._active_jobs = 0
    
    async def start(self):
        """Start the background worker."""
        if self.is_running:
            logger.warning("Acquisition worker already running")
            return
        
        self.is_running = True
        self._task = asyncio.create_task(self._run())
        logger.info("Acquisition worker started")
    
    async def stop(self):
        """Stop the background worker."""
        logger.info("Stopping acquisition worker...")
        self.is_running = False
        
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        logger.info("Acquisition worker stopped")
    
    async def _run(self):
        """Main worker loop."""
        logger.info("Acquisition worker loop started")
        
        while self.is_running:
            try:
                # Check for QUEUED jobs if we have capacity
                if self._active_jobs < self.max_concurrent:
                    await self._process_queued_jobs()
                
                # Sleep before next poll
                await asyncio.sleep(self.poll_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Acquisition worker error: {e}")
                import traceback
                traceback.print_exc()
                await asyncio.sleep(5)
    
    async def _process_queued_jobs(self):
        """Find and process QUEUED jobs."""
        try:
            async with get_db_session() as db:
                # Find QUEUED jobs (oldest first)
                result = await db.execute(
                    select(AcquisitionJob)
                    .where(AcquisitionJob.status == AcquisitionJobStatus.QUEUED.value)
                    .order_by(AcquisitionJob.created_at)
                    .limit(self.max_concurrent - self._active_jobs)
                )
                jobs = result.scalars().all()
                
                if not jobs:
                    return
                
                logger.info(f"Found {len(jobs)} queued acquisition jobs")
                
                # Process jobs in parallel (up to max_concurrent)
                tasks = []
                for job in jobs:
                    task = asyncio.create_task(self._process_job(job.id))
                    tasks.append(task)
                
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
        except Exception as e:
            # Handle case where table doesn't exist yet (during initial startup)
            error_str = str(e)
            if "no such table" in error_str.lower() or "acquisition_jobs" in error_str.lower():
                logger.debug("Acquisition jobs table not yet created, skipping poll")
                return
            # Re-raise other errors to be handled by the main loop
            raise
    
    async def _process_job(self, job_id: str):
        """Process a single acquisition job.
        
        Args:
            job_id: Acquisition job ID
        """
        self._active_jobs += 1
        
        try:
            async with get_db_session() as db:
                # Load job and intent
                result = await db.execute(
                    select(AcquisitionJob)
                    .where(AcquisitionJob.id == job_id)
                )
                job = result.scalar_one_or_none()
                
                if not job:
                    logger.warning(f"Job {job_id} not found")
                    return
                
                # Load intent
                result = await db.execute(
                    select(TrackIntent)
                    .where(TrackIntent.id == job.track_intent_id)
                )
                intent = result.scalar_one_or_none()
                
                if not intent:
                    logger.warning(f"Intent {job.track_intent_id} not found for job {job_id}")
                    job.status = "FAILED"
                    job.last_error = "Intent not found"
                    await db.commit()
                    return
                
                # Mark job as running
                job.status = AcquisitionJobStatus.RUNNING.value
                job.started_at = utc_now()
                await db.commit()
                
                # Use acquisition service
                service = get_acquisition_service()
                success = await service.acquire(db, intent, timeout_per_provider=120)
                
                logger.info(f"Job {job_id} completed: {'success' if success else 'failed'}")
                
        except Exception as e:
            logger.error(f"Error processing job {job_id}: {e}")
        finally:
            self._active_jobs -= 1


# Global worker instance
_worker: Optional[AcquisitionWorker] = None


async def start_acquisition_worker(poll_interval: int = 5, max_concurrent: int = 2):
    """Start the global acquisition worker.
    
    Args:
        poll_interval: Poll interval in seconds
        max_concurrent: Max concurrent jobs
    """
    global _worker
    if _worker is None:
        _worker = AcquisitionWorker(
            poll_interval=poll_interval,
            max_concurrent=max_concurrent
        )
    
    await _worker.start()


async def stop_acquisition_worker():
    """Stop the global acquisition worker."""
    global _worker
    if _worker:
        await _worker.stop()


def get_acquisition_worker() -> Optional[AcquisitionWorker]:
    """Get the global acquisition worker instance."""
    return _worker

