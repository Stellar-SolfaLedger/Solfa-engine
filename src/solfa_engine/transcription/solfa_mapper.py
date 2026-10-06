"""Movable-do tonic solfa syllable mapper with chromatic inflections and octave registers."""

from dataclasses import dataclass
from typing import Literal

PITCH_CLASS_NAMES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]

# Interval to solfa syllable in Major tonality
MAJOR_INTERVAL_SOLFA = {
    0: "d",    # do (tonic)
    1: "di",   # chromatic sharp / ra (flat)
    2: "r",    # re (supertonic)
    3: "ri",   # chromatic sharp / me (minor 3rd)
    4: "m",    # mi (mediant)
    5: "f",    # fa (subdominant)
    6: "fi",   # chromatic sharp / se
    7: "s",    # so (dominant)
    8: "si",   # chromatic sharp / le (minor 6th)
    9: "l",    # la (submediant)
    10: "li",  # chromatic sharp / te (minor 7th)
    11: "t",   # ti (leading tone)
}

# In minor mode, default chromatic thirds/sixths/sevenths to natural minor syllables (me, le, te)
MINOR_INTERVAL_SOLFA = {
    0: "d",
    1: "ra",
    2: "r",
    3: "me",   # minor third
    4: "m",
    5: "f",
    6: "fi",
    7: "s",
    8: "le",   # minor sixth
    9: "l",
    10: "te",  # minor seventh
    11: "t",
}


@dataclass
class SolfaNote:
    """Note mapped to movable-do tonic solfa syllable and octave."""
    solfa: str       # d, r, m, f, s, l, t, di, me, etc.
    octave: str      # '', '1', '2', ',', ',,'
    full_symbol: str # e.g. 'd', 's1', 'd,'
    semitone_interval: int
    midi: int


def get_pitch_class_index(key_name: str) -> int:
    """Get 0-11 pitch class index for a given key string (e.g. 'C', 'F#', 'Eb')."""
    clean_key = key_name.strip()
    # Normalize flats and sharps
    aliases = {
        "DB": "C#", "D#": "Eb", "GB": "F#", "G#": "Ab", "A#": "Bb", "E#": "F", "B#": "C", "CB": "B"
    }
    upper_key = clean_key.upper()
    resolved = aliases.get(upper_key, clean_key)

    for idx, name in enumerate(PITCH_CLASS_NAMES):
        if name.upper() == resolved.upper():
            return idx

    # Default to C (0) if unrecognized
    return 0


def midi_to_solfa(
    midi_note: int,
    key_root: str = "C",
    mode: Literal["major", "minor"] = "major",
    center_octave_midi: int = 60,  # Middle C is default center register
) -> SolfaNote:
    """
    Convert a MIDI pitch to movable-do tonic solfa representation relative to the key.

    Octave register conventions:
    - Base octave: '' (e.g. 'd', 'r', 'm')
    - Higher register: '1', '2' (e.g. 'd1', 'r1')
    - Lower register: ',', ',,' (e.g. 'd,', 's,')
    """
    tonic_pc = get_pitch_class_index(key_root)
    note_pc = midi_note % 12

    # Calculate interval in semitones (0-11)
    interval = (note_pc - tonic_pc) % 12

    mapping = MINOR_INTERVAL_SOLFA if mode == "minor" else MAJOR_INTERVAL_SOLFA
    syllable = mapping.get(interval, "d")

    # Determine octave register relative to center tonic octave
    # Center tonic note is Middle C octave (4) plus tonic_pc offset
    center_tonic_midi = 60 + tonic_pc
    octave_diff = (midi_note - center_tonic_midi) // 12

    if octave_diff > 0:
        octave_mark = "1" if octave_diff == 1 else str(octave_diff)
    elif octave_diff < 0:
        octave_mark = "," * abs(octave_diff)
    else:
        octave_mark = ""

    full_symbol = f"{syllable}{octave_mark}"

    return SolfaNote(
        solfa=syllable,
        octave=octave_mark,
        full_symbol=full_symbol,
        semitone_interval=interval,
        midi=midi_note,
    )
