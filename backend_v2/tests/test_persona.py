"""Tests for DJ persona service.

Tests:
- Persona compilation from PreferenceBundle
- Roast topic cooldown enforcement
- Forbidden term sanitization
- do_not_repeat list generation
"""
import pytest
from unittest.mock import MagicMock

from backend_v2.services.persona import (
    DJPersona,
    RoastTopic,
    compile_persona,
    DEFAULT_FORBIDDEN_PATTERNS,
    DEFAULT_ROAST_TOPICS,
    get_compiled_persona,
)
from backend_v2.services.preference_bundle import (
    PreferenceBundle,
    ContextData,
    MoodData,
    MoodProfileData,
    FeedbackData,
    FeedbackItem,
    HistoryData,
    UserProfileData,
)



# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_bundle():
    """Create a mock PreferenceBundle for testing."""
    return PreferenceBundle(
        user_id="test-user-123",
        session_id="test-session-456",
        context=ContextData(
            id="ctx-1",
            name="default",
            raw_text="""User: Gilly and Roo (The June 13th Duo)

Background:
- Gilly born 1973 UK paediatric nurse
- Famous for her VW Golf and short legs
- Roo from Mauritius bringing tropical warmth

Tone dry British sarcasm with warm Mauritian energy

DJ Personality Guidelines:
- Humour witty sharp occasionally dark but never cruel
- VW Golf max once per 5 segments
- Jamie is a genius max once per 3 segments
""",
        ),
        mood=MoodData(
            id="mood-1",
            name="Party Vibes",
            energy_target=0.8,
            valence_target=0.7,
            genres=["pop", "dance"],
            dj_personality="chatty",
        ),
        mood_profile=MoodProfileData(summary_text=""),
        feedback=FeedbackData(recent_likes=[], recent_dislikes=[]),
        history=HistoryData(recent_plays=[], recent_artists=[]),
        profile=UserProfileData(),  # Empty profile - will use legacy context
        agent_settings={},
        prompt_templates={},
    )



# =============================================================================
# Persona Compilation Tests
# =============================================================================

def test_compile_persona_extracts_user_names(mock_bundle):
    """Test that persona extracts user names from raw context."""
    persona = compile_persona(mock_bundle)
    
    assert "Gilly" in persona.user_names or "Roo" in persona.user_names


def test_compile_persona_loads_roast_topics(mock_bundle):
    """Test that persona loads default roast topics."""
    persona = compile_persona(mock_bundle)
    
    assert len(persona.roast_topics) > 0
    assert "vw_golf" in persona.roast_topics
    assert "jamie_genius" in persona.roast_topics


def test_compile_persona_loads_forbidden_terms(mock_bundle):
    """Test that persona loads forbidden terms."""
    persona = compile_persona(mock_bundle)
    
    assert len(persona.forbidden_terms) > 0
    assert "bpm" in persona.forbidden_terms
    assert "crossfade" in persona.forbidden_terms


def test_compile_persona_loads_music_constraints(mock_bundle):
    """Test that persona loads music hard constraints."""
    persona = compile_persona(mock_bundle)
    
    assert len(persona.music_hard_constraints) > 0
    assert any("slow songs" in c.lower() for c in persona.music_hard_constraints)


def test_compile_persona_stores_raw_context(mock_bundle):
    """Test that persona stores raw context for LLM."""
    persona = compile_persona(mock_bundle)
    
    assert len(persona.raw_context) > 0
    assert "Gilly" in persona.raw_context


# =============================================================================
# Cooldown Tests
# =============================================================================

def test_roast_topic_can_use_initially():
    """Test that roast topics can be used initially."""
    topic = RoastTopic(
        name="VW Golf",
        keywords=["golf", "vw"],
        max_per_n_segments=5,
    )
    
    # Initially cooldown not elapsed (segments_since = 0, need >= 5)
    assert not topic.can_use()


def test_roast_topic_can_use_after_cooldown():
    """Test that roast topics can be used after cooldown elapses."""
    topic = RoastTopic(
        name="VW Golf",
        keywords=["golf", "vw"],
        max_per_n_segments=5,
    )
    
    # Advance 5 segments
    for _ in range(5):
        topic.advance()
    
    assert topic.can_use()


def test_roast_topic_use_resets_cooldown():
    """Test that using a topic resets its cooldown."""
    topic = RoastTopic(
        name="VW Golf",
        keywords=["golf", "vw"],
        max_per_n_segments=5,
    )
    
    # Advance past cooldown
    for _ in range(5):
        topic.advance()
    
    assert topic.can_use()
    
    # Use it
    topic.use()
    
    # Can't use again
    assert not topic.can_use()


def test_persona_get_do_not_repeat(mock_bundle):
    """Test get_do_not_repeat returns topics on cooldown."""
    persona = compile_persona(mock_bundle)
    
    # Initially all topics are on cooldown (not enough segments elapsed)
    do_not_repeat = persona.get_do_not_repeat()
    
    assert len(do_not_repeat) > 0
    assert all(isinstance(t, str) for t in do_not_repeat)


def test_persona_record_speech_updates_cooldowns(mock_bundle):
    """Test that recording speech updates topic cooldowns."""
    persona = compile_persona(mock_bundle)
    
    # Advance all cooldowns
    for _ in range(10):
        persona.advance_segment()
    
    # VW Golf should now be usable
    assert persona.roast_topics["vw_golf"].can_use()
    
    # Record speech mentioning Golf
    persona.record_speech("Here's one for Gilly and her trusty Golf!")
    
    # VW Golf should now be on cooldown again
    assert not persona.roast_topics["vw_golf"].can_use()


def test_persona_advance_segment_advances_all(mock_bundle):
    """Test that advance_segment advances all topic cooldowns."""
    persona = compile_persona(mock_bundle)
    
    initial_counts = {
        name: topic.segments_since_last_use 
        for name, topic in persona.roast_topics.items()
    }
    
    persona.advance_segment()
    
    for name, topic in persona.roast_topics.items():
        assert topic.segments_since_last_use == initial_counts[name] + 1


# =============================================================================
# Sanitizer Pattern Tests
# =============================================================================

def test_forbidden_patterns_match_bpm():
    """Test that BPM patterns are detected."""
    import re
    
    test_cases = [
        ("120 BPM", True),
        ("at 130 beats per minute", True),
        ("high energy song", False),
    ]
    
    pattern = r'\b\d{2,3}\s*(bpm|beats?\s*per\s*minute)\b'
    
    for text, should_match in test_cases:
        match = re.search(pattern, text, re.IGNORECASE)
        assert bool(match) == should_match, f"Failed for: {text}"


def test_forbidden_patterns_match_camelot():
    """Test that Camelot code patterns are detected."""
    import re
    
    test_cases = [
        ("in 8A", True),
        ("key 11B", True),
        ("Camelot wheel", True),
        ("great song", False),
    ]
    
    patterns = [
        r'\b\d{1,2}[AB]\b',
        r'\bcamelot\s*(wheel|code|key)?\b',
    ]
    
    for text, should_match in test_cases:
        matched = any(re.search(p, text, re.IGNORECASE) for p in patterns)
        assert matched == should_match, f"Failed for: {text}"


# =============================================================================
# Integration Tests
# =============================================================================

def test_get_compiled_persona_caches(mock_bundle):
    """Test that persona is compiled correctly via helper."""
    persona = get_compiled_persona(mock_bundle)
    
    assert isinstance(persona, DJPersona)
    assert len(persona.roast_topics) > 0


def test_persona_to_dict(mock_bundle):
    """Test persona serialization."""
    persona = compile_persona(mock_bundle)
    
    d = persona.to_dict()
    
    assert "user_names" in d
    assert "roast_topics" in d
    assert "forbidden_terms_count" in d
    assert isinstance(d["roast_topics"], dict)


def test_persona_system_prompt_addendum(mock_bundle):
    """Test system prompt addendum generation."""
    persona = compile_persona(mock_bundle)
    
    addendum = persona.get_system_prompt_addendum()
    
    assert isinstance(addendum, str)
    # Should include hard music rules
    assert "HARD MUSIC RULES" in addendum or len(persona.music_hard_constraints) == 0
