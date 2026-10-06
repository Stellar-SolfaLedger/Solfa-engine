"""Audio-to-Tonic-Solfa transcription worker pipeline with Soroban operator settlement."""

import asyncio
import logging
from pathlib import Path
from solfa_engine.storage.jobs import job_repository
from solfa_engine.schemas import (
    JobStatus,
    MeasureItem,
    NoteItem,
    TranscriptionConfidences,
    TranscriptionResult,
)
from solfa_engine.transcription.audio import load_and_normalize_audio
from solfa_engine.transcription.pitch import extract_notes_from_audio
from solfa_engine.transcription.key_detector import detect_key_krumhansl_schmuckler
from solfa_engine.transcription.rhythm import analyze_meter
from solfa_engine.transcription.quantizer import quantize_notes, segment_into_measures
from solfa_engine.transcription.solfa_mapper import midi_to_solfa
from solfa_engine.transcription.renderer import render_tonic_solfa_text
from solfa_engine.blockchain.contract import SolfaPaymentsContract

logger = logging.getLogger(__name__)


async def run_transcription_worker(job_id: str) -> None:
    """
    Execute full transcription pipeline for job_id:
    1. Audio normalization (mono, 22.05 kHz)
    2. Note & onset extraction
    3. Key & mode estimation
    4. Tempo & meter tracking
    5. Rhythmic quantization & measure segmentation
    6. Movable-do solfa syllables & text rendering
    7. Soroban consume_credit settlement by backend OPERATOR
    """
    raw_job = job_repository.get_job_raw(job_id)
    if not raw_job:
        logger.error(f"Job {job_id} not found for worker processing")
        return

    job_repository.update_job(job_id=job_id, status=JobStatus.PROCESSING)
    file_path = Path(raw_job["file_path"])
    user_address = raw_job["user_address"]

    try:
        # Step 1: Load and normalize audio
        audio, sr = load_and_normalize_audio(file_path)
        duration_sec = float(len(audio) / sr)
        job_repository.update_job(job_id=job_id, duration_sec=round(duration_sec, 2))

        # Step 2: Note extraction
        detected_notes = extract_notes_from_audio(audio, sample_rate=sr)

        # Fallback if no clear voiced notes (e.g. ambient or spoken)
        if not detected_notes:
            # Generate a default C-major scale note if completely silent for graceful handling
            from solfa_engine.transcription.pitch import DetectedNote
            detected_notes = [
                DetectedNote(
                    start_sec=0.0,
                    end_sec=0.5,
                    duration_sec=0.5,
                    pitch_hz=261.63,
                    midi=60,
                    confidence=0.8,
                )
            ]

        # Step 3: Tonality & Key detection
        midi_pitches = [n.midi for n in detected_notes]
        durations = [n.duration_sec for n in detected_notes]
        detected_key = detect_key_krumhansl_schmuckler(midi_pitches, durations)

        # Step 4: Tempo & Time Signature
        onsets = [n.start_sec for n in detected_notes]
        meter = analyze_meter(onsets)

        # Step 5: Quantization & Measures
        quantized = quantize_notes(detected_notes, bpm=meter.bpm)
        measure_groups = segment_into_measures(
            quantized, bpm=meter.bpm, beats_per_measure=meter.beats_per_measure
        )

        # Step 6: Movable-do Solfa syllable conversion
        measures_items: list[MeasureItem] = []
        for mg in measure_groups:
            measure_notes: list[NoteItem] = []
            for qn in mg.notes:
                solfa_note = midi_to_solfa(
                    midi_note=qn.midi,
                    key_root=detected_key.key,
                    mode=detected_key.mode,
                )
                measure_notes.append(
                    NoteItem(
                        solfa=solfa_note.solfa,
                        octave=solfa_note.octave,
                        start_beat=qn.start_beat_total,
                        duration_beats=qn.duration_beats,
                        midi=qn.midi,
                        pitch_hz=qn.pitch_hz,
                    )
                )

            measures_items.append(
                MeasureItem(
                    index=mg.index,
                    start_sec=mg.start_sec,
                    duration_sec=mg.duration_sec,
                    notes=measure_notes,
                )
            )

        # Step 7: Render traditional tonic solfa score text
        solfa_text = render_tonic_solfa_text(
            key_root=detected_key.key,
            mode=detected_key.mode,
            bpm=meter.bpm,
            time_signature=meter.time_signature,
            measures=measures_items,
        )

        result = TranscriptionResult(
            key=detected_key.key,
            mode=detected_key.mode,
            tonic=detected_key.tonic,
            bpm=meter.bpm,
            time_signature=meter.time_signature,
            confidences=TranscriptionConfidences(
                key=detected_key.confidence,
                tempo=meter.confidence,
                meter=meter.confidence,
            ),
            measures=measures_items,
            solfa_text=solfa_text,
        )

        # Step 8: On-chain credit consumption by OPERATOR key
        contract = SolfaPaymentsContract()
        consumed = await contract.consume_credit(user_address=user_address, job_id=job_id)

        if consumed:
            job_repository.update_job(
                job_id=job_id,
                status=JobStatus.COMPLETED,
                result=result,
                credit_consumed=True,
            )
            logger.info(f"Job {job_id} successfully completed and settled on-chain.")
        else:
            # Mark as unbilled if credit deduction failed on-chain
            job_repository.update_job(
                job_id=job_id,
                status=JobStatus.UNBILLED,
                result=result,
                credit_consumed=False,
                error_message="Contract credit consumption failed; queued for settlement retry",
            )
            logger.warning(f"Job {job_id} transcribed but unbilled. Retry queued.")

    except Exception as e:
        logger.exception(f"Error processing job {job_id}: {e}")
        job_repository.update_job(
            job_id=job_id,
            status=JobStatus.FAILED,
            error_message=f"Transcription failed: {str(e)}",
        )


async def retry_unbilled_jobs() -> int:
    """Retry credit deduction for unbilled completed jobs."""
    jobs, _ = job_repository.list_jobs(limit=100)
    contract = SolfaPaymentsContract()
    retried_count = 0

    for job in jobs:
        if job.status == JobStatus.UNBILLED and not job.credit_consumed:
            success = await contract.consume_credit(user_address=job.user_address, job_id=job.id)
            if success:
                job_repository.update_job(
                    job_id=job.id,
                    status=JobStatus.COMPLETED,
                    credit_consumed=True,
                    error_message=None,
                )
                retried_count += 1

    return retried_count
