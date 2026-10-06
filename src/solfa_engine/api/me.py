"""User entitlements and account status endpoints."""

from fastapi import APIRouter, Depends
from solfa_engine.auth.jwt import get_current_user
from solfa_engine.blockchain.contract import SolfaPaymentsContract
from solfa_engine.schemas import EntitlementsResponse

router = APIRouter(prefix="/me", tags=["User Entitlements"])


@router.get(
    "/entitlements",
    response_model=EntitlementsResponse,
    summary="Get user subscription and credit entitlements",
    description="Reads live on-chain subscription status, expiry, and remaining credits from the SolfaPayments contract.",
)
async def get_my_entitlements(
    user_address: str = Depends(get_current_user),
) -> EntitlementsResponse:
    """Fetch current user's on-chain transcription entitlements."""
    contract = SolfaPaymentsContract()
    return await contract.get_user_entitlements(user_address)
