"""Backfill audio features for cached songs."""

import argparse
import asyncio
import logging
import os
import sys
import time
from pathlib import Path
from typing import Optional, Tuple

# Add project root to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend_v2.audio.features import extract_audio_features
from backend_v2.db.session import get_db_session
from backend_v2.models.existing import Song, SongFeatures

logger = logging.getLogger("ai-dj.tools.backfill_features")


async def _upsert_features(
    db,
    song: Song,
    features: dict,
):
    """Upsert features for a song."""
    existing = song.features
    if existing:
        logger.debug("Updating existing features for song %s", song.uuid)
        for key, value in features.items():
            setattr(existing, key, value)
    else:
        logger.debug("Creating new features for song %s", song.uuid)
        db.add(SongFeatures(song_uuid=song.uuid, **features))


async def _process_song(
    db,
    song: Song,
    semaphore: asyncio.Semaphore,
) -> Tuple[bool, bool, Optional[dict]]:
    """Process a single song: extract features and update database.
    
    Returns:
        (processed, updated, features) - whether song was processed, updated, and extracted features
    """
    async with semaphore:
        try:
            if not song.local_path:
                logger.debug("Skipping song %s: no local_path", song.uuid)
                return True, False, None
            
            if not os.path.exists(song.local_path):
                logger.warning("Skipping song %s: file not found at %s", song.uuid, song.local_path)
                return True, False, None

            logger.info("Processing song %s: %s", song.uuid, song.local_path)
            start_time = time.time()
            
            features = await asyncio.to_thread(extract_audio_features, song.local_path)
            elapsed = time.time() - start_time
            
            if not features:
                logger.warning("No features extracted for song %s", song.uuid)
                return True, False, None
            
            if not any(v is not None for v in features.values()):
                logger.warning("All features are None for song %s", song.uuid)
                return True, False, None

            logger.info(
                "Extracted features for song %s in %.2fs (tempo=%s, key=%s, energy=%s)",
                song.uuid,
                elapsed,
                features.get("tempo"),
                features.get("key"),
                features.get("energy"),
            )

            return True, True, features
            
        except Exception as exc:
            logger.error("Error processing song %s: %s", song.uuid, exc, exc_info=True)
            return True, False, None


async def backfill_features(
    limit: Optional[int] = None,
    force: bool = False,
    commit_every: int = 10,
    workers: int = 4,
):
    """Backfill audio features for cached songs.
    
    Args:
        limit: Maximum number of songs to process
        force: Recompute features even if already present
        commit_every: Commit database changes every N updates
        workers: Number of concurrent workers for processing songs
    """
    start_time = time.time()
    processed = 0
    updated = 0
    skipped = 0
    errors = 0

    logger.info("Starting backfill (limit=%s, force=%s, workers=%s, commit_every=%s)", 
                limit, force, workers, commit_every)

    async with get_db_session() as db:
        stmt = select(Song).options(selectinload(Song.features)).where(Song.local_path.isnot(None))
        if not force:
            stmt = stmt.outerjoin(SongFeatures).where(SongFeatures.song_uuid.is_(None))

        if limit:
            stmt = stmt.limit(limit)

        result = await db.execute(stmt)
        songs = result.scalars().all()
        total_songs = len(songs)
        
        logger.info("Found %s song(s) to process", total_songs)
        
        if total_songs == 0:
            logger.info("No songs to process")
            return

        # Create semaphore to limit concurrent processing
        semaphore = asyncio.Semaphore(workers)

        # Process songs in batches to avoid concurrent commit issues
        # We'll process songs concurrently but commit serially
        batch_size = commit_every
        pending_updates = []  # List of (song, features) tuples to update
        
        for batch_start in range(0, total_songs, batch_size):
            batch_songs = songs[batch_start:batch_start + batch_size]
            batch_num = (batch_start // batch_size) + 1
            total_batches = (total_songs + batch_size - 1) // batch_size
            
            logger.info("Processing batch %s/%s (%s songs)", batch_num, total_batches, len(batch_songs))
            
            # Process batch concurrently
            tasks = [
                _process_song(db, song, semaphore)
                for song in batch_songs
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Collect successful updates and apply them to DB
            batch_updated = 0
            for song, result in zip(batch_songs, results):
                if isinstance(result, Exception):
                    errors += 1
                    logger.error("Task failed with exception: %s", result, exc_info=result)
                    processed += 1
                else:
                    was_processed, was_updated, features = result
                    if was_processed:
                        processed += 1
                    if was_updated and features:
                        # Apply update to database
                        await _upsert_features(db, song, features)
                        updated += 1
                        batch_updated += 1
                    elif was_processed:
                        skipped += 1
            
            # Commit after each batch
            if batch_updated > 0:
                await db.commit()
                logger.info(
                    "Committed batch %s/%s: %s updates (total: %s processed, %s updated)",
                    batch_num,
                    total_batches,
                    batch_updated,
                    processed,
                    updated,
                )

    elapsed = time.time() - start_time
    logger.info(
        "Backfill complete: processed=%s updated=%s skipped=%s errors=%s (total=%s) in %.2fs",
        processed,
        updated,
        skipped,
        errors,
        total_songs,
        elapsed,
    )


def setup_logging(verbose: bool = False):
    """Configure logging for the script."""
    level = logging.DEBUG if verbose else logging.INFO
    format_str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"
    
    logging.basicConfig(
        level=level,
        format=format_str,
        datefmt=date_format,
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )


def parse_args():
    parser = argparse.ArgumentParser(
        description="Backfill audio features for cached songs.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process up to 100 songs with 4 workers
  python backend_v2/tools/backfill_song_features.py --limit 100 --workers 4
  
  # Force recompute all features with verbose logging
  python backend_v2/tools/backfill_song_features.py --force --verbose
  
  # Process with custom commit frequency
  python backend_v2/tools/backfill_song_features.py --commit-every 20 --workers 8
        """,
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max songs to process (default: all)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Recompute features even if already present",
    )
    parser.add_argument(
        "--commit-every",
        type=int,
        default=10,
        help="Commit database changes every N updates (default: 10)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Number of concurrent workers for processing songs (default: 4)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose (DEBUG) logging",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    setup_logging(verbose=args.verbose)
    
    try:
        asyncio.run(
            backfill_features(
                limit=args.limit,
                force=args.force,
                commit_every=args.commit_every,
                workers=args.workers,
            )
        )
    except KeyboardInterrupt:
        logger.warning("Interrupted by user")
        sys.exit(1)
    except Exception as exc:
        logger.error("Fatal error: %s", exc, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
