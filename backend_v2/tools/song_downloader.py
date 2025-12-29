"""Song downloader using yt-dlp for AI DJ system.

Downloads songs from YouTube and other platforms, extracts audio as MP3,
and stores metadata in the database.

Ported from backend/song_downloader.py with SQLAlchemy async support.
"""
import os
import logging
import asyncio
import uuid
from typing import Optional, Dict, Any, List
from pathlib import Path

import yt_dlp
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend_v2.config import SONG_CACHE_DIR
from backend_v2.db.session import get_db_session
from backend_v2.models.existing import Song

logger = logging.getLogger("ai-dj.downloader")


class SongDownloader:
    """Downloads songs using yt-dlp and manages the song cache."""
    
    def __init__(self, cache_dir: str = None):
        """
        Initialize the song downloader.
        
        Args:
            cache_dir: Directory to store downloaded songs
        """
        self.cache_dir = Path(cache_dir or SONG_CACHE_DIR)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Look for YouTube cookies file in project root or data directory
        project_root = Path(__file__).parent.parent.parent
        cookies_file = None
        
        # Check multiple possible locations for cookies file
        possible_paths = [
            project_root / 'www.youtube.com_cookies.txt',
            project_root / 'cookies.txt',
            project_root / 'youtube_cookies.txt',
            project_root / 'data' / 'www.youtube.com_cookies.txt',
            project_root / 'data' / 'cookies.txt',
        ]
        
        for path in possible_paths:
            if path.exists():
                cookies_file = str(path)
                logger.info(f"Using YouTube cookies file: {cookies_file}")
                break
        
        if not cookies_file:
            logger.warning("No YouTube cookies file found - downloads may fail due to bot detection")
        
        # Default yt-dlp options for audio extraction
        self.base_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'outtmpl': str(self.cache_dir / '%(artist)s - %(title)s.%(ext)s'),
            'quiet': False,
            'no_warnings': False,
            'extract_flat': False,
            'ignoreerrors': False,
            'nocheckcertificate': True,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            'http_headers': {
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                'Accept-Language': 'en-US,en;q=0.9',
                'Sec-Fetch-Mode': 'navigate',
            },
        }
        
        # Add cookies if file exists
        if cookies_file:
            self.base_opts['cookiefile'] = cookies_file
    
    async def download_song(
        self, 
        query: str, 
        artist: Optional[str] = None,
        title: Optional[str] = None,
        target_uuid: Optional[str] = None,
        skip_db_storage: bool = False
    ) -> Optional[Dict[str, Any]]:
        """
        Download a song from YouTube by search query.
        
        Args:
            query: Search query (e.g., "Taylor Swift Shake It Off")
            artist: Optional artist name for metadata
            title: Optional song title for metadata
            target_uuid: Optional UUID to use when storing in database
            skip_db_storage: If True, don't store in database
        
        Returns:
            Dict with song info and file path, or None if failed
        """
        try:
            # Build search URL
            search_url = f"ytsearch1:{query}"
            
            logger.info(f"Downloading song: {query}")
            
            # Run yt-dlp in thread pool to avoid blocking
            result = await asyncio.to_thread(
                self._download_with_ytdlp,
                search_url,
                artist,
                title
            )
            
            if result:
                # Generate UUID now so we can return it
                song_uuid = target_uuid or str(uuid.uuid4())
                
                # Store in database unless caller wants to handle it
                if not skip_db_storage:
                    await self._store_in_db(result, target_uuid=song_uuid)
                logger.info(f"Successfully downloaded: {result['file_path']} (uuid={song_uuid})")
                
                # Include uuid in the result
                result['uuid'] = song_uuid
            
            return result
        
        except Exception as e:
            logger.error(f"Error downloading song '{query}': {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _download_with_ytdlp(
        self, 
        url: str,
        artist: Optional[str] = None,
        title: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Synchronous download using yt-dlp.
        
        Args:
            url: YouTube URL or search query
            artist: Optional artist name
            title: Optional song title
        
        Returns:
            Dict with download info or None
        """
        opts = self.base_opts.copy()
        
        # Custom output template if artist/title provided
        if artist and title:
            safe_artist = self._sanitize_filename(artist)
            safe_title = self._sanitize_filename(title)
            opts['outtmpl'] = str(self.cache_dir / f'{safe_artist} - {safe_title}.%(ext)s')
        
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                # Extract info first
                info = ydl.extract_info(url, download=False)
                
                if not info:
                    logger.error("No video found for query")
                    return None
                
                # Get the first result if it's a search
                if 'entries' in info:
                    info = info['entries'][0]
                
                # Now download
                ydl.download([info['webpage_url']])
                
                # Determine output file path
                file_path = self._get_output_path(info, artist, title)
                
                # Extract metadata
                return {
                    'file_path': str(file_path),
                    'title': title or info.get('title', 'Unknown'),
                    'artist': artist or info.get('artist') or info.get('uploader', 'Unknown'),
                    'duration_sec': info.get('duration', 0),
                    'youtube_id': info.get('id'),
                    'youtube_url': info.get('webpage_url'),
                    'thumbnail_url': info.get('thumbnail'),
                }
        
        except Exception as e:
            logger.error(f"yt-dlp error: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _get_output_path(
        self, 
        info: Dict[str, Any],
        artist: Optional[str] = None,
        title: Optional[str] = None
    ) -> Path:
        """
        Determine the output file path based on info and provided metadata.
        
        Args:
            info: yt-dlp info dict
            artist: Optional artist name
            title: Optional song title
        
        Returns:
            Path to the downloaded file
        """
        if artist and title:
            safe_artist = self._sanitize_filename(artist)
            safe_title = self._sanitize_filename(title)
            filename = f'{safe_artist} - {safe_title}.mp3'
        else:
            # Use yt-dlp's default naming
            artist_name = info.get('artist') or info.get('uploader', 'Unknown')
            song_title = info.get('title', 'Unknown')
            safe_artist = self._sanitize_filename(artist_name)
            safe_title = self._sanitize_filename(song_title)
            filename = f'{safe_artist} - {safe_title}.mp3'
        
        return self.cache_dir / filename
    
    def _sanitize_filename(self, name: str) -> str:
        """
        Sanitize a string for use in filenames.
        
        Args:
            name: String to sanitize
        
        Returns:
            Sanitized string safe for filenames
        """
        # Remove or replace invalid filename characters
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            name = name.replace(char, '')
        
        # Limit length
        return name[:100].strip()
    
    async def _store_in_db(self, song_info: Dict[str, Any], target_uuid: Optional[str] = None) -> None:
        """
        Store downloaded song metadata in the database and enrich with external metadata.
        
        Args:
            song_info: Dict with song metadata and file path
            target_uuid: Optional UUID to use (instead of generating new one)
        """
        try:
            # Use provided UUID or generate new one
            song_uuid = target_uuid or str(uuid.uuid4())
            
            async with get_db_session() as db:
                # Check if song already exists
                existing = await db.execute(
                    select(Song).where(Song.uuid == song_uuid)
                )
                if existing.scalar_one_or_none():
                    logger.info(f"Song {song_uuid} already exists in database")
                    return
                
                # Create Song record
                song = Song(
                    uuid=song_uuid,
                    title=song_info['title'],
                    artist=song_info['artist'],
                    duration_sec=song_info['duration_sec'],
                    local_path=song_info['file_path'],
                    filesize_bytes=os.path.getsize(song_info['file_path']) if os.path.exists(song_info['file_path']) else 0,
                )
                db.add(song)
                await db.commit()
                
            logger.info(f"Stored song in database: {song_uuid}")
            
            # Enrich with external metadata (MusicBrainz + Apple Music)
            await self._enrich_song_metadata(
                song_uuid=song_uuid,
                artist=song_info['artist'],
                title=song_info['title'],
                audio_path=song_info.get("file_path"),
            )
        
        except Exception as e:
            logger.error(f"Error storing song in database: {e}")
            import traceback
            traceback.print_exc()
    
    async def _enrich_song_metadata(
        self,
        song_uuid: str,
        artist: str,
        title: str,
        audio_path: Optional[str] = None,
    ) -> None:
        """
        Enrich song with external metadata (MusicBrainz, Apple Music).
        
        This runs asynchronously after download to add:
        - MusicBrainz IDs (recording, release, artist)
        - ISRC codes
        - Apple Music artwork URLs
        - Genre information
        
        Args:
            song_uuid: UUID of the song in database
            artist: Artist name
            title: Song title
        """
        try:
            from backend_v2.integrations.metadata import enrich_song_metadata
            
            logger.info(f"Enriching metadata: {artist} - {title}")
            
            enrichment = await enrich_song_metadata(
                song_uuid=song_uuid,
                artist=artist,
                title=title,
                audio_path=audio_path,
            )
            
            if enrichment.get('artwork_url'):
                logger.info(f"  → Artwork: {enrichment['artwork_url'][:50]}...")
            if enrichment.get('genres'):
                logger.info(f"  → Genres: {enrichment['genres']}")
            if enrichment.get('recording_mbid'):
                logger.info(f"  → MusicBrainz ID: {enrichment['recording_mbid']}")
                
        except Exception as e:
            # Non-fatal - song is already saved, enrichment is optional
            logger.warning(f"Metadata enrichment failed (non-fatal): {e}")
    
    async def download_multiple(
        self, 
        songs: List[Dict[str, str]]
    ) -> List[Optional[Dict[str, Any]]]:
        """
        Download multiple songs.
        
        Args:
            songs: List of dicts with 'query', 'artist', 'title' keys
        
        Returns:
            List of download results
        """
        results = []
        
        for song in songs:
            query = song.get('query')
            artist = song.get('artist')
            title = song.get('title')
            
            if not query:
                logger.warning(f"Skipping song with no query: {song}")
                results.append(None)
                continue
            
            result = await self.download_song(query, artist, title)
            results.append(result)
            
            # Small delay to avoid rate limiting
            await asyncio.sleep(2)
        
        return results
    
    def get_cached_songs(self) -> List[Path]:
        """
        Get list of all cached song files.
        
        Returns:
            List of Path objects for cached MP3 files
        """
        return list(self.cache_dir.glob('*.mp3'))
    
    def get_cache_size(self) -> int:
        """
        Calculate total size of cached songs in bytes.
        
        Returns:
            Total cache size in bytes
        """
        total_size = 0
        for file_path in self.get_cached_songs():
            if file_path.is_file():
                total_size += file_path.stat().st_size
        return total_size


# Singleton instance
_downloader: Optional[SongDownloader] = None

def get_song_downloader() -> SongDownloader:
    """Get the singleton SongDownloader instance."""
    global _downloader
    if _downloader is None:
        _downloader = SongDownloader()
    return _downloader


async def download_song_cli(query: str, artist: str = None, title: str = None):
    """
    CLI helper function to download a song.
    
    Args:
        query: Search query
        artist: Optional artist name
        title: Optional song title
    """
    downloader = SongDownloader()
    result = await downloader.download_song(query, artist, title)
    
    if result:
        print(f"✓ Downloaded: {result['file_path']}")
        print(f"  Artist: {result['artist']}")
        print(f"  Title: {result['title']}")
        print(f"  Duration: {result['duration_sec']}s")
    else:
        print(f"✗ Failed to download: {query}")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python -m backend_v2.tools.song_downloader <search_query> [artist] [title]")
        print("Example: python -m backend_v2.tools.song_downloader 'Taylor Swift Shake It Off'")
        print("Example: python -m backend_v2.tools.song_downloader 'shake it off' 'Taylor Swift' 'Shake It Off'")
        sys.exit(1)
    
    query = sys.argv[1]
    artist = sys.argv[2] if len(sys.argv) > 2 else None
    title = sys.argv[3] if len(sys.argv) > 3 else None
    
    asyncio.run(download_song_cli(query, artist, title))
