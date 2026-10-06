"""Rhythmic quantization and measure bar segmentation."""

from dataclasses import dataclass
from solfa_engine.transcription.pitch import DetectedNote

# Standard quantization grids in fraction of beats
QUANTIZATION_GRID = [0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0]


@dataclass
class QuantizedNote:
    """Note with rhythm aligned to musical beats."""
    midi: int
    pitch_hz: float
    start_beat_total: float  # Cumulative beat position from start of song
    duration_beats: float
    start_sec: float
    duration_sec: float


@dataclass
class MeasureGroup:
    """A single bar of music containing quantized notes."""
    index: int
    start_sec: float
    duration_sec: float
    notes: list[QuantizedNote]


def quantize_to_grid(value: float, grid: list[float] = QUANTIZATION_GRID) -> float:
    """Snap a beat duration or position to the nearest rhythmic grid value."""
    # Also allow simple 0.25 steps
    snapped = round(value * 4) / 4.0
    return max(0.25, snapped)


def quantize_notes(
    notes: list[DetectedNote],
    bpm: float,
) -> list[QuantizedNote]:
    """Convert raw time-based notes into beat-quantized notes."""
    if not notes:
        return []

    beat_sec = 60.0 / bpm
    quantized: list[QuantizedNote] = []

    # First note starts song beat grid
    start_offset_sec = notes[0].start_sec

    for n in notes:
        rel_time_sec = max(0.0, n.start_sec - start_offset_sec)
        raw_start_beat = rel_time_sec / beat_sec
        raw_dur_beat = n.duration_sec / beat_sec

        quantized_start = round(raw_start_beat * 4) / 4.0
        quantized_dur = quantize_to_grid(raw_dur_beat)

        quantized.append(
            QuantizedNote(
                midi=n.midi,
                pitch_hz=n.pitch_hz,
                start_beat_total=quantized_start,
                duration_beats=quantized_dur,
                start_sec=n.start_sec,
                duration_sec=n.duration_sec,
            )
        )

    return quantized


def segment_into_measures(
    quantized_notes: list[QuantizedNote],
    bpm: float,
    beats_per_measure: int = 4,
) -> list[MeasureGroup]:
    """Group quantized notes into chronological bar measures."""
    if not quantized_notes:
        return []

    beat_sec = 60.0 / bpm
    bar_dur_sec = beats_per_measure * beat_sec

    # Find total beats
    last_beat = max(n.start_beat_total + n.duration_beats for n in quantized_notes)
    num_measures = max(1, int(np_ceil(last_beat / beats_per_measure)))

    measures: list[MeasureGroup] = []
    for m_idx in range(num_measures):
        m_start_beat = m_idx * beats_per_measure
        m_end_beat = m_start_beat + beats_per_measure
        m_start_sec = m_idx * bar_dur_sec

        m_notes: list[QuantizedNote] = []
        for n in quantized_notes:
            if m_start_beat <= n.start_beat_total < m_end_beat:
                # Adjust start beat relative to this measure
                rel_note = QuantizedNote(
                    midi=n.midi,
                    pitch_hz=n.pitch_hz,
                    start_beat_total=round(n.start_beat_total - m_start_beat, 2),
                    duration_beats=round(min(n.duration_beats, m_end_beat - n.start_beat_total), 2),
                    start_sec=n.start_sec,
                    duration_sec=n.duration_sec,
                )
                m_notes.append(rel_note)

        # Sort notes within measure
        m_notes.sort(key=lambda x: x.start_beat_total)

        measures.append(
            MeasureGroup(
                index=m_idx + 1,
                start_sec=round(m_start_sec, 3),
                duration_sec=round(bar_dur_sec, 3),
                notes=m_notes,
            )
        )

    return measures


def np_ceil(x: float) -> int:
    """Helper integer ceiling."""
    import math
    return int(math.ceil(x))
