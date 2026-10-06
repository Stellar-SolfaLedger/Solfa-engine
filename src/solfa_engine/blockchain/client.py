"""Soroban JSON-RPC client and transaction submission interface."""

import logging
from typing import Any
import httpx
from stellar_sdk import Keypair

from solfa_engine.config import settings

logger = logging.getLogger(__name__)


class SorobanRPCError(Exception):
    """Raised when Soroban RPC call returns an error or failure."""
    pass


class SorobanClient:
    """JSON-RPC 2.0 client for querying and invoking Soroban smart contracts."""

    def __init__(
        self,
        rpc_url: str | None = None,
        network_passphrase: str | None = None,
        contract_id: str | None = None,
    ):
        self.rpc_url = rpc_url or settings.soroban_rpc_url
        self.network_passphrase = network_passphrase or settings.stellar_network_passphrase
        self.contract_id = contract_id or settings.payments_contract_id
        self._request_id = 0

    async def _call_rpc(self, method: str, params: dict[str, Any] | list[Any] | None = None) -> Any:
        """Execute a JSON-RPC 2.0 POST request."""
        self._request_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params or {},
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                response = await client.post(self.rpc_url, json=payload)
                response.raise_for_status()
                data = response.json()
            except httpx.HTTPError as e:
                logger.warning(f"HTTP error connecting to Soroban RPC {self.rpc_url}: {e}")
                raise SorobanRPCError(f"Soroban RPC connection error: {e}") from e

        if "error" in data:
            err = data["error"]
            raise SorobanRPCError(f"Soroban RPC error [{err.get('code')}]: {err.get('message')}")

        return data.get("result")

    async def get_health(self) -> dict[str, Any]:
        """Check Soroban RPC server health status."""
        return await self._call_rpc("getHealth")

    async def get_network(self) -> dict[str, Any]:
        """Fetch network information and passphrase from the RPC server."""
        return await self._call_rpc("getNetwork")

    async def simulate_transaction(self, transaction_xdr: str) -> dict[str, Any]:
        """Simulate a transaction against the current ledger state."""
        return await self._call_rpc("simulateTransaction", {"transaction": transaction_xdr})

    async def send_transaction(self, transaction_xdr: str) -> dict[str, Any]:
        """Submit a signed transaction to the Soroban network."""
        return await self._call_rpc("sendTransaction", {"transaction": transaction_xdr})

    async def get_transaction(self, tx_hash: str) -> dict[str, Any]:
        """Fetch status and result of a submitted transaction by hash."""
        return await self._call_rpc("getTransaction", {"hash": tx_hash})

    async def get_latest_ledger(self) -> dict[str, Any]:
        """Fetch the latest ledger sequence and protocol version."""
        return await self._call_rpc("getLatestLedger")
