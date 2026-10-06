"""Transcription job endpoints: creation, status, history, override, and exports."""

import asyncio
import json
from pathlib import Path
import uuid
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile, status
import httpx

from solfa_engine.config import settings
from solfa_engine.auth.jwt import get_current_user
from solfa_engine.api.ratelimit import check_rate_limit
from solfa_engine.blockchain.contract import SolfaPaymentsContract
from solfa_engine.storage.jobs import job_repository
from solfa_engine.schemas import (
    ExportFormat,
    JobResponse,
    JobListResponse,
    JobStatus,
    MeasureItem,
    NoteItem,
    OverrideRequest,
    TranscriptionResult,
)
from solfa_engine.transcription.validator import validate_audio_metadata, validate_audio_header
from solfa_engine.transcription.security import scan_file_for_viruses
from solfa_engine.transcription.solfa_mapper import midi_to_solfa
from solfa_engine.transcription.renderer import render_tonic_solfa_text
from solfa_engine.export.pdf import generate_pdf_score
from solfa_engine.export.musicxml import export_to_musicxml

router = APIRouter(prefix="/jobs", tags=["Transcription Jobs"])


@router.post(
    "",
    response_model=JobResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_rate_limit)],
    summary="Submit a new audio transcription job",
    description="Accepts a multipart audio file upload (MP3/WAV/M4A/OGG/FLAC, max 50MB) or an audio URL. Checks Soroban can_transcribe entitlement before queuing.",
)
async def create_job(
    request: Request,
    file: UploadFile | None = File(default=None),
    audio_url: str | None = Form(default=None),
    user_address: str = Depends(get_current_user),
) -> JobResponse:
    """Validate entitlement, ingest audio file or URL, and register transcription job."""
    contract = SolfaPaymentsContract()
    can_transcribe = await contract.can_transcribe(user_address)
    if not can_transcribe:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Subscription expired or insufficient credits. Please subscribe or buy credits on-chain.",
        )

    if not file and not audio_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Must provide either an uploaded audio file or an audio_url parameter",
        )

    job_id = str(uuid.uuid4())
    upload_dir = settings.upload_dir
    upload_dir.mkdir(parents=True, exist_ok=True)

    dest_path: Path
    original_name: str

    if file:
        original_name = file.filename or f"audio_{job_id}.wav"
        dest_path = upload_dir / f"{job_id}_{original_name}"

        content = await file.read()
        validate_audio_metadata(original_name, file.content_type, len(content))
        if len(content) > 0:
            validate_audio_header(content[:64], original_name)

        with open(dest_path, "wb") as f:
            f.write(content)
    else:
        assert audio_url is not None
        original_name = Path(audio_url.split("?")[0]).name or f"audio_{job_id}.mp3"
        dest_path = upload_dir / f"{job_id}_{original_name}"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                res = await client.get(audio_url)
                res.raise_for_status()
                content = res.content
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to download audio from provided URL: {e}",
            )

        validate_audio_metadata(original_name, None, len(content))
        if len(content) > 0:
            validate_audio_header(content[:64], original_name)

        with open(dest_path, "wb") as f:
            f.write(content)

    await scan_file_for_viruses(dest_path)

    job = job_repository.create_job(
        user_address=user_address,
        original_filename=original_name,
        file_path=str(dest_path),
        job_id=job_id,
    )

    try:
        from solfa_engine.transcription.pipeline import run_transcription_worker
        asyncio.create_task(run_transcription_worker(job_id))
    except Exception:
        pass

    return job


@router.get(
    "",
    response_model=JobListResponse,
    summary="List transcription jobs for current user",
    description="Returns paginated history of transcription jobs submitted by the authenticated wallet.",
)
async def list_jobs(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user_address: str = Depends(get_current_user),
) -> JobListResponse:
    """Retrieve history of jobs submitted by current user."""
    jobs, total = job_repository.list_jobs(user_address=user_address, limit=limit, offset=offset)
    return JobListResponse(jobs=jobs, total=total)


@router.get(
    "/{job_id}",
    response_model=JobResponse,
    summary="Get job status and transcription results",
    description="Fetches detailed status, detected musical metadata, and tonic solfa notation for a job.",
)
async def get_job(
    job_id: str,
    user_address: str = Depends(get_current_user),
) -> JobResponse:
    """Fetch status or results of a transcription job."""
    job = job_repository.get_job(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job '{job_id}' not found")

    if job.user_address != user_address:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to job")

    return job


@router.post(
    "/{job_id}/override",
    response_model=JobResponse,
    summary="Override musical key or meter parameters without recharge",
    description="Allows user to correct detected key, mode, tempo, or time signature and immediately regenerates solfa score at no cost.",
)
async def override_job_parameters(
    job_id: str,
    override: OverrideRequest,
    user_address: str = Depends(get_current_user),
) -> JobResponse:
    """Re-render tonic solfa notation with custom user musical parameters."""
    job = job_repository.get_job(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job '{job_id}' not found")

    if job.user_address != user_address:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to job")

    if job.status != JobStatus.COMPLETED or not job.result:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot override incomplete job (current status: {job.status.value})",
        )

    res = job.result
    new_key = override.key.strip() if override.key else res.key
    new_mode = override.mode if override.mode else res.mode
    new_bpm = override.bpm if (override.bpm and override.bpm > 30) else res.bpm
    new_time_sig = override.time_signature if override.time_signature else res.time_signature

    # Re-map all notes to movable-do solfa syllables relative to new key
    updated_measures: list[MeasureItem] = []
    for m in res.measures:
        updated_notes: list[NoteItem] = []
        for n in m.notes:
            solfa_info = midi_to_solfa(n.midi, key_root=new_key, mode=new_mode)
            updated_notes.append(
                NoteItem(
                    solfa=solfa_info.solfa,
                    octave=solfa_info.octave,
                    start_beat=n.start_beat,
                    duration_beats=n.duration_beats,
                    midi=n.midi,
                    pitch_hz=n.pitch_hz,
                )
            )
        updated_measures.append(
            MeasureItem(
                index=m.index,
                start_sec=m.start_sec,
                duration_sec=m.duration_sec,
                notes=updated_notes,
            )
        )

    new_solfa_text = render_tonic_solfa_text(
        key_root=new_key,
        mode=new_mode,
        bpm=new_bpm,
        time_signature=new_time_sig,
        measures=updated_measures,
    )

    new_result = TranscriptionResult(
        key=new_key,
        mode=new_mode,
        tonic=f"{new_key} {new_mode.capitalize()}",
        bpm=new_bpm,
        time_signature=new_time_sig,
        confidences=res.confidences,
        measures=updated_measures,
        solfa_text=new_solfa_text,
    )

    updated_job = job_repository.update_job(job_id=job_id, result=new_result)
    assert updated_job is not None
    return updated_job


@router.get(
    "/{job_id}/export",
    summary="Export transcribed score in multiple formats",
    description="Export completed score as PDF document, MusicXML 3.1 score, plaintext tonic-solfa notation, or JSON.",
)
async def export_job(
    job_id: str,
    format: ExportFormat = Query(default=ExportFormat.TXT, description="Export file format"),
    user_address: str = Depends(get_current_user),
) -> Response:
    """Download transcription result in chosen format."""
    job = job_repository.get_job(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job '{job_id}' not found")

    if job.user_address != user_address:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to job")

    if job.status != JobStatus.COMPLETED or not job.result:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Job is not completed yet (current status: {job.status.value})",
        )

    title = job.original_filename or f"Score_{job_id[:8]}"

    if format == ExportFormat.PDF:
        pdf_bytes = generate_pdf_score(job.result, title=f"SolfaLedger: {title}")
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{job_id}.pdf"'},
        )
    elif format == ExportFormat.MUSICXML:
        xml_content = export_to_musicxml(
            key_root=job.result.key,
            mode=job.result.mode,
            bpm=job.result.bpm,
            time_signature=job.result.time_signature,
            measures=job.result.measures,
            title=title,
        )
        return Response(
            content=xml_content,
            media_type="application/vnd.recordare.musicxml+xml",
            headers={"Content-Disposition": f'attachment; filename="{job_id}.musicxml"'},
        )
    elif format == ExportFormat.TXT:
        return Response(
            content=job.result.solfa_text,
            media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{job_id}.txt"'},
        )
    else:  # JSON
        return Response(
            content=job.result.model_dump_json(indent=2),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{job_id}.json"'},
        )
