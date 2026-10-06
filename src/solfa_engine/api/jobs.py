"""Transcription job endpoints: creation, status, history, override, and exports."""

import asyncio
from pathlib import Path
import uuid
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
import httpx

from solfa_engine.config import settings
from solfa_engine.auth.jwt import get_current_user
from solfa_engine.api.ratelimit import check_rate_limit
from solfa_engine.blockchain.contract import SolfaPaymentsContract
from solfa_engine.storage.jobs import job_repository
from solfa_engine.schemas import JobResponse, JobListResponse, JobStatus, OverrideRequest
from solfa_engine.transcription.validator import validate_audio_metadata, validate_audio_header
from solfa_engine.transcription.security import scan_file_for_viruses

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
    # 1. Verify on-chain entitlement via Soroban
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

        # Read content and validate
        content = await file.read()
        validate_audio_metadata(original_name, file.content_type, len(content))
        if len(content) > 0:
            validate_audio_header(content[:64], original_name)

        with open(dest_path, "wb") as f:
            f.write(content)
    else:
        # Download from URL
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

    # 2. Virus scan hook
    await scan_file_for_viruses(dest_path)

    # 3. Store job in repository
    job = job_repository.create_job(
        user_address=user_address,
        original_filename=original_name,
        file_path=str(dest_path),
        job_id=job_id,
    )

    # 4. Asynchronously kick off worker processing
    try:
        from solfa_engine.transcription.pipeline import run_transcription_worker
        asyncio.create_task(run_transcription_worker(job_id))
    except Exception:
        # Fallback if pipeline is being loaded
        pass

    return job
