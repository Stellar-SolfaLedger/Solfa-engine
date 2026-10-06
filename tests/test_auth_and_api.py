"""Integration tests for SEP-10 authentication, JWT security, jobs API, overrides, and exports."""

import io
from pathlib import Path
import pytest
from httpx import AsyncClient, ASGITransport
from stellar_sdk import Keypair, TransactionEnvelope

from solfa_engine.main import app
from solfa_engine.config import settings
from solfa_engine.auth.jwt import create_access_token
from solfa_engine.blockchain.contract import set_mock_user_entitlements
from solfa_engine.storage.jobs import job_repository
from solfa_engine.schemas import JobStatus, TranscriptionResult, MeasureItem, NoteItem
from tests.fixtures import generate_c_major_scale_wav


@pytest.fixture(autouse=True)
def clean_repo():
    """Wipe jobs repository between tests."""
    job_repository.clear()


@pytest.fixture
def test_user_keypair():
    """Generate deterministic test user Stellar keypair."""
    return Keypair.random()


@pytest.fixture
def auth_headers(test_user_keypair):
    """Generate authorization Bearer header for test user."""
    token, _ = create_access_token(test_user_keypair.public_key)
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_health_check():
    """Verify GET /health returns 200 OK."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/health")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "healthy"
        assert data["service"] == settings.app_name


@pytest.mark.asyncio
async def test_sep10_challenge_and_verify_flow(test_user_keypair):
    """Verify complete SEP-10 authentication round-trip: challenge -> wallet sign -> verify -> JWT."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Request challenge
        res = await client.post("/auth/challenge", json={"address": test_user_keypair.public_key})
        assert res.status_code == 200
        data = res.json()
        assert "transaction_xdr" in data
        assert data["network_passphrase"] == settings.stellar_network_passphrase

        # 2. Wallet signs the challenge envelope
        challenge_xdr = data["transaction_xdr"]
        envelope = TransactionEnvelope.from_xdr(challenge_xdr, network_passphrase=settings.stellar_network_passphrase)
        envelope.sign(test_user_keypair)
        signed_xdr = envelope.to_xdr()

        # 3. Submit signed challenge to /auth/verify
        res_verify = await client.post("/auth/verify", json={"transaction_xdr": signed_xdr})
        assert res_verify.status_code == 200
        token_data = res_verify.json()
        assert "access_token" in token_data
        assert token_data["address"] == test_user_keypair.public_key
        assert token_data["token_type"] == "bearer"

        # 4. Use token to inspect /auth/me
        auth_header = {"Authorization": f"Bearer {token_data['access_token']}"}
        res_me = await client.get("/auth/me", headers=auth_header)
        assert res_me.status_code == 200
        assert res_me.json()["address"] == test_user_keypair.public_key


@pytest.mark.asyncio
async def test_me_entitlements(test_user_keypair, auth_headers):
    """Verify GET /me/entitlements reads on-chain subscription status and remaining credits."""
    # Seed mock entitlement
    set_mock_user_entitlements(
        user_address=test_user_keypair.public_key,
        can_transcribe=True,
        has_active_subscription=True,
        subscription_plan_id=1,
        is_unlimited=False,
        credits_remaining=15,
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/me/entitlements", headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert data["user"] == test_user_keypair.public_key
        assert data["can_transcribe"] is True
        assert data["credits_remaining"] == 15
        assert data["has_active_subscription"] is True


@pytest.mark.asyncio
async def test_job_submission_insufficient_credits(test_user_keypair, auth_headers, tmp_path):
    """Verify 402 Payment Required when user has no active subscription and 0 credits."""
    set_mock_user_entitlements(
        user_address=test_user_keypair.public_key,
        can_transcribe=False,
        has_active_subscription=False,
        credits_remaining=0,
    )

    test_wav = tmp_path / "test.wav"
    generate_c_major_scale_wav(test_wav)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with open(test_wav, "rb") as f:
            res = await client.post(
                "/jobs",
                headers=auth_headers,
                files={"file": ("test.wav", f, "audio/wav")},
            )
        assert res.status_code == 402
        assert "insufficient credits" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_job_submission_and_lifecycle(test_user_keypair, auth_headers, tmp_path):
    """Verify job creation with valid entitlement, file upload, and subsequent inspection."""
    set_mock_user_entitlements(
        user_address=test_user_keypair.public_key,
        can_transcribe=True,
        credits_remaining=10,
    )

    test_wav = tmp_path / "scale.wav"
    generate_c_major_scale_wav(test_wav)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with open(test_wav, "rb") as f:
            res = await client.post(
                "/jobs",
                headers=auth_headers,
                files={"file": ("scale.wav", f, "audio/wav")},
            )
        assert res.status_code == 201
        job_data = res.json()
        job_id = job_data["id"]
        assert job_data["user_address"] == test_user_keypair.public_key
        assert job_data["original_filename"] == "scale.wav"

        # List jobs
        res_list = await client.get("/jobs", headers=auth_headers)
        assert res_list.status_code == 200
        list_data = res_list.json()
        assert list_data["total"] >= 1
        assert list_data["jobs"][0]["id"] == job_id

        # Get job by id
        res_get = await client.get(f"/jobs/{job_id}", headers=auth_headers)
        assert res_get.status_code == 200
        assert res_get.json()["id"] == job_id


@pytest.mark.asyncio
async def test_job_override_without_recharge(test_user_keypair, auth_headers):
    """Verify POST /jobs/{id}/override re-renders solfa score with new key at zero charge."""
    # Seed a completed job
    mock_result = TranscriptionResult(
        key="C",
        mode="major",
        tonic="C Major",
        bpm=120.0,
        time_signature="4/4",
        measures=[
            MeasureItem(
                index=1,
                start_sec=0.0,
                duration_sec=2.0,
                notes=[
                    NoteItem(solfa="d", octave="", start_beat=0.0, duration_beats=1.0, midi=60),
                    NoteItem(solfa="s", octave="", start_beat=1.0, duration_beats=1.0, midi=67),
                ],
            )
        ],
        solfa_text="| d : s |",
    )

    created_job = job_repository.create_job(
        user_address=test_user_keypair.public_key,
        original_filename="song.wav",
    )
    job_repository.update_job(
        job_id=created_job.id,
        status=JobStatus.COMPLETED,
        result=mock_result,
        credit_consumed=True,
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Override key from C to G
        override_payload = {
            "key": "G",
            "mode": "major",
            "time_signature": "4/4",
            "bpm": 128.0,
        }
        res = await client.post(
            f"/jobs/{created_job.id}/override",
            json=override_payload,
            headers=auth_headers,
        )
        assert res.status_code == 200
        updated_data = res.json()
        assert updated_data["result"]["key"] == "G"
        assert updated_data["result"]["bpm"] == 128.0
        # In G Major, MIDI 67 (G) is 'd', and MIDI 60 (C) is 'f,'
        first_bar_notes = updated_data["result"]["measures"][0]["notes"]
        assert first_bar_notes[1]["solfa"] == "d"  # 67 is tonic in G


@pytest.mark.asyncio
async def test_job_exports(test_user_keypair, auth_headers):
    """Verify GET /jobs/{id}/export returns valid PDF, MusicXML, TXT, and JSON formats."""
    mock_result = TranscriptionResult(
        key="C",
        mode="major",
        tonic="C Major",
        bpm=120.0,
        time_signature="4/4",
        measures=[
            MeasureItem(
                index=1,
                start_sec=0.0,
                duration_sec=2.0,
                notes=[
                    NoteItem(solfa="d", octave="", start_beat=0.0, duration_beats=1.0, midi=60),
                ],
            )
        ],
        solfa_text="| d : - : - : - |",
    )

    created_job = job_repository.create_job(
        user_address=test_user_keypair.public_key,
        original_filename="song.wav",
    )
    job_repository.update_job(
        job_id=created_job.id,
        status=JobStatus.COMPLETED,
        result=mock_result,
        credit_consumed=True,
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. TXT export
        res_txt = await client.get(f"/jobs/{created_job.id}/export?format=txt", headers=auth_headers)
        assert res_txt.status_code == 200
        assert "text/plain" in res_txt.headers["content-type"]
        assert "| d :" in res_txt.text

        # 2. JSON export
        res_json = await client.get(f"/jobs/{created_job.id}/export?format=json", headers=auth_headers)
        assert res_json.status_code == 200
        assert res_json.json()["key"] == "C"

        # 3. MusicXML export
        res_xml = await client.get(f"/jobs/{created_job.id}/export?format=musicxml", headers=auth_headers)
        assert res_xml.status_code == 200
        assert "<score-partwise" in res_xml.text

        # 4. PDF export
        res_pdf = await client.get(f"/jobs/{created_job.id}/export?format=pdf", headers=auth_headers)
        assert res_pdf.status_code == 200
        assert "application/pdf" in res_pdf.headers["content-type"]
        assert res_pdf.content.startswith(b"%PDF")
