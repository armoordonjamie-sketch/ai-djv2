"""Transition parameter compiler for BPM-aware transitions."""

import logging
from typing import Dict, Optional

logger = logging.getLogger("ai-dj.audio.transition_params")


def beats_ms(bpm: float, beat_fraction: float = 1.0) -> int:
    """Convert BPM and beat fraction to milliseconds."""
    if bpm <= 0:
        logger.warning("Invalid BPM %s, defaulting to 120", bpm)
        bpm = 120.0

    quarter_note_ms = 60000.0 / bpm
    return int(round(quarter_note_ms * beat_fraction))


def choose_echo_fraction(bpm: float) -> float:
    """Choose an echo beat fraction based on BPM."""
    if bpm >= 150:
        return 0.25  # 16th note
    if bpm >= 110:
        return 0.5   # 8th note
    return 1.0       # quarter note


def compute_crossfade_duration(
    bpm_a: float,
    bpm_b: float,
    base: float = 10.0,
    min_duration: float = 3.0,
    max_duration: float = 12.0,
) -> float:
    """Compute adaptive crossfade duration based on BPM gap."""
    bpm_gap = abs(bpm_a - bpm_b)

    if bpm_gap >= 25:
        target = 4.0
    elif bpm_gap >= 15:
        target = 6.0
    elif bpm_gap >= 8:
        target = 8.0
    else:
        target = min(base, 10.0)

    result = max(min_duration, min(target, max_duration))

    logger.debug(
        "Crossfade duration: bpm_gap=%.1f, target=%.1f, result=%.1f",
        bpm_gap,
        target,
        result,
    )
    return result


def compute_sweep_profile(fade_start: float, duration: float) -> Dict[str, object]:
    """Compute 3-stage filter sweep profile for progressive transitions."""
    t0 = fade_start
    t1 = fade_start + duration / 3
    t2 = fade_start + 2 * duration / 3
    t3 = fade_start + duration

    return {
        "outgoing_lpf_cutoffs": [18000, 6000, 2000],
        "incoming_hpf_cutoffs": [1200, 500, 80],
        "stage_times": [t0, t1, t2, t3],
        "duration": duration,
        "fade_start": fade_start,
    }


def compute_echo_params(
    bpm: float,
    taps: int = 3,
    initial_decay: float = 0.55,
) -> Dict[str, object]:
    """Compute beat-synced multi-tap echo parameters for FFmpeg aecho."""
    beat_fraction = choose_echo_fraction(bpm)
    base_delay = beats_ms(bpm, beat_fraction)

    delays = []
    decays = []
    decay = initial_decay

    for i in range(1, taps + 1):
        delays.append(base_delay * i)
        decays.append(round(decay, 3))
        decay *= 0.65

    delays_str = "|".join(str(d) for d in delays)
    decays_str = "|".join(str(d) for d in decays)

    return {
        "delay_ms": base_delay,
        "delays_str": delays_str,
        "decays_str": decays_str,
        "beat_fraction": beat_fraction,
        "taps": taps,
    }


def compile_transition_params(
    transition_type: str,
    bpm_a: float,
    bpm_b: float,
    peak_time: float,
    base_duration: float = 10.0,
    duration_override: Optional[float] = None,
) -> Dict[str, object]:
    """Compile transition parameters for a given transition type."""
    if duration_override is not None:
        # Clamp override to avoid unusable transition lengths.
        if transition_type == "quick_cut":
            min_dur, max_dur = 1.0, 2.0
        elif transition_type == "vinyl_stop":
            min_dur, max_dur = 2.0, 6.0
        else:
            min_dur, max_dur = 3.0, 24.0
        crossfade_duration = max(min_dur, min(float(duration_override), max_dur))
    else:
        crossfade_duration = compute_crossfade_duration(bpm_a, bpm_b, base_duration)
    fade_start = peak_time - (crossfade_duration / 2)

    params: Dict[str, object] = {
        "transition_type": transition_type,
        "bpm_a": bpm_a,
        "bpm_b": bpm_b,
        "bpm_gap": abs(bpm_a - bpm_b),
        "crossfade_duration": crossfade_duration,
        "fade_start": fade_start,
        "peak_time": peak_time,
    }

    if transition_type in ("eq_blend", "filter_sweep"):
        sweep = compute_sweep_profile(fade_start, crossfade_duration)
        params["sweep_profile"] = sweep
        params["outgoing_lpf_cutoffs"] = sweep["outgoing_lpf_cutoffs"]
        params["incoming_hpf_cutoffs"] = sweep["incoming_hpf_cutoffs"]

    if transition_type == "echo_out":
        echo = compute_echo_params(bpm_a)
        params["echo_delay_ms"] = echo["delay_ms"]
        params["echo_delays_str"] = echo["delays_str"]
        params["echo_decays_str"] = echo["decays_str"]
        params["echo_beat_fraction"] = echo["beat_fraction"]
        params["echo_taps"] = echo["taps"]

    logger.info(
        "Transition params: type=%s bpm_gap=%.1f crossfade=%.1fs%s",
        transition_type,
        params["bpm_gap"],
        crossfade_duration,
        f" echo_delay_ms={params.get('echo_delay_ms')}" if "echo_delay_ms" in params else "",
    )

    return params
