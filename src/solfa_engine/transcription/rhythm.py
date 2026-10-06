"""Tempo estimation, beat tracking, and time signature detection."""

from dataclasses import dataclass
import numpy as np

SUPPORTED_TIME_SIGNATURES = ["4/4", "3/4", "2/4", "6/8"]


@dataclass
class DetectedMeter:
    """Estimated musical tempo and time signature."""
    bpm: float
    time_signature: str
    beats_per_measure: int
    beat_unit: int  # 4 for quarter note, 8 for eighth note
    confidence: float


def estimate_tempo_ioi(onset_times: list[float], min_bpm: float = 60.0, max_bpm: float = 200.0) -> tuple[float, float]:
    """
    Estimate tempo in BPM from Inter-Onset Intervals (IOIs).
    Returns (bpm: float, confidence: float).
    """
    if len(onset_times) < 2:
        return 120.0, 0.5

    iois = []
    for i in range(len(onset_times) - 1):
        diff = onset_times[i + 1] - onset_times[i]
        if 0.15 <= diff <= 2.0:  # Reasonable musical intervals (30 to 400 BPM)
            iois.append(diff)

    if not iois:
        return 120.0, 0.5

    # Histogram of IOIs into tempo bins
    candidate_bpms = np.linspace(min_bpm, max_bpm, 141)  # 1 BPM increments
    scores = np.zeros(len(candidate_bpms))

    for i, bpm in enumerate(candidate_bpms):
        beat_period = 60.0 / bpm
        for ioi in iois:
            # Check integer or half/quarter beat multiples
            for mult in [0.5, 1.0, 1.5, 2.0, 3.0, 4.0]:
                expected = beat_period * mult
                diff = abs(ioi - expected)
                if diff < 0.05 * beat_period:
                    scores[i] += 1.0 - (diff / (0.05 * beat_period))

    best_idx = int(np.argmax(scores))
    best_bpm = round(float(candidate_bpms[best_idx]), 1)
    max_score = scores[best_idx]
    confidence = min(1.0, max(0.4, float(max_score / (len(iois) * 1.5 + 1e-6))))

    return best_bpm, round(confidence, 2)


def estimate_time_signature(
    onset_times: list[float],
    bpm: float,
    hint_meter: str | None = None,
) -> tuple[str, int, int, float]:
    """
    Estimate time signature (e.g. '4/4', '3/4', '2/4', '6/8').
    Returns (time_sig_str, beats_per_measure, beat_unit, confidence).
    """
    if hint_meter and hint_meter in SUPPORTED_TIME_SIGNATURES:
        num, den = map(int, hint_meter.split("/"))
        return hint_meter, num, den, 0.95

    beat_sec = 60.0 / bpm
    if len(onset_times) < 4:
        return "4/4", 4, 4, 0.8

    # Measure periodicity for 2, 3, 4, 6 beats
    candidates = [
        ("4/4", 4, 4),
        ("3/4", 3, 4),
        ("6/8", 6, 8),
        ("2/4", 2, 4),
    ]

    scores: dict[str, float] = {}
    for name, num, den in candidates:
        bar_dur = (num * beat_sec) if den == 4 else (num * (beat_sec / 2))
        score = 0.0
        for t in onset_times:
            # Check how closely onset aligns to bar boundaries
            phase = (t % bar_dur) / bar_dur
            if phase < 0.1 or phase > 0.9:
                score += 1.5
            elif abs(phase - 0.5) < 0.1:
                score += 0.8
        scores[name] = score

    # Bias slightly towards 4/4 as standard default
    scores["4/4"] *= 1.15

    best_sig = max(scores, key=lambda k: scores[k])
    best_num, best_den = map(int, best_sig.split("/"))
    confidence = 0.85

    return best_sig, best_num, best_den, confidence


def analyze_meter(
    onset_times: list[float],
    hint_time_signature: str | None = None,
    hint_bpm: float | None = None,
) -> DetectedMeter:
    """Analyze tempo and time signature from note onsets."""
    if hint_bpm and hint_bpm > 30.0:
        bpm, bpm_conf = hint_bpm, 0.95
    else:
        bpm, bpm_conf = estimate_tempo_ioi(onset_times)

    time_sig, beats_per_bar, beat_unit, meter_conf = estimate_time_signature(
        onset_times, bpm, hint_meter=hint_time_signature
    )

    combined_conf = round(0.5 * bpm_conf + 0.5 * meter_conf, 2)

    return DetectedMeter(
        bpm=bpm,
        time_signature=time_sig,
        beats_per_measure=beats_per_bar,
        beat_unit=beat_unit,
        confidence=combined_conf,
    )
