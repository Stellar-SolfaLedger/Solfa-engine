"""Traditional tonic solfa notation textual layout renderer."""

from solfa_engine.schemas import MeasureItem, NoteItem


def render_tonic_solfa_text(
    key_root: str,
    mode: str,
    bpm: float,
    time_signature: str,
    measures: list[MeasureItem],
    bars_per_line: int = 4,
) -> str:
    """
    Render measures into traditional tonic solfa score text.

    Traditional Notation Marks:
    - '|' : Bar line
    - ':' : Beat separator
    - '.' : Half-beat division
    - '-' : Held note across beat
    - '||': Final double barline
    """
    header = (
        f"KEY: {key_root} {mode.capitalize()} | TEMPO: {int(round(bpm))} BPM | TIME: {time_signature}\n"
        f"{'=' * 65}\n\n"
    )

    if not measures:
        return header + "|   |\n"

    try:
        beats_per_bar = int(time_signature.split("/")[0])
    except Exception:
        beats_per_bar = 4

    rendered_bars: list[str] = []

    for measure in measures:
        # Group notes by integer beat index (0 to beats_per_bar - 1)
        beat_slots: list[list[NoteItem]] = [[] for _ in range(beats_per_bar)]

        for n in measure.notes:
            b_idx = int(n.start_beat)
            if 0 <= b_idx < beats_per_bar:
                beat_slots[b_idx].append(n)

        beat_strings: list[str] = []
        for b_idx in range(beats_per_bar):
            notes_in_beat = beat_slots[b_idx]
            if not notes_in_beat:
                # Held note or empty beat
                beat_strings.append("-")
            elif len(notes_in_beat) == 1:
                n = notes_in_beat[0]
                symbol = f"{n.solfa}{n.octave}"
                beat_strings.append(symbol)
            else:
                # Sub-divided beat using dot '.'
                symbols = [f"{n.solfa}{n.octave}" for n in notes_in_beat]
                beat_strings.append(".".join(symbols))

        # Join beats with colon ':'
        bar_text = " : ".join(beat_strings)
        rendered_bars.append(f"| {bar_text} ")

    # Group into lines of bars_per_line
    lines: list[str] = []
    for i in range(0, len(rendered_bars), bars_per_line):
        line_bars = rendered_bars[i : i + bars_per_line]
        is_last_line = (i + bars_per_line) >= len(rendered_bars)
        line_str = "".join(line_bars) + ("||" if is_last_line else "|")
        lines.append(line_str)

    score_body = "\n\n".join(lines)
    return header + score_body + "\n"
