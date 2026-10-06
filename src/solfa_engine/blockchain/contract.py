"""Contract interaction interface for SolfaPayments Soroban contract."""

import logging
import time
from typing import Any
import httpx
from stellar_sdk import Account, Keypair, Network, TransactionBuilder, scval, xdr
from stellar_sdk.operation import InvokeHostFunction

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

    async def _get_account_sequence(self, account_address: str) -> int:
        """Fetch current sequence number for an account from Horizon or RPC."""
        try:
            async with httpx.AsyncClient(timeout=8.0) as http_client:
                resp = await http_client.get(f"{settings.horizon_url}/accounts/{account_address}")
                if resp.status_code == 200:
                    data = resp.json()
                    return int(data.get("sequence", 0))
        except Exception as e:
            logger.debug(f"Horizon sequence query fallback for {account_address}: {e}")
        return 1

    async def _simulate_call(
        self,
        function_name: str,
        args: list[Any],
        caller_address: str | None = None,
    ) -> Any:
        """
        Simulate a contract function invocation via Soroban RPC and return the native decoded result.
        """
        caller = caller_address or "GBBD47IF6LWK7P7MDEVSCWR7DPUWV3NY3DTQEVFL4NAT4AQH3ZLLFLA5"
        
        hf = xdr.HostFunction(
            type=xdr.HostFunctionType.HOST_FUNCTION_TYPE_INVOKE_CONTRACT,
            invoke_contract=xdr.InvokeContractArgs(
                contract_address=scval.to_address(self.contract_id),
                function_name=scval.to_symbol(function_name),
                args=args,
            ),
        )
        op = InvokeHostFunction(host_function=hf, source=caller)

        # Build dummy transaction with sequence -1 for simulation
        account = Account(account=caller, sequence=-1)
        tx = (
            TransactionBuilder(
                account,
                network_passphrase=self.client.network_passphrase,
                base_fee=100,
            )
            .add_operation(op)
            .set_timeout(30)
            .build()
        )

        sim_result = await self.client.simulate_transaction(tx.to_xdr())
        if not sim_result:
            raise SorobanRPCError("Empty simulation response")

        if "error" in sim_result:
            raise SorobanRPCError(f"Simulation error: {sim_result.get('error')}")

        results = sim_result.get("results")
        if not results or len(results) == 0:
            return None

        ret_xdr = results[0].get("xdr")
        if not ret_xdr:
            return None

        val = xdr.SCVal.from_xdr(ret_xdr)
        return scval.to_native(val)

    async def can_transcribe(self, user_address: str) -> bool:
        """
        Check if user is authorized to transcribe (active subscription or positive credits).
        Queries contract `can_transcribe(user)` via RPC simulation.
        """
        # 1. Check test/mock override first
        mock_data = get_mock_user_entitlements(user_address)
        if mock_data is not None:
            return mock_data["can_transcribe"]

        # 2. Query live Soroban RPC via simulation
        try:
            res = await self._simulate_call(
                function_name="can_transcribe",
                args=[scval.to_address(user_address)],
                caller_address=user_address,
            )
            if isinstance(res, bool):
                return res
        except Exception as e:
            logger.warning(f"Live Soroban RPC call for can_transcribe({user_address}) fallback: {e}")

        # In development or test without seeded mock, default to permit
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

        # Live RPC queries
        can_trans = False
        credits_rem = 0
        has_active_sub = False
        plan_id = None
        expires_at = None
        is_unlimited = False

        try:
            # 1. can_transcribe
            can_trans = await self.can_transcribe(user_address)

            # 2. get_credits
            credits_val = await self._simulate_call(
                function_name="get_credits",
                args=[scval.to_address(user_address)],
                caller_address=user_address,
            )
            if isinstance(credits_val, int):
                credits_rem = credits_val

            # 3. get_subscription
            sub_val = await self._simulate_call(
                function_name="get_subscription",
                args=[scval.to_address(user_address)],
                caller_address=user_address,
            )
            if sub_val and isinstance(sub_val, (dict, list)):
                if isinstance(sub_val, dict):
                    plan_id = sub_val.get("plan_id")
                    expires_at = sub_val.get("expires_at")
                elif isinstance(sub_val, list) and len(sub_val) >= 2:
                    plan_id = sub_val[0]
                    expires_at = sub_val[1]

                if expires_at and expires_at > int(time.time()):
                    has_active_sub = True
                    if plan_id == 2:  # Pro plan ID 2 is unlimited
                        is_unlimited = True

            return EntitlementsResponse(
                user=user_address,
                can_transcribe=can_trans or credits_rem > 0 or has_active_sub,
                has_active_subscription=has_active_sub,
                subscription_plan_id=plan_id,
                subscription_expires_at=expires_at,
                is_unlimited=is_unlimited,
                credits_remaining=credits_rem,
            )
        except Exception as e:
            logger.warning(f"Error fetching live entitlements for {user_address}: {e}")

        # Fallback for development/testing
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

        # Live Soroban network execution using backend OPERATOR key
        try:
            operator_kp = Keypair.from_secret(settings.operator_secret_key)
            
            hf = xdr.HostFunction(
                type=xdr.HostFunctionType.HOST_FUNCTION_TYPE_INVOKE_CONTRACT,
                invoke_contract=xdr.InvokeContractArgs(
                    contract_address=scval.to_address(self.contract_id),
                    function_name=scval.to_symbol("consume_credit"),
                    args=[
                        scval.to_address(user_address),
                        scval.to_string(job_id),
                    ],
                ),
            )
            op = InvokeHostFunction(host_function=hf, source=operator_kp.public_key)

            seq = await self._get_account_sequence(operator_kp.public_key)
            account = Account(account=operator_kp.public_key, sequence=seq)

            tx = (
                TransactionBuilder(
                    account,
                    network_passphrase=self.client.network_passphrase,
                    base_fee=100,
                )
                .add_operation(op)
                .set_timeout(30)
                .build()
            )

            sim_result = await self.client.simulate_transaction(tx.to_xdr())
            if not sim_result or "error" in sim_result:
                logger.warning(f"Simulation of consume_credit failed: {sim_result}")
                if settings.environment in ("development", "test"):
                    return True
                return False

            min_fee = int(sim_result.get("minResourceFee", 100))
            tx_data_xdr = sim_result.get("transactionData")
            if tx_data_xdr:
                tx.soroban_data = xdr.SorobanTransactionData.from_xdr(tx_data_xdr)
            tx.fee = tx.fee + min_fee

            tx.sign(operator_kp)
            send_res = await self.client.send_transaction(tx.to_xdr())
            tx_status = send_res.get("status")
            if tx_status in ("PENDING", "SUCCESS"):
                logger.info(f"consume_credit successfully submitted on-chain: tx {send_res.get('hash')}")
                return True

            logger.warning(f"consume_credit submission returned {tx_status}: {send_res}")
            return False
        except Exception as e:
            logger.warning(f"Operator consume_credit failed against live network: {e}")
            if settings.environment in ("development", "test"):
                return True
            return False
