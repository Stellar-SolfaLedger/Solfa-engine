"""Pitch detection, onset extraction, and note segmentation algorithms."""

import math
from dataclasses import dataclass
import numpy as np


@dataclass
class DetectedNote:
    """Raw detected note segment before rhythmic quantization."""
    start_sec: float
    end_sec: float
    duration_sec: float
    pitch_hz: float
    midi: int
    confidence: float


def hz_to_midi(freq_hz: float) -> int:
    """Convert frequency in Hertz to nearest MIDI note number."""
    if freq_hz <= 0:
        return 0
    return int(round(69.0 + 12.0 * math.log2(freq_hz / 440.0)))


def midi_to_hz(midi: int) -> float:
    """Convert MIDI note number to fundamental frequency in Hertz."""
    return 440.0 * (2.0 ** ((midi - 69.0) / 12.0))


def extract_pitch_autocorrelation(
    frame: np.ndarray,
    sample_rate: int = 22050,
    min_hz: float = 65.0,   # Approx C2
    max_hz: float = 1200.0, # Approx D6
) -> tuple[float, float]:
    """
    Compute fundamental frequency (F0) using normalized autocorrelation and parabolic peak interpolation.

    Returns:
        (pitch_hz: float, confidence: float)
    """
    n = len(frame)
    if n == 0 or np.max(np.abs(frame)) < 0.01:
        return 0.0, 0.0

    # Hann window
    windowed = frame * np.hanning(n)

    # Autocorrelation via FFT for speed
    n_fft = 2 ** int(np.ceil(np.log2(2 * n - 1)))
    fft_val = np.fft.rfft(windowed, n=n_fft)
    corr = np.fft.irfft(fft_val * np.conj(fft_val))
    corr = corr[:n]

    if corr[0] <= 1e-9:
        return 0.0, 0.0

    # Normalized autocorrelation
    norm_corr = corr / corr[0]

    min_lag = int(sample_rate / max_hz)
    max_lag = int(sample_rate / min_hz)
    max_lag = min(max_lag, n - 2)

    if min_lag >= max_lag:
        return 0.0, 0.0

    search_region = norm_corr[min_lag:max_lag]
    if len(search_region) == 0:
        return 0.0, 0.0

    peak_idx = int(np.argmax(search_region)) + min_lag
    peak_val = norm_corr[peak_idx]

    # Require minimum correlation confidence
    if peak_val < 0.35:
        return 0.0, float(peak_val)

    # Parabolic interpolation around peak
    if 0 < peak_idx < len(norm_corr) - 1:
        alpha = norm_corr[peak_idx - 1]
        beta = norm_corr[peak_idx]
        gamma = norm_corr[peak_idx + 1]
        denom = 2 * (alpha - 2 * beta + gamma)
        delta = (alpha - gamma) / denom if abs(denom) > 1e-9 else 0.0
        refined_lag = peak_idx + delta
    else:
        refined_lag = float(peak_idx)

    pitch_hz = sample_rate / refined_lag
    confidence = float(min(1.0, max(0.0, peak_val)))
    return pitch_hz, confidence


def extract_notes_from_audio(
    audio: np.ndarray,
    sample_rate: int = 22050,
    frame_size_ms: float = 46.4,  # 1024 samples at 22050 Hz
    hop_size_ms: float = 11.6,    # 256 samples at 22050 Hz
    min_note_duration_sec: float = 0.08,
) -> list[DetectedNote]:
    """
    Extract segmented musical notes from an audio signal.
    """
    frame_len = int((frame_size_ms / 1000.0) * sample_rate)
    hop_len = int((hop_size_ms / 1000.0) * sample_rate)

    if len(audio) < frame_len:
        return []

    num_frames = (len(audio) - frame_len) // hop_len + 1
    pitches = []
    confidences = []
    times = []

    for i in range(num_frames):
        start = i * hop_len
        frame = audio[start : start + frame_len]
        pitch, conf = extract_pitch_autocorrelation(frame, sample_rate)
        pitches.append(pitch)
        confidences.append(conf)
        times.append(start / sample_rate)

    # Segment consecutive frames with matching pitch into notes
    notes: list[DetectedNote] = []
    current_midi: int | None = None
    note_start_sec = 0.0
    note_pitches: list[float] = []
    note_confs: list[float] = []

    for t, p, c in zip(times, pitches, confidences):
        if c > 0.4 and p > 50.0:
            midi = hz_to_midi(p)
            if current_midi is None:
                # Start new note
                current_midi = midi
                note_start_sec = t
                note_pitches = [p]
                note_confs = [c]
            elif abs(midi - current_midi) <= 0.7:  # Same pitch tolerance
                note_pitches.append(p)
                note_confs.append(c)
            else:
                # Pitch changed - finish previous note if long enough
                dur = t - note_start_sec
                if dur >= min_note_duration_sec and current_midi is not None:
                    notes.append(
                        DetectedNote(
                            start_sec=round(note_start_sec, 3),
                            end_sec=round(t, 3),
                            duration_sec=round(dur, 3),
                            pitch_hz=float(np.median(note_pitches)),
                            midi=current_midi,
                            confidence=float(np.mean(note_confs)),
                        )
                    )
                current_midi = midi
                note_start_sec = t
                note_pitches = [p]
                note_confs = [c]
        else:
            # Silence or unvoiced
            if current_midi is not None:
                dur = t - note_start_sec
                if dur >= min_note_duration_sec:
                    notes.append(
                        DetectedNote(
                            start_sec=round(note_start_sec, 3),
                            end_sec=round(t, 3),
                            duration_sec=round(dur, 3),
                            pitch_hz=float(np.median(note_pitches)),
                            midi=current_midi,
                            confidence=float(np.mean(note_confs)),
                        )
                    )
                current_midi = None
                note_pitches = []
                note_confs = []

    # Final trailing note
    if current_midi is not None and len(times) > 0:
        dur = times[-1] - note_start_sec
        if dur >= min_note_duration_sec:
            notes.append(
                DetectedNote(
                    start_sec=round(note_start_sec, 3),
                    end_sec=round(times[-1], 3),
                    duration_sec=round(dur, 3),
                    pitch_hz=float(np.median(note_pitches)),
                    midi=current_midi,
                    confidence=float(np.mean(note_confs)),
                )
            )

    return notes
