
import os
import sys
import logging
import asyncio
import time
from pathlib import Path
import ffmpeg

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend_v2.audio.mix import create_dj_mix
from backend_v2.config import SEGMENT_DIR

# Check for required env var
if not os.environ.get("AUDIO_MIX_PROFILE"):
    print("WARNING: AUDIO_MIX_PROFILE not set. Setting it now.")
    os.environ["AUDIO_MIX_PROFILE"] = "1"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bench_mix")

def generate_tone(filename, duration=180, freq=440):
    """Generate a test tone file using ffmpeg."""
    path = os.path.join(SEGMENT_DIR, filename)
    if not os.path.exists(path):
        logger.info(f"Generating test tone: {path}")
        (
            ffmpeg
            .input(f'sine=f={freq}:r=44100', t=duration, f='lavfi')
            .output(path, acodec='libmp3lame', audio_bitrate='192k')  # Use MP3 to force decoding profile
            .overwrite_output()
            .run(quiet=True)
        )
    return path

async def run_bench():
    os.makedirs(SEGMENT_DIR, exist_ok=True)
    
    song1 = generate_tone("bench_song_a.mp3", 180, 440)
    song2 = generate_tone("bench_song_b.mp3", 180, 880)
    
    print("\n--- Benchmark Run 1 (Cold) ---")
    t0 = time.time()
    res = create_dj_mix(
        song1_path=song1,
        song2_path=song2,
        transition_type="crossfade",
        output_path=os.path.join(SEGMENT_DIR, "bench_output.wav"),
        user_id="bench_user"
    )
    print(f"Total Cold Time: {time.time() - t0:.3f}s")
    
    print("\n--- Benchmark Run 2 (Warm?) ---")
    t0 = time.time()
    res = create_dj_mix(
        song1_path=song1,
        song2_path=song2,
        transition_type="crossfade",
        output_path=os.path.join(SEGMENT_DIR, "bench_output_2.wav"),
        user_id="bench_user"
    )
    print(f"Total Warm Time: {time.time() - t0:.3f}s")

if __name__ == "__main__":
    asyncio.run(run_bench())
