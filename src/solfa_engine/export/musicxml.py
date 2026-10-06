"""MusicXML 3.1 exporter embedding tonic solfa syllables as lyrics."""

import xml.etree.ElementTree as ET
from xml.dom import minidom
from solfa_engine.schemas import MeasureItem, NoteItem

KEY_FIFTHS = {
    "C": 0, "G": 1, "D": 2, "A": 3, "E": 4, "B": 5, "F#": 6,
    "F": -1, "Bb": -2, "Eb": -3, "Ab": -4, "Db": -5, "Gb": -6,
}

PITCH_STEPS = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]


def midi_to_step_and_octave(midi: int) -> tuple[str, int, int]:
    """Convert MIDI number to (step: str, octave: int, alter: int)."""
    pc = midi % 12
    octave = (midi // 12) - 1
    step_str = PITCH_STEPS[pc]

    if "#" in step_str:
        step = step_str[0]
        alter = 1
    elif "b" in step_str:
        step = step_str[0]
        alter = -1
    else:
        step = step_str
        alter = 0

    return step, octave, alter


def beats_to_note_type(duration_beats: float) -> str:
    """Map duration in quarter beats to standard musical note types."""
    if duration_beats >= 4.0:
        return "whole"
    if duration_beats >= 2.0:
        return "half"
    if duration_beats >= 1.0:
        return "quarter"
    if duration_beats >= 0.5:
        return "eighth"
    return "16th"


def export_to_musicxml(
    key_root: str,
    mode: str,
    bpm: float,
    time_signature: str,
    measures: list[MeasureItem],
    title: str = "SolfaLedger Transcription",
) -> str:
    """Generate a standard MusicXML 3.1 document string."""
    score = ET.Element("score-partwise", version="3.1")

    # Work / Title
    work = ET.SubElement(score, "work")
    ET.SubElement(work, "work-title").text = title

    # Identification
    ident = ET.SubElement(score, "identification")
    creator = ET.SubElement(ident, "creator", type="composer")
    creator.text = "SolfaLedger Web3 Audio Transcriber"

    # Part List
    part_list = ET.SubElement(score, "part-list")
    score_part = ET.SubElement(part_list, "score-part", id="P1")
    ET.SubElement(score_part, "part-name").text = "Vocal / Solfa Melody"

    part = ET.SubElement(score, "part", id="P1")

    divisions = 4  # 4 subdivisions per quarter note beat
    try:
        num, den = map(int, time_signature.split("/"))
    except Exception:
        num, den = 4, 4

    fifths = KEY_FIFTHS.get(key_root, 0)

    for m in measures:
        measure_el = ET.SubElement(part, "measure", number=str(m.index))

        # First measure attributes
        if m.index == 1:
            attrs = ET.SubElement(measure_el, "attributes")
            ET.SubElement(attrs, "divisions").text = str(divisions)

            key_el = ET.SubElement(attrs, "key")
            ET.SubElement(key_el, "fifths").text = str(fifths)
            ET.SubElement(key_el, "mode").text = mode

            time_el = ET.SubElement(attrs, "time")
            ET.SubElement(time_el, "beats").text = str(num)
            ET.SubElement(time_el, "beat-type").text = str(den)

            clef = ET.SubElement(attrs, "clef")
            ET.SubElement(clef, "sign").text = "G"
            ET.SubElement(clef, "line").text = "2"

            direction = ET.SubElement(measure_el, "direction", placement="above")
            ET.SubElement(direction, "sound", tempo=str(int(round(bpm))))

        # Add notes
        for n in m.notes:
            note_el = ET.SubElement(measure_el, "note")
            step, octave, alter = midi_to_step_and_octave(n.midi)

            pitch_el = ET.SubElement(note_el, "pitch")
            ET.SubElement(pitch_el, "step").text = step
            if alter != 0:
                ET.SubElement(pitch_el, "alter").text = str(alter)
            ET.SubElement(pitch_el, "octave").text = str(octave)

            duration_divisions = max(1, int(round(n.duration_beats * divisions)))
            ET.SubElement(note_el, "duration").text = str(duration_divisions)
            ET.SubElement(note_el, "type").text = beats_to_note_type(n.duration_beats)

            # Solfa syllable as lyrical text
            lyric_el = ET.SubElement(note_el, "lyric", number="1")
            ET.SubElement(lyric_el, "syllabic").text = "single"
            ET.SubElement(lyric_el, "text").text = f"{n.solfa}{n.octave}"

    rough_xml = ET.tostring(score, encoding="utf-8")
    parsed = minidom.parseString(rough_xml)
    return parsed.toprettyxml(indent="  ")
