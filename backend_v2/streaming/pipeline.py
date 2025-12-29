"""Per-user Radio Pipeline for AI DJ streaming.

Each authenticated user gets their own isolated RadioPipeline instance,
enabling personalized streams with per-user segment queues.

Features:
- Per-user FFmpeg encoder instance
- Dummy audio generator for testing (swapped for real segments in Batch 2)
- Idle cleanup after configurable timeout
- Session caps enforcement
"""
import asyncio
import logging
import math
import os
import struct
import subprocess
import sys
import time
import traceback
import wave
from datetime import datetime
from typing import Dict, Optional, Any

from backend_v2.config import (
    STREAM_MP3_BITRATE,
    STREAM_SAMPLE_RATE,
    STREAM_CHANNELS,
    STREAM_CLIENT_QUEUE_SIZE,
    MAX_SESSIONS_TOTAL,
)

logger = logging.getLogger("ai-dj.streaming")

PCM_BYTES_PER_SAMPLE = 2
PCM_CHUNK_SIZE = 16384
PCM_MAX_LEAD_SEC = 0.5


class UserRadioPipeline:
    """Per-user radio pipeline with isolated segment queue and encoder.
    
    Architecture:
    1. Segment queue receives audio segments (or dummy audio for testing)
    2. PCM feeder decodes segments and writes to encoder stdin
    3. FFmpeg encoder outputs MP3 continuously
    4. Output queue provides MP3 chunks for HTTP streaming
    """
    
    def __init__(self, user_id: str, session_id: str):
        self.user_id = user_id
        self.session_id = session_id
        self.created_at = datetime.utcnow()
        self.last_activity = datetime.utcnow()
        
        # Queues
        self.segment_queue: asyncio.Queue = asyncio.Queue(maxsize=5)
        self._stream_subscribers: set[asyncio.Queue] = set()
        
        # State
        self.encoder_process: Optional[subprocess.Popen] = None
        self.is_running = False
        self._shutdown = False
        self._skip_requested = False  # Interrupt current segment feeding
        self.now_playing: Optional[str] = None
        
        # Tasks
        self._feeder_task: Optional[asyncio.Task] = None
        self._fanout_task: Optional[asyncio.Task] = None
        self._dummy_task: Optional[asyncio.Task] = None
        
        # Locks
        self._encoder_lock = asyncio.Lock()
        self._stream_lock = asyncio.Lock()
        
        # PCM pacing (byte-accurate)
        self._pcm_start_time: Optional[float] = None
        self._pcm_bytes_written = 0
        self._pcm_bytes_per_second = STREAM_SAMPLE_RATE * STREAM_CHANNELS * PCM_BYTES_PER_SAMPLE
        
    async def start(self, use_dummy_audio: bool = True):
        """Start the pipeline.
        
        Args:
            use_dummy_audio: If True, generate test tone instead of waiting for segments
        """
        if self.is_running:
            logger.warning(f"Pipeline for user {self.user_id} already running")
            return
            
        self.is_running = True
        self._shutdown = False
        self._reset_pcm_clock()
        
        logger.info(f"🎵 Starting pipeline for user {self.user_id}")
        
        # Spawn encoder
        await self._spawn_encoder()
        
        # Start tasks
        self._feeder_task = asyncio.create_task(self._segment_feeder())
        self._fanout_task = asyncio.create_task(self._fanout())
        
        if use_dummy_audio:
            self._dummy_task = asyncio.create_task(self._dummy_audio_generator())
            
        logger.info(f"🎵 Pipeline started for user {self.user_id}")
        
    async def stop(self):
        """Stop the pipeline and clean up."""
        logger.info(f"🎵 Stopping pipeline for user {self.user_id}")
        self._shutdown = True
        self.is_running = False
        
        # Cancel tasks
        for task in [self._feeder_task, self._fanout_task, self._dummy_task]:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                    
        # Terminate encoder
        if self.encoder_process:
            try:
                self.encoder_process.terminate()
                self.encoder_process.wait(timeout=5.0)
            except:
                try:
                    self.encoder_process.kill()
                except (ProcessLookupError, OSError):
                    pass
                    
        # Signal end to any waiting consumers
        await self._close_stream_subscribers()
        
        self._reset_pcm_clock()
            
        logger.info(f"🎵 Pipeline stopped for user {self.user_id}")
        
    def touch(self):
        """Update last activity timestamp."""
        self.last_activity = datetime.utcnow()

    async def skip_current(self):
        """Skip the current segment and advance to the next one.
        
        Sets a skip flag to interrupt current segment feeding.
        The feeder will then immediately move to the next queued segment
        (which is already prepared), avoiding regeneration delay.
        """
        logger.info(f"🎵 Skip requested for user {self.user_id}")
        
        # Set skip flag - the feeding loop will check this and exit early
        self._skip_requested = True
        
        # Reset PCM clock to allow immediate playback of next segment
        self._reset_pcm_clock()
        
        # Emit skip event via WebSocket
        from backend_v2.orchestration.events import get_event_emitter
        emitter = get_event_emitter()
        await emitter.emit_stream_status(
            user_id=self.user_id,
            status="skipping"
        )

    async def _register_stream(self) -> asyncio.Queue:
        """Register a streaming subscriber queue."""
        queue: asyncio.Queue = asyncio.Queue(maxsize=STREAM_CLIENT_QUEUE_SIZE)
        async with self._stream_lock:
            self._stream_subscribers.add(queue)
        return queue

    async def _unregister_stream(self, queue: asyncio.Queue) -> None:
        """Unregister a streaming subscriber queue."""
        async with self._stream_lock:
            self._stream_subscribers.discard(queue)

    async def _close_stream_subscribers(self) -> None:
        """Close all active stream subscribers."""
        async with self._stream_lock:
            subscribers = list(self._stream_subscribers)
            self._stream_subscribers.clear()

        for queue in subscribers:
            try:
                queue.put_nowait(None)
            except asyncio.QueueFull:
                try:
                    while True:
                        queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                try:
                    queue.put_nowait(None)
                except asyncio.QueueFull:
                    pass
        
    async def _spawn_encoder(self):
        """Start FFmpeg encoder: stdin=PCM, stdout=MP3."""
        async with self._encoder_lock:
            if self.encoder_process and self.encoder_process.poll() is None:
                return
                
            cmd = [
                "ffmpeg",
                "-hide_banner",
                "-loglevel", "error",
                "-fflags", "+nobuffer",
                "-flags", "low_delay",
                "-max_delay", "0",
                "-f", "s16le",
                "-ar", str(STREAM_SAMPLE_RATE),
                "-ac", str(STREAM_CHANNELS),
                "-i", "pipe:0",
                "-c:a", "libmp3lame",
                "-b:a", STREAM_MP3_BITRATE,
                "-ar", str(STREAM_SAMPLE_RATE),
                "-ac", str(STREAM_CHANNELS),
                "-flush_packets", "1",
                "-write_xing", "0",
                "-id3v2_version", "0",
                "-f", "mp3",
                "pipe:1"
            ]
            
            creationflags = 0
            if sys.platform == 'win32':
                creationflags = subprocess.CREATE_NO_WINDOW
                
            self.encoder_process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=creationflags
            )
            
            logger.debug(f"Encoder spawned with PID: {self.encoder_process.pid}")
            
    async def _dummy_audio_generator(self):
        """Generate a test tone for stream verification.
        
        Produces a 440Hz sine wave as PCM and queues it for encoding.
        This allows testing the full stream lifecycle without real audio segments.
        """
        logger.info(f"🔊 Starting dummy audio generator for user {self.user_id}")
        
        frequency = 440.0  # A4 note
        sample_rate = STREAM_SAMPLE_RATE
        channels = STREAM_CHANNELS
        amplitude = 8000  # Low volume to avoid ear damage
        
        # Generate 1 second of audio at a time
        samples_per_chunk = sample_rate
        
        t = 0
        while not self._shutdown:
            try:
                # Generate sine wave samples
                pcm_data = bytearray()
                for i in range(samples_per_chunk):
                    sample_t = (t + i) / sample_rate
                    value = int(amplitude * math.sin(2 * math.pi * frequency * sample_t))
                    # Stereo: duplicate sample for both channels
                    for _ in range(channels):
                        pcm_data.extend(struct.pack('<h', value))
                        
                t += samples_per_chunk
                
                # Write directly to encoder
                if self.encoder_process and self.encoder_process.stdin:
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(
                        None,
                        lambda: self.encoder_process.stdin.write(bytes(pcm_data))
                    )
                    await loop.run_in_executor(
                        None,
                        self.encoder_process.stdin.flush
                    )
                    
                # Pace in real-time
                await asyncio.sleep(0.9)  # Slightly less than 1s to prevent gaps
                
            except (BrokenPipeError, OSError) as e:
                logger.warning(f"Encoder pipe error: {e}")
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                break
                
        logger.info(f"🔊 Dummy audio generator stopped for user {self.user_id}")
        


    def _reset_pcm_clock(self):
        """Reset PCM pacing state."""
        self._pcm_start_time = None
        self._pcm_bytes_written = 0

    async def _pace_pcm(self):
        """Keep PCM writes near realtime with a small lead buffer."""
        if self._pcm_start_time is None:
            return
        
        elapsed = time.perf_counter() - self._pcm_start_time
        expected = self._pcm_bytes_written / self._pcm_bytes_per_second
        lead = expected - elapsed
        if lead > PCM_MAX_LEAD_SEC:
            await asyncio.sleep(lead - PCM_MAX_LEAD_SEC)

    async def _write_pcm(self, data: bytes):
        """Write PCM bytes to the encoder with byte-based pacing."""
        if not data:
            return
        
        if not self.encoder_process or self.encoder_process.poll() is not None:
            await self._spawn_encoder()
        if not self.encoder_process or not self.encoder_process.stdin:
            return
        
        if self._pcm_start_time is None:
            self._pcm_start_time = time.perf_counter()
            self._pcm_bytes_written = 0
        
        loop = asyncio.get_event_loop()
        
        def write_and_flush():
            self.encoder_process.stdin.write(data)
            self.encoder_process.stdin.flush()
        
        await loop.run_in_executor(None, write_and_flush)
        self._pcm_bytes_written += len(data)
        await self._pace_pcm()

    async def _feed_silence(self, duration: float = 2.0):
        """Feed silence to encoder to prime the stream."""
        if duration > 0.5:
            logger.info(f"Adding {duration}s of silence to prime stream")
        sample_rate = STREAM_SAMPLE_RATE
        channels = STREAM_CHANNELS
        
        # Calculate bytes: rate * duration * channels * 2 bytes/sample (16-bit)
        num_samples = int(sample_rate * duration)
        pcm_size = num_samples * channels * 2
        
        # Create zero-filled buffer
        silence = bytes(pcm_size)

        try:
            offset = 0
            while offset < pcm_size and not self._shutdown:
                chunk = silence[offset:offset + PCM_CHUNK_SIZE]
                if not chunk:
                    break
                await self._write_pcm(chunk)
                offset += len(chunk)
        except Exception as e:
            logger.error(f"Failed to feed silence: {e}")
        
    async def _segment_feeder(self):
        """Feed segments from queue to encoder by decoding to PCM.
        
        Decodes segments to PCM (WAV fast path, FFmpeg fallback) and writes to encoder stdin.
        This enables playing real audio segments instead of dummy sine waves.
        Also emits now_playing events when segments START playback.
        """
        from backend_v2.orchestration.events import get_event_emitter
        from backend_v2.schemas.status_events import StatusCategory, StatusStep
        
        logger.debug(f"Segment feeder task started for user {self.user_id}")
        emitter = get_event_emitter()
        
        # Dynamic startup buffer: Wait for first segment with bounded silence
        # This prevents client timeouts while avoiding unbounded silence backlog
        # Two modes:
        # - "defer": Don't emit audio until first real segment (preferred)
        # - "bounded": Emit bounded silence to keep connection alive
        from backend_v2.config import (
            STREAM_STARTUP_MODE,
            MAX_SILENCE_AHEAD_SEC,
            STREAM_STARTUP_TIMEOUT_SEC,
        )
        
        has_started = False
        buffering_emitted = False
        startup_wall_start = time.perf_counter()
        silence_fed_sec = 0.0
        
        logger.info(f"🎧 Starting segment feeder in '{STREAM_STARTUP_MODE}' mode for user {self.user_id}")
        
        while not has_started and not self._shutdown:
            try:
                # Check if we have a segment ready
                segment_data = self.segment_queue.get_nowait()
                has_started = True
                elapsed = time.perf_counter() - startup_wall_start
                logger.info(f"🎧 First segment ready after {elapsed:.1f}s (silence fed: {silence_fed_sec:.1f}s)")
            except asyncio.QueueEmpty:
                # Emit buffering status (only once)
                if not buffering_emitted:
                    await emitter.emit_status(
                        user_id=self.user_id,
                        category=StatusCategory.PLAYBACK,
                        step=StatusStep.BUFFERING,
                        user_message="Preparing your music...",
                        session_id=self.session_id,
                    )
                    buffering_emitted = True
                
                elapsed = time.perf_counter() - startup_wall_start
                
                # Check startup timeout
                if elapsed > STREAM_STARTUP_TIMEOUT_SEC:
                    logger.warning(f"Startup timeout ({STREAM_STARTUP_TIMEOUT_SEC}s) reached for user {self.user_id}")
                    # Continue waiting but log the issue
                
                if STREAM_STARTUP_MODE == "defer":
                    # MODE A: Don't emit silence at all, just wait
                    # The HTTP connection stays open; frontend sees status events
                    await asyncio.sleep(0.5)
                else:
                    # MODE B: Bounded silence keepalive
                    # Only emit silence if we're under the max lead threshold
                    silence_lead = silence_fed_sec - elapsed
                    
                    if silence_lead < MAX_SILENCE_AHEAD_SEC:
                        # Calculate how much silence we can add without exceeding the cap
                        max_chunk = MAX_SILENCE_AHEAD_SEC - silence_lead
                        chunk_sec = min(0.5, max_chunk + 0.1)  # Small chunks for responsiveness
                        
                        if chunk_sec > 0.1:
                            try:
                                await self._feed_silence(chunk_sec)
                                silence_fed_sec += chunk_sec
                                if silence_fed_sec % 5 < chunk_sec:  # Log every ~5 seconds
                                    logger.debug(
                                        f"Bounded silence: {silence_fed_sec:.1f}s fed, "
                                        f"{elapsed:.1f}s elapsed, lead {silence_lead:.1f}s"
                                    )
                            except Exception as e:
                                logger.error(f"Error feeding startup silence: {e}")
                    
                    # Wait before checking again (short interval for responsiveness)
                    await asyncio.sleep(0.25)
        
        # We have the first segment (or shutdown)
        if self._shutdown:
            return

        # Process the first segment immediately
        # (The loop below will handle subsequent segments)
        
        while not self._shutdown:
            # We already have segment_data from the first iteration
            # For subsequent iterations, we fetch from queue
            if has_started and segment_data:
                # Process current segment_data
                pass 
            else:
                # Wait for next segment
                try:
                    segment_data = await asyncio.wait_for(
                        self.segment_queue.get(),
                        timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue
                except asyncio.CancelledError:
                    break
            
            # Reset flag after first pass so we fetch next time
            has_started = False 
                
            if segment_data is None:
                continue
            
            # Support both old string path and new metadata dict format
            if isinstance(segment_data, str):
                segment_path = segment_data
                song_meta = None
            else:
                segment_path = segment_data.get("path")
                song_meta = segment_data
                
            if not segment_path:
                continue
                
            # Emit now_playing when segment STARTS (not when queued)
            if song_meta:
                await emitter.emit_now_playing(
                    user_id=self.user_id,
                    song_uuid=song_meta.get("song_uuid", ""),
                    title=song_meta.get("title", "Unknown"),
                    artist=song_meta.get("artist", "Unknown"),
                    artwork_url=song_meta.get("artwork_url"),
                )
                logger.info(f"🎵 Now playing: {song_meta.get('artist')} - {song_meta.get('title')}")
                
            # Clear skip flag before feeding new segment
            self._skip_requested = False
            
            # Decode segment to PCM and feed to encoder
            logger.info(f"🎵 Feeding segment: {segment_path}")
            
            try:
                await self._decode_and_feed_segment(segment_path)
            except Exception as e:
                logger.error(f"Failed to decode segment {segment_path}: {e}")
                traceback.print_exc()
            
        logger.debug(f"Segment feeder task stopped for user {self.user_id}")
        
    async def _decode_and_feed_segment(self, segment_path: str):
        """Decode an audio segment to PCM and feed to encoder.
        
        WAV segments are streamed as raw PCM for sample-accurate stitching.
        Other formats fall back to FFmpeg decoding.
        """
        if not os.path.exists(segment_path):
            logger.error(f"Segment file not found: {segment_path}")
            return
        
        start_time = time.time()
        bytes_written = 0
        
        try:
            if segment_path.lower().endswith(".wav"):
                bytes_written = await self._feed_wav_segment(segment_path)
            else:
                bytes_written = await self._feed_ffmpeg_segment(segment_path)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Error feeding segment: {e}")
        finally:
            duration = time.time() - start_time
            logger.info(f"Fed segment {os.path.basename(segment_path)}: {duration:.2f}s (bytes={bytes_written})")
            
        logger.debug(f"Segment fed: {bytes_written / 1024:.1f} KB")

    async def _feed_wav_segment(self, segment_path: str) -> int:
        """Stream PCM from a WAV file without re-decoding."""
        bytes_written = 0
        
        try:
            with wave.open(segment_path, "rb") as wav_reader:
                sampwidth = wav_reader.getsampwidth()
                channels = wav_reader.getnchannels()
                sample_rate = wav_reader.getframerate()
                
                if sampwidth != PCM_BYTES_PER_SAMPLE or channels != STREAM_CHANNELS or sample_rate != STREAM_SAMPLE_RATE:
                    logger.info(
                        "WAV format mismatch (sr=%s ch=%s sw=%s). Falling back to ffmpeg.",
                        sample_rate,
                        channels,
                        sampwidth,
                    )
                    return await self._feed_ffmpeg_segment(segment_path)
                
                frames_per_chunk = PCM_CHUNK_SIZE // (channels * sampwidth)
                
                while not self._shutdown and not self._skip_requested:
                    data = wav_reader.readframes(frames_per_chunk)
                    if not data:
                        break
                    await self._write_pcm(data)
                    bytes_written += len(data)
        except (wave.Error, EOFError) as e:
            logger.warning(f"WAV read failed ({e}), falling back to ffmpeg")
            return await self._feed_ffmpeg_segment(segment_path)
        
        return bytes_written

    async def _feed_ffmpeg_segment(self, segment_path: str) -> int:
        """Decode an audio segment to PCM via FFmpeg."""
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "error",
            "-i", segment_path,
            "-f", "s16le",
            "-ar", str(STREAM_SAMPLE_RATE),
            "-ac", str(STREAM_CHANNELS),
            "pipe:1"
        ]
        
        creationflags = 0
        if sys.platform == 'win32':
            creationflags = subprocess.CREATE_NO_WINDOW
            
        decoder = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=creationflags
        )
        
        loop = asyncio.get_event_loop()
        bytes_written = 0
        
        def read_chunk():
            if decoder.stdout:
                return decoder.stdout.read(PCM_CHUNK_SIZE)
            return b""
        
        try:
            while not self._shutdown:
                chunk = await loop.run_in_executor(None, read_chunk)
                if not chunk:
                    break
                await self._write_pcm(chunk)
                bytes_written += len(chunk)
        except asyncio.CancelledError:
            decoder.kill()
            raise
        except Exception as e:
            logger.error(f"Error decoding segment: {e}")
        finally:
            try:
                decoder.kill()
            except Exception:
                pass
            await loop.run_in_executor(None, decoder.wait)
        
        return bytes_written
        
    async def _fanout(self):
        logger.debug(f"Fanout task started for user {self.user_id}")
        
        chunk_size = 4096
        loop = asyncio.get_event_loop()
        
        def read_chunk():
            if self.encoder_process and self.encoder_process.stdout:
                return self.encoder_process.stdout.read(chunk_size)
            return b""
            
        while not self._shutdown:
            try:
                if not self.encoder_process or not self.encoder_process.stdout:
                    await asyncio.sleep(0.5)
                    continue

                chunk = await loop.run_in_executor(None, read_chunk)
                if not chunk:
                    await asyncio.sleep(0.1)
                    continue
                    
                # Fan out to all active subscribers without blocking
                async with self._stream_lock:
                    subscribers = list(self._stream_subscribers)

                if not subscribers:
                    continue

                stale = []
                for queue in subscribers:
                    try:
                        queue.put_nowait(chunk)
                    except asyncio.QueueFull:
                        stale.append(queue)

                if stale:
                    async with self._stream_lock:
                        for queue in stale:
                            self._stream_subscribers.discard(queue)
                    for queue in stale:
                        try:
                            queue.put_nowait(None)
                        except asyncio.QueueFull:
                            try:
                                while True:
                                    queue.get_nowait()
                            except asyncio.QueueEmpty:
                                pass
                            try:
                                queue.put_nowait(None)
                            except asyncio.QueueFull:
                                pass
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Fanout error for user {self.user_id}: {e}")
                await asyncio.sleep(1)
                
        logger.debug(f"Fanout task stopped for user {self.user_id}")
        
    async def stream_audio(self):
        """Async generator yielding MP3 chunks for HTTP streaming."""
        logger.info(f"📻 Stream started for user {self.user_id}")
        self.touch()
        queue = await self._register_stream()
        
        try:
            while self.is_running:
                try:
                    chunk = await asyncio.wait_for(
                        queue.get(),
                        timeout=30.0
                    )
                    if chunk is None:
                        break
                    self.touch()
                    yield chunk
                except asyncio.TimeoutError:
                    # Keep connection alive
                    continue
        finally:
            await self._unregister_stream(queue)
            logger.info(f"📻 Stream ended for user {self.user_id}")
            
    def get_state(self) -> Dict[str, Any]:
        """Get pipeline state for debugging."""
        state = {
            "user_id": self.user_id,
            "session_id": self.session_id,
            "is_running": self.is_running,
            "now_playing": self.now_playing,
            "encoder_pid": self.encoder_process.pid if self.encoder_process else None,
            "output_queue_size": 0,
            "stream_subscribers": 0,
            "segment_queue_size": self.segment_queue.qsize(),
            "created_at": self.created_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
        }
        
        # Include DJLoop state if available
        if hasattr(self, '_dj_loop') and self._dj_loop:
            state["loop_state"] = self._dj_loop.get_state()
        
        if self._stream_subscribers:
            state["output_queue_size"] = max(queue.qsize() for queue in self._stream_subscribers)
            state["stream_subscribers"] = len(self._stream_subscribers)

        return state


# Global pipeline manager
_user_pipelines: Dict[str, UserRadioPipeline] = {}
_pipelines_lock = asyncio.Lock()


async def get_user_pipeline(
    user_id: str,
    session_id: str,
    create_if_missing: bool = True,
    mood_id: str = None,
    context_name: str = None,
) -> Optional[UserRadioPipeline]:
    """Get or create a pipeline for a user.
    
    Args:
        user_id: The user's ID
        session_id: The session ID
        create_if_missing: If True, create a new pipeline if none exists
        mood_id: Optional mood ID for personalization
        context_name: Optional context name for personalization
        
    Returns:
        UserRadioPipeline instance or None
        
    Raises:
        ValueError: If session limit exceeded
    """
    async with _pipelines_lock:
        existing = _user_pipelines.get(user_id)
        
        if existing and existing.is_running:
            existing.touch()
            return existing
            
        if not create_if_missing:
            return None
            
        # Clean up old pipeline if exists
        if existing:
            await existing.stop()
            del _user_pipelines[user_id]
            
        # Check global limit
        if len(_user_pipelines) >= MAX_SESSIONS_TOTAL:
            raise ValueError(f"Global session limit reached ({MAX_SESSIONS_TOTAL})")
            
        # Create new pipeline
        pipeline = UserRadioPipeline(user_id, session_id)
        
        # Try to start with DJLoop (Batch 3 integration)
        try:
            from backend_v2.orchestration.loop import DJLoop
            
            # Create DJLoop with the pipeline's segment queue
            dj_loop = DJLoop(
                user_id=user_id,
                session_id=session_id,
                mood_id=mood_id,
                context_name=context_name,
                segment_queue=pipeline.segment_queue,
            )
            
            # Store reference on pipeline for status reporting
            pipeline._dj_loop = dj_loop
            
            # Start pipeline WITHOUT dummy audio (DJLoop will provide segments)
            await pipeline.start(use_dummy_audio=False)
            
            # Start DJLoop
            await dj_loop.start()
            
            logger.info(f"Pipeline with DJLoop started for user {user_id}")
            
        except Exception as e:
            logger.warning(f"DJLoop failed, using dummy audio: {e}")
            import traceback
            traceback.print_exc()
            # Fallback to dummy audio
            await pipeline.start(use_dummy_audio=True)
        
        _user_pipelines[user_id] = pipeline
        logger.info(f"Created pipeline for user {user_id}. Total: {len(_user_pipelines)}")
        
        return pipeline




async def stop_user_pipeline(user_id: str) -> bool:
    """Stop and remove a user's pipeline.
    
    Returns:
        True if pipeline was stopped, False if not found
    """
    # Cancel any pending shutdown timers
    if user_id in _shutdown_timers:
        _shutdown_timers[user_id].cancel()
        del _shutdown_timers[user_id]
        logger.debug(f"Cancelled shutdown timer for user {user_id}")
    
    async with _pipelines_lock:
        pipeline = _user_pipelines.pop(user_id, None)
        
        if not pipeline:
            return False
        
        # Stop DJLoop first if exists
        if hasattr(pipeline, '_dj_loop') and pipeline._dj_loop:
            try:
                await pipeline._dj_loop.stop()
            except Exception as e:
                logger.warning(f"Error stopping DJLoop: {e}")
            
        await pipeline.stop()
        logger.info(f"Removed pipeline for user {user_id}. Total: {len(_user_pipelines)}")
        return True


# Track shutdown timers for grace period
_shutdown_timers: Dict[str, asyncio.Task] = {}


async def schedule_pipeline_stop(user_id: str, grace_period_seconds: int = 60):
    """Schedule pipeline stop with a grace period.
    
    If the user reconnects before the grace period expires, the shutdown is cancelled.
    This allows brief disconnects (page navigation, network issues) without killing the stream.
    
    Args:
        user_id: User ID
        grace_period_seconds: Seconds to wait before stopping pipeline (default 60)
    """
    # Cancel any existing timer
    if user_id in _shutdown_timers:
        _shutdown_timers[user_id].cancel()
        del _shutdown_timers[user_id]
    
    async def delayed_stop():
        try:
            await asyncio.sleep(grace_period_seconds)
            # Check if user has reconnected
            from backend_v2.orchestration.events import get_event_emitter
            emitter = get_event_emitter()
            if emitter.get_user_connection_count(user_id) == 0:
                logger.info(f"Grace period expired, stopping pipeline for user {user_id}")
                await stop_user_pipeline(user_id)
            else:
                logger.info(f"User {user_id} reconnected, cancelling shutdown")
        except asyncio.CancelledError:
            logger.debug(f"Shutdown cancelled for user {user_id} (reconnected)")
        finally:
            if user_id in _shutdown_timers:
                del _shutdown_timers[user_id]
    
    # Schedule the delayed stop
    timer = asyncio.create_task(delayed_stop())
    _shutdown_timers[user_id] = timer
    logger.info(f"Scheduled pipeline stop for user {user_id} in {grace_period_seconds}s")



async def cleanup_idle_pipelines(max_idle_minutes: int = 10):
    """Stop pipelines that have been idle too long."""
    now = datetime.utcnow()
    idle_threshold = max_idle_minutes * 60
    to_remove = []
    
    async with _pipelines_lock:
        for user_id, pipeline in _user_pipelines.items():
            idle_seconds = (now - pipeline.last_activity).total_seconds()
            if idle_seconds > idle_threshold:
                to_remove.append(user_id)
                
        for user_id in to_remove:
            pipeline = _user_pipelines.pop(user_id, None)
            if pipeline:
                await pipeline.stop()
                logger.info(f"Cleaned up idle pipeline for user {user_id}")
                
    if to_remove:
        logger.info(f"Cleaned up {len(to_remove)} idle pipelines")


def get_pipeline_count() -> int:
    """Get current number of active pipelines."""
    return len(_user_pipelines)
