"""Re-enrich all songs in database using Spotify Web API.

This script re-processes all songs in the database to get fresh metadata
from Spotify, replacing any old metadata from MusicBrainz/Apple Music/Deezer.

The script processes songs in batches for better performance and reliability.
Each batch is committed separately, so progress is saved even if the script
is interrupted.

Usage:
    cd backend_v2
    python -m scripts.redo_all_metadata
    
    # Options:
    python -m scripts.redo_all_metadata --limit 100          # Process only first 100 songs
    python -m scripts.redo_all_metadata --missing-features     # Only songs missing features
    python -m scripts.redo_all_metadata --missing-artwork     # Only songs missing artwork
    python -m scripts.redo_all_metadata --force               # Re-enrich even if metadata exists
    python -m scripts.redo_all_metadata --batch-size 20      # Process 20 songs per batch (default: 10)
    python -m scripts.redo_all_metadata --workers 10         # Use 10 concurrent workers (default: 5)
"""
import asyncio
import argparse
import logging
import sys
from typing import Optional

from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("redo_metadata")


async def redo_all_metadata(
    limit: Optional[int] = None,
    missing_features_only: bool = False,
    missing_artwork_only: bool = False,
    force: bool = False,
    delay_seconds: float = 0.1,  # Reduced delay (parallel processing handles rate limiting)
    batch_size: int = 10,  # Process songs in batches
    workers: int = 5,  # Number of concurrent workers
):
    """Re-enrich all songs using Spotify metadata service.
    
    Args:
        limit: Maximum number of songs to process (None = all)
        missing_features_only: Only process songs missing audio features
        missing_artwork_only: Only process songs missing artwork
        force: Re-enrich even if metadata already exists
        delay_seconds: Delay between batches (reduced since we process in parallel)
        batch_size: Number of songs to process per batch before committing (default: 10)
        workers: Number of concurrent workers for parallel processing (default: 5)
    """
    # Import all models to ensure SQLAlchemy relationships resolve correctly
    from backend_v2.models import existing  # noqa: F401
    from backend_v2.models.spotify_context import SpotifyUserContext  # noqa: F401
    from backend_v2.db.session import get_db_session
    from backend_v2.models.existing import Song, SongFeatures
    from backend_v2.integrations.metadata.enrichment import get_metadata_service
    
    service = get_metadata_service()
    
    if not service.spotify_client.enabled:
        logger.error("Spotify metadata client not enabled. Please set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET environment variables.")
        sys.exit(1)
    
    async with get_db_session() as db:
        # Build query based on filters
        query = select(Song)
        
        if missing_features_only:
            # Only songs without features
            query = (
                select(Song)
                .outerjoin(SongFeatures, Song.uuid == SongFeatures.song_uuid)
                .where(SongFeatures.song_uuid.is_(None))
            )
            logger.info("Filter: Only songs missing audio features")
        
        elif missing_artwork_only:
            # Only songs without artwork
            query = select(Song).where(
                or_(
                    Song.artwork_url.is_(None),
                    Song.artwork_url == ""
                )
            )
            logger.info("Filter: Only songs missing artwork")
        
        elif not force:
            # By default, prioritize songs missing metadata
            # But still process all songs if force=True
            query = select(Song).where(
                or_(
                    Song.artwork_url.is_(None),
                    Song.artwork_url == "",
                    ~Song.uuid.in_(
                        select(SongFeatures.song_uuid).where(SongFeatures.song_uuid.isnot(None))
                    )
                )
            )
            logger.info("Filter: Songs missing artwork or features (use --force to process all)")
        
        # Order by most recently added first (or by UUID for consistent ordering)
        query = query.order_by(Song.uuid)
        
        # Apply limit
        if limit:
            query = query.limit(limit)
        
        result = await db.execute(query)
        songs = result.scalars().all()
        
        total_songs = len(songs)
        logger.info(f"Found {total_songs} songs to re-enrich")
        
        if total_songs == 0:
            logger.info("No songs to process")
            return
        
        # Confirm before proceeding
        if not force and total_songs > 10:
            logger.warning(f"This will process {total_songs} songs. This may take a while.")
            logger.info("Use --force flag to skip this check")
            response = input("Continue? (yes/no): ")
            if response.lower() != "yes":
                logger.info("Cancelled")
                return
        
        # Process songs in batches with parallel processing
        success_count = 0
        error_count = 0
        skipped_count = 0
        
        # Create semaphore to limit concurrent API calls
        semaphore = asyncio.Semaphore(workers)
        
        # Split songs into batches
        num_batches = (total_songs + batch_size - 1) // batch_size
        logger.info(f"Processing {total_songs} songs in {num_batches} batches of {batch_size} (workers: {workers})")
        
        async def process_song(song, global_idx: int):
            """Process a single song with semaphore for rate limiting.
            
            Returns enrichment data without persisting (we persist sequentially).
            """
            async with semaphore:
                artist = song.artist or "Unknown"
                title = song.title or "Unknown"
                
                logger.info(f"[{global_idx}/{total_songs}] Processing: {artist} - {title}")
                
                # Skip if missing required fields
                if not song.artist or not song.title:
                    logger.warning(f"  ⚠ Skipping: Missing artist or title")
                    return ("skipped", None, None)
                
                try:
                    # Fetch enrichment data WITHOUT persisting (we'll persist sequentially)
                    enrichment = await service.enrich_song(
                        song_uuid=song.uuid,
                        artist=song.artist,
                        title=song.title,
                        isrc=song.isrc,
                        audio_path=song.local_path,
                        update_db=False,  # Don't persist yet - we'll do it sequentially
                        db=None  # Don't pass db session for parallel fetching
                    )
                    
                    # Check what we got
                    has_artwork = bool(enrichment.get("artwork_url"))
                    has_features = bool(enrichment.get("features"))
                    has_genres = bool(enrichment.get("genres"))
                    
                    if has_artwork or has_features or has_genres:
                        parts = []
                        if has_artwork:
                            parts.append("artwork")
                        if has_features:
                            parts.append("features")
                        if has_genres:
                            parts.append(f"{len(enrichment.get('genres', []))} genres")
                        logger.info(f"  ✓ Enriched: {', '.join(parts)}")
                        return ("success", song, enrichment)
                    else:
                        logger.warning(f"  ⚠ No metadata found on Spotify")
                        return ("skipped", None, None)
                    
                except Exception as e:
                    logger.error(f"  ✗ Failed: {e}")
                    import traceback
                    logger.debug(traceback.format_exc())
                    return ("error", None, None)
        
        for batch_num in range(num_batches):
            start_idx = batch_num * batch_size
            end_idx = min(start_idx + batch_size, total_songs)
            batch_songs = songs[start_idx:end_idx]
            
            logger.info("")
            logger.info(f"--- Batch {batch_num + 1}/{num_batches} ({len(batch_songs)} songs) ---")
            
            # Process batch in parallel (fetch metadata only)
            tasks = [
                process_song(song, start_idx + i + 1)
                for i, song in enumerate(batch_songs)
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Persist enrichments sequentially to avoid transaction conflicts
            batch_success = 0
            batch_errors = 0
            batch_skipped = 0
            
            for result in results:
                if isinstance(result, Exception):
                    batch_errors += 1
                    error_count += 1
                else:
                    status, song_obj, enrichment = result
                    if status == "success" and song_obj and enrichment:
                        # Persist enrichment sequentially
                        try:
                            await service._persist_enrichment(
                                song_obj.uuid,
                                enrichment,
                                db=db
                            )
                            batch_success += 1
                            success_count += 1
                        except Exception as e:
                            logger.error(f"  ✗ Failed to persist {song_obj.artist} - {song_obj.title}: {e}")
                            batch_errors += 1
                            error_count += 1
                    elif status == "skipped":
                        batch_skipped += 1
                        skipped_count += 1
                    elif status == "error":
                        batch_errors += 1
                        error_count += 1
            
            # Commit batch after persisting all enrichments
            try:
                await db.commit()
                logger.info(f"✓ Batch {batch_num + 1} committed: {batch_success} success, {batch_errors} errors, {batch_skipped} skipped")
            except Exception as e:
                logger.error(f"✗ Batch {batch_num + 1} commit failed: {e}")
                await db.rollback()
                # Re-mark batch songs as errors since commit failed
                error_count += batch_success
                success_count -= batch_success
            
            # Small delay between batches
            if batch_num < num_batches - 1:
                await asyncio.sleep(delay_seconds)
        
        # Summary
        logger.info("")
        logger.info("=" * 70)
        logger.info("RE-ENRICHMENT COMPLETE")
        logger.info("=" * 70)
        logger.info(f"Total processed: {total_songs}")
        logger.info(f"  ✓ Success: {success_count}")
        logger.info(f"  ✗ Errors: {error_count}")
        logger.info(f"  ⚠ Skipped: {skipped_count}")
        logger.info("=" * 70)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Re-enrich all songs using Spotify Web API metadata"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of songs to process (default: all)"
    )
    parser.add_argument(
        "--missing-features",
        action="store_true",
        help="Only process songs missing audio features"
    )
    parser.add_argument(
        "--missing-artwork",
        action="store_true",
        help="Only process songs missing artwork"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-enrich all songs even if metadata already exists"
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.2,
        help="Delay between API calls in seconds (default: 0.2)"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Number of songs to process per batch before committing (default: 10)"
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=5,
        help="Number of concurrent workers for parallel processing (default: 5)"
    )
    
    args = parser.parse_args()
    
    # Validate arguments
    if args.missing_features and args.missing_artwork:
        logger.error("Cannot use both --missing-features and --missing-artwork")
        sys.exit(1)
    
    asyncio.run(redo_all_metadata(
        limit=args.limit,
        missing_features_only=args.missing_features,
        missing_artwork_only=args.missing_artwork,
        force=args.force,
        delay_seconds=args.delay,
        batch_size=args.batch_size,
        workers=args.workers,
    ))


if __name__ == "__main__":
    main()

