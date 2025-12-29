# AI DJ Audio Subsystem Audit Report

## 1. Executive Summary

This report is a validated audit of the audio processing pipeline in `backend_v2/audio/mix.py` and `transitions.py`. The system implements a DJ mixing engine using FFmpeg, supporting dynamic transitions, TTS overlay, and unified handoff timing.

**Phase 1 Performance Update (Dec 2025):**
Implementation of caching and optimization has reduced "warm" mix generation latency by **>90%** (from ~5.3s to ~0.3s in benchmarks).

**Key Findings:**
*   **Centralized Mixing Logic:** `mix.py` is the single source of truth for audio rendering, used by both the live `DJLoop` and batch generation scripts.
*   **Performance Bottleneck (Solved):** `get_loudness` usage of `loudnorm` is now cached via `backend_v2/audio/media_cache.py`.
*   **Disabled Feature (Restored):** The `echo_out` transition is now enabled.
*   **Inconsistent BPM usage (Fixed):** `create_mix_from_list.py` now fetches BPM from DB (if available) to enable adaptive transitions.

## 2. Key Files & Usage Map

### Core Components

| File | Responsibility | Key Exports |
| :--- | :--- | :--- |
| `backend_v2/audio/mix.py` | Main mixing engine. Handles loudness, trim, synthesis, and rendering. | `create_intro_mix`, `create_dj_mix`, `get_loudness` |
| `backend_v2/audio/media_cache.py` | [NEW] Sidecar JSON caching for audio analysis. | `get_cached_analysis`, `save_cached_analysis` |
| `backend_v2/audio/transitions.py` | FFmpeg filter chain implementations for specific effects. | `get_transition_function`, `apply_crossfade`, `apply_eq_blend`, etc. |
| `backend_v2/audio/transition_types.py` | Resolves aliases (e.g., "fade" -> "crossfade") and defines canonical types. | `resolve_transition_type`, `CANONICAL_TRANSITIONS` |
| `backend_v2/audio/transition_params.py` | Calculates adaptive timings (e.g., shorter fades for high BPM gaps). | `compile_transition_params` |

### Call Graph: Who Calls `mix.py`?

| Function | Callsite File:Line | Caller Function | Context | Data Flow |
| :--- | :--- | :--- | :--- | :--- |
| **`create_intro_mix`** | `orchestration/loop.py:371` | `_produce_initial_segment` | **Live Loop:** Starts a session or recovers from empty queue. | `output_path` -> `segment_queue` -> Streamed. Metadata -> DB (`Segment`). |
| | `scripts/create_mix_from_list.py` | `create_mix` | **Batch Script:** Generates the first segment of a static mix. | `output_path` -> List -> Concatenated to final MP3. |
| **`create_dj_mix`** | `orchestration/loop.py:611` | `_produce_mix_segment` | **Live Loop:** Main loop iteration. Transitions `current_song` -> `selected`. | `output_path` -> `segment_queue` -> Streamed. Metadata -> DB (`Segment`). |
| | `scripts/create_mix_from_list.py` | `create_mix` | **Batch Script:** Transitions for list-based mix generation. | **UPDATED:** Now passes `bpm_a`/`bpm_b` retrieved from DB. |

## 3. Transition System Inventory

The transition logic flows as:
`User/LLM Request` -> `resolve_transition_type` -> `mix.py` (checks fallback) -> `transitions.py` filter chain.

### Transition Types

| Type (Canonical) | Implementation Function | Fallback? | Guard / Notes |
| :--- | :--- | :--- | :--- |
| `crossfade` | `apply_crossfade` | No | Standard `amix` + `afade`. |
| `eq_blend` | `apply_eq_blend` | No | Splitting audio into 3 streams (Low/Mid/High), blending with custom volume curves. |
| `filter_sweep` | `apply_filter_sweep` | No | Progressive LPF on outgoing track + crossfade. |
| `bass_swap` | `apply_bass_swap` | No | Splits at 250Hz. Instant cut for Lows at peak, fade for Highs. |
| `quick_cut` | `apply_quick_cut` | No | 0.1s very fast crossfade. "Slam" transition. |
| `vinyl_stop` | `apply_vinyl_stop` | No | `afade` (out) + `aecho` (brake effect) on outgoing. |
| **`echo_out`** | `apply_echo_out` | **NO** | **ENABLED** (Dec 2025). Uses multi-tap delay. |
| `loop_mix` | `apply_loop_mix` | No | Uses `aecho` with tight delays (125ms) to simulate looping + crossfade. |
| `drop_mix` | `apply_drop_mix` | No | High-pass (400Hz) on outgoing + quick fade out. |

### BPM Handling
*   **Source:** BPM is retrieved from `song.get("features")["tempo"]` in `loop.py`, which pulls from the database.
*   **Adaptive Logic:** `transition_params.compute_crossfade_duration` scales fade time based on BPM gap.

## 4. Data Flow & Timing Model

The "Handoff" model relies on calculating backwards from the *end* of the song files to align transitions.

### The Math (`mix.py`)

1.  **Constants**:
    *   `TRANSITION_BUFFER_SEC = 20.0` (Safety margin at eof)
    *   `CROSSFADE_SEC = 10.0` (Base transition window)
    *   `LEAD_IN_SEC = 12.0` (Audio pre-roll before transition starts)

2.  **`get_mix_start_in_song(D)`**:
    *   `Start = D - 20 - 10 - 12 = D - 42.0s`
    *   This is the anchor point. Every segment starts playing from `SongDuration - 42s`.

3.  **DJ Mix Composition**:
    *   **Segment Start:** Song A starts playing at `A_Duration - 42s`.
    *   **Transition Center:** Occurs exactly 12.0s into the segment (the `LEAD_IN_SEC`).
    *   **Song B Entry:** Song B starts playing at `12.0s - (CrossfadeDur / 2)`.
    *   **Handoff Point:** The player switches to the *next* segment when Song B reaches *its* `mix_start_pos` (B_Duration - 42s).

## 5. Performance Optimization (Phase 1)

### Implemented Improvements
1.  **Loudness/Duration Caching**:
    *   **Mechanism:** Stores `lufs` and `duration` in `<file>.analysis.json` sidecar.
    *   **Impact:** Eliminates full-file `loudnorm` scan on subsequent runs.
2.  **Input Seeking**:
    *   **Mechanism:** Uses `ffmpeg.input(..., ss=Start)` to skip decoding unused prefixes.
    *   **Impact:** Reduces CPU/Disk I/O for large files.
3.  **Profiling**:
    *   **Flags:** Set `AUDIO_MIX_PROFILE=1` to log wall-clock times.
    *   **Tool:** Run `python backend_v2/scripts/bench_mix.py` to verify performance.

### Benchmarks (Test Environment)
*   **Cold Run (Uncached):** 5.3s
*   **Warm Run (Cached):** 0.3s
*   **Speedup:** ~17x

### Next Steps (Phase 2)
*   Integrate DB-level caching to avoid sidecar files (if preferred).
*   Optimize filter graphs (merge `aresample`/`atrim`).
*   Verify `echo_out` stability in production.
