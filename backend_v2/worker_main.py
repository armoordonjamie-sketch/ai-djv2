"""Background workers entrypoint (no API server).

Runs acquisition, intro generation, and mood enrichment without blocking the API.
"""
import asyncio
import logging
import os
from typing import Optional, IO

from backend_v2.config import SEGMENT_DIR, SONG_CACHE_DIR
from backend_v2.db.session import init_db, close_db

logger = logging.getLogger("ai-dj-workers")


def _acquire_worker_lock() -> Optional[IO[str]]:
    """Acquire a cross-process lock to ensure only one instance runs background workers."""
    lock_path = os.path.join("data", "workers.lock")
    try:
        handle = open(lock_path, "a+", encoding="utf-8")
    except OSError:
        return None
    try:
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            handle.seek(0)
            handle.truncate()
            handle.write(str(os.getpid()))
            handle.flush()
        except OSError:
            try:
                handle.close()
            except OSError:
                pass
            return None
        return handle
    except OSError:
        try:
            handle.close()
        except OSError:
            pass
        return None


def _release_worker_lock(handle: Optional[IO[str]]) -> None:
    if not handle:
        return
    try:
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass
    try:
        handle.close()
    except OSError:
        pass


async def _ensure_training_metrics_table() -> None:
    """Ensure the training_metrics table exists in dev mode."""
    try:
        from sqlalchemy import text
        from backend_v2.db.base import Base
        from backend_v2.db.session import engine
        from backend_v2 import models  # noqa: F401 - ensure models are registered

        async with engine.begin() as conn:
            result = await conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='training_metrics'")
            )
            exists = result.scalar_one_or_none()
            if exists is None:
                await conn.run_sync(Base.metadata.create_all)
                logger.info("Training metrics table created (dev mode)")
    except Exception as e:
        logger.warning(f"Failed to ensure training_metrics table: {e}")


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    os.makedirs(SEGMENT_DIR, exist_ok=True)
    os.makedirs(SONG_CACHE_DIR, exist_ok=True)
    os.makedirs("data", exist_ok=True)

    await init_db()
    await _ensure_training_metrics_table()

    worker_lock = _acquire_worker_lock()
    if not worker_lock:
        logger.error("Workers already running or lock unavailable. Exiting.")
        return

    try:
        from backend_v2.services.acquisition_worker import start_acquisition_worker, stop_acquisition_worker
        from backend_v2.services.intro_generator_worker import start_intro_generator_worker, stop_intro_generator_worker
        from backend_v2.services.mood_enrichment import ensure_moods_enriched

        await start_acquisition_worker(poll_interval=5, max_concurrent=2)
        logger.info("Acquisition worker started")

        await start_intro_generator_worker(poll_interval=60, max_concurrent=1, regenerate_after_days=7)
        logger.info("Intro generator worker started")

        await ensure_moods_enriched()
        logger.info("Mood enrichment worker started")

        while True:
            await asyncio.sleep(1)
    finally:
        try:
            await stop_acquisition_worker()
            logger.info("Acquisition worker stopped")
        except Exception as e:
            logger.warning(f"Error stopping acquisition worker: {e}")

        try:
            await stop_intro_generator_worker()
            logger.info("Intro generator worker stopped")
        except Exception as e:
            logger.warning(f"Error stopping intro generator worker: {e}")

        await close_db()
        _release_worker_lock(worker_lock)
        logger.info("Workers shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
