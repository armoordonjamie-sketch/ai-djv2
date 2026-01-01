"""Song downloader using yt-dlp for AI DJ system.

Downloads songs from YouTube and other platforms, extracts audio as MP3,
and stores metadata in the database.

Ported from backend/song_downloader.py with SQLAlchemy async support.
"""
import os
import logging
import asyncio
import concurrent.futures
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
_db_write_lock = asyncio.Lock()


def _standalone_download_task(
    url: str,
    base_opts: Dict[str, Any],
    cache_dir_str: str,
    artist: Optional[str] = None,
    title: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Standalone function to run yt-dlp download in a separate process.
    Must be top-level for pickling.
    """
    import yt_dlp
    from pathlib import Path
    import logging
    
    # Setup logging in the worker process
    # We can't easily share the main logger, so we create a new one or print
    # Using print for worker stdout capture if needed, or basic config
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("ai-dj.downloader.worker")
    
    cache_dir = Path(cache_dir_str)
    opts = base_opts.copy()
    
    # Custom output template if artist/title provided
    if artist and title:
        # Simple sanitization here since we can't call instance method
        invalid_chars = '<>:"/\\|?*'
        safe_artist = artist
        safe_title = title
        for char in invalid_chars:
            safe_artist = safe_artist.replace(char, '')
            safe_title = safe_title.replace(char, '')
        safe_artist = safe_artist[:100].strip()
        safe_title = safe_title[:100].strip()
        
        opts['outtmpl'] = str(cache_dir / f'{safe_artist} - {safe_title}.%(ext)s')
    
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            # Extract info first
            info = ydl.extract_info(url, download=False)
            
            if not info:
                return None
            
            # Get the first result if it's a search
            if 'entries' in info:
                if not info['entries']:
                    return None
                info = info['entries'][0]
            
            # Now download
            ydl.download([info['webpage_url']])
            
            # Re-determine filename logic to find the file
            # This must match _get_output_path logic
            if artist and title:
                # Re-sanitize
                safe_artist = artist
                safe_title = title
                for char in invalid_chars:
                    safe_artist = safe_artist.replace(char, '')
                    safe_title = safe_title.replace(char, '')
                safe_artist = safe_artist[:100].strip()
                safe_title = safe_title[:100].strip()
                filename = f'{safe_artist} - {safe_title}.mp3'
            else:
                artist_name = info.get('artist') or info.get('uploader', 'Unknown')
                song_title = info.get('title', 'Unknown')
                # Re-sanitize
                safe_artist = artist_name
                safe_title = song_title
                for char in invalid_chars:
                    safe_artist = safe_artist.replace(char, '')
                    safe_title = safe_title.replace(char, '')
                safe_artist = safe_artist[:100].strip()
                safe_title = safe_title[:100].strip()
                
                filename = f'{safe_artist} - {safe_title}.mp3'
            
            file_path = cache_dir / filename
            
            # Clean up original files (basic version)
            video_extensions = ['.webm', '.m4a', '.mp4', '.opus', '.ogg', '.wav']
            base_path = file_path.with_suffix('')
            
            for ext in video_extensions:
                original_file = base_path.with_suffix(ext)
                if original_file.exists():
                    try:
                        original_file.unlink()
                    except Exception:
                        pass

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
        print(f"Worker process download error: {e}")
        return None

# Global executor
_process_executor = None

def get_process_executor():
    global _process_executor
    if _process_executor is None:
        # Use only 2 workers to avoid crushing the CPU
        _process_executor = concurrent.futures.ProcessPoolExecutor(max_workers=2)
    return _process_executor


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
            if path.exists() and self._is_valid_netscape_cookies(path):
                cookies_file = str(path)
                logger.info(f"Using YouTube cookies file: {cookies_file}")
                break
        
        if not cookies_file:
            logger.warning("No valid YouTube cookies file found - downloads may fail due to bot detection")
        
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
            'keepvideo': True,  # Don't delete original - we handle cleanup manually
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
    
    def _is_valid_netscape_cookies(self, path: Path) -> bool:
        """
        Check if a file is a valid Netscape format cookies file.
        
        The Netscape format requires the file to start with a specific header
        and contain tab-separated cookie data.
        
        Args:
            path: Path to the cookies file
            
        Returns:
            True if the file appears to be valid Netscape format
        """
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read(1024)  # Read first 1KB
                
            # Empty file is not valid
            if not content.strip():
                logger.debug(f"Cookies file {path} is empty")
                return False
            
            # Check for Netscape header (common variations)
            valid_headers = [
                '# Netscape HTTP Cookie File',
                '# HTTP Cookie File',
            ]
            
            first_line = content.split('\n')[0].strip()
            if any(first_line.startswith(header) for header in valid_headers):
                return True
            
            # Some cookie files don't have headers but are still valid
            # Check if it looks like tab-separated cookie data
            lines = [l for l in content.split('\n') if l.strip() and not l.startswith('#')]
            if lines:
                # Valid cookie lines have 7 tab-separated fields
                first_data_line = lines[0]
                if '\t' in first_data_line and len(first_data_line.split('\t')) >= 6:
                    return True
            
            logger.debug(f"Cookies file {path} is not in Netscape format")
            return False
            
        except Exception as e:
            logger.debug(f"Error reading cookies file {path}: {e}")
            return False
    
    async def download_song(
        self, 
        query: str, 
        artist: Optional[str] = None,
        title: Optional[str] = None,
        target_uuid: Optional[str] = None,
        skip_db_storage: bool = False,
        db: Optional[AsyncSession] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Download a song from YouTube by search query.
        
        Args:
            query: Search query (e.g., "Taylor Swift Shake It Off")
            artist: Optional artist name for metadata
            title: Optional song title for metadata
            target_uuid: Optional UUID to use when storing in database
            skip_db_storage: If True, don't store in database
            db: Optional database session (prevents nested session deadlock)
        
        Returns:
            Dict with song info and file path, or None if failed
        """
        try:
            # Build search URL
            search_url = f"ytsearch1:{query}"
            
            logger.info(f"Downloading song: {query}")
            
            # Run in separate PROCESS to avoid blocking main thread/GIL
            # This ensures CPU-heavy yt-dlp/ffmpeg doesn't affect API responsiveness
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                get_process_executor(),
                _standalone_download_task,
                search_url,
                self.base_opts,
                str(self.cache_dir),
                artist,
                title
            )
            
            if result:
                # Generate UUID now so we can return it
                song_uuid = target_uuid or str(uuid.uuid4())
                logger.info(f"Download complete, storing in db (uuid={song_uuid})")
                
                # Store in database unless caller wants to handle it
                if skip_db_storage:
                    logger.info(f"Successfully downloaded (db storage skipped): {result['file_path']} (uuid={song_uuid})")
                else:
                    stored_in_db = await self._store_in_db(result, target_uuid=song_uuid, db=db)
                    if stored_in_db:
                        logger.info(f"Successfully downloaded and stored: {result['file_path']} (uuid={song_uuid})")
                    else:
                        logger.warning(
                            f"Downloaded but failed to store in database: {result['file_path']} (uuid={song_uuid})"
                        )
                
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
                    if not info['entries']:
                        logger.warning(f"No search results found for: {url}")
                        return None
                    info = info['entries'][0]
                
                # Now download
                ydl.download([info['webpage_url']])
                
                # Determine output file path
                file_path = self._get_output_path(info, artist, title)
                
                # Clean up original video file (we kept it to avoid Windows file lock hang)
                logger.debug(f"Cleaning up original files for: {file_path}")
                self._cleanup_original_files(file_path)
                logger.debug(f"Cleanup complete, returning download result")
                
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
    
    def _cleanup_original_files(self, mp3_path: Path) -> None:
        """
        Clean up original video files after MP3 extraction.
        
        yt-dlp's automatic deletion can hang on Windows due to file locks,
        so we handle cleanup manually with proper error handling.
        
        Args:
            mp3_path: Path to the converted MP3 file
        """
        import time
        
        # Common video extensions yt-dlp downloads
        video_extensions = ['.webm', '.m4a', '.mp4', '.opus', '.ogg', '.wav']
        base_path = mp3_path.with_suffix('')
        
        for ext in video_extensions:
            original_file = base_path.with_suffix(ext)
            if original_file.exists():
                # Try to delete with retries (file may still be locked briefly)
                for attempt in range(3):
                    try:
                        original_file.unlink()
                        logger.debug(f"Cleaned up original file: {original_file}")
                        break
                    except PermissionError:
                        if attempt < 2:
                            time.sleep(0.5)  # Brief wait for file lock release
                        else:
                            logger.warning(f"Could not delete original file (still locked): {original_file}")
                    except Exception as e:
                        logger.warning(f"Error cleaning up {original_file}: {e}")
                        break
    
    async def _store_in_db(
        self, 
        song_info: Dict[str, Any], 
        target_uuid: Optional[str] = None,
        max_retries: int = 5,
        db: Optional[AsyncSession] = None
    ) -> bool:
        """
        Store downloaded song metadata in the database and enrich with external metadata.
        
        Includes retry logic for SQLite "database is locked" errors which occur
        when multiple sessions try to write concurrently.
        
        Args:
            song_info: Dict with song metadata and file path
            target_uuid: Optional UUID to use (instead of generating new one)
            max_retries: Maximum number of retries on database lock (default 5)
            db: Optional database session (if provided, uses it directly to avoid nested sessions)
        
        Returns:
            True if the song was stored successfully, False otherwise.
        """
        logger.info(f"📦 _store_in_db called for: {song_info.get('title', 'unknown')}")
        
        song_uuid = target_uuid or str(uuid.uuid4())
        
        # If external session provided, use it directly (prevents nested session deadlock)
        if db is not None:
            logger.info(f"📝 Using provided database session (avoiding nested session)")
            try:
                # Check if song already exists (with timeout)
                try:
                    existing = await asyncio.wait_for(
                        db.execute(select(Song).where(Song.uuid == song_uuid)),
                        timeout=5.0
                    )
                    if existing.scalar_one_or_none():
                        logger.info(f"Song {song_uuid} already exists in database")
                        return True
                except asyncio.TimeoutError:
                    logger.warning(f"⚠️ DB query timed out, proceeding anyway...")
                
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
                logger.info(f"📝 Flushing to database (not committing - parent session will commit)...")
                await db.flush()  # Flush but don't commit - let parent session handle commit
                    
                logger.info(f"✅ Stored song in database: {song_uuid}")
                
                # Enrich with external metadata (MusicBrainz + Apple Music)
                # Use timeout to prevent indefinite hangs on API calls
                logger.info(f"🔍 Starting metadata enrichment (60s timeout)...")
                try:
                    await asyncio.wait_for(
                        self._enrich_song_metadata(
                            song_uuid=song_uuid,
                            artist=song_info['artist'],
                            title=song_info['title'],
                            audio_path=song_info.get("file_path"),
                            db=db  # Pass session to enrichment
                        ),
                        timeout=60.0  # 60 second total timeout for enrichment
                    )
                    logger.info(f"✅ Metadata enrichment complete")
                except asyncio.TimeoutError:
                    logger.warning(f"⚠️ Metadata enrichment timed out after 60s (song saved, enrichment skipped)")
                
                return True  # Success
                
            except Exception as e:
                logger.error(f"Error storing song with provided session: {e}")
                import traceback
                traceback.print_exc()
                raise  # Re-raise to let parent handle
        
        # Fallback: No external session provided, create our own (original behavior)
        for attempt in range(max_retries):
            try:
                logger.info(f"📝 Storing song in db (attempt {attempt + 1}/{max_retries})...")
                async with _db_write_lock:
                    async with get_db_session() as db:
                        # Check if song already exists (with timeout)
                        try:
                            existing = await asyncio.wait_for(
                                db.execute(select(Song).where(Song.uuid == song_uuid)),
                                timeout=5.0
                            )
                            if existing.scalar_one_or_none():
                                logger.info(f"Song {song_uuid} already exists in database")
                                return True
                        except asyncio.TimeoutError:
                            logger.warning(f"⚠️ DB query timed out, proceeding anyway...")
                    
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
                        logger.info(f"📝 Committing to database...")
                        try:
                            await asyncio.wait_for(db.commit(), timeout=10.0)
                        except asyncio.TimeoutError:
                            logger.error(f"❌ Database commit timed out after 10s - possible lock")
                            await db.rollback()
                            raise Exception("Database commit timeout")
                    
                logger.info(f"✅ Stored song in database: {song_uuid}")
                
                # Enrich with external metadata (MusicBrainz + Apple Music)
                # Use timeout to prevent indefinite hangs on API calls
                logger.info(f"🔍 Starting metadata enrichment (60s timeout)...")
                try:
                    await asyncio.wait_for(
                        self._enrich_song_metadata(
                            song_uuid=song_uuid,
                            artist=song_info['artist'],
                            title=song_info['title'],
                            audio_path=song_info.get("file_path"),
                        ),
                        timeout=60.0  # 60 second total timeout for enrichment
                    )
                    logger.info(f"✅ Metadata enrichment complete")
                except asyncio.TimeoutError:
                    logger.warning(f"⚠️ Metadata enrichment timed out after 60s (song saved, enrichment skipped)")
                
                return True  # Success - exit retry loop
            
            except Exception as e:
                error_str = str(e).lower()
                is_lock_error = "database is locked" in error_str or "locked" in error_str
                is_connection_error = (
                    "no active connection" in error_str
                    or "cannot operate on a closed database" in error_str
                    or "connection is closed" in error_str
                )
                is_timeout_error = "database commit timeout" in error_str
                is_retryable = is_lock_error or is_connection_error or is_timeout_error
                
                if is_retryable and attempt < max_retries - 1:
                    # Exponential backoff: 1s, 2s, 4s, 8s, 16s
                    wait_time = 2 ** attempt
                    logger.warning(
                        f"Database write failed, retrying in {wait_time}s "
                        f"(attempt {attempt + 1}/{max_retries})"
                    )
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"Error storing song in database: {e}")
                    import traceback
                    traceback.print_exc()
                    return False  # Give up after max retries or non-retryable error
        
        return False
    
    async def _enrich_song_metadata(
        self,
        song_uuid: str,
        artist: str,
        title: str,
        audio_path: Optional[str] = None,
        db: Optional[AsyncSession] = None
    ) -> None:
        """
        Enrich song with external metadata using Spotify Web API.
        
        This runs asynchronously after download to add:
        - Spotify track ID
        - ISRC codes
        - High-quality artwork URLs
        - Audio features (energy, valence, tempo, danceability, etc.)
        - Genre information
        - Release dates
        
        Args:
            song_uuid: UUID of the song in database
            artist: Artist name
            title: Song title
            audio_path: Path to audio file for feature extraction (fallback)
            db: Optional database session (prevents nested sessions)
        """
        try:
            from backend_v2.integrations.metadata import enrich_song_metadata
            
            logger.info(f"Enriching metadata: {artist} - {title}")
            
            enrichment = await enrich_song_metadata(
                song_uuid=song_uuid,
                artist=artist,
                title=title,
                audio_path=audio_path,
                db=db  # Pass session through
            )
            
            if enrichment.get('artwork_url'):
                logger.info(f"  → Artwork: {enrichment['artwork_url'][:50]}...")
            if enrichment.get('genres'):
                logger.info(f"  → Genres: {enrichment['genres']}")
            if enrichment.get('spotify_id'):
                logger.info(f"  → Spotify ID: {enrichment['spotify_id']}")
            if enrichment.get('features'):
                logger.info(f"  → Audio features: energy={enrichment['features'].get('energy')}, tempo={enrichment['features'].get('tempo')}")
                
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
