"""Backfill metadata for songs missing features or artwork.

Usage:
    cd backend_v2
    python -m scripts.backfill_metadata

This script:
1. Finds songs missing features or artwork
2. Enriches using all available sources (MusicBrainz, Apple Music, Deezer)
3. Updates database
"""
import asyncio
import logging
import sys

from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("backfill")


async def backfill_metadata():
    """Find and backfill songs missing metadata."""
    from backend_v2.db.session import get_db_session
    from backend_v2.models.existing import Song, SongFeatures
    from backend_v2.integrations.metadata.enrichment import get_metadata_service
    
    service = get_metadata_service()
    
    async with get_db_session() as db:
        # Find songs missing features
        stmt = (
            select(Song)
            .outerjoin(SongFeatures, Song.uuid == SongFeatures.song_uuid)
            .where(SongFeatures.song_uuid.is_(None))
        )
        result = await db.execute(stmt)
        songs_missing_features = result.scalars().all()
        
        logger.info(f"Found {len(songs_missing_features)} songs missing features")
        
        # Find songs missing artwork
        stmt = select(Song).where(
            (Song.artwork_url.is_(None)) | (Song.artwork_url == "")
        )
        result = await db.execute(stmt)
        songs_missing_artwork = result.scalars().all()
        
        logger.info(f"Found {len(songs_missing_artwork)} songs missing artwork")
        
        # Combine unique songs
        all_uuids = set()
        songs_to_enrich = []
        
        for song in songs_missing_features + songs_missing_artwork:
            if song.uuid not in all_uuids:
                all_uuids.add(song.uuid)
                songs_to_enrich.append(song)
        
        logger.info(f"Total unique songs to enrich: {len(songs_to_enrich)}")
        
        # Enrich each song
        success_count = 0
        for i, song in enumerate(songs_to_enrich, 1):
            logger.info(f"[{i}/{len(songs_to_enrich)}] Enriching: {song.artist} - {song.title}")
            
            try:
                enrichment = await service.enrich_song(
                    song_uuid=song.uuid,
                    artist=song.artist or "",
                    title=song.title or "",
                    isrc=song.isrc,
                    audio_path=song.local_path,
                    update_db=True,
                )
                
                if enrichment.get("artwork_url") or enrichment.get("features"):
                    success_count += 1
                    logger.info(f"  ✓ artwork={'yes' if enrichment.get('artwork_url') else 'no'}, "
                               f"features={'yes' if enrichment.get('features') else 'no'}")
                else:
                    logger.warning(f"  ⚠ No enrichment data found")
                
                # Rate limiting
                await asyncio.sleep(0.5)
                
            except Exception as e:
                logger.error(f"  ✗ Failed: {e}")
        
        logger.info(f"\nBackfill complete: {success_count}/{len(songs_to_enrich)} enriched")


if __name__ == "__main__":
    asyncio.run(backfill_metadata())
