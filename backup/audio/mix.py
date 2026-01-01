"""Audio mixing engine for AI DJ Backend v2.

Simplified port from backend/dj_mix.py with no backend dependencies.
Handles loudness normalization, transitions, and TTS integration.
"""
import json
import logging
import os
import re
import uuid
import time
from typing import Optional, Dict, Any

import ffmpeg

from backend_v2.audio import transitions as transition_lib
from backend_v2.audio.media_cache import get_cached_analysis, save_cached_analysis
from backend_v2.audio.transition_params import compile_transition_params, compute_crossfade_duration
from backend_v2.audio.transition_types import resolve_transition_type
from backend_v2.config import (
    SEGMENT_DIR,
    TARGET_LUFS,
    STREAM_SAMPLE_RATE,
    TTS_DUCK_VOLUME,
)

logger = logging.getLogger("ai-dj.audio.mix")

# Audio processing constants
SAMPLE_RATE = STREAM_SAMPLE_RATE  # From config, default 44100

# Unified handoff constants
TRANSITION_BUFFER_SEC = 20.0
CROSSFADE_SEC = 10.0
LEAD_IN_SEC = 12.0
MIN_INCOMING_SEC = TRANSITION_BUFFER_SEC + LEAD_IN_SEC
# Keep segment boundaries sample-accurate; transition overlap happens inside the render.
SEGMENT_OVERLAP_SEC = 0.0


def get_mix_start_in_song(song_duration: float, crossfade_sec: float = CROSSFADE_SEC) -> float:
    """Calculate where mix segment should start in a song.
    
    This is the SINGLE SOURCE OF TRUTH for handoff alignment.
    """
    return max(0, song_duration - TRANSITION_BUFFER_SEC - crossfade_sec - LEAD_IN_SEC)


def get_loudness(file_path: str) -> float:
    """Measure Integrated Loudness (LUFS) of an audio file.
    
    Uses FFmpeg's loudnorm filter to analyze the audio.
    
    Returns:
        Integrated loudness in LUFS (e.g., -10.5)
        Returns TARGET_LUFS as fallback on error
    """
    try:
        start_time = time.time()
        
        # Check cache
        cached = get_cached_analysis(file_path)
        if cached and "lufs" in cached:
            if os.environ.get("AUDIO_MIX_PROFILE"):
                logger.info(f"[PROFILE] get_loudness({os.path.basename(file_path)}): CACHED")
            return cached["lufs"]

        logger.debug(f"Measuring loudness: {file_path}")
        _, err = (
            ffmpeg
            .input(file_path)
            .filter('loudnorm', print_format='json')
            .output('-', format='null')
            .run(capture_stdout=True, capture_stderr=True)
        )
        
        output_str = err.decode('utf-8')
        json_match = re.search(r'\{[\s\S]*\}', output_str)
        if json_match:
            stats = json.loads(json_match.group(0))
            lufs = float(stats['input_i'])
            
            # Save to cache
            save_cached_analysis(file_path, {
                "lufs": lufs,
                "duration": cached.get("duration") if cached else 0.0 # Preserve duration if partial cache
            })
            
            if os.environ.get("AUDIO_MIX_PROFILE"):
                duration = time.time() - start_time
                logger.info(f"[PROFILE] get_loudness({os.path.basename(file_path)}): {duration:.3f}s")
                
            logger.debug(f"Measured: {lufs} LUFS")
            return lufs
    except Exception as e:
        logger.warning(f"Error measuring {file_path}: {e}")
    return TARGET_LUFS


def get_duration(file_path: str) -> float:
    """Get duration of an audio file in seconds."""
    try:
        start_time = time.time()
        
        # Check cache
        cached = get_cached_analysis(file_path)
        if cached and "duration" in cached:
            if os.environ.get("AUDIO_MIX_PROFILE"):
                logger.info(f"[PROFILE] get_duration({os.path.basename(file_path)}): CACHED")
            return cached["duration"]
            
        probe = ffmpeg.probe(file_path)
        duration = float(probe['format']['duration'])
        
        # Save to cache (update lufs if exists)
        cache_data = {"duration": duration}
        if cached and "lufs" in cached:
            cache_data["lufs"] = cached["lufs"]
        save_cached_analysis(file_path, cache_data)
        
        if os.environ.get("AUDIO_MIX_PROFILE"):
            elapsed = time.time() - start_time
            logger.info(f"[PROFILE] get_duration({os.path.basename(file_path)}): {elapsed:.3f}s")
            
        return duration
    except Exception as e:
        logger.error(f"Failed to probe duration: {e}")
        return 210.0  # Default fallback


def normalize_stream(stream, current_lufs: float, target_lufs: float = TARGET_LUFS):
    """Apply static gain to reach target LUFS."""
    gain_db = target_lufs - current_lufs
    logger.debug(f"Applying gain: {gain_db:.2f} dB to reach {target_lufs} LUFS")
    return stream.filter('volume', f"{gain_db}dB")


def create_intro_mix(
    song_path: str,
    tts_path: Optional[str] = None,
    output_path: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Create initial segment (first song with TTS intro).
    
    Normalizes TTS and Song to TARGET_LUFS.
    Applies overlap: Song starts just as TTS is ending.
    
    Args:
        song_path: Path to song file
        tts_path: Path to TTS file
        output_path: Optional output path
        user_id: Optional user ID for segment naming
        
    Returns:
        Dict with output_path, metadata, and metadata_path
    """
    if output_path is None:
        os.makedirs(SEGMENT_DIR, exist_ok=True)
        prefix = user_id[:8] if user_id else ""
        mix_id = uuid.uuid4().hex[:8]
        output_path = os.path.join(SEGMENT_DIR, f"{prefix}intro_{mix_id}.wav")
        
    # Get durations
    song_duration = get_duration(song_path)
    tts_duration = get_duration(tts_path) if tts_path and os.path.exists(tts_path) else 0.0
    
    # Calculate trim using unified handoff
    mix_start_pos = get_mix_start_in_song(song_duration)
    song_trim_end = mix_start_pos + SEGMENT_OVERLAP_SEC
    
    if song_trim_end < 60:
        song_trim_end = max(song_duration - 15.0, 60.0)
        
    logger.info(f"Intro: TTS={tts_duration:.2f}s, Song={song_duration:.2f}s, TrimEnd={song_trim_end:.2f}s")
    
    # Process song
    song_in = ffmpeg.input(song_path).audio
    song_in = song_in.filter('aresample', SAMPLE_RATE)
    
    s1_lufs = get_loudness(song_path)
    song_trimmed = song_in.filter('atrim', start=0, end=song_trim_end)
    song_trimmed = song_trimmed.filter('asetpts', 'PTS-STARTPTS')
    song_norm = normalize_stream(song_trimmed, s1_lufs, TARGET_LUFS)
    
    song_delay_ms = 0
    leading_silence_duration = 0.0
    overlap_duration = 0.0
    
    if tts_path and os.path.exists(tts_path):
        tts_in = ffmpeg.input(tts_path).audio
        tts_lufs = get_loudness(tts_path)
        tts_norm = normalize_stream(tts_in, tts_lufs, TARGET_LUFS)
        
        # Add leading silence before TTS to ensure player is ready (2.5s silence + 0.3s fade-in = safe start)
        # This prevents TTS cutoff even if playback starts immediately
        leading_silence_duration = 2.5
        
        overlap_duration = 1.0
        song_delay_ms = int(max(0, (tts_duration - overlap_duration) * 1000))
        
        song_delayed = song_norm.filter('adelay', f"{song_delay_ms}|{song_delay_ms}")
        # Add fade-in to TTS to prevent cutoff at beginning (0.3s fade-in for smooth start)
        # Add fade-out at end (0.5s fade-out)
        tts_faded = tts_norm.filter('afade', t='in', st=0, d=0.3).filter('afade', t='out', st=tts_duration - 0.5, d=0.5)
        song_faded = song_delayed.filter('afade', t='in', st=0, d=overlap_duration)
        
        # Mix TTS and song normally
        mixed_audio = ffmpeg.filter([tts_faded, song_faded], 'amix', inputs=2, duration='longest', dropout_transition=0)
        
        # Create leading silence stream and concatenate with mixed audio
        # This ensures silence is baked into the file, preventing TTS cutoff
        silence = ffmpeg.input('anullsrc', format='lavfi', r=SAMPLE_RATE, ac=2).filter('atrim', duration=leading_silence_duration)
        # Delay the mixed audio to start after silence
        mixed_delayed = mixed_audio.filter('adelay', f"{int(leading_silence_duration * 1000)}|{int(leading_silence_duration * 1000)}")
        final_audio = ffmpeg.filter([silence, mixed_delayed], 'amix', inputs=2, duration='longest', dropout_transition=0)
    else:
        final_audio = song_norm
        
    # Render
    try:
        final_audio = final_audio.filter('alimiter', limit=0.95)
        out = ffmpeg.output(
            final_audio,
            output_path,
            acodec='pcm_s16le',
            format='wav',
            ar=SAMPLE_RATE,
            ac=2,
            map_metadata=-1
        )
        
        render_start = time.time()
        out.overwrite_output().run(capture_stdout=True, capture_stderr=True)
        if os.environ.get("AUDIO_MIX_PROFILE"):
            logger.info(f"[PROFILE] create_intro_mix render: {time.time() - render_start:.3f}s")
        
        actual_duration = get_duration(output_path)
        tts_delay_sec = song_delay_ms / 1000.0
        segment_handoff_start = tts_delay_sec + mix_start_pos
        
        if segment_handoff_start > actual_duration:
            segment_handoff_start = actual_duration - 0.5
            
        song_delay_sec = song_delay_ms / 1000.0
        song_start_sec = max(0.0, leading_silence_duration + song_delay_sec)
        metadata = {
            "type": "intro",
            "segment_handoff_start": segment_handoff_start,
            "handoff_at": segment_handoff_start,
            "song_a_start_sec": 0.0,
            "song_a_end_sec": song_trim_end,
            "mix_start_in_song": mix_start_pos,
            "song": {"path": song_path, "duration": song_duration},
            "tts": {"path": tts_path, "duration": tts_duration} if tts_path else None,
            "intro": {
                "leading_silence_sec": leading_silence_duration,
                "song_delay_sec": song_delay_sec,
                "song_start_sec": song_start_sec,
                "overlap_sec": overlap_duration,
            },
            "render": {
                "actual_duration": actual_duration,
                "format": "wav",
                "sr_hz": SAMPLE_RATE,
            },
        }
        
        metadata_path = f"{output_path}.json"
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)
            
        logger.info(f"Intro segment saved: {output_path} ({actual_duration:.1f}s)")
        return {
            "output_path": output_path,
            "metadata_path": metadata_path,
            "metadata": metadata
        }
    except ffmpeg.Error as e:
        logger.error(f"Intro render failed: {e.stderr.decode() if e.stderr else str(e)}")
        return None


def create_dj_mix(
    song1_path: str,
    song2_path: str,
    transition_type: str = 'crossfade',
    output_path: Optional[str] = None,
    tts_path: Optional[str] = None,
    song2_start_sec: float = 0.0,
    transition_start_a_sec: Optional[float] = None,  # NEW: LLM-specified start in Song A
    xfade_dur: float = 10.0,
    bpm_a: Optional[float] = None,
    bpm_b: Optional[float] = None,
    adaptive_crossfade: bool = True,
    user_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Create transition segment between two songs.
    
    Contains:
    - Last ~12s of Song A (lead-in for crossfade)
    - The transition (~10s crossfade)
    - Most of Song B (except last ~20s for next transition)
    
    Args:
        song1_path: Path to outgoing song (A)
        song2_path: Path to incoming song (B)
        transition_type: Transition style (crossfade, eq_blend, etc.)
        output_path: Optional output path
        tts_path: Optional TTS audio
        song2_start_sec: Start position in Song B
        transition_start_a_sec: LLM-specified transition start in Song A (NEW)
        xfade_dur: Crossfade duration
        bpm_a: Outgoing song BPM (optional)
        bpm_b: Incoming song BPM (optional)
        user_id: Optional user ID for segment naming
        
    Returns:
        Dict with output_path, metadata, metadata_path
    """
    if output_path is None:
        os.makedirs(SEGMENT_DIR, exist_ok=True)
        prefix = user_id[:8] + "_" if user_id else ""
        mix_id = uuid.uuid4().hex[:8]
        output_path = os.path.join(SEGMENT_DIR, f"{prefix}mix_{mix_id}.wav")
        
    # Get durations
    song1_duration = get_duration(song1_path)
    song2_full_duration = get_duration(song2_path)
    if song2_full_duration <= 0:
        logger.warning("Incoming song duration unavailable; defaulting to 0")
        song2_full_duration = 0.0

    if song2_start_sec:
        max_start = max(0.0, song2_full_duration - MIN_INCOMING_SEC)
        song2_start_sec = max(0.0, min(song2_start_sec, max_start))
    else:
        song2_start_sec = 0.0

    song2_duration = max(0.0, song2_full_duration - song2_start_sec)
    tts_duration = get_duration(tts_path) if tts_path and os.path.exists(tts_path) else 0.0
    
    # Calculate positions
    effective_bpm_a = bpm_a if bpm_a and bpm_a > 0 else 120.0
    effective_bpm_b = bpm_b if bpm_b and bpm_b > 0 else 120.0
    raw_type, resolved_type = resolve_transition_type(transition_type)
    crossfade_duration = xfade_dur
    if adaptive_crossfade:
        crossfade_duration = compute_crossfade_duration(
            effective_bpm_a,
            effective_bpm_b,
            crossfade_duration,
        )

    if resolved_type == "quick_cut":
        min_dur, max_dur = 1.0, 2.0
    elif resolved_type == "vinyl_stop":
        min_dur, max_dur = 2.0, 6.0
    else:
        min_dur, max_dur = 3.0, 24.0

    crossfade_duration = max(min_dur, min(crossfade_duration, max_dur))
    
    # NEW: Use LLM-specified transition start if provided, with validation
    if transition_start_a_sec is not None:
        # LLM wants transition to start at this position in Song A
        transition_start = transition_start_a_sec
        logger.info(f"Using LLM-specified transition start: {transition_start:.1f}s")
        
        # Validate it's safe
        min_start = 20.0  # Don't start transition too early
        max_start = song1_duration - crossfade_duration - 5.0  # Leave tail for crossfade + buffer
        
        if transition_start < min_start:
            logger.warning(
                f"Transition start {transition_start:.1f}s too early, clamping to {min_start:.1f}s"
            )
            transition_start = min_start
        elif transition_start > max_start:
            logger.warning(
                f"Transition start {transition_start:.1f}s too late, clamping to {max_start:.1f}s"
            )
            transition_start = max_start
        
        timing_source = "llm"
    else:
        # Fallback: compute transition start position
        transition_start = song1_duration - TRANSITION_BUFFER_SEC - crossfade_duration
        timing_source = "computed"
    
    
    if transition_start < 20:
        transition_start = 20
        
    # Where to start reading Song A
    song1_start = get_mix_start_in_song(song1_duration, crossfade_duration)
    song1_end = song1_duration
    song1_segment_duration = song1_end - song1_start
    segment_transition_pos = transition_start - song1_start
    
    # How much of Song B to include
    song2_next_transition = song2_duration - TRANSITION_BUFFER_SEC - crossfade_duration
    song2_handoff = max(0.0, song2_next_transition - LEAD_IN_SEC)
    song2_trim = min(song2_handoff + SEGMENT_OVERLAP_SEC, song2_duration)
    
    if song2_trim < 60:
        song2_trim = song2_duration
        
    logger.info(f"Mix: Song A {song1_segment_duration:.1f}s, Song B {song2_trim:.1f}s, transition at {segment_transition_pos:.1f}s")
    
    # Get loudness
    s1_lufs = get_loudness(song1_path)
    s2_lufs = get_loudness(song2_path)
    
    # Check if same song
    same_song = os.path.normpath(song1_path) == os.path.normpath(song2_path)
    
    if same_song:
        logger.warning(f"Same song for both A and B: {song1_path}. Using asplit.")
        # When same file, we must use asplit to fork the stream.
        # Use filter_multi_output to get a FilterNode with 2 outputs.
        in_stream = ffmpeg.input(song1_path).audio
        split = in_stream.filter_multi_output('asplit', 2)
        audio1 = split[0]
        audio2 = split[1]
        
        # No seek optimization for same-song split
        s1_trim_start = song1_start
        s1_trim_end = song1_end
        s2_trim_start = song2_start_sec
        s2_trim_end = song2_start_sec + song2_trim
    else:
        use_seek = os.environ.get("AUDIO_MIX_USE_INPUT_SEEK", "1") == "1"
        
        # Song A
        if use_seek and song1_start > 1.0:
            s1_seek = song1_start - 1.0
            audio1 = ffmpeg.input(song1_path, ss=s1_seek).audio
            s1_trim_start = 1.0
            s1_trim_end = song1_end - s1_seek
        else:
            audio1 = ffmpeg.input(song1_path).audio
            s1_trim_start = song1_start
            s1_trim_end = song1_end
            
        # Song B
        if use_seek and song2_start_sec > 1.0:
            s2_seek = song2_start_sec - 1.0
            audio2 = ffmpeg.input(song2_path, ss=s2_seek).audio
            s2_trim_start = 1.0
            s2_trim_end = (song2_start_sec + song2_trim) - s2_seek
        else:
            audio2 = ffmpeg.input(song2_path).audio
            s2_trim_start = song2_start_sec
            s2_trim_end = song2_start_sec + song2_trim
    
    # Process Song A
    # Note: We must apply filters sequentially to avoid graph issues
    a1 = audio1.filter('aresample', SAMPLE_RATE)
    a1 = a1.filter('atrim', start=s1_trim_start, end=s1_trim_end)
    a1 = a1.filter('asetpts', 'PTS-STARTPTS')
    a1 = normalize_stream(a1, s1_lufs, TARGET_LUFS)
    
    # Process Song B
    a2 = audio2.filter('aresample', SAMPLE_RATE)
    a2 = a2.filter('atrim', start=s2_trim_start, end=s2_trim_end)
    a2 = a2.filter('asetpts', 'PTS-STARTPTS')
    a2 = normalize_stream(a2, s2_lufs, TARGET_LUFS)
    
    # Apply crossfade
    transition_func, implementation_name, is_fallback = transition_lib.get_transition_function(resolved_type)
    disabled_reason = None

    if resolved_type == "echo_out":
        # Echo out enabled in Phase 1
        pass

    trans_params = compile_transition_params(
        transition_type=resolved_type,
        bpm_a=effective_bpm_a,
        bpm_b=effective_bpm_b,
        peak_time=segment_transition_pos,
        base_duration=crossfade_duration,
        duration_override=crossfade_duration,
    )

    adaptive_crossfade = trans_params.get("crossfade_duration", crossfade_duration)

    transition_start_sec = max(segment_transition_pos - (adaptive_crossfade / 2), 0.0)
    transition_peak_sec = max(segment_transition_pos, 0.0)
    transition_end_sec = transition_peak_sec + (adaptive_crossfade / 2)

    delay_seconds = transition_start_sec
    delay_ms = int(round(delay_seconds * 1000))
    transition_peak_ms = int(round(transition_peak_sec * 1000))
    transition_end_ms = int(round(transition_end_sec * 1000))
    a2_delayed = a2.filter("adelay", f"{delay_ms}|{delay_ms}")

    transition_kwargs = {
        "outgoing_lpf_cutoffs": trans_params.get("outgoing_lpf_cutoffs"),
        "incoming_hpf_cutoffs": trans_params.get("incoming_hpf_cutoffs"),
        "echo_delay_ms": trans_params.get("echo_delay_ms"),
        "echo_delays_str": trans_params.get("echo_delays_str"),
        "echo_decays_str": trans_params.get("echo_decays_str"),
    }
    transition_kwargs = {k: v for k, v in transition_kwargs.items() if v is not None}

    if resolved_type == "vinyl_stop":
        mixed_music = transition_func(
            a1,
            a2_delayed,
            segment_transition_pos,
            2.0,
            **transition_kwargs,
        )
    else:
        mixed_music = transition_func(
            a1,
            a2_delayed,
            adaptive_crossfade,
            segment_transition_pos,
            **transition_kwargs,
        )

    fallback_reason = None
    if is_fallback:
        if disabled_reason:
            fallback_reason = disabled_reason
        else:
            fallback_reason = f"Unknown type '{raw_type}' fell back to crossfade"
        logger.warning("Transition fallback: %s -> %s -> %s", raw_type, resolved_type, implementation_name)
    else:
        logger.info("Transition: %s -> %s -> %s", raw_type, resolved_type, implementation_name)
    
    # Handle TTS with ducking
    if tts_path and os.path.exists(tts_path):
        tts_in = ffmpeg.input(tts_path).audio
        tts_lufs = get_loudness(tts_path)
        tts = normalize_stream(tts_in.filter('aresample', SAMPLE_RATE), tts_lufs, TARGET_LUFS)
        
        tts_start = max(0, segment_transition_pos - 5.0)
        tts_end = tts_start + tts_duration
        delay_ms_tts = int(tts_start * 1000)
        tts_delayed = tts.filter('adelay', f"{delay_ms_tts}|{delay_ms_tts}")
        
        # Duck music during TTS
        ducked = mixed_music.filter(
            'volume',
            enable=f'between(t,{tts_start},{tts_end})',
            volume=TTS_DUCK_VOLUME
        )
        
        final_audio = (
            ffmpeg
            .filter([ducked, tts_delayed], 'amix', inputs=2, duration='longest', normalize=0)
            .filter('alimiter', limit=0.95)
        )
    else:
        final_audio = mixed_music.filter('alimiter', limit=0.95)
        
    # Render
    try:
        logger.info(f"Rendering mix segment: {output_path}")
        out = ffmpeg.output(
            final_audio,
            output_path,
            acodec='pcm_s16le',
            format='wav',
            ar=SAMPLE_RATE,
            ac=2,
            map_metadata=-1
        )
        
        render_start = time.time()
        out.overwrite_output().run(capture_stdout=True, capture_stderr=True)
        if os.environ.get("AUDIO_MIX_PROFILE"):
            logger.info(f"[PROFILE] create_dj_mix render: {time.time() - render_start:.3f}s")
        
        actual_duration = get_duration(output_path)
        
        metadata = {
            "type": "mix",
            "segment_handoff_start": delay_seconds + song2_handoff,
            "handoff_at": delay_seconds + song2_handoff,
            "song1": {
                "start": song1_start,
                "end": song1_end,
                "transition_start": transition_start,
                "transition_start_source": timing_source,  # NEW: Track if LLM or computed
            },
            "song2": {
                "start": song2_start_sec,
                "end": song2_start_sec + song2_trim,
                "handoff_start": song2_handoff,
            },
            "transition": {
                "type": resolved_type,
                "type_raw": raw_type,
                "implementation": implementation_name,
                "fallback_reason": fallback_reason,
                "duration": adaptive_crossfade,
                "duration_base": crossfade_duration,
                "delay_ms": delay_ms,
                "start_ms": delay_ms,
                "peak_ms": transition_peak_ms,
                "end_ms": transition_end_ms,
            },
            "transition_debug": {
                "bpm_a": effective_bpm_a,
                "bpm_b": effective_bpm_b,
                "bpm_gap": trans_params.get("bpm_gap"),
                "computed_crossfade_sec": adaptive_crossfade,
                "echo_delay_ms": trans_params.get("echo_delay_ms"),
                "echo_beat_fraction": trans_params.get("echo_beat_fraction"),
                "echo_taps": trans_params.get("echo_taps"),
                "eq_blend_cutoffs": {
                    "a_lpf": trans_params.get("outgoing_lpf_cutoffs"),
                    "b_hpf": trans_params.get("incoming_hpf_cutoffs"),
                } if trans_params.get("outgoing_lpf_cutoffs") else None,
            },
            "render": {
                "actual_duration": actual_duration,
                "actual_duration": actual_duration,
                "format": "wav",
                "sr_hz": SAMPLE_RATE,
            },
        }
        
        metadata_path = f"{output_path}.json"
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)
            
        logger.info(f"Mix segment saved: {output_path} ({actual_duration:.1f}s)")
        return {
            "output_path": output_path,
            "metadata_path": metadata_path,
            "metadata": metadata
        }
    except ffmpeg.Error as e:
        logger.error(f"Mix render failed: {e.stderr.decode() if e.stderr else str(e)}")
        return None
