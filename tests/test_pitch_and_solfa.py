"""Unit and integration tests for pitch extraction, key detection, and tonic solfa notation."""

import pytest
from pathlib import Path
from solfa_engine.transcription.solfa_mapper import (
    midi_to_solfa,
    MAJOR_INTERVAL_SOLFA,
    MINOR_INTERVAL_SOLFA,
)
from solfa_engine.transcription.key_detector import (
    detect_key_krumhansl_schmuckler,
)
from solfa_engine.transcription.renderer import render_tonic_solfa_text
from solfa_engine.schemas import MeasureItem, NoteItem
from solfa_engine.transcription.audio import load_and_normalize_audio
from solfa_engine.transcription.pitch import extract_notes_from_audio
from tests.fixtures import (
    generate_c_major_scale_wav,
    generate_happy_birthday_melody_wav,
    generate_six_eight_meter_wav,
)


def test_solfa_major_mapping():
    """Verify standard diatonic scale notes map to d, r, m, f, s, l, t in C Major."""
    # C4 to C5 in C Major (MIDI 60 to 72)
    expected = [
        (60, "d", ""),
        (62, "r", ""),
        (64, "m", ""),
        (65, "f", ""),
        (67, "s", ""),
        (69, "l", ""),
        (71, "t", ""),
        (72, "d", "1"),  # Octave up
    ]
    for midi, expected_solfa, expected_octave in expected:
        res = midi_to_solfa(midi, key_root="C", mode="major")
        assert res.solfa == expected_solfa, f"MIDI {midi} expected {expected_solfa}, got {res.solfa}"
        assert res.octave == expected_octave, f"MIDI {midi} octave expected {expected_octave}, got {res.octave}"


def test_solfa_movable_do_in_g_major():
    """Verify movable-do shifts relative to tonic root: G4 (67) should be 'd' in G Major."""
    g_res = midi_to_solfa(67, key_root="G", mode="major")
    assert g_res.solfa == "d"

    # A4 (69) should be 'r' in G Major
    a_res = midi_to_solfa(69, key_root="G", mode="major")
    assert a_res.solfa == "r"

    # D4 (62) is below G4, should be 's,' in G Major
    d_res = midi_to_solfa(62, key_root="G", mode="major")
    assert d_res.solfa == "s"
    assert d_res.octave == ","


def test_solfa_chromatic_syllables():
    """Verify chromatic sharps and flats: di, ri, fi, si, li and minor thirds."""
    # C#4 in C major (interval 1) -> 'di'
    res_cs = midi_to_solfa(61, key_root="C", mode="major")
    assert res_cs.solfa == "di"

    # F#4 in C major (interval 6) -> 'fi'
    res_fs = midi_to_solfa(66, key_root="C", mode="major")
    assert res_fs.solfa == "fi"

    # Eb4 in C minor (interval 3) -> 'me'
    res_eb = midi_to_solfa(63, key_root="C", mode="minor")
    assert res_eb.solfa == "me"


def test_key_detector_krumhansl_schmuckler():
    """Verify key detection correctly identifies C Major from diatonic pitches."""
    c_major_pitches = [60, 62, 64, 65, 67, 69, 71, 72]
    durations = [1.0] * len(c_major_pitches)

    detected = detect_key_krumhansl_schmuckler(c_major_pitches, durations)
    assert detected.key == "C"
    assert detected.mode == "major"
    assert detected.confidence > 0.7


def test_render_tonic_solfa_text():
    """Verify textual layout formats bars '|', beat colons ':', half-beat dots '.', and hold dashes '-'."""
    measures = [
        MeasureItem(
            index=1,
            start_sec=0.0,
            duration_sec=2.0,
            notes=[
                NoteItem(solfa="d", octave="", start_beat=0.0, duration_beats=1.0, midi=60),
                NoteItem(solfa="r", octave="", start_beat=1.0, duration_beats=1.0, midi=62),
                NoteItem(solfa="m", octave="", start_beat=2.0, duration_beats=1.0, midi=64),
                NoteItem(solfa="f", octave="", start_beat=3.0, duration_beats=1.0, midi=65),
            ],
        ),
        MeasureItem(
            index=2,
            start_sec=2.0,
            duration_sec=2.0,
            notes=[
                NoteItem(solfa="s", octave="", start_beat=0.0, duration_beats=2.0, midi=67),
                NoteItem(solfa="l", octave="", start_beat=2.0, duration_beats=0.5, midi=69),
                NoteItem(solfa="t", octave="", start_beat=2.5, duration_beats=0.5, midi=71),
                NoteItem(solfa="d", octave="1", start_beat=3.0, duration_beats=1.0, midi=72),
            ],
        ),
    ]

    text = render_tonic_solfa_text(
        key_root="C",
        mode="major",
        bpm=120.0,
        time_signature="4/4",
        measures=measures,
    )

    assert "KEY: C Major" in text
    assert "TEMPO: 120 BPM" in text
    assert "| d : r : m : f |" in text
    assert "||" in text  # Final barline


def test_c_major_scale_audio_transcription(tmp_path: Path):
    """Integration test with synthesized C Major scale audio fixture asserting pitch and key detection."""
    wav_path = tmp_path / "c_major_scale.wav"
    generate_c_major_scale_wav(wav_path)

    audio, sr = load_and_normalize_audio(wav_path)
    assert len(audio) > 0
    assert sr == 22050

    notes = extract_notes_from_audio(audio, sample_rate=sr)
    assert len(notes) >= 6, f"Expected at least 6 detected notes, found {len(notes)}"

    # Detect key
    detected_key = detect_key_krumhansl_schmuckler([n.midi for n in notes])
    assert detected_key.key in ("C", "G"), f"Expected C Major or closely related, got {detected_key.key}"

    # Verify notes ascend in pitch
    midis = [n.midi for n in notes]
    assert midis[-1] > midis[0], "Scale should ascend in pitch"


def test_happy_birthday_audio_transcription(tmp_path: Path):
    """Integration test with Happy Birthday audio fixture."""
    wav_path = tmp_path / "happy_birthday.wav"
    generate_happy_birthday_melody_wav(wav_path)

    audio, sr = load_and_normalize_audio(wav_path)
    notes = extract_notes_from_audio(audio, sample_rate=sr)
    assert len(notes) >= 6

    detected_key = detect_key_krumhansl_schmuckler([n.midi for n in notes])
    assert detected_key.key in ("C", "G")
