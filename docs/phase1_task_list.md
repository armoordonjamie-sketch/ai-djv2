# Phase 1 Task List: Audio Subsystem Performance

## A. Measurement Hooks
- [ ] **A1. Add Timers to `mix.py`**
    - **Goal:** Measure wall-clock time for `get_loudness`, `get_duration`, and `render`.
    - **Implementation:** Wrap calls with `time.time()`. Log only if `AUDIO_MIX_PROFILE=1` env var is set.
    - **Risk:** Low. No functional change.
- [ ] **A2. Create `scripts/bench_mix.py`**
    - **Goal:** Reproducible benchmark script.
    - **Implementation:**
        - Calls `create_dj_mix` with 2 representative songs.
        - Prints duration of each phase.
        - Runs twice to measure cold vs warm (cache) performance.
    - **Risk:** None (script only).

## B. Caching (High Impact)
- [ ] **B1. Create `backend_v2/audio/media_cache.py`**
    - **Goal:** Centralized caching logic.
    - **Implementation:**
        - `get_cached_analysis(file_path) -> dict | None`
        - `save_cached_analysis(file_path, data: dict)`
        - Uses sidecar JSON (`<filename>.analysis.json`) or DB. Stick to simple sidecar for now to match file-based workflow.
        - Check `mtime` and `size` to invalidate.
    - **Risk:** Medium (cache invalidation bugs).
- [ ] **B2. Integrate Cache into `mix.py`**
    - **Goal:** Avoid running `loudnorm` and `probe` repeatedly.
    - **Implementation:**
        - `get_loudness` checks cache first.
        - `get_duration` checks cache first.
        - On miss, run ffmpeg and save to cache.
        - **Acceptance:** 2nd run of `bench_mix.py` shows near-zero time for loudness/duration.

## C. Seek/Trim Optimization
- [ ] **C1. Implement Seek-Before-Decode**
    - **Goal:** Reduce decoding overhead for reading the end of large files.
    - **Implementation:**
        - Calculate `start_time` for the segment.
        - Use `ffmpeg.input(..., ss=max(0, start_time - 0.5))` to fast-seek.
        - Adjust `atrim` to cut relative to the new start point.
        - Guard with `AUDIO_MIX_USE_INPUT_SEEK=1` (default True).
    - **Risk:** Medium (frame alignment issues). Validate no audio gaps.

## D. Batch Parity
- [ ] **D1. Pass BPM in Batch Script**
    - **Goal:** Enable adaptive transitions in batch mode.
    - **Implementation:**
        - Update `scripts/create_mix_from_list.py` to fetch/pass `bpm` if available in song metadata (or downloader results).
    - **Risk:** Low.

## E. Cleanup & Correctness
- [ ] **E1. Enable `echo_out`**
    - **Goal:** Restore disabled functionality.
    - **Implementation:** Remove the explicit disable block in `mix.py`.
    - **Risk:** Low (if it fails, we can disable again).
- [ ] **E2. Fix Metadata Duplication**
    - **Goal:** Clean JSON output.
    - **Implementation:** Remove double assignment of `actual_duration`.

## F. Tests
- [ ] **F1. Add Integration Test**
    - **Goal:** Prevent regressions.
    - **Implementation:** `tests/test_mix_performance.py` running a mix and asserting output/metadata validity.
