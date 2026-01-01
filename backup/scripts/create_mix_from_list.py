"""Script to create a single MP3 mix from a list of songs.

This script:
1. Downloads songs from the provided list
2. Generates intro TTS with full song list
3. Plans transitions between songs using AI DJ logic
4. Generates TTS every 2-3 songs
5. Mixes everything into a single MP3 file

Usage:
    python backend_v2/scripts/create_mix_from_list.py --songs "Artist1 - Song1" "Artist2 - Song2" ...
    
    Or provide songs in a file:
    python backend_v2/scripts/create_mix_from_list.py --file songs.txt
    
    songs.txt format (one per line):
    Artist1 - Song1
    Artist2 - Song2
    ...

Options:
    --output OUTPUT     Output MP3 filename (default: mix_YYYYMMDD_HHMMSS.mp3)
    --dj-personality    DJ personality: casual_funny, hype_energetic, etc. (default: casual_funny)
    --tts-interval     Generate TTS every N songs (default: 2)
    --no-intro         Skip intro TTS
    --no-transitions   Skip transition TTS (only intro)
"""
import os
import sys
import asyncio
import logging
import argparse
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import ffmpeg

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
load_dotenv()

from backend_v2.tools.song_downloader import SongDownloader
from backend_v2.audio.mix import create_intro_mix, create_dj_mix, get_duration
from backend_v2.audio.transition_params import compile_transition_params
from backend_v2.audio.transition_types import resolve_transition_type
from backend_v2.integrations.elevenlabs import get_elevenlabs_client
from backend_v2.db.session import get_db_session
from backend_v2.models.existing import Song
from backend_v2.integrations.openrouter import get_openrouter_client
from backend_v2.config import SONG_CACHE_DIR, TTS_DIR, SEGMENT_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("mix-creator")


# =============================================================================
# Custom Prompts for Mix Creation
# =============================================================================

INTRO_SPEECH_PROMPT = """You are a DJ introducing a custom mix. The user has provided a specific list of songs.

Song List:
{song_list}

Create a brief, energetic intro (2-3 sentences max) that:
- Welcomes listeners to the mix
- Mentions it's a curated selection
- Sets the vibe/energy level
- Keep it concise and engaging

Return ONLY the speech text, no JSON, no markdown."""

TRANSITION_SPEECH_PROMPT = """You are a DJ transitioning between songs in a custom mix.

Previous Song: {prev_artist} - {prev_title}
Next Song: {next_artist} - {next_title}
Songs Played So Far: {songs_played_count}
Total Songs: {total_songs}

Create a brief transition (1-2 sentences max) that:
- Smoothly transitions from previous to next song
- Mentions the next song naturally
- Keeps energy flowing
- Avoids repetition

Return ONLY the speech text, no JSON, no markdown."""

TRANSITION_PLAN_PROMPT = """You are a DJ planning transitions between songs in a custom mix.

Previous Song: {prev_artist} - {prev_title}
Next Song: {next_artist} - {next_title}

Available transition types:
- crossfade: Smooth volume crossfade (default)
- eq_blend: EQ-based blend
- filter_sweep: Filter sweep transition
- bass_swap: Bass swap transition
- quick_cut: Quick cut
- vinyl_stop: Vinyl stop effect
- loop_mix: Loop-based mix
- drop_mix: Drop mix

Choose the best transition type for these two songs. Consider:
- Energy levels
- Tempo compatibility
- Genre similarity
- Flow and vibe

Return JSON:
{{
  "transition_type": "crossfade",
  "rationale": "Brief explanation"
}}"""


# =============================================================================
# Helper Functions
# =============================================================================

async def generate_intro_speech(song_list: List[str]) -> Optional[str]:
    """Generate intro TTS with full song list."""
    client = get_openrouter_client()
    if not client.enabled:
        logger.warning("OpenRouter not enabled, skipping intro TTS")
        return None
    
    song_list_text = "\n".join([f"{i+1}. {song}" for i, song in enumerate(song_list)])
    
    try:
        messages = [
            {"role": "system", "content": "You are an energetic DJ."},
            {"role": "user", "content": INTRO_SPEECH_PROMPT.format(song_list=song_list_text)}
        ]
        
        response = await client.chat_completion(
            messages=messages,
            temperature=0.8,
            use_lite_model=True,
            session_id=None,  # Standalone script call
        )
        
        if response and response.get("content"):
            text = response["content"].strip()
            # Clean up any markdown or JSON formatting
            text = text.replace("```", "").replace("json", "").strip()
            if text.startswith('"') and text.endswith('"'):
                text = text[1:-1]
            
            logger.info(f"Generated intro speech: {text[:100]}...")
            return text
    except Exception as e:
        logger.error(f"Failed to generate intro speech: {e}")
    
    return None


async def generate_transition_speech(
    prev_song: Dict[str, Any],
    next_song: Dict[str, Any],
    songs_played: int,
    total_songs: int,
) -> Optional[str]:
    """Generate transition TTS between songs."""
    client = get_openrouter_client()
    if not client.enabled:
        return None
    
    try:
        messages = [
            {"role": "system", "content": "You are an energetic DJ."},
            {"role": "user", "content": TRANSITION_SPEECH_PROMPT.format(
                prev_artist=prev_song.get("artist", "Unknown"),
                prev_title=prev_song.get("title", "Unknown"),
                next_artist=next_song.get("artist", "Unknown"),
                next_title=next_song.get("title", "Unknown"),
                songs_played_count=songs_played,
                total_songs=total_songs,
            )}
        ]
        
        response = await client.chat_completion(
            messages=messages,
            temperature=0.8,
            use_lite_model=True,
            session_id=None,  # Standalone script call
        )
        
        if response and response.get("content"):
            text = response["content"].strip()
            text = text.replace("```", "").replace("json", "").strip()
            if text.startswith('"') and text.endswith('"'):
                text = text[1:-1]
            
            logger.info(f"Generated transition speech: {text[:100]}...")
            return text
    except Exception as e:
        logger.error(f"Failed to generate transition speech: {e}")
    
    return None


async def plan_transition(
    prev_song: Dict[str, Any],
    next_song: Dict[str, Any],
) -> Dict[str, Any]:
    """Plan transition between two songs."""
    client = get_openrouter_client()
    
    default_plan = {
        "transition_type": "crossfade",
        "mix_length_bars": 16,
        "start_position_b_seconds": 0.0,
        "rationale": "Default crossfade",
    }
    
    if not client.enabled:
        return default_plan
    
    try:
        messages = [
            {"role": "system", "content": "You are a DJ planning transitions. Return only valid JSON."},
            {"role": "user", "content": TRANSITION_PLAN_PROMPT.format(
                prev_artist=prev_song.get("artist", "Unknown"),
                prev_title=prev_song.get("title", "Unknown"),
                next_artist=next_song.get("artist", "Unknown"),
                next_title=next_song.get("title", "Unknown"),
            )}
        ]
        
        response = await client.chat_completion(
            messages=messages,
            temperature=0.7,
            json_mode=True,
            use_lite_model=True,  # Use lite model instead of model parameter
        )
        
        if response and response.get("parsed"):
            plan = response["parsed"]
            
            transition_type = plan.get("transition_type", "crossfade")
            # Validate transition type
            allowed = ["crossfade", "eq_blend", "filter_sweep", "bass_swap", "quick_cut", "vinyl_stop", "loop_mix", "drop_mix"]
            if transition_type not in allowed:
                transition_type = "crossfade"
            
            return {
                "transition_type": transition_type,
                "mix_length_bars": 16,
                "start_position_b_seconds": 0.0,
                "rationale": plan.get("rationale", "AI planned"),
            }
    except Exception as e:
        logger.error(f"Failed to plan transition: {e}")
    
    return default_plan


async def synthesize_speech(text: str) -> Optional[str]:
    """Synthesize TTS using ElevenLabs."""
    if not text:
        return None
    
    client = get_elevenlabs_client()
    if not client.enabled:
        logger.warning("ElevenLabs not enabled, skipping TTS")
        return None
    
    try:
        output_path = await client.synthesize_speech(text=text)
        return output_path
    except Exception as e:
        logger.error(f"TTS synthesis failed: {e}")
        return None


# =============================================================================
# Main Mix Creation
# =============================================================================

async def create_mix(
    songs: List[str],
    output_path: str,
    tts_interval: int = 2,
    include_intro: bool = True,
    include_transitions: bool = True,
) -> bool:
    """Create a mix from a list of songs."""
    logger.info(f"Creating mix with {len(songs)} songs")
    logger.info(f"Output: {output_path}")
    
    # Step 1: Check cache and download missing songs
    logger.info("📥 Checking cache and downloading songs...")
    downloader = SongDownloader()
    
    # Helper function to sanitize filename (same logic as SongDownloader)
    def sanitize_filename(name: str) -> str:
        """Sanitize a string for use in filenames."""
        import re
        # Remove or replace invalid characters
        name = re.sub(r'[<>:"/\\|?*]', '', name)
        # Replace multiple spaces with single space
        name = re.sub(r'\s+', ' ', name)
        # Limit length
        return name[:100].strip()
    
    # Helper function to check if song exists in cache
    def check_cache(artist: str, title: str) -> Optional[str]:
        """Check if song exists in cache, return file path if found."""
        if not artist or not title:
            return None
        
        safe_artist = sanitize_filename(artist)
        safe_title = sanitize_filename(title)
        filename = f"{safe_artist} - {safe_title}.mp3"
        file_path = downloader.cache_dir / filename
        
        if file_path.exists():
            return str(file_path)
        return None
    
    # Helper function to download a single song (async, will be run in thread pool)
    async def download_song_async(song_info: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Download a single song - async version."""
        song_query = song_info["query"]
        artist = song_info.get("artist")
        title = song_info.get("title")
        index = song_info["index"]
        
        try:
            # Check cache first
            if artist and title:
                cached_path = check_cache(artist, title)
                if cached_path:
                    logger.info(f"[{index}/{len(songs)}] ✅ Found in cache: {artist} - {title}")
                    return {
                        "artist": artist,
                        "title": title,
                        "file_path": cached_path,
                        "query": song_query,
                        "cached": True,
                    }
            
            # Download if not in cache
            logger.info(f"[{index}/{len(songs)}] ⬇️  Downloading: {song_query}")
            
            result = await downloader.download_song(
                query=song_query,
                artist=artist,
                title=title,
                skip_db_storage=False,
            )
            
            if result and result.get("file_path"):
                logger.info(f"[{index}/{len(songs)}] ✅ Downloaded: {result.get('artist')} - {result.get('title')}")
                return {
                    "artist": result.get("artist") or artist or "Unknown",
                    "title": result.get("title") or title or "Unknown",
                    "file_path": result["file_path"],
                    "query": song_query,
                    "uuid": result.get("uuid"),
                    "cached": False,
                }
            else:
                logger.error(f"[{index}/{len(songs)}] ❌ Failed to download: {song_query}")
                return None
                
        except Exception as e:
            logger.error(f"[{index}/{len(songs)}] ❌ Error downloading {song_query}: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    # Helper function to run async download in thread (thread-safe wrapper)
    def download_song_task(song_info: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Download a single song - thread-safe wrapper for async function."""
        # Create new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(download_song_async(song_info))
        finally:
            loop.close()
    
    # Parse all songs first
    song_tasks = []
    for i, song_query in enumerate(songs, 1):
        if " - " in song_query:
            parts = song_query.split(" - ", 1)
            artist = parts[0].strip()
            title = parts[1].strip()
        else:
            artist = None
            title = None
        
        song_tasks.append({
            "query": song_query,
            "artist": artist,
            "title": title,
            "index": i,
        })
    
    # Download songs in parallel with 4 threads
    downloaded_songs = []
    cache_hits = 0
    downloads = 0
    
    with ThreadPoolExecutor(max_workers=4) as executor:
        # Submit all download tasks
        future_to_song = {
            executor.submit(download_song_task, task): task 
            for task in song_tasks
        }
        
        # Process completed downloads
        for future in as_completed(future_to_song):
            result = future.result()
            if result:
                downloaded_songs.append(result)
                if result.get("cached"):
                    cache_hits += 1
                else:
                    downloads += 1
            else:
                logger.error(f"Failed to get song: {future_to_song[future]['query']}")
    
    # Sort by original order
    downloaded_songs.sort(key=lambda x: next(i for i, task in enumerate(song_tasks) if task["query"] == x["query"]))
    
    if not downloaded_songs:
        logger.error("No songs available (cache or downloads)")
        return False
    
    logger.info(f"✅ Ready: {len(downloaded_songs)} songs ({cache_hits} from cache, {downloads} downloaded)")
    
    # Step 2: Generate intro TTS
    intro_tts_path = None
    if include_intro:
        logger.info("🎤 Generating intro TTS...")
        song_list = [f"{s['artist']} - {s['title']}" for s in downloaded_songs]
        intro_text = await generate_intro_speech(song_list)
        if intro_text:
            intro_tts_path = await synthesize_speech(intro_text)
            if intro_tts_path:
                logger.info(f"✅ Intro TTS generated: {intro_tts_path}")
    
    # Step 3: Create segments
    logger.info("🎵 Creating audio segments...")
    segments = []
    
    # Create intro segment (first song)
    first_song = downloaded_songs[0]
    logger.info(f"Creating intro segment: {first_song['artist']} - {first_song['title']}")
    
    intro_result = await asyncio.to_thread(
        create_intro_mix,
        song_path=first_song["file_path"],
        tts_path=intro_tts_path,
        output_path=None,
    )
    
    if not intro_result or not intro_result.get("output_path"):
        logger.error("Failed to create intro segment")
        return False
    
    segments.append(intro_result["output_path"])
    logger.info(f"✅ Intro segment: {intro_result['output_path']}")
    
    # Create transition segments for remaining songs
    songs_since_tts = 0
    for i in range(1, len(downloaded_songs)):
        prev_song = downloaded_songs[i - 1]
        next_song = downloaded_songs[i]
        
        logger.info(f"Creating transition: {prev_song['artist']} - {prev_song['title']} → {next_song['artist']} - {next_song['title']}")
        
        # Plan transition
        transition_plan = await plan_transition(prev_song, next_song)
        transition_type = transition_plan.get("transition_type", "crossfade")
        logger.info(f"Transition type: {transition_type}")
        
        # Generate TTS if needed
        tts_path = None
        if include_transitions and songs_since_tts >= tts_interval - 1:
            logger.info("🎤 Generating transition TTS...")
            transition_text = await generate_transition_speech(
                prev_song=prev_song,
                next_song=next_song,
                songs_played=i,
                total_songs=len(downloaded_songs),
            )
            if transition_text:
                tts_path = await synthesize_speech(transition_text)
                if tts_path:
                    songs_since_tts = 0
                    logger.info(f"✅ Transition TTS: {tts_path}")
        
        songs_since_tts += 1
        
        # Get BPM from DB if available
        bpm_a = None
        bpm_b = None
        
        if prev_song.get("uuid"):
            async with get_db_session() as db:
                s = await db.get(Song, prev_song["uuid"])
                if s and s.features:
                    bpm_a = s.features.get("tempo")
                    
        if next_song.get("uuid"):
            async with get_db_session() as db:
                s = await db.get(Song, next_song["uuid"])
                if s and s.features:
                    bpm_b = s.features.get("tempo")
        
        # Create mix segment
        mix_result = await asyncio.to_thread(
            create_dj_mix,
            song1_path=prev_song["file_path"],
            song2_path=next_song["file_path"],
            transition_type=transition_type,
            tts_path=tts_path,
            output_path=None,
            bpm_a=bpm_a,
            bpm_b=bpm_b,
        )
        
        if not mix_result or not mix_result.get("output_path"):
            logger.error(f"Failed to create mix segment {i}")
            return False
        
        segments.append(mix_result["output_path"])
        logger.info(f"✅ Mix segment {i}: {mix_result['output_path']}")
    
    # Step 4: Concatenate all segments into single MP3
    logger.info("🔗 Concatenating segments into final mix...")
    
    try:
        # Create concat file for ffmpeg concat demuxer
        concat_file = os.path.join(SEGMENT_DIR, f"concat_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
        with open(concat_file, 'w', encoding='utf-8') as f:
            for segment in segments:
                # Use absolute path and escape for Windows
                abs_path = os.path.abspath(segment).replace('\\', '/')
                f.write(f"file '{abs_path}'\n")
        
        # Use ffmpeg concat demuxer (more reliable than filter)
        input_file = ffmpeg.input(concat_file, format='concat', safe=0)
        output = ffmpeg.output(
            input_file,
            output_path,
            acodec='libmp3lame',
            audio_bitrate='192k',
            ac=2,
            ar=44100,
        )
        
        ffmpeg.run(output, overwrite_output=True, quiet=True)
        
        logger.info(f"✅ Final mix created: {output_path}")
        
        # Get file size
        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        logger.info(f"📊 File size: {size_mb:.2f} MB")
        
        # Cleanup
        os.remove(concat_file)
        logger.info("🧹 Cleaned up temporary files")
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to concatenate segments: {e}")
        import traceback
        traceback.print_exc()
        return False


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Create a single MP3 mix from a list of songs")
    parser.add_argument(
        "--songs",
        nargs="+",
        help="List of songs in 'Artist - Title' format",
    )
    parser.add_argument(
        "--file",
        type=str,
        help="File containing song list (one per line)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output MP3 filename (default: mix_YYYYMMDD_HHMMSS.mp3)",
    )
    parser.add_argument(
        "--tts-interval",
        type=int,
        default=2,
        help="Generate TTS every N songs (default: 2)",
    )
    parser.add_argument(
        "--no-intro",
        action="store_true",
        help="Skip intro TTS",
    )
    parser.add_argument(
        "--no-transitions",
        action="store_true",
        help="Skip transition TTS (only intro)",
    )
    
    args = parser.parse_args()
    
    # Get songs list
    songs = []
    if args.file:
        # Try current directory first, then script directory
        file_path = args.file
        if not os.path.exists(file_path):
            script_dir = Path(__file__).parent
            alt_path = script_dir / file_path
            if alt_path.exists():
                file_path = str(alt_path)
            else:
                parser.error(f"File not found: {args.file} (checked current directory and {script_dir})")
        
        with open(file_path, 'r', encoding='utf-8') as f:
            songs = [line.strip() for line in f if line.strip()]
    elif args.songs:
        songs = args.songs
    else:
        parser.error("Must provide either --songs or --file")
    
    if not songs:
        parser.error("No songs provided")
    
    # Generate output filename
    if not args.output:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        args.output = f"mix_{timestamp}.mp3"
    
    # Ensure output is MP3
    if not args.output.endswith('.mp3'):
        args.output += '.mp3'
    
    # Run async mix creation
    success = asyncio.run(create_mix(
        songs=songs,
        output_path=args.output,
        tts_interval=args.tts_interval,
        include_intro=not args.no_intro,
        include_transitions=not args.no_transitions,
    ))
    
    if success:
        print(f"\n✅ Mix created successfully: {args.output}")
        sys.exit(0)
    else:
        print("\n❌ Failed to create mix")
        sys.exit(1)


if __name__ == "__main__":
    main()

