"""Audio synthesis fixtures for C Major scale, Happy Birthday melody, and 6/8 meter."""

from pathlib import Path
import numpy as np
from solfa_engine.transcription.audio import synthesize_tone, write_wav

TARGET_SR = 22050


def generate_c_major_scale_wav(output_path: Path) -> Path:
    """
    Synthesize an 8-note ascending C major scale: C4, D4, E4, F4, G4, A4, B4, C5.
    Expected solfa: d, r, m, f, s, l, t, d1.
    """
    # Note frequencies (Hz) for C4 to C5
    notes = [
        261.63,  # C4 (do)
        293.66,  # D4 (re)
        329.63,  # E4 (mi)
        349.23,  # F4 (fa)
        392.00,  # G4 (so)
        440.00,  # A4 (la)
        493.88,  # B4 (ti)
        523.25,  # C5 (do1)
    ]

    audio_chunks: list[np.ndarray] = []
    gap = np.zeros(int(0.05 * TARGET_SR), dtype=np.float32)

    for freq in notes:
        tone = synthesize_tone(frequency_hz=freq, duration_sec=0.45, sample_rate=TARGET_SR)
        audio_chunks.append(tone)
        audio_chunks.append(gap)

    full_audio = np.concatenate(audio_chunks)
    write_wav(output_path, full_audio, sample_rate=TARGET_SR)
    return output_path


def generate_happy_birthday_melody_wav(output_path: Path) -> Path:
    """
    Synthesize "Happy Birthday" opening phrases in C Major, 3/4 time signature.
    Notes:
    Bar 1: G3 (s,), G3 (s,)
    Bar 2: A3 (l,), G3 (s,), C4 (d)
    Bar 3: B3 (t,)
    Bar 4: G3 (s,), G3 (s,)
    Bar 5: A3 (l,), G3 (s,), D4 (r)
    Bar 6: C4 (d)
    """
    # (frequency_hz, duration_sec)
    melody = [
        (196.00, 0.35),  # G3 (so,)
        (196.00, 0.35),  # G3 (so,)
        (220.00, 0.70),  # A3 (la,)
        (196.00, 0.70),  # G3 (so,)
        (261.63, 0.70),  # C4 (do)
        (246.94, 1.40),  # B3 (ti,)
        (196.00, 0.35),  # G3 (so,)
        (196.00, 0.35),  # G3 (so,)
        (220.00, 0.70),  # A3 (la,)
        (196.00, 0.70),  # G3 (so,)
        (293.66, 0.70),  # D4 (re)
        (261.63, 1.40),  # C4 (do)
    ]

    audio_chunks: list[np.ndarray] = []
    gap = np.zeros(int(0.04 * TARGET_SR), dtype=np.float32)

    for freq, dur in melody:
        tone = synthesize_tone(frequency_hz=freq, duration_sec=dur, sample_rate=TARGET_SR)
        audio_chunks.append(tone)
        audio_chunks.append(gap)

    full_audio = np.concatenate(audio_chunks)
    write_wav(output_path, full_audio, sample_rate=TARGET_SR)
    return output_path


def generate_six_eight_meter_wav(output_path: Path) -> Path:
    """
    Synthesize a 6/8 compound meter melody in G Major with 6 eighth-notes per measure.
    D4, G4, B4, D5, B4, G4
    """
    # 6 eighth notes per bar at 120 dotted quarter (approx 0.25s per eighth note)
    notes = [
        293.66,  # D4
        392.00,  # G4
        493.88,  # B4
        587.33,  # D5
        493.88,  # B4
        392.00,  # G4
        293.66,  # D4
        392.00,  # G4
        493.88,  # B4
        587.33,  # D5
        493.88,  # B4
        392.00,  # G4
    ]

    audio_chunks: list[np.ndarray] = []
    gap = np.zeros(int(0.02 * TARGET_SR), dtype=np.float32)

    for freq in notes:
        tone = synthesize_tone(frequency_hz=freq, duration_sec=0.23, sample_rate=TARGET_SR)
        audio_chunks.append(tone)
        audio_chunks.append(gap)

    full_audio = np.concatenate(audio_chunks)
    write_wav(output_path, full_audio, sample_rate=TARGET_SR)
    return output_path
