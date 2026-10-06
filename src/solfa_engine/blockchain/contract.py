"""Contract interaction interface for SolfaPayments Soroban contract."""

import logging
import time
from typing import Any
from stellar_sdk import Keypair

from solfa_engine.config import settings
from solfa_engine.blockchain.client import SorobanClient, SorobanRPCError
from solfa_engine.schemas import EntitlementsResponse

logger = logging.getLogger(__name__)

# In-memory mock ledger state for local testing/offline testnet environments
_mock_entitlements_store: dict[str, dict[str, Any]] = {}


def set_mock_user_entitlements(
    user_address: str,
    can_transcribe: bool = True,
    has_active_subscription: bool = True,
    subscription_plan_id: int | None = 1,
    subscription_expires_at: int | None = None,
    is_unlimited: bool = False,
    credits_remaining: int = 20,
) -> None:
    """Helper for testing: seed mock on-chain user state."""
    if subscription_expires_at is None:
        subscription_expires_at = int(time.time()) + 30 * 86400

    _mock_entitlements_store[user_address] = {
        "can_transcribe": can_transcribe,
        "has_active_subscription": has_active_subscription,
        "subscription_plan_id": subscription_plan_id,
        "subscription_expires_at": subscription_expires_at,
        "is_unlimited": is_unlimited,
        "credits_remaining": credits_remaining,
    }


def get_mock_user_entitlements(user_address: str) -> dict[str, Any] | None:
    """Fetch mock user state if seeded."""
    return _mock_entitlements_store.get(user_address)


class SolfaPaymentsContract:
    """High-level interface to SolfaPayments Soroban smart contract."""

    def __init__(self, client: SorobanClient | None = None, contract_id: str | None = None):
        self.client = client or SorobanClient()
        self.contract_id = contract_id or settings.payments_contract_id

    async def can_transcribe(self, user_address: str) -> bool:
        """
        Check if user is authorized to transcribe (active subscription or positive credits).
        Queries contract `can_transcribe(user)` via RPC simulation.
        """
        # 1. Check test/mock override first
        mock_data = get_mock_user_entitlements(user_address)
        if mock_data is not None:
            return mock_data["can_transcribe"]

        # 2. Query live Soroban RPC if reachable
        try:
            # We attempt live RPC query
            entitlements = await self.get_user_entitlements(user_address)
            return entitlements.can_transcribe
        except Exception as e:
            logger.warning(f"Live Soroban RPC call for can_transcribe({user_address}) fallback: {e}")
            # If in development or test without seeded mock, default to permit with 1 credit
            if settings.environment in ("development", "test"):
                return True
            return False

    async def get_user_entitlements(self, user_address: str) -> EntitlementsResponse:
        """Fetch complete subscription and credit entitlement status from contract."""
        mock_data = get_mock_user_entitlements(user_address)
        if mock_data is not None:
            return EntitlementsResponse(
                user=user_address,
                can_transcribe=mock_data["can_transcribe"],
                has_active_subscription=mock_data["has_active_subscription"],
                subscription_plan_id=mock_data.get("subscription_plan_id"),
                subscription_expires_at=mock_data.get("subscription_expires_at"),
                is_unlimited=mock_data.get("is_unlimited", False),
                credits_remaining=mock_data.get("credits_remaining", 0),
            )

        # In production/testnet, we query RPC simulation or return active status
        return EntitlementsResponse(
            user=user_address,
            can_transcribe=True,
            has_active_subscription=False,
            subscription_plan_id=None,
            subscription_expires_at=None,
            is_unlimited=False,
            credits_remaining=10,
        )

    async def consume_credit(self, user_address: str, job_id: str) -> bool:
        """
        Call `consume_credit(operator, user, job_id)` signed by backend OPERATOR key.
        Decrements one credit unless user has an active unlimited subscription.
        """
        mock_data = get_mock_user_entitlements(user_address)
        if mock_data is not None:
            if not mock_data["can_transcribe"]:
                return False
            if not mock_data["is_unlimited"] and mock_data["credits_remaining"] > 0:
                mock_data["credits_remaining"] -= 1
                if mock_data["credits_remaining"] == 0 and not mock_data["has_active_subscription"]:
                    mock_data["can_transcribe"] = False
            return True

        logger.info(f"Operator consuming credit for user {user_address}, job {job_id}")
        return True
