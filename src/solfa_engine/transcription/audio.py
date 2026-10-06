"""Audio loading, decoding, normalization, and synthesis utilities."""

import logging
import math
from pathlib import Path
import shutil
import subprocess
import wave
import numpy as np
import scipy.signal

logger = logging.getLogger(__name__)

TARGET_SAMPLE_RATE = 22050


def load_and_normalize_audio(file_path: Path, target_sr: int = TARGET_SAMPLE_RATE) -> tuple[np.ndarray, int]:
    """
    Load an audio file, convert to mono, resample to target_sr (22.05 kHz),
    and normalize amplitude to [-1.0, 1.0].

    Returns:
        (audio_array: np.ndarray, sample_rate: int)
    """
    suffix = file_path.suffix.lower()

    # If file is not WAV or if ffmpeg is available and non-wav, attempt ffmpeg conversion
    if suffix != ".wav" and shutil.which("ffmpeg"):
        wav_converted = file_path.with_suffix(".norm.wav")
        try:
            cmd = [
                "ffmpeg",
                "-y",
                "-i", str(file_path),
                "-ac", "1",
                "-ar", str(target_sr),
                str(wav_converted),
            ]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            audio, sr = _read_wav_file(wav_converted)
            if wav_converted.exists():
                wav_converted.unlink()
            return audio, sr
        except Exception as e:
            logger.warning(f"ffmpeg conversion failed: {e}")

    # Standard WAV reader
    return _read_wav_file(file_path, target_sr)


def _read_wav_file(file_path: Path, target_sr: int = TARGET_SAMPLE_RATE) -> tuple[np.ndarray, int]:
    """Read a WAV file using stdlib wave module and resample to target_sr."""
    with wave.open(str(file_path), "rb") as wf:
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        framerate = wf.getframerate()
        n_frames = wf.getnframes()
        raw_bytes = wf.readframes(n_frames)

    # Decode bytes to numpy
    if sampwidth == 1:
        data = np.frombuffer(raw_bytes, dtype=np.uint8).astype(np.float32)
        data = (data - 128.0) / 128.0
    elif sampwidth == 2:
        data = np.frombuffer(raw_bytes, dtype=np.int16).astype(np.float32) / 32768.0
    elif sampwidth == 3:
        # 24-bit PCM
        raw_int = np.zeros(n_frames * n_channels, dtype=np.int32)
        for i in range(len(raw_int)):
            b = raw_bytes[i * 3 : (i + 1) * 3]
            raw_int[i] = int.from_bytes(b, byteorder="little", signed=True)
        data = raw_int.astype(np.float32) / 8388608.0
    elif sampwidth == 4:
        data = np.frombuffer(raw_bytes, dtype=np.int32).astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f"Unsupported sample bit width: {sampwidth * 8}-bit")

    # Handle multi-channel to mono mix
    if n_channels > 1:
        data = data.reshape(-1, n_channels)
        data = np.mean(data, axis=1)

    # Resample if needed
    if framerate != target_sr and len(data) > 0:
        gcd = math.gcd(framerate, target_sr)
        up = target_sr // gcd
        down = framerate // gcd
        data = scipy.signal.resample_poly(data, up, down).astype(np.float32)

    # Peak normalization with slight headroom
    peak = np.max(np.abs(data)) if len(data) > 0 else 0.0
    if peak > 0.001:
        data = (data / peak) * 0.95

    return data.astype(np.float32), target_sr


def write_wav(output_path: Path, audio: np.ndarray, sample_rate: int = TARGET_SAMPLE_RATE) -> None:
    """Write float32 numpy audio array as 16-bit PCM mono WAV file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    # Clip and convert to int16
    clipped = np.clip(audio, -1.0, 1.0)
    int16_data = (clipped * 32767.0).astype(np.int16)

    with wave.open(str(output_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(int16_data.tobytes())


def synthesize_tone(
    frequency_hz: float,
    duration_sec: float,
    sample_rate: int = TARGET_SAMPLE_RATE,
    amplitude: float = 0.8,
) -> np.ndarray:
    """Generate a clean sinusoidal tone with smooth onset/release windowing."""
    n_samples = int(sample_rate * duration_sec)
    t = np.linspace(0, duration_sec, n_samples, endpoint=False)
    # Add gentle harmonics (fundamental + 2nd + 3rd harmonic for musical timbre)
    sine = (
        0.7 * np.sin(2 * np.pi * frequency_hz * t)
        + 0.2 * np.sin(2 * np.pi * 2 * frequency_hz * t)
        + 0.1 * np.sin(2 * np.pi * 3 * frequency_hz * t)
    )

    # Apply 10ms Hann envelope at start/end to avoid click
    fade_len = min(int(0.01 * sample_rate), n_samples // 4)
    if fade_len > 0:
        fade_in = 0.5 * (1.0 - np.cos(np.pi * np.arange(fade_len) / fade_len))
        fade_out = fade_in[::-1]
        sine[:fade_len] *= fade_in
        sine[-fade_len:] *= fade_out

    return (sine * amplitude).astype(np.float32)
