"""Thread-safe file-backed and memory job repository."""

import json
from datetime import datetime, timezone
from pathlib import Path
import threading
import uuid
from typing import Any

from solfa_engine.config import settings
from solfa_engine.schemas import JobResponse, JobStatus, TranscriptionResult


class JobRepository:
    """Stores and retrieves transcription jobs."""

    def __init__(self, persistence_file: Path | None = None):
        self._lock = threading.Lock()
        self._jobs: dict[str, dict[str, Any]] = {}
        self.persistence_file = persistence_file or (settings.storage_dir / "jobs.json")
        self._load()

    def _load(self) -> None:
        """Load persisted jobs from JSON file if it exists."""
        if self.persistence_file.exists():
            try:
                with open(self.persistence_file, "r", encoding="utf-8") as f:
                    self._jobs = json.load(f)
            except Exception:
                self._jobs = {}

    def _persist(self) -> None:
        """Save jobs to JSON file atomically."""
        try:
            self.persistence_file.parent.mkdir(parents=True, exist_ok=True)
            temp_file = self.persistence_file.with_suffix(".tmp")
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(self._jobs, f, indent=2, default=str)
            temp_file.replace(self.persistence_file)
        except Exception:
            pass

    def create_job(
        self,
        user_address: str,
        original_filename: str | None = None,
        file_path: str | None = None,
        job_id: str | None = None,
    ) -> JobResponse:
        """Create and store a new job in PENDING status."""
        jid = job_id or str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        record: dict[str, Any] = {
            "id": jid,
            "user_address": user_address,
            "status": JobStatus.PENDING.value,
            "created_at": now,
            "updated_at": now,
            "original_filename": original_filename,
            "file_path": file_path,
            "duration_sec": None,
            "error_message": None,
            "result": None,
            "credit_consumed": False,
        }

        with self._lock:
            self._jobs[jid] = record
            self._persist()

        return self._to_response(record)

    def get_job(self, job_id: str) -> JobResponse | None:
        """Retrieve a job by its ID."""
        with self._lock:
            record = self._jobs.get(job_id)
            if not record:
                return None
            return self._to_response(record)

    def get_job_raw(self, job_id: str) -> dict[str, Any] | None:
        """Retrieve raw job dictionary internally."""
        with self._lock:
            return self._jobs.get(job_id)

    def update_job(self, job_id: str, **kwargs: Any) -> JobResponse | None:
        """Update job fields."""
        with self._lock:
            record = self._jobs.get(job_id)
            if not record:
                return None

            for key, val in kwargs.items():
                if key == "result" and isinstance(val, TranscriptionResult):
                    record[key] = val.model_dump()
                elif key == "status" and isinstance(val, JobStatus):
                    record[key] = val.value
                else:
                    record[key] = val

            record["updated_at"] = datetime.now(timezone.utc).isoformat()
            self._persist()
            return self._to_response(record)

    def list_jobs(
        self,
        user_address: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[JobResponse], int]:
        """List jobs filtered by user address ordered newest first."""
        with self._lock:
            records = list(self._jobs.values())
            if user_address:
                records = [r for r in records if r.get("user_address") == user_address]

            # Sort descending by created_at
            records.sort(key=lambda r: r.get("created_at", ""), reverse=True)
            total = len(records)
            paginated = records[offset : offset + limit]

            return [self._to_response(r) for r in paginated], total

    def delete_job(self, job_id: str) -> bool:
        """Delete a job by ID."""
        with self._lock:
            if job_id in self._jobs:
                del self._jobs[job_id]
                self._persist()
                return True
            return False

    def clear(self) -> None:
        """Wipe all jobs (used for testing)."""
        with self._lock:
            self._jobs.clear()
            if self.persistence_file.exists():
                try:
                    self.persistence_file.unlink()
                except Exception:
                    pass

    @staticmethod
    def _to_response(record: dict[str, Any]) -> JobResponse:
        """Convert internal storage dictionary to JobResponse schema."""
        result_obj = None
        if record.get("result"):
            try:
                result_obj = TranscriptionResult.model_validate(record["result"])
            except Exception:
                result_obj = None

        return JobResponse(
            id=record["id"],
            user_address=record["user_address"],
            status=JobStatus(record["status"]),
            created_at=record["created_at"],
            updated_at=record["updated_at"],
            original_filename=record.get("original_filename"),
            duration_sec=record.get("duration_sec"),
            error_message=record.get("error_message"),
            result=result_obj,
            credit_consumed=record.get("credit_consumed", False),
        )


# Global singleton instance
job_repository = JobRepository()
