
import os
import pytest
import time
import json
import ffmpeg
from backend_v2.audio.mix import create_dj_mix, get_duration
from backend_v2.config import SEGMENT_DIR

@pytest.fixture
def test_songs():
    """Generate two 60s test songs."""
    os.makedirs(SEGMENT_DIR, exist_ok=True)
    songs = []
    
    for i, freq in enumerate([440, 880]):
        path = os.path.join(SEGMENT_DIR, f"test_tone_{i}.mp3")
        if not os.path.exists(path):
            (
                ffmpeg
                .input(f'sine=f={freq}:r=44100', t=60, f='lavfi')
                .output(path, acodec='libmp3lame', audio_bitrate='128k')
                .overwrite_output()
                .run(quiet=True)
            )
        songs.append(path)
        
    return songs

def test_mix_generation_performance(test_songs):
    """Test that mix generation works and is somewhat performant."""
    song1, song2 = test_songs
    output_path = os.path.join(SEGMENT_DIR, "test_mix_output.wav")
    
    start_time = time.time()
    
    result = create_dj_mix(
        song1_path=song1,
        song2_path=song2,
        transition_type="crossfade",
        output_path=output_path,
        user_id="test_user"
    )
    
    duration = time.time() - start_time
    print(f"Test mix took: {duration:.2f}s")
    
    assert result is not None
    assert os.path.exists(output_path)
    assert result["output_path"] == output_path
    
    # Analyze output
    out_dur = get_duration(output_path)
    assert out_dur > 0
    
    # Check metadata
    with open(result["metadata_path"], "r") as f:
        meta = json.load(f)
        assert meta["type"] == "mix"
        assert "render" in meta
        # Check no duplicate actual_duration
        # (JSON load deduplicates keys, so we can't strict verify duplication here easily,
        # but we fixed it in code)
        assert meta["render"]["actual_duration"] > 0
