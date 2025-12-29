"""Additional tests for AI DJ Backend V2 features (Phases 4, 7, 8)."""
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch

class TestOpenRouterWebSearch:
    """Test OpenRouter client web search capabilities."""
    
    @pytest.mark.asyncio
    async def test_search_web_flag_appends_suffix(self):
        """Test search_web=True appends :online to model name."""
        from backend_v2.integrations.openrouter import OpenRouterClient
        
        client = OpenRouterClient()
        client.model = "test-model"
        client.enabled = True
        
        with patch('httpx.AsyncClient') as MockClient:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'choices': [{'message': {'content': '{"test": "ok"}'}}]
            }
            mock_response.raise_for_status = Mock()

            mock_client = Mock()
            mock_client.post = AsyncMock(return_value=mock_response)
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=None)
            
            await client.chat_completion(
                messages=[{"role": "user", "content": "hi"}],
                search_web=True
            )
            
            # Verify call args
            call_args = mock_client.post.call_args
            assert call_args is not None
            payload = call_args[1]['json']
            assert payload['model'] == "test-model:online"

    @pytest.mark.asyncio
    async def test_generate_song_suggestion_uses_search_web(self):
        """Test generate_song_suggestion passes search_web=True."""
        from backend_v2.integrations.openrouter import OpenRouterClient
        from backend_v2.services.preference_bundle import (
            PreferenceBundle,
            ContextData,
            MoodData,
            MoodProfileData,
            FeedbackData,
            HistoryData,
            UserProfileData,
        )
        
        client = OpenRouterClient()
        client.enabled = True
        
        bundle = PreferenceBundle(
            user_id="user-1",
            session_id="session-1",
            context=ContextData(id="ctx-1", name="default", raw_text=""),
            mood=MoodData(
                id="mood-1",
                name="Test",
                genres=["pop"],
                energy_target=0.5,
                valence_target=0.5,
                dj_personality="chill",
            ),
            mood_profile=MoodProfileData(),
            feedback=FeedbackData(),
            history=HistoryData(),
            profile=UserProfileData(),
            agent_settings={},
            prompt_templates={},
        )
        
        client.chat_completion = AsyncMock(return_value={
            'parsed': {"artist": "Artist", "title": "Song", "rationale": "Test"}
        })
        
        suggestion = await client.generate_song_suggestion(bundle)
        
        assert suggestion is not None
        assert client.chat_completion.call_args[1]['search_web'] is True

class TestDJMixSchema:
    """Test DJ Mix engine schema updates."""
    
    def test_create_dj_mix_uses_start_pos(self):
        """Test create_dj_mix uses song2_start_sec."""
        with patch('backend_v2.audio.mix.ffmpeg') as mock_ffmpeg, \
             patch('backend_v2.audio.mix.transition_lib.get_transition_function') as mock_transition_fn:
            
            from backend_v2.audio.mix import create_dj_mix
            
            # Setup mocks
            stream = Mock()
            mock_ffmpeg.input.return_value.audio = stream
            stream.filter.return_value = stream
            mock_transition_fn.return_value = (lambda *_args, **_kwargs: stream, "apply_crossfade", False)
            
            # Mock get_duration and get_loudness
            with patch('backend_v2.audio.mix.get_duration', return_value=300.0), \
                 patch('backend_v2.audio.mix.get_loudness', return_value=-14.0), \
                 patch('os.makedirs'), \
                 patch('os.path.exists', return_value=True), \
                 patch.dict('os.environ', {'AUDIO_MIX_USE_INPUT_SEEK': '1'}):
                 
                # Mock output run to avoid actual ffmpeg calls
                mock_node = Mock()
                mock_node.run.return_value = (b"", b"")  # stdout, stderr
                mock_ffmpeg.output.return_value.overwrite_output.return_value = mock_node
                
                create_dj_mix(
                    song1_path="song1.mp3",
                    song2_path="song2.mp3",
                    song2_start_sec=15.0  # Start 15s in
                )
                
                # Check ffmpeg.input calls
                # Expected: input("song1.mp3", ss=X), input("song2.mp3", ss=14.0)
                input_calls = mock_ffmpeg.input.call_args_list
                
                # assert that one of the calls was for song2 with ss=15.0
                found_start_sec = False
                for call in input_calls:
                    args, kwargs = call
                    if args[0] == "song2.mp3" and kwargs.get('ss') == 14.0:
                        found_start_sec = True
                        break
                
                assert found_start_sec, "Did not find ffmpeg.input('song2.mp3', ss=14.0)"

    def test_create_intro_mix_normalizes(self):
        """Test create_intro_mix calls normalization."""
        with patch('backend_v2.audio.mix.ffmpeg') as mock_ffmpeg, \
             patch('backend_v2.audio.mix.normalize_stream') as mock_norm:
            
            from backend_v2.audio.mix import create_intro_mix
            
            # Setup mocks
            mock_ffmpeg.input.return_value.audio.filter.return_value.filter.return_value = Mock()
            mock_norm.return_value = Mock()
            
            with patch('backend_v2.audio.mix.get_duration', return_value=300.0), \
                 patch('backend_v2.audio.mix.get_loudness', return_value=-14.0), \
                 patch('os.makedirs'), \
                 patch('os.path.exists', return_value=True):
                 
                create_intro_mix(
                    song_path="song.mp3",
                    tts_path="tts.mp3"
                )
                
                # Verify normalize_stream was called twice (song and tts)
                assert mock_norm.call_count == 2

class TestContextMemory:
    """Test Context Memory integration."""
    
    @pytest.mark.asyncio
    async def test_initial_speech_fetches_banter(self):
        """Test InitialSpeechWriterAgent calls get_recent_banter."""
        pytest.skip("Legacy graph-based agents removed in backend_v2")

class TestSongDiscovery:
    """Test Song Discovery logic (Phase 11)."""

    @pytest.mark.asyncio
    async def test_get_ai_song_candidates_web(self):
        """Test that get_ai_song_candidates calls web search and returns list."""
        pytest.skip("Legacy graph-based discovery removed in backend_v2")
