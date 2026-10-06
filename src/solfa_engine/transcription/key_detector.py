"""Krumhansl-Schmuckler key and mode detection algorithm."""

from dataclasses import dataclass
from typing import Literal
import numpy as np

PITCH_CLASSES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]

# Krumhansl-Kessler key profile weights
MAJOR_PROFILE = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR_PROFILE = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])


@dataclass
class DetectedKey:
    """Detected musical tonality."""
    key: str  # e.g. "C", "F#", "Eb"
    mode: Literal["major", "minor"]
    tonic: str  # e.g. "C Major", "A Minor"
    confidence: float  # Pearson correlation [0.0, 1.0]
    pitch_class_index: int  # 0 to 11


def compute_pitch_class_distribution(midi_notes: list[int], durations: list[float] | None = None) -> np.ndarray:
    """
    Compute 12-dimensional pitch-class chroma distribution.
    If durations are provided, weights pitches by their sounding length.
    """
    chroma = np.zeros(12, dtype=np.float64)
    if not midi_notes:
        return chroma

    if durations is None or len(durations) != len(midi_notes):
        durations = [1.0] * len(midi_notes)

    for midi, dur in zip(midi_notes, durations):
        if midi > 0:
            pc = midi % 12
            chroma[pc] += max(0.01, dur)

    total = np.sum(chroma)
    if total > 0:
        chroma = chroma / total

    return chroma


def detect_key_krumhansl_schmuckler(
    midi_notes: list[int],
    durations: list[float] | None = None,
) -> DetectedKey:
    """
    Estimate musical key and mode using Pearson correlation against Krumhansl-Schmuckler profiles.
    """
    if not midi_notes:
        return DetectedKey(
            key="C",
            mode="major",
            tonic="C Major",
            confidence=0.5,
            pitch_class_index=0,
        )

    chroma = compute_pitch_class_distribution(midi_notes, durations)
    std_chroma = np.std(chroma)
    if std_chroma < 1e-9:
        # Flat distribution
        return DetectedKey(
            key="C",
            mode="major",
            tonic="C Major",
            confidence=0.5,
            pitch_class_index=0,
        )

    best_key = "C"
    best_mode: Literal["major", "minor"] = "major"
    best_r = -1.0
    best_pc = 0

    # Test all 12 pitch classes for both major and minor
    for shift in range(12):
        # Rotate chroma vector so candidate tonic is at index 0
        rotated_chroma = np.roll(chroma, -shift)

        # Pearson correlation for Major
        r_major = np.corrcoef(rotated_chroma, MAJOR_PROFILE)[0, 1]
        if r_major > best_r:
            best_r = r_major
            best_key = PITCH_CLASSES[shift]
            best_mode = "major"
            best_pc = shift

        # Pearson correlation for Minor
        r_minor = np.corrcoef(rotated_chroma, MINOR_PROFILE)[0, 1]
        if r_minor > best_r:
            best_r = r_minor
            best_key = PITCH_CLASSES[shift]
            best_mode = "minor"
            best_pc = shift

    confidence = float(np.clip(best_r, 0.0, 1.0))
    tonic_str = f"{best_key} {best_mode.capitalize()}"

    return DetectedKey(
        key=best_key,
        mode=best_mode,
        tonic=tonic_str,
        confidence=round(confidence, 3),
        pitch_class_index=best_pc,
    )
