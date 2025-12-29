"""Audio feature extraction using librosa (optional dependency)."""

from typing import Optional, Dict, Any, Tuple
import logging

logger = logging.getLogger("ai-dj.audio.features")

DEFAULT_SR = 22050
MAX_ANALYSIS_SECONDS = 120.0


def _try_import_librosa():
    try:
        import librosa  # type: ignore
        return librosa
    except Exception as exc:  # pragma: no cover - dependency optional
        logger.warning("librosa not available, skipping audio feature extraction: %s", exc)
        return None


def _estimate_key_mode(chroma_mean, np_module) -> Tuple[Optional[int], Optional[int]]:
    """Estimate key and mode using Krumhansl profiles."""
    if chroma_mean is None or chroma_mean.size == 0:
        return None, None

    major_profile = np_module.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
    minor_profile = np_module.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])

    chroma_norm = chroma_mean / (np_module.linalg.norm(chroma_mean) + 1e-8)
    major_norm = major_profile / np_module.linalg.norm(major_profile)
    minor_norm = minor_profile / np_module.linalg.norm(minor_profile)

    major_scores = []
    minor_scores = []
    for i in range(12):
        major_scores.append(float(np_module.dot(chroma_norm, np_module.roll(major_norm, i))))
        minor_scores.append(float(np_module.dot(chroma_norm, np_module.roll(minor_norm, i))))

    max_major = max(major_scores)
    max_minor = max(minor_scores)

    if max_major >= max_minor:
        return int(major_scores.index(max_major)), 1
    return int(minor_scores.index(max_minor)), 0


def extract_audio_features(
    file_path: str,
    sample_rate: int = DEFAULT_SR,
    max_seconds: float = MAX_ANALYSIS_SECONDS,
) -> Optional[Dict[str, Any]]:
    """Extract audio features from a file path.

    Returns a dict compatible with SongFeatures or None if unavailable.
    """
    librosa = _try_import_librosa()
    if librosa is None:
        return None

    try:
        import numpy as np  # type: ignore
    except Exception as exc:  # pragma: no cover - dependency optional
        logger.warning("numpy not available, skipping audio feature extraction: %s", exc)
        return None

    try:
        y, sr = librosa.load(file_path, sr=sample_rate, mono=True, duration=max_seconds)
        if y is None or y.size == 0:
            return None

        # Normalize to reduce amplitude variance across sources.
        y = librosa.util.normalize(y)

        onset_env = librosa.onset.onset_strength(y=y, sr=sr)
        tempo, _ = librosa.beat.beat_track(onset_envelope=onset_env, sr=sr)

        rms = librosa.feature.rms(y=y)[0]
        if rms.size > 0:
            rms_db = librosa.amplitude_to_db(rms, ref=1.0)
            loudness = float(rms_db.mean())
            energy = float(np.clip((loudness + 60.0) / 60.0, 0.0, 1.0))
            rms_mean = float(rms.mean())
        else:
            loudness = None
            energy = None
            rms_mean = 0.0

        y_harm, y_perc = librosa.effects.hpss(y)
        rms_perc = librosa.feature.rms(y=y_perc)[0]
        percussive_ratio = float(rms_perc.mean() / max(rms_mean, 1e-6)) if rms_perc.size else 0.0

        tempo_score = 0.5
        if tempo and tempo > 0:
            tempo_score = float(1.0 - min(abs(tempo - 120.0) / 120.0, 1.0))
        danceability = float(np.clip(0.5 * percussive_ratio + 0.5 * tempo_score, 0.0, 1.0))

        flatness = librosa.feature.spectral_flatness(y=y)
        acousticness = float(np.clip(1.0 - float(flatness.mean()), 0.0, 1.0)) if flatness.size else None

        chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
        chroma_mean = chroma.mean(axis=1) if chroma.size else None
        key, mode = _estimate_key_mode(chroma_mean, np)

        valence = None
        if energy is not None:
            mode_bias = 0.15 if mode == 1 else (-0.15 if mode == 0 else 0.0)
            valence = float(np.clip(0.5 + mode_bias + (energy - 0.5) * 0.2, 0.0, 1.0))

        features = {
            "tempo": float(tempo) if tempo and tempo > 0 else None,
            "energy": energy,
            "danceability": danceability,
            "acousticness": acousticness,
            "key": key,
            "mode": mode,
            "loudness": loudness,
            "valence": valence,
        }

        return features
    except Exception as exc:
        logger.warning("Audio feature extraction failed for %s: %s", file_path, exc)
        return None
