# Stream Startup Silence Fix

## Problem Summary

When the DJLoop takes a long time to produce the first audio segment (30-60+ seconds for YouTube downloads, TTS generation, and audio rendering), the streaming pipeline previously emitted unbounded 1-second silence chunks. These silence chunks accumulated in the encoder's output buffer, resulting in 60-120 seconds of queued silence before real audio could play.

## Root Cause

**Location:** [pipeline.py](file:///c:/Users/JamiePC/Desktop/ai-djv2/backend_v2/streaming/pipeline.py) lines 378-403 (original)

**Mechanism:**
1. `_segment_feeder` waited for the first segment in a tight loop
2. Each iteration called `_feed_silence(1.0)` then `asyncio.sleep(1)`
3. While `_write_pcm` had real-time pacing (max 0.5s lead), the **encoded MP3 output** accumulated in FFmpeg's output buffer
4. After 60s of waiting, 60s of silence was queued ahead of real audio

## Fix Strategy

### Two Configurable Modes

#### Mode A: "defer" (Default)
- **Don't emit audio until first real segment is ready**
- HTTP connection stays open (server-side wait)
- Status events (`BUFFERING`) keep frontend alive
- No silence backlog possible

#### Mode B: "bounded"
- **Emit bounded silence** for environments that require keepalive
- Track "silence lead" = `silence_fed_sec - wall_elapsed_sec`
- Only emit silence when `silence_lead < MAX_SILENCE_AHEAD_SEC`
- Small chunks (0.5s) for responsiveness

## Configuration

Add to `.env` or environment variables:

```bash
# Startup mode: "defer" (default) or "bounded"
STREAM_STARTUP_MODE=defer

# Max silence lead in bounded mode (seconds)
MAX_SILENCE_AHEAD_SEC=3.0

# General audio buffer backpressure limit
MAX_BUFFERED_AUDIO_SEC=20.0

# Timeout before logging warning (doesn't force fallback yet)
STREAM_STARTUP_TIMEOUT_SEC=60
```

## Nginx Configuration (if proxied)

If the streaming endpoint is behind nginx, ensure proper timeout and buffering settings:

```nginx
location /api/v1/stream {
    proxy_pass http://backend:8000;
    
    # Disable response buffering for streaming
    proxy_buffering off;
    
    # Long timeouts for slow startup
    proxy_read_timeout 120s;
    proxy_send_timeout 120s;
    
    # Keep connection alive
    proxy_http_version 1.1;
    proxy_set_header Connection "";
}
```

## Testing

### Automated Tests

```bash
# Run bounded silence tests
pytest backend_v2/tests/test_bounded_silence_startup.py -v
```

Tests verify:
1. **Defer mode**: No silence fed before first segment
2. **Bounded mode**: Silence capped at MAX_SILENCE_AHEAD_SEC
3. **First segment priority**: Real audio plays immediately when ready
4. **Stability**: No crashes during extended startup wait

### Manual Verification

1. Start backend with logging:
   ```powershell
   $env:STREAM_STARTUP_MODE="bounded"
   .\.venv\Scripts\python.exe -m uvicorn backend_v2.main:app --reload
   ```

2. Start a stream and observe logs:
   ```
   🎧 Starting segment feeder in 'bounded' mode for user xxx
   Bounded silence: 3.0s fed, 5.0s elapsed, lead -2.0s
   🎧 First segment ready after 45.0s (silence fed: 3.0s)
   ```

3. Verify: Silence fed should never exceed ~3s regardless of wait time

## Files Changed

| File | Change |
|------|--------|
| `config.py` | Added STREAM_STARTUP_MODE, MAX_SILENCE_AHEAD_SEC, MAX_BUFFERED_AUDIO_SEC, STREAM_STARTUP_TIMEOUT_SEC |
| `pipeline.py` | Refactored `_segment_feeder` startup loop with defer/bounded modes |
| `tests/test_bounded_silence_startup.py` | New test file |
| `docs/stream_startup_fix.md` | This documentation |

## Recent Improvements (Dec 29, 2024)

### Issue: Defer Mode Polling Delay
**Problem:** In defer mode, the segment feeder was checking the queue every 0.5 seconds, causing a noticeable ~0.5s delay before playback started, even when pre-generated intro segments were ready almost immediately.

**Fix:** Reduced the polling interval in defer mode from 0.5s to 0.05s (50ms). This makes the feeder much more responsive to segments becoming available, reducing the maximum delay from ~500ms to ~50ms.

**Location:** `pipeline.py` line 423

**Result:** Nearly instantaneous playback when using pre-generated mood intros (delay reduced by ~90%).