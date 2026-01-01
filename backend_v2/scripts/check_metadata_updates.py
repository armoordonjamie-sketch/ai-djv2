"""Check what metadata was added to songs in the database.

Usage:
    python -m backend_v2.scripts.check_metadata_updates --limit 10
    python -m backend_v2.scripts.check_metadata_updates --song "Risk"
"""
import asyncio
import argparse
import logging
import json
from typing import Optional

from sqlalchemy import select, or_
from sqlalchemy.orm import selectinload

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("check_metadata")


async def check_metadata_updates(
    limit: Optional[int] = None,
    song_title: Optional[str] = None,
    artist_name: Optional[str] = None,
):
    """Check what metadata was added to songs.
    
    Args:
        limit: Maximum number of songs to check (None = all)
        song_title: Filter by song title (partial match)
        artist_name: Filter by artist name (partial match)
    """
    # Import all models to ensure SQLAlchemy relationships resolve correctly
    from backend_v2.models import existing  # noqa: F401
    from backend_v2.models.spotify_context import SpotifyUserContext  # noqa: F401
    from backend_v2.db.session import get_db_session
    from backend_v2.models.existing import Song, SongFeatures
    
    async with get_db_session() as db:
        # Build query
        query = (
            select(Song)
            .options(selectinload(Song.features))
            .order_by(Song.uuid)
        )
        
        if song_title:
            query = query.where(Song.title.ilike(f"%{song_title}%"))
        
        if artist_name:
            query = query.where(Song.artist.ilike(f"%{artist_name}%"))
        
        if limit:
            query = query.limit(limit)
        
        result = await db.execute(query)
        songs = result.scalars().all()
        
        logger.info(f"Found {len(songs)} songs to check\n")
        
        for i, song in enumerate(songs, 1):
            logger.info("=" * 80)
            logger.info(f"[{i}/{len(songs)}] {song.artist} - {song.title}")
            logger.info("=" * 80)
            
            # Basic info
            logger.info(f"UUID: {song.uuid}")
            logger.info(f"Duration: {song.duration_sec}s" if song.duration_sec else "Duration: N/A")
            logger.info(f"ISRC: {song.isrc}" if song.isrc else "ISRC: None")
            logger.info(f"Explicit: {song.explicit}" if song.explicit is not None else "Explicit: N/A")
            
            # Artwork
            if song.artwork_url:
                logger.info(f"Artwork URL: {song.artwork_url}")
            else:
                logger.info("Artwork URL: None")
            
            # Genres
            if song.genres:
                try:
                    genres = json.loads(song.genres) if isinstance(song.genres, str) else song.genres
                    logger.info(f"Genres ({len(genres)}): {', '.join(genres[:5])}")
                except:
                    logger.info(f"Genres: {song.genres}")
            else:
                logger.info("Genres: None")
            
            # Tags
            if song.tags:
                try:
                    tags = json.loads(song.tags) if isinstance(song.tags, str) else song.tags
                    logger.info(f"Tags ({len(tags)}): {', '.join(tags[:5])}")
                except:
                    logger.info(f"Tags: {song.tags}")
            else:
                logger.info("Tags: None")
            
            # External IDs
            logger.info(f"Recording MBID: {song.recording_mbid}" if song.recording_mbid else "Recording MBID: None")
            logger.info(f"Apple Song ID: {song.apple_song_id}" if song.apple_song_id else "Apple Song ID: None")
            
            # Audio Features
            if song.features:
                logger.info("\nAudio Features:")
                logger.info(f"  Energy: {song.features.energy:.3f}" if song.features.energy is not None else "  Energy: N/A")
                logger.info(f"  Valence: {song.features.valence:.3f}" if song.features.valence is not None else "  Valence: N/A")
                logger.info(f"  Tempo: {song.features.tempo:.1f} BPM" if song.features.tempo is not None else "  Tempo: N/A")
                logger.info(f"  Key: {song.features.key}" if song.features.key is not None else "  Key: N/A")
                logger.info(f"  Mode: {song.features.mode}" if song.features.mode is not None else "  Mode: N/A")
                logger.info(f"  Danceability: {song.features.danceability:.3f}" if song.features.danceability is not None else "  Danceability: N/A")
                logger.info(f"  Acousticness: {song.features.acousticness:.3f}" if song.features.acousticness is not None else "  Acousticness: N/A")
                logger.info(f"  Instrumentalness: {song.features.instrumentalness:.3f}" if song.features.instrumentalness is not None else "  Instrumentalness: N/A")
            else:
                logger.info("\nAudio Features: None")
            
            logger.info("")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Check what metadata was added to songs"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of songs to check (default: all)"
    )
    parser.add_argument(
        "--song",
        type=str,
        default=None,
        help="Filter by song title (partial match)"
    )
    parser.add_argument(
        "--artist",
        type=str,
        default=None,
        help="Filter by artist name (partial match)"
    )
    
    args = parser.parse_args()
    
    asyncio.run(check_metadata_updates(
        limit=args.limit,
        song_title=args.song,
        artist_name=args.artist,
    ))


if __name__ == "__main__":
    main()



