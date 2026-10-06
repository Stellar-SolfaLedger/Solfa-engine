"""Core domain models, enums, and request-response schemas for SolfaLedger."""

from enum import Enum
from typing import Literal
from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    """Transcription job lifecycle state."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    UNBILLED = "unbilled"


class ExportFormat(str, Enum):
    """Supported score export formats."""

    PDF = "pdf"
    TXT = "txt"
    MUSICXML = "musicxml"
    JSON = "json"


# --- Authentication & SEP-10 Schemas ---

class ChallengeRequest(BaseModel):
    """Request SEP-10 challenge for a Stellar public key."""

    address: str = Field(..., description="Stellar public key (G...)")


class ChallengeResponse(BaseModel):
    """SEP-10 challenge transaction envelope."""

    transaction_xdr: str = Field(..., description="Base64 encoded Stellar challenge transaction XDR")
    network_passphrase: str = Field(..., description="Network passphrase for verification")


class VerifyRequest(BaseModel):
    """Submit signed challenge transaction XDR."""

    transaction_xdr: str = Field(..., description="Signed challenge transaction XDR from wallet")


class VerifyResponse(BaseModel):
    """Authentication token response."""

    access_token: str
    token_type: str = "bearer"
    address: str
    expires_in: int


class JWTPayload(BaseModel):
    """Decoded JWT claims."""

    sub: str  # Stellar G-address
    exp: int
    iat: int
    iss: str


# --- Entitlements Schemas ---

class EntitlementsResponse(BaseModel):
    """On-chain user subscription and credit entitlement status."""

    user: str
    can_transcribe: bool
    has_active_subscription: bool
    subscription_plan_id: int | None = None
    subscription_expires_at: int | None = None
    is_unlimited: bool = False
    credits_remaining: int = 0


# --- Musical Structure Schemas ---

class NoteItem(BaseModel):
    """Single musical note in tonic solfa notation."""

    solfa: str = Field(..., description="Tonic solfa syllable (d, r, m, f, s, l, t, di, ra, etc.)")
    octave: str = Field(..., description="Octave indicator: '' for center, '1' higher, ',' lower")
    start_beat: float = Field(..., description="Beat index within the measure (0-indexed)")
    duration_beats: float = Field(..., description="Note duration in beats")
    midi: int = Field(..., description="MIDI pitch number (e.g. 60 = Middle C)")
    pitch_hz: float | None = Field(default=None, description="Fundamental frequency in Hertz")


class MeasureItem(BaseModel):
    """Single musical bar / measure containing notes."""

    index: int = Field(..., description="Measure sequence index (1-indexed)")
    start_sec: float = Field(..., description="Audio timestamp when measure begins")
    duration_sec: float = Field(..., description="Measure duration in seconds")
    notes: list[NoteItem] = Field(default_factory=list, description="Notes within this bar")


class TranscriptionConfidences(BaseModel):
    """Algorithmic confidence estimates (0.0 to 1.0)."""

    key: float = Field(default=0.9, ge=0.0, le=1.0)
    tempo: float = Field(default=0.9, ge=0.0, le=1.0)
    meter: float = Field(default=0.9, ge=0.0, le=1.0)


class TranscriptionResult(BaseModel):
    """Complete musical transcription payload."""

    key: str = Field(..., description="Musical key root (e.g. 'C', 'G', 'F#', 'Eb')")
    mode: Literal["major", "minor"] = Field(default="major", description="Major or Minor mode")
    tonic: str = Field(..., description="Full tonic specification (e.g. 'C Major' or 'A Minor')")
    bpm: float = Field(..., description="Detected tempo in Beats Per Minute")
    time_signature: str = Field(..., description="Time signature meter (e.g. '4/4', '3/4', '6/8')")
    confidences: TranscriptionConfidences = Field(default_factory=TranscriptionConfidences)
    measures: list[MeasureItem] = Field(default_factory=list)
    solfa_text: str = Field(..., description="Traditional tonic solfa textual score notation")


# --- Job API Schemas ---

class JobResponse(BaseModel):
    """Transcription job status and results."""

    id: str
    user_address: str
    status: JobStatus
    created_at: str
    updated_at: str
    original_filename: str | None = None
    duration_sec: float | None = None
    error_message: str | None = None
    result: TranscriptionResult | None = None
    credit_consumed: bool = False


class JobListResponse(BaseModel):
    """List of transcription jobs for user."""

    jobs: list[JobResponse]
    total: int


class OverrideRequest(BaseModel):
    """Re-render transcription with user-specified musical parameters without additional charge."""

    key: str | None = Field(default=None, description="New musical key (e.g., 'D', 'G', 'F#')")
    mode: Literal["major", "minor"] | None = Field(default=None, description="New mode")
    time_signature: str | None = Field(default=None, description="New time signature (e.g. '3/4', '6/8')")
    bpm: float | None = Field(default=None, description="New BPM tempo")
