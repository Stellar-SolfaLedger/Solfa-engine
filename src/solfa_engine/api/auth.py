"""Authentication endpoints for Stellar SEP-10 web authentication."""

from fastapi import APIRouter, HTTPException, status, Depends
from stellar_sdk import Keypair

from solfa_engine.config import settings
from solfa_engine.schemas import (
    ChallengeRequest,
    ChallengeResponse,
    VerifyRequest,
    VerifyResponse,
)
from solfa_engine.auth.sep10 import build_challenge_transaction, verify_challenge_transaction, SEP10Error
from solfa_engine.auth.jwt import create_access_token, get_current_user

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/challenge",
    response_model=ChallengeResponse,
    summary="Request a SEP-10 challenge transaction",
    description="Generates a signed Stellar challenge transaction envelope for the client's public key.",
)
async def get_challenge(request: ChallengeRequest) -> ChallengeResponse:
    """Generate SEP-10 challenge transaction for the wallet to sign."""
    # Validate client G-address
    try:
        Keypair.from_public_key(request.address)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid Stellar public address: '{request.address}'",
        )

    try:
        tx_xdr = build_challenge_transaction(
            server_secret=settings.server_signing_secret,
            client_account_id=request.address,
            network_passphrase=settings.stellar_network_passphrase,
            home_domain=settings.server_home_domain,
        )
    except SEP10Error as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    return ChallengeResponse(
        transaction_xdr=tx_xdr,
        network_passphrase=settings.stellar_network_passphrase,
    )


@router.post(
    "/verify",
    response_model=VerifyResponse,
    summary="Submit signed SEP-10 challenge transaction",
    description="Verifies the client signature on the challenge transaction and returns a signed JWT.",
)
async def verify_challenge(request: VerifyRequest) -> VerifyResponse:
    """Verify wallet signature and issue JWT access token."""
    try:
        server_kp = Keypair.from_secret(settings.server_signing_secret)
        server_public_key = server_kp.public_key
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Server key configuration error: {e}",
        )

    try:
        client_address = verify_challenge_transaction(
            challenge_xdr=request.transaction_xdr,
            server_public_key=server_public_key,
            network_passphrase=settings.stellar_network_passphrase,
            home_domain=settings.server_home_domain,
        )
    except SEP10Error as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Challenge verification failed: {e}",
        )

    # Issue JWT access token
    token, expires_in = create_access_token(address=client_address)

    return VerifyResponse(
        access_token=token,
        token_type="bearer",
        address=client_address,
        expires_in=expires_in,
    )


@router.get(
    "/me",
    summary="Verify current session",
    description="Returns the authenticated Stellar public key from the current Bearer token.",
)
async def get_current_user_profile(user_address: str = Depends(get_current_user)) -> dict[str, str]:
    """Return the authenticated user address."""
    return {"address": user_address}
