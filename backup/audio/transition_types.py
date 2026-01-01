"""Canonical transition types and alias resolution for backend_v2."""

from typing import Tuple, Set, Dict
import logging

logger = logging.getLogger("ai-dj.audio.transition_types")


CANONICAL_TRANSITIONS: Set[str] = {
    "crossfade",
    "bass_swap",
    "filter_sweep",
    "echo_out",
    "vinyl_stop",
    "quick_cut",
    "eq_blend",
    "loop_mix",
    "drop_mix",
}

ALIASES: Dict[str, str] = {
    # Direct mappings (already canonical)
    "crossfade": "crossfade",
    "bass_swap": "bass_swap",
    "filter_sweep": "filter_sweep",
    "echo_out": "echo_out",
    "vinyl_stop": "vinyl_stop",
    "quick_cut": "quick_cut",
    "eq_blend": "eq_blend",
    "loop_mix": "loop_mix",
    "drop_mix": "drop_mix",
    # Legacy aliases
    "blend": "crossfade",
    "fade": "crossfade",
    "standard": "crossfade",
    # DJ vocabulary aliases
    "hard_cut": "quick_cut",
    "cut": "quick_cut",
    "slam": "quick_cut",
    "eq_swap": "eq_blend",
    "loop": "loop_mix",
    "drop": "drop_mix",
    # Effect variants
    "echo": "echo_out",
    "reverb_out": "echo_out",
    "vinyl": "vinyl_stop",
    "brake": "vinyl_stop",
}


def resolve_transition_type(raw_type: str) -> Tuple[str, str]:
    """Resolve a transition type string to its canonical form."""
    if not raw_type or not isinstance(raw_type, str):
        logger.warning("Invalid transition type: %r, defaulting to crossfade", raw_type)
        return ("", "crossfade")

    normalized = raw_type.lower().strip()

    if normalized in CANONICAL_TRANSITIONS:
        return (normalized, normalized)

    if normalized in ALIASES:
        resolved = ALIASES[normalized]
        if normalized != resolved:
            logger.debug("Resolved transition alias: %r -> %r", normalized, resolved)
        return (normalized, resolved)

    logger.warning(
        "Unknown transition type: %r, falling back to crossfade. Valid types: %s",
        raw_type,
        sorted(CANONICAL_TRANSITIONS),
    )
    return (normalized, "crossfade")


def is_canonical(transition_type: str) -> bool:
    """Check if a transition type is in the canonical set."""
    return transition_type.lower().strip() in CANONICAL_TRANSITIONS


def get_all_valid_types() -> Set[str]:
    """Get all valid input types (canonical + aliases)."""
    return CANONICAL_TRANSITIONS | set(ALIASES.keys())


LLM_TRANSITION_TYPE_LIST = (
    "crossfade, bass_swap, filter_sweep, echo_out, vinyl_stop, "
    "quick_cut, eq_blend, loop_mix, drop_mix"
)

LLM_TRANSITION_TYPE_DESCRIPTIONS = """
- crossfade: Standard 8-16 bar linear crossfade (safe for most tracks)
- bass_swap: Crossfade highs while instant-swapping bass at peak
- filter_sweep: Low-pass filter sweep on outgoing track, clean intro for incoming
- echo_out: Add echo tail to outgoing track, clean entry for incoming
- vinyl_stop: Turntable brake effect on outgoing track (use sparingly)
- quick_cut: Short 1-2s equal-power blend for abrupt transitions
- eq_blend: Filter outgoing lows, incoming highs, then crossfade
- loop_mix: Loop last bar of outgoing while bringing in incoming
- drop_mix: Quick bass cut on outgoing, then drop to incoming on downbeat
"""
