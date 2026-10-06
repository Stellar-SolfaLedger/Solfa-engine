"""Audio file format, MIME type, and size validation."""

from pathlib import Path
from fastapi import HTTPException, status
from solfa_engine.config import settings

ALLOWED_EXTENSIONS = {".mp3", ".wav", ".m4a", ".ogg", ".flac"}

ALLOWED_MIME_TYPES = {
    "audio/wav",
    "audio/x-wav",
    "audio/wave",
    "audio/mpeg",
    "audio/mp3",
    "audio/m4a",
    "audio/mp4",
    "audio/x-m4a",
    "audio/ogg",
    "application/ogg",
    "audio/flac",
    "audio/x-flac",
    "application/octet-stream",  # Fallback often sent by browsers
}


class AudioValidationError(HTTPException):
    """Exception raised for invalid audio files."""

    def __init__(self, detail: str):
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


def validate_audio_metadata(
    filename: str,
    content_type: str | None = None,
    size_bytes: int = 0,
) -> None:
    """Validate filename extension, MIME type, and byte length."""
    ext = Path(filename).suffix.lower()
    if not ext or ext not in ALLOWED_EXTENSIONS:
        raise AudioValidationError(
            f"Unsupported audio format '{ext}'. Allowed extensions: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    if size_bytes > settings.max_upload_size_bytes:
        max_mb = settings.max_upload_size_bytes // (1024 * 1024)
        raise AudioValidationError(f"Audio file size exceeds maximum permitted limit of {max_mb} MB")

    if content_type and content_type.lower() not in ALLOWED_MIME_TYPES:
        raise AudioValidationError(f"Unsupported content type '{content_type}'")


def validate_audio_header(header_bytes: bytes, filename: str) -> None:
    """Verify magic header bytes match audio format."""
    ext = Path(filename).suffix.lower()
    if len(header_bytes) < 4:
        raise AudioValidationError("Audio file is empty or too short to contain a valid header")

    if ext == ".wav":
        if not (header_bytes.startswith(b"RIFF") and b"WAVE" in header_bytes[:16]):
            raise AudioValidationError("Corrupted or invalid WAV file header")
    elif ext == ".flac":
        if not header_bytes.startswith(b"fLaC"):
            raise AudioValidationError("Corrupted or invalid FLAC file header")
    elif ext == ".ogg":
        if not header_bytes.startswith(b"OggS"):
            raise AudioValidationError("Corrupted or invalid Ogg Vorbis file header")
    elif ext == ".mp3":
        # ID3 tag or MPEG sync word (0xFF 0xEx)
        is_id3 = header_bytes.startswith(b"ID3")
        is_sync = (header_bytes[0] == 0xFF) and ((header_bytes[1] & 0xE0) == 0xE0)
        if not (is_id3 or is_sync):
            # Some mp3s start with metadata or padding, lenient check
            pass
    elif ext == ".m4a":
        if b"ftyp" not in header_bytes[:32]:
            raise AudioValidationError("Corrupted or invalid M4A/MP4 audio container")
