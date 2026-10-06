# SolfaLedger Engine (`solfa-engine`)

> **High-Performance Audio-to-Tonic-Solfa Transcription Backend & Stellar Soroban Bridge**

SolfaLedger Engine is a production-grade Python 3.11 service built with FastAPI, SciPy, NumPy, and ReportLab. It transcribes songs of any musical style into traditional movable-do **tonic solfa notation** (`do re mi fa so la ti do`) and reports musical key, tempo (BPM), time signature, and timing breakdowns. Access is metered and gated on-chain via the **Stellar Soroban `SolfaPayments` smart contract**.

---

## Architecture Overview

```
                      +-----------------------------+
                      |   Stellar Wallet / Client   |
                      +--------------+--------------+
                                     |
               1. SEP-10 Auth        |  2. Audio Upload / URL
               (Sign Challenge)      v
                      +-----------------------------+
                      |    FastAPI Engine Service   |
                      |   /auth, /me, /jobs, export |
                      +--------------+--------------+
                                     |
            +------------------------+------------------------+
            |                                                 |
            v                                                 v
  +-------------------+                             +-------------------+
  | Soroban RPC Check |                             | Audio Pipeline    |
  | can_transcribe()  |                             | (22.05kHz Mono)   |
  +---------+---------+                             +---------+---------+
            | (If approved)                                   |
            v                                                 v
  +-------------------+                             +-------------------+
  | Job Enqueued      |                             | Note Extraction   |
  | Status: PENDING   |                             | Pitch & Onsets    |
  +---------+---------+                             +---------+---------+
            |                                                 |
            +------------------------+------------------------+
                                     |
                                     v
                 +---------------------------------------+
                 |  Music Analysis:                      |
                 |  - Krumhansl-Schmuckler Key Detection |
                 |  - Tempo (BPM) & Time Signature (4/4) |
                 |  - Rhythmic Beat Quantization         |
                 |  - Movable-Do Syllables & Octaves     |
                 |  - Traditional Solfa Layout (: . - |) |
                 +-------------------+-------------------+
                                     |
                                     v
                 +---------------------------------------+
                 |  Operator Credit Settlement:          |
                 |  consume_credit(operator, user, job)  |
                 +-------------------+-------------------+
                                     |
                                     v
                 +---------------------------------------+
                 |  Multi-Format Exporters:              |
                 |  - PDF Sheet Music (ReportLab)        |
                 |  - MusicXML 3.1 (Engraving)           |
                 |  - Plaintext Tonic Solfa Score        |
                 |  - Machine-Readable JSON              |
                 +---------------------------------------+
```

---

## Published OpenAPI Specification

The complete API schema is published at:
- Interactive Swagger UI: [`/docs`](http://localhost:8000/docs)
- Interactive ReDoc: [`/redoc`](http://localhost:8000/redoc)
- Machine-Readable OpenAPI JSON: [`/openapi.json`](http://localhost:8000/openapi.json) and committed as [`openapi.json`](./openapi.json).

---

## Stellar Soroban Contract Integration

| Contract Property | Testnet Value |
| :--- | :--- |
| **Contract ID** | `CAAU3BUYOH7464VPCE26ONCSHQRR3O6VLR7SVN5UPDK4ZLMT47EW2Q33` |
| **Network** | Stellar Testnet (`Test SDF Network ; September 2015`) |
| **RPC Endpoint** | `https://soroban-testnet.stellar.org` |
| **Native Asset (XLM)** | `CDLZFC3SYJYDZT7K67VZ75HPJVIEUVNIXF47ZG2FB2RMQQVU2HHGCYSC` |
| **USDC Testnet Asset** | `CBIELTK6YBZJU5UP2WWQEUCYKLPU6AUNZ2BQ4WWUIE3USSTHZX5C6WD7` |

### On-Chain Billing Flow
1. **Entitlement Verification (`can_transcribe`)**:
   Before accepting any job upload in `POST /jobs`, the backend invokes `can_transcribe(user)` on the Soroban contract. If the user has neither an active subscription nor remaining credits, the server returns `402 Payment Required`.
2. **Operator Credit Deduction (`consume_credit`)**:
   Upon successful audio transcription, the worker executes `consume_credit(operator, user, job_id)` signed with the backend's secret **Operator Key**. If the transaction fails or the network times out, the job status is set to `unbilled` and queued for settlement retry.
3. **No-Charge Overrides (`POST /jobs/{id}/override`)**:
   Users can correct the detected musical key, tempo, or meter and immediately re-render the tonic solfa score without being billed a second time.

---

## API Endpoints

### 1. Authentication (SEP-10 Web Auth)
- `POST /auth/challenge`: Accepts `{ "address": "G..." }`, returns a signed SEP-10 Stellar challenge transaction XDR.
- `POST /auth/verify`: Accepts signed `{ "transaction_xdr": "..." }`, verifies cryptographic Ed25519 signatures, and returns a signed JWT access token.
- `GET /auth/me`: Validates JWT token and returns authenticated G-address.

### 2. Entitlements
- `GET /me/entitlements`: Returns user's on-chain subscription status, expiry timestamp, unlimited status, and remaining credit balance.

### 3. Transcription Jobs
- `POST /jobs`: Multipart audio file upload (`.mp3`, `.wav`, `.m4a`, `.ogg`, `.flac`, max 50 MB) or audio URL. Enforces `can_transcribe` check, runs anti-malware scan, and starts processing.
- `GET /jobs`: Returns paginated history of jobs submitted by the user.
- `GET /jobs/{id}`: Inspects real-time job status and transcription results.
- `POST /jobs/{id}/override`: Re-renders tonic solfa score with user-specified key, tempo, or time signature at zero additional cost.
- `GET /jobs/{id}/export?format=pdf|txt|musicxml|json`: Downloads score in chosen format.

---

## Audio-to-Solfa Transcription Pipeline

1. **Audio Ingestion & Normalization (`audio.py`)**:
   Converts input audio stream to single-channel (mono), resamples to **22.05 kHz**, and normalizes peak amplitude with 5% headroom. Non-WAV formats are processed via `ffmpeg`.
2. **Pitch & Onset Extraction (`pitch.py`)**:
   Applies normalized autocorrelation with parabolic peak refinement across musical frequencies (65 Hz to 1200 Hz). Consecutive stable frames are segmented into discrete note events with MIDI pitch, start time, and duration.
3. **Key & Mode Detection (`key_detector.py`)**:
   Calculates the 12-tone chroma pitch-class distribution and correlates against **Krumhansl-Schmuckler** major and minor probe tone profiles using Pearson's correlation coefficient $r$.
4. **Tempo & Meter Detection (`rhythm.py`)**:
   Analyzes Inter-Onset Intervals (IOI) to estimate BPM and computes downbeat periodicity to classify time signature (`4/4`, `3/4`, `2/4`, `6/8`).
5. **Rhythmic Quantization (`quantizer.py`)**:
   Snaps note timings to a musical grid (quarter, eighth, sixteenth notes) and segments the score into chronological bar measures.
6. **Movable-Do Solfa Mapping (`solfa_mapper.py`)**:
   Maps pitch class intervals relative to the detected tonic:
   - Diatonic: `d` (do), `r` (re), `m` (mi), `f` (fa), `s` (so), `l` (la), `t` (ti).
   - Chromatic inflections: `di`, `ri`, `fi`, `si`, `li` / `ra`, `me`, `se`, `le`, `te`.
   - Octave registers: `d` (center), `d1` (higher), `d,` (lower).
7. **Traditional Layout Renderer (`renderer.py`)**:
   Formats measures using standard tonic solfa layout notation:
   - Bar line: `|`
   - Beat mark: `:`
   - Half-beat division: `.`
   - Sustain/hold: `-`
   - Final double bar: `||`

---

## Local Development & Testing

### Prerequisites
- Python 3.11+
- `ffmpeg` (for multi-format audio conversion)

### Setup & Run
```bash
# 1. Clone repository
git clone https://github.com/Stellar-SolfaLedger/Solfa-engine.git
cd Solfa-engine

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: .\venv\Scripts\Activate.ps1

# 3. Install dependencies
pip install -e ".[dev]"

# 4. Copy environment configuration
cp .env.example .env

# 5. Run test suite
pytest -v

# 6. Start API server (In-Process Worker Mode)
uvicorn solfa_engine.main:app --reload --host 0.0.0.0 --port 8000

# 7. (Optional) Run with Distributed Celery + Redis Worker
# Set WORKER_MODE=celery in .env, start Redis, and launch:
celery -A solfa_engine.worker.celery_app worker --loglevel=info
celery -A solfa_engine.worker.celery_app beat --loglevel=info
```

### Docker
```bash
# Build and run containerized service with Redis
docker-compose up --build
```

---

## Security & Operational Safeguards

- **No Client Entitlement Trust**: The engine never trusts client claims about credits or subscription validity. All access is verified directly against the Soroban contract.
- **Wallet-Bound JWTs**: Tokens are cryptographically bound to the user's Stellar public key with short expiry (60 minutes).
- **Anti-Malware & File Validation**: Uploads are restricted to 50 MB, format-checked by magic byte headers, and checked against security scan hooks.
- **Automatic Data Retention**: Audio files and temporary export artifacts are automatically purged after $N$ days (`AUDIO_RETENTION_DAYS=7`).
- **Sliding-Window Rate Limiting**: Protects against denial-of-service attempts with standard 60 req/min limits and `Retry-After` response headers.
- **Live Soroban Operator Settlement**: Background worker uses the `OPERATOR_SECRET_KEY` to assemble, simulate, footprint, sign, and submit `consume_credit` transactions to Soroban RPC, with automatic fallback and retry if the network is temporarily congested.
- **Worker Scalability**: Supports both in-process `asyncio.create_task` and enterprise distributed queueing with `Celery + Redis` (`WORKER_MODE=celery`).
- **Unbilled Job Auto-Recovery**: Periodic background task in FastAPI lifespan and Celery Beat periodically checks for unbilled transcriptions and re-attempts contract credit deduction until settlement succeeds.
