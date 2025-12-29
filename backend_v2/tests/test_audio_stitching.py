import unittest
from unittest.mock import MagicMock, patch
import os
import sys

# Add backend_v2 to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from backend_v2.streaming.pipeline import UserRadioPipeline
from backend_v2.audio.mix import create_dj_mix, create_intro_mix

class TestAudioStitching(unittest.TestCase):
    
    @patch('subprocess.Popen')
    def test_pipeline_decoder_command_is_pcm(self, mock_popen):
        """Verify pipeline decodes to raw PCM without realtime throttling."""
        pipeline = UserRadioPipeline(user_id="test_user", session_id="test_session")
        
        # Mock encoder process to allowed feeding
        pipeline.encoder_process = MagicMock()
        pipeline.encoder_process.stdin = MagicMock()
        pipeline.encoder_process.poll.return_value = None
        
        # Run _decode_and_feed_segment (mocking os.path.exists)
        with patch('os.path.exists', return_value=True):
            # We call it as a coroutine (using asyncio run not needed if we just inspect the call before await)
            # Actually, _decode_and_feed_segment is async. We can inspect the code or run it.
            # For simplicity, we'll assume the file parsing is enough, or we can use asyncio.run
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # Create a mock Popen instance
            process_mock = MagicMock()
            process_mock.stdout = MagicMock()
            process_mock.stdout.read.return_value = b'' # valid empty chunk to end loop
            mock_popen.return_value = process_mock
            
            # The method will probably fail quickly due to mocks but we just want to see the Popen call
            try:
                loop.run_until_complete(pipeline._decode_and_feed_segment("test_segment.mp3"))
            except:
                pass
                
            # Verify call args
            calls = mock_popen.call_args_list
            decoder_cmd = None
            for args, _ in calls:
                cmd = args[0]
                if "test_segment.mp3" in cmd:
                    decoder_cmd = cmd
                    break
            
            self.assertIsNotNone(decoder_cmd, "Decoder command should be invoked for non-WAV input")
            self.assertNotIn('-re', decoder_cmd, "Decoder must not throttle input with -re")
            self.assertNotIn('-af', decoder_cmd, "Decoder must not apply drift-correcting filters")
            self.assertIn('-f', decoder_cmd)
            self.assertIn('s16le', decoder_cmd)
            self.assertIn('pipe:1', decoder_cmd)
            
    @patch('backend_v2.audio.mix.get_duration', return_value=120.0)
    @patch('backend_v2.audio.mix.get_loudness', return_value=-14.0)
    @patch('backend_v2.audio.mix.ffmpeg')
    @patch('os.makedirs')
    def test_mix_outputs_wav(self, mock_makedirs, mock_ffmpeg, mock_loudness, mock_duration):
        """Verify create_dj_mix outputs WAV format."""
        
        # Setup mocks
        mock_input = mock_ffmpeg.input
        mock_output = mock_ffmpeg.output
        
        # Mock ffmpeg chain return values to support chaining
        stream = MagicMock()
        mock_input.return_value.audio = stream
        stream.filter.return_value = stream # chaining
        
        create_intro_mix(
            song_path="song.mp3",
            user_id="test_user"
        )
        
        # Check output extension in the first arg of ffmpeg.output
        args, kwargs = mock_output.call_args
        output_filename = args[1]
        self.assertTrue(output_filename.endswith('.wav'), f"Intro mix must end with .wav, got {output_filename}")
        self.assertEqual(kwargs.get('acodec'), 'pcm_s16le')
        self.assertEqual(kwargs.get('format'), 'wav')
        
    @patch('backend_v2.audio.mix.get_duration', return_value=120.0)
    @patch('backend_v2.audio.mix.get_loudness', return_value=-14.0)
    @patch('backend_v2.audio.mix.ffmpeg')
    @patch('os.makedirs')
    def test_dj_mix_outputs_wav(self, mock_makedirs, mock_ffmpeg, mock_loudness, mock_duration):
        """Verify create_dj_mix outputs WAV format."""
        
        # Setup mocks
        mock_input = mock_ffmpeg.input
        mock_output = mock_ffmpeg.output
        
        # Mock filters to avoid issues
        stream = MagicMock()
        mock_input.return_value.audio = stream
        stream.filter.return_value = stream
        
        # Ensure ffmpeg.filter returns a stream too (for amix)
        mock_ffmpeg.filter.return_value = stream
        
        create_dj_mix(
            song1_path="song1.mp3",
            song2_path="song2.mp3",
            user_id="test_user"
        )
        
        args, kwargs = mock_output.call_args
        output_filename = args[1]
        self.assertTrue(output_filename.endswith('.wav'), f"DJ mix must end with .wav, got {output_filename}")
        self.assertEqual(kwargs.get('acodec'), 'pcm_s16le')

if __name__ == '__main__':
    unittest.main()
