"""Virus scanning hook and audio file retention cleanup tasks."""

from datetime import datetime, timezone, timedelta
import logging
from pathlib import Path
import time
from fastapi import HTTPException, status
import httpx

from solfa_engine.config import settings

logger = logging.getLogger(__name__)

# Standard EICAR test string signature for anti-malware verification
EICAR_SIGNATURE = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"


class SecurityScanError(HTTPException):
    """Raised when file scanning detects security threats."""

    def __init__(self, detail: str = "Uploaded file failed security/anti-malware check"):
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


async def scan_file_for_viruses(file_path: Path) -> bool:
    """
    Scan an uploaded file for malware signatures.
    If virus scanning webhook is configured, calls external scanner service.
    Also validates against test signatures (e.g., EICAR).
    """
    if not file_path.exists():
        return True

    # 1. Quick in-memory signature check
    try:
        with open(file_path, "rb") as f:
            chunk = f.read(1024)
            if EICAR_SIGNATURE in chunk:
                logger.warning(f"Malware test signature detected in file {file_path}")
                raise SecurityScanError("Malware signature detected in uploaded file")
    except SecurityScanError:
        raise
    except Exception as e:
        logger.warning(f"Error reading file for scan: {e}")

    # 2. External scanning hook if enabled and webhook configured
    if settings.virus_scan_enabled and settings.virus_scan_webhook_url:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                with open(file_path, "rb") as f:
                    res = await client.post(
                        settings.virus_scan_webhook_url,
                        files={"file": (file_path.name, f, "application/octet-stream")},
                    )
                if res.status_code == 200:
                    payload = res.json()
                    if payload.get("infected", False):
                        raise SecurityScanError(
                            f"File infected with: {payload.get('virus_name', 'Unknown Threat')}"
                        )
        except SecurityScanError:
            raise
        except Exception as e:
            logger.warning(f"External virus scan service unreachable or failed: {e}")

    return True


def cleanup_expired_audio_files(retention_days: int | None = None) -> int:
    """
    Delete audio uploads and transient export artifacts older than N days.
    Returns number of deleted files.
    """
    days = retention_days if retention_days is not None else settings.audio_retention_days
    cutoff = time.time() - (days * 86400)
    deleted_count = 0

    directories = [settings.upload_dir, settings.export_dir]
    for directory in directories:
        if not directory.exists():
            continue

        for p in directory.glob("*"):
            if p.is_file():
                try:
                    if p.stat().st_mtime < cutoff:
                        p.unlink()
                        deleted_count += 1
                        logger.info(f"Purged expired audio artifact: {p.name}")
                except Exception as e:
                    logger.warning(f"Failed to delete expired file {p}: {e}")

    return deleted_count
