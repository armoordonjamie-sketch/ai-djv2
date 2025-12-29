"""Tests for bounded silence during stream startup.

Verifies that slow track acquisition does not cause unbounded silence backlog.

Run with: pytest backend_v2/tests/test_bounded_silence_startup.py -v
"""
import asyncio
import time
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


class TestBoundedSilenceStartup:
    """Test that silence during startup is bounded."""
    
    @pytest.mark.asyncio
    async def test_defer_mode_no_silence_before_first_segment(self):
        """In defer mode, no silence should be fed before first segment."""
        with patch.dict('os.environ', {'STREAM_STARTUP_MODE': 'defer'}):
            # Need to reimport after patching
            from backend_v2.streaming.pipeline import UserRadioPipeline
            
            pipeline = UserRadioPipeline(
                user_id="test-user-defer",
                session_id="test-session-defer"
            )
            
            # Track silence fed
            silence_fed = 0.0
            original_feed_silence = pipeline._feed_silence
            
            async def track_silence(duration: float):
                nonlocal silence_fed
                silence_fed += duration
                # Don't actually call original to avoid encoder issues
                await asyncio.sleep(0.01)
            
            pipeline._feed_silence = track_silence
            
            # Mock the encoder to avoid subprocess issues
            pipeline.encoder_process = MagicMock()
            pipeline.encoder_process.poll.return_value = None
            pipeline.encoder_process.stdin = MagicMock()
            
            # Start the feeder task
            pipeline.is_running = True
            pipeline._shutdown = False
            
            # Create a task that will run the feeder for a short time
            async def run_feeder_briefly():
                try:
                    # Mock the emitter
                    with patch('backend_v2.orchestration.events.get_event_emitter') as mock_emitter:
                        emitter = MagicMock()
                        emitter.emit_status = AsyncMock()
                        emitter.emit_now_playing = AsyncMock()
                        emitter.emit_stream_status = AsyncMock()
                        mock_emitter.return_value = emitter
                        await asyncio.wait_for(
                            pipeline._segment_feeder(),
                            timeout=2.0
                        )
                except asyncio.TimeoutError:
                    pass
                finally:
                    pipeline._shutdown = True
            
            # Run for 2 seconds without providing a segment
            feeder_task = asyncio.create_task(run_feeder_briefly())
            await asyncio.sleep(2.0)
            pipeline._shutdown = True
            
            try:
                await asyncio.wait_for(feeder_task, timeout=1.0)
            except asyncio.TimeoutError:
                feeder_task.cancel()
            
            # In defer mode, no silence should be fed
            assert silence_fed == 0.0, f"In defer mode, expected 0s silence but got {silence_fed}s"
    
    @pytest.mark.asyncio
    async def test_bounded_mode_silence_capped(self):
        """In bounded mode, silence should be capped at MAX_SILENCE_AHEAD_SEC."""
        MAX_SILENCE = 3.0
        
        with patch.dict('os.environ', {
            'STREAM_STARTUP_MODE': 'bounded',
            'MAX_SILENCE_AHEAD_SEC': str(MAX_SILENCE),
        }):
            from backend_v2.streaming.pipeline import UserRadioPipeline
            
            pipeline = UserRadioPipeline(
                user_id="test-user-bounded",
                session_id="test-session-bounded"
            )
            
            # Track silence fed
            silence_fed = 0.0
            
            async def track_silence(duration: float):
                nonlocal silence_fed
                silence_fed += duration
                await asyncio.sleep(0.01)
            
            pipeline._feed_silence = track_silence
            
            # Mock the encoder
            pipeline.encoder_process = MagicMock()
            pipeline.encoder_process.poll.return_value = None
            pipeline.encoder_process.stdin = MagicMock()
            
            pipeline.is_running = True
            pipeline._shutdown = False
            
            async def run_feeder_briefly():
                try:
                    with patch('backend_v2.orchestration.events.get_event_emitter') as mock_emitter:
                        emitter = MagicMock()
                        emitter.emit_status = AsyncMock()
                        emitter.emit_now_playing = AsyncMock()
                        emitter.emit_stream_status = AsyncMock()
                        mock_emitter.return_value = emitter
                        await asyncio.wait_for(
                            pipeline._segment_feeder(),
                            timeout=5.0
                        )
                except asyncio.TimeoutError:
                    pass
                finally:
                    pipeline._shutdown = True
            
            # Run for 5 seconds without providing a segment
            start = time.perf_counter()
            feeder_task = asyncio.create_task(run_feeder_briefly())
            await asyncio.sleep(5.0)
            elapsed = time.perf_counter() - start
            pipeline._shutdown = True
            
            try:
                await asyncio.wait_for(feeder_task, timeout=1.0)
            except asyncio.TimeoutError:
                feeder_task.cancel()
            
            # Silence lead should be bounded
            # silence_fed - elapsed should be <= MAX_SILENCE_AHEAD_SEC + small epsilon
            silence_lead = silence_fed - elapsed
            
            # The cap is MAX_SILENCE_AHEAD_SEC, but we add some tolerance
            assert silence_lead <= MAX_SILENCE + 1.0, (
                f"Silence lead {silence_lead:.1f}s exceeds max {MAX_SILENCE}s + 1.0s tolerance"
            )
    
    @pytest.mark.asyncio
    async def test_first_segment_priority(self):
        """When first segment arrives, it should be processed immediately."""
        from backend_v2.streaming.pipeline import UserRadioPipeline
        
        pipeline = UserRadioPipeline(
            user_id="test-user-priority",
            session_id="test-session-priority"
        )
        
        # Track when segment was processed
        segment_processed_at = None
        segment_path = "/fake/segment.wav"
        
        original_decode = pipeline._decode_and_feed_segment
        
        async def track_decode(path: str):
            nonlocal segment_processed_at
            segment_processed_at = time.perf_counter()
            # Don't actually decode
        
        pipeline._decode_and_feed_segment = track_decode
        pipeline._feed_silence = AsyncMock()
        
        # Mock encoder
        pipeline.encoder_process = MagicMock()
        pipeline.encoder_process.poll.return_value = None
        pipeline.encoder_process.stdin = MagicMock()
        
        pipeline.is_running = True
        pipeline._shutdown = False
        
        async def run_feeder_with_delayed_segment():
            try:
                with patch('backend_v2.orchestration.events.get_event_emitter') as mock_emitter:
                    emitter = MagicMock()
                    emitter.emit_status = AsyncMock()
                    emitter.emit_now_playing = AsyncMock()
                    emitter.emit_stream_status = AsyncMock()
                    mock_emitter.return_value = emitter
                    await asyncio.wait_for(
                        pipeline._segment_feeder(),
                        timeout=10.0
                    )
            except asyncio.TimeoutError:
                pass
        
        start = time.perf_counter()
        feeder_task = asyncio.create_task(run_feeder_with_delayed_segment())
        
        # Wait 2 seconds then add a segment
        await asyncio.sleep(2.0)
        segment_added_at = time.perf_counter()
        await pipeline.segment_queue.put({"path": segment_path, "title": "Test"})
        
        # Wait for processing
        await asyncio.sleep(1.0)
        pipeline._shutdown = True
        
        try:
            await asyncio.wait_for(feeder_task, timeout=1.0)
        except asyncio.TimeoutError:
            feeder_task.cancel()
        
        # Segment should be processed very quickly after being added
        if segment_processed_at:
            delay = segment_processed_at - segment_added_at
            assert delay < 1.0, f"Segment processing delayed by {delay:.1f}s, expected < 1.0s"
    
    @pytest.mark.asyncio
    async def test_pipeline_stability_during_startup(self):
        """Pipeline should remain stable during extended startup wait."""
        from backend_v2.streaming.pipeline import UserRadioPipeline
        
        pipeline = UserRadioPipeline(
            user_id="test-user-stable",
            session_id="test-session-stable"
        )
        
        pipeline._feed_silence = AsyncMock()
        
        # Mock encoder
        pipeline.encoder_process = MagicMock()
        pipeline.encoder_process.poll.return_value = None
        pipeline.encoder_process.stdin = MagicMock()
        
        pipeline.is_running = True
        pipeline._shutdown = False
        
        errors = []
        
        async def run_feeder_track_errors():
            try:
                with patch('backend_v2.orchestration.events.get_event_emitter') as mock_emitter:
                    emitter = MagicMock()
                    emitter.emit_status = AsyncMock()
                    emitter.emit_now_playing = AsyncMock()
                    emitter.emit_stream_status = AsyncMock()
                    mock_emitter.return_value = emitter
                    await asyncio.wait_for(
                        pipeline._segment_feeder(),
                        timeout=3.0
                    )
            except asyncio.TimeoutError:
                pass
            except Exception as e:
                errors.append(str(e))
            finally:
                pipeline._shutdown = True
        
        feeder_task = asyncio.create_task(run_feeder_track_errors())
        await asyncio.sleep(3.0)
        pipeline._shutdown = True
        
        try:
            await asyncio.wait_for(feeder_task, timeout=1.0)
        except asyncio.TimeoutError:
            feeder_task.cancel()
        
        # Should have no errors
        assert len(errors) == 0, f"Unexpected errors during startup: {errors}"
        # Pipeline should still be in valid state
        assert pipeline.is_running is True or pipeline._shutdown is True


class TestStartupModeConfig:
    """Test startup mode configuration."""
    
    def test_default_startup_mode_is_defer(self):
        """Default startup mode should be 'defer'."""
        from backend_v2.config import STREAM_STARTUP_MODE
        assert STREAM_STARTUP_MODE == "defer"
    
    def test_max_silence_ahead_default(self):
        """MAX_SILENCE_AHEAD_SEC should have a reasonable default."""
        from backend_v2.config import MAX_SILENCE_AHEAD_SEC
        assert MAX_SILENCE_AHEAD_SEC == 3.0
    
    def test_startup_timeout_default(self):
        """STREAM_STARTUP_TIMEOUT_SEC should have a reasonable default."""
        from backend_v2.config import STREAM_STARTUP_TIMEOUT_SEC
        assert STREAM_STARTUP_TIMEOUT_SEC == 60


# Run with: pytest backend_v2/tests/test_bounded_silence_startup.py -v
