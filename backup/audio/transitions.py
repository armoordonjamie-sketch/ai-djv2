"""FFmpeg-python transition library for AI DJ backend_v2."""

import logging
from typing import List, Dict, Any, Tuple

import ffmpeg

logger = logging.getLogger("ai-dj.audio.transitions")


PI_HALF = 1.5707963267948966


def _equal_power_expr(fade_start: float, fade_end: float, incoming: bool) -> str:
    """Equal-power fade expression to keep perceived loudness steady."""
    duration = max(fade_end - fade_start, 0.001)
    phase = f"((t-{fade_start})/{duration})*{PI_HALF}"
    if incoming:
        curve = f"sin({phase})"
        pre = "0"
        post = "1"
    else:
        curve = f"cos({phase})"
        pre = "1"
        post = "0"
    return f"if(lt(t,{fade_start}),{pre},if(lt(t,{fade_end}),{curve},{post}))"


def mix_sweep_stages(
    stream_clean,
    cutoffs: List[int],
    filter_name: str,
    fade_start: float,
    duration: float,
    **kwargs,
):
    """Create a 3-stage filter sweep by blending filtered versions."""
    if len(cutoffs) < 3:
        return stream_clean.filter(filter_name, f=cutoffs[-1] if cutoffs else 2000)

    stage_duration = duration / 3
    t0 = fade_start
    t1 = fade_start + stage_duration
    t2 = fade_start + 2 * stage_duration

    split = stream_clean.filter_multi_output("asplit", 3)
    stream0 = split.stream(0)
    stream1 = split.stream(1)
    stream2 = split.stream(2)

    stage0 = stream0.filter(filter_name, f=cutoffs[0])
    stage1 = stream1.filter(filter_name, f=cutoffs[1])
    stage2 = stream2.filter(filter_name, f=cutoffs[2])

    w0_expr = f"if(lt(t,{t0}),1,if(lt(t,{t1}),1-((t-{t0})/{stage_duration}),0))"
    w1_expr = (
        f"if(lt(t,{t0}),0,"
        f"if(lt(t,{t1}),(t-{t0})/{stage_duration},"
        f"if(lt(t,{t2}),1-((t-{t1})/{stage_duration}),0)))"
    )
    w2_expr = f"if(lt(t,{t1}),0,if(lt(t,{t2}),(t-{t1})/{stage_duration},1))"

    stage0_weighted = stage0.filter("volume", volume=w0_expr, eval="frame")
    stage1_weighted = stage1.filter("volume", volume=w1_expr, eval="frame")
    stage2_weighted = stage2.filter("volume", volume=w2_expr, eval="frame")

    return ffmpeg.filter(
        [stage0_weighted, stage1_weighted, stage2_weighted],
        "amix",
        inputs=3,
        duration="longest",
        normalize=0,
    )


def apply_crossfade(a1, a2, duration: float, peak_time: float, **kwargs):
    """Equal-power crossfade for constant perceived loudness."""
    fade_start = peak_time - (duration / 2)
    fade_end = peak_time + (duration / 2)
    a1_v = a1.filter("volume", volume=_equal_power_expr(fade_start, fade_end, incoming=False), eval="frame")
    a2_v = a2.filter("volume", volume=_equal_power_expr(fade_start, fade_end, incoming=True), eval="frame")
    return ffmpeg.filter([a1_v, a2_v], "amix", inputs=2, duration="longest", normalize=0)


def apply_quick_cut(a1, a2, duration: float, peak_time: float, **kwargs):
    """Hard cut with a minimal fade to avoid clicks."""
    hard_cut_duration = max(1.0, min(duration, 2.0))
    fade_start = peak_time - (hard_cut_duration / 2)
    fade_end = peak_time + (hard_cut_duration / 2)
    a1_cut = a1.filter("volume", volume=_equal_power_expr(fade_start, fade_end, incoming=False), eval="frame")
    a2_cut = a2.filter("volume", volume=_equal_power_expr(fade_start, fade_end, incoming=True), eval="frame")
    return ffmpeg.filter([a1_cut, a2_cut], "amix", inputs=2, duration="longest", normalize=0)


def apply_eq_blend(a1, a2, duration: float, peak_time: float, **kwargs):
    """EQ-style blend with progressive filter sweeps."""
    fade_start = peak_time - (duration / 2)
    fade_end = peak_time + (duration / 2)

    lpf_cutoffs = kwargs.get("outgoing_lpf_cutoffs", [18000, 6000, 2000])
    hpf_cutoffs = kwargs.get("incoming_hpf_cutoffs", [1200, 500, 80])

    logger.debug("eq_blend: LPF %s, HPF %s, duration=%.2fs", lpf_cutoffs, hpf_cutoffs, duration)

    a1_swept = mix_sweep_stages(a1, lpf_cutoffs, "lowpass", fade_start, duration)
    a2_swept = mix_sweep_stages(a2, hpf_cutoffs, "highpass", fade_start, duration)

    a1_faded = a1_swept.filter("volume", volume=_equal_power_expr(fade_start, fade_end, incoming=False), eval="frame")
    a2_faded = a2_swept.filter("volume", volume=_equal_power_expr(fade_start, fade_end, incoming=True), eval="frame")

    return ffmpeg.filter([a1_faded, a2_faded], "amix", inputs=2, duration="longest", normalize=0)


def apply_bass_swap(a1, a2, duration: float, peak_time: float, **kwargs):
    """Frequency-split bass swap transition.
    
    Swaps bass frequencies at peak_time while crossfading highs.
    Requires asplit since each input stream is used twice (low and high).
    """
    crossover = 250
    half = duration / 2
    fade_start = peak_time - half
    fade_end = peak_time + half

    # Split streams since we need each for both low and high filters
    a1_split = a1.filter_multi_output("asplit", 2)
    a2_split = a2.filter_multi_output("asplit", 2)
    
    a1_low = a1_split.stream(0).filter("lowpass", f=crossover)
    a1_high = a1_split.stream(1).filter("highpass", f=crossover)
    a2_low = a2_split.stream(0).filter("lowpass", f=crossover)
    a2_high = a2_split.stream(1).filter("highpass", f=crossover)

    w1_low = f"if(lt(t,{peak_time}),1,0)"
    w2_low = f"if(lt(t,{peak_time}),0,1)"
    a1_low_v = a1_low.filter("volume", volume=w1_low, eval="frame")
    a2_low_v = a2_low.filter("volume", volume=w2_low, eval="frame")

    w1_high = _equal_power_expr(fade_start, fade_end, incoming=False)
    w2_high = _equal_power_expr(fade_start, fade_end, incoming=True)
    a1_high_v = a1_high.filter("volume", volume=w1_high, eval="frame")
    a2_high_v = a2_high.filter("volume", volume=w2_high, eval="frame")

    return ffmpeg.filter(
        [a1_low_v, a2_low_v, a1_high_v, a2_high_v],
        "amix",
        inputs=4,
        duration="longest",
        normalize=0,
    )


def apply_filter_sweep(a1, a2, duration: float, peak_time: float, **kwargs):
    """Progressive LPF sweep on outgoing track."""
    fade_start = peak_time - (duration / 2)
    fade_end = peak_time + (duration / 2)
    lpf_cutoffs = kwargs.get("outgoing_lpf_cutoffs", [18000, 6000, 1500])

    logger.debug("filter_sweep: LPF %s, duration=%.2fs", lpf_cutoffs, duration)

    a1_swept = mix_sweep_stages(a1, lpf_cutoffs, "lowpass", fade_start, duration)

    a1_faded = a1_swept.filter("volume", volume=_equal_power_expr(fade_start, fade_end, incoming=False), eval="frame")
    a2_faded = a2.filter("volume", volume=_equal_power_expr(fade_start, fade_end, incoming=True), eval="frame")

    return ffmpeg.filter([a1_faded, a2_faded], "amix", inputs=2, duration="longest", normalize=0)


def apply_echo_out(a1, a2, duration: float, peak_time: float, **kwargs):
    """Echo-out transition with multi-tap delay."""
    delays_str = kwargs.get("echo_delays_str", "500|1000|1500")
    decays_str = kwargs.get("echo_decays_str", "0.55|0.35|0.2")

    logger.debug("echo_out: delays=%sms, decays=%s", delays_str, decays_str)

    a1_echo = a1.filter("aecho", 0.8, 0.88, delays_str, decays_str)

    fade_start = peak_time - (duration / 2)
    fade_end = peak_time + (duration / 2)
    a1_faded = a1_echo.filter("volume", volume=_equal_power_expr(fade_start, fade_end, incoming=False), eval="frame")
    a2_faded = a2.filter("volume", volume=_equal_power_expr(fade_start, fade_end, incoming=True), eval="frame")

    return ffmpeg.filter([a1_faded, a2_faded], "amix", inputs=2, duration="longest", normalize=0)


def apply_vinyl_stop(a1, a2, peak_time: float, stop_duration: float = 2.0, **kwargs):
    """Turntable brake effect on outgoing track."""
    a1_brake = a1.filter("afade", t="out", st=peak_time - stop_duration, d=stop_duration)
    a1_wash = a1_brake.filter("aecho", 0.8, 0.9, "100", "0.6")
    return apply_crossfade(a1_wash, a2, 1.0, peak_time)


def apply_loop_mix(a1, a2, duration: float, peak_time: float, **kwargs):
    """Loop mix using tight echo to mimic a short loop."""
    base_delay = kwargs.get("echo_delay_ms", 125)

    a1_loop = a1.filter("aecho", 0.6, 0.7, str(base_delay), "0.6")
    a1_loop = a1_loop.filter("aecho", 0.5, 0.5, str(base_delay * 2), "0.4")

    return apply_crossfade(a1_loop, a2, duration, peak_time)


def apply_drop_mix(a1, a2, duration: float, peak_time: float, **kwargs):
    """Drop mix with quick bass cut on outgoing track."""
    a1_no_bass = a1.filter("highpass", f=400)

    fade_start = peak_time - (duration / 2)
    fade_end = peak_time + (duration / 2)
    a1_faded = a1_no_bass.filter("volume", volume=_equal_power_expr(fade_start, fade_end, incoming=False), eval="frame")
    a2_faded = a2.filter("volume", volume=_equal_power_expr(fade_start, fade_end, incoming=True), eval="frame")

    return ffmpeg.filter([a1_faded, a2_faded], "amix", inputs=2, duration="longest", normalize=0)


TRANSITION_FUNCTIONS = {
    "crossfade": apply_crossfade,
    "quick_cut": apply_quick_cut,
    "eq_blend": apply_eq_blend,
    "bass_swap": apply_bass_swap,
    "filter_sweep": apply_filter_sweep,
    "echo_out": apply_echo_out,
    "vinyl_stop": apply_vinyl_stop,
    "loop_mix": apply_loop_mix,
    "drop_mix": apply_drop_mix,
    "blend": apply_crossfade,
}


def get_transition_function(transition_type: str) -> Tuple[object, str, bool]:
    """Get the transition function for a given type."""
    func = TRANSITION_FUNCTIONS.get(transition_type)

    if func:
        return func, func.__name__, False

    logger.warning(
        "Unknown transition type '%s', falling back to crossfade. Valid types: %s",
        transition_type,
        sorted(TRANSITION_FUNCTIONS.keys()),
    )
    return apply_crossfade, "apply_crossfade", True
