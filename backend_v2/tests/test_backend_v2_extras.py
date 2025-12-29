"""Additional tests for AI DJ Backend V2 features (Phases 4, 7, 8)."""
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch

class TestOpenRouterWebSearch:
    """Test OpenRouter client web search capabilities."""
    
    @pytest.mark.asyncio
    async def test_search_web_flag_appends_suffix(self):
        """Test search_web=True appends :online to model name."""
        from backend.integrations.openrouter import OpenRouterClient
        
        client = OpenRouterClient()
        client.model = "test-model"
        
        with patch('httpx.AsyncClient') as MockClient:
            mock_post = AsyncMock()
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {
                'choices': [{'message': {'content': '{"test": "ok"}'}}]
            }
            MockClient.return_value.__aenter__.return_value.post = mock_post
            
            await client.chat_completion(
                messages=[{"role": "user", "content": "hi"}],
                search_web=True
            )
            
            # Verify call args
            call_args = mock_post.call_args
            assert call_args is not None
            payload = call_args[1]['json']
            assert payload['model'] == "test-model:online"

    @pytest.mark.asyncio
    async def test_get_artist_facts(self):
        """Test get_artist_facts parses list response."""
        from backend.integrations.openrouter import OpenRouterClient
        
        client = OpenRouterClient()
        
        # Mock chat_completion to return a list of facts
        client.chat_completion = AsyncMock(return_value={
            'parsed': ["Fact 1", "Fact 2", "Fact 3"]
        })
        
        facts = await client.get_artist_facts("The Beatles")
        
        assert len(facts) == 3
        assert facts[0] == "Fact 1"
        assert client.chat_completion.call_args[1]['search_web'] is True

class TestDJMixSchema:
    """Test DJ Mix engine schema updates."""
    
    def test_create_dj_mix_uses_start_pos(self):
        """Test create_dj_mix uses song2_start_sec."""
        with patch('backend.dj_mix.ffmpeg') as mock_ffmpeg, \
             patch('backend.dj_mix.transitions') as mock_transitions:
            
            from backend.dj_mix import create_dj_mix
            
            # Setup mocks
            mock_transitions.apply_crossfade.return_value = Mock()
            
            # Mock get_duration and get_loudness
            with patch('backend.dj_mix.get_duration', return_value=300.0), \
                 patch('backend.dj_mix.get_loudness', return_value=-14.0), \
                 patch('os.makedirs'), \
                 patch('os.path.exists', return_value=True):
                 
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
                # Expected: input("song1.mp3", ss=X), input("song2.mp3", ss=15.0)
                input_calls = mock_ffmpeg.input.call_args_list
                
                # assert that one of the calls was for song2 with ss=15.0
                found_start_sec = False
                for call in input_calls:
                    args, kwargs = call
                    if args[0] == "song2.mp3" and kwargs.get('ss') == 15.0:
                        found_start_sec = True
                        break
                
                assert found_start_sec, "Did not find ffmpeg.input('song2.mp3', ss=15.0)"

    def test_create_intro_mix_normalizes(self):
        """Test create_intro_mix calls normalization."""
        with patch('backend.dj_mix.ffmpeg') as mock_ffmpeg, \
             patch('backend.dj_mix.normalize_stream') as mock_norm:
            
            from backend.dj_mix import create_intro_mix
            
            # Setup mocks
            mock_ffmpeg.input.return_value.audio.filter.return_value.filter.return_value = Mock()
            mock_norm.return_value = Mock()
            
            with patch('backend.dj_mix.get_duration', return_value=300.0), \
                 patch('backend.dj_mix.get_loudness', return_value=-14.0), \
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
        from backend.orchestration.graph import InitialSpeechWriterAgent
        
        # Mock state
        state = {"session_id": "sess_123", "selected_song_uuid": "abc"}
        
        # Mock DB
        mock_db = AsyncMock()
        mock_db.get_recent_banter.return_value = ["Joke 1", "Joke 2"]
        mock_db.get_song.return_value = {"title": "Song", "artist": "Artist"}
        
        # Mock get_db
        with patch('backend.orchestration.graph.get_db', new=AsyncMock(return_value=mock_db)), \
             patch('backend.orchestration.graph.get_openrouter_client') as mock_get_client, \
             patch('os.path.exists', return_value=True), \
             patch('builtins.open', new_callable=Mock):
            
            mock_client = AsyncMock()
            mock_client.generate_dj_intro_speech.return_value = {"parsed": {"text": "Intro"}}
            mock_get_client.return_value = mock_client
            
            await InitialSpeechWriterAgent(state)
            
            # Verify DB call
            mock_db.get_recent_banter.assert_called_with("sess_123", limit=5)
            
            # Verify LLM call received history
            call_kwargs = mock_client.generate_dj_intro_speech.call_args[1]
            assert call_kwargs['banter_history'] == ["Joke 1", "Joke 2"]
            assert 'do_not_repeat' in call_kwargs

class TestSongDiscovery:
    """Test Song Discovery logic (Phase 11)."""

    @pytest.mark.asyncio
    async def test_get_ai_song_candidates_web(self):
        """Test that get_ai_song_candidates calls web search and returns list."""
        from backend.orchestration.graph import get_ai_song_candidates
        
        with patch('backend.orchestration.graph.get_openrouter_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.enabled = True
            mock_client.generate_search_queries.return_value = {
                'parsed': {
                    'queries': ["Analyzed Song", "Discovered Track"]
                }
            }
            mock_get_client.return_value = mock_client
            
            context = {"music_preferences": ["pop"]}
            candidates = await get_ai_song_candidates(context)
            
            assert candidates == ["Analyzed Song", "Discovered Track"]
            
            # Verify search_web=True was passed
            call_args = mock_client.generate_search_queries.call_args
            call_kwargs = call_args[1]
            assert call_kwargs['search_web'] is True
            assert call_kwargs['count'] == 8
