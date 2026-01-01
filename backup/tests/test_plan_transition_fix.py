
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from backend_v2.orchestration.agents import plan_transition
from backend_v2.services.preference_bundle import PreferenceBundle


@pytest.mark.asyncio
async def test_plan_transition_null_features():
    """plan_transition should handle missing features without crashing."""
    db = AsyncMock()

    bundle = MagicMock(spec=PreferenceBundle)
    bundle.user_id = "test-user"
    bundle.session_id = "test-session"
    bundle.mood = MagicMock()
    bundle.mood.id = "test-mood"

    song_a = {
        "uuid": "uuid-a",
        "title": "Song A",
        "artist": "Artist A",
        "features": {"tempo": 120.0, "energy": 0.8},
    }

    song_b = {
        "uuid": "uuid-b",
        "title": "Song B",
        "artist": "Artist B",
        "features": None,
    }

    mock_client = MagicMock()
    mock_client.enabled = False

    with patch("backend_v2.orchestration.agents.get_openrouter_client", return_value=mock_client):
        result = await plan_transition(db, bundle, song_a, song_b)

    assert result is not None
    assert "transition_type" in result
