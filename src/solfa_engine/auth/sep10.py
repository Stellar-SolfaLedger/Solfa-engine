"""Stellar SEP-10 authentication challenge transaction creation and verification."""

import base64
import os
import time
from stellar_sdk import Account, Keypair, ManageData, Network, TransactionBuilder, TransactionEnvelope
from stellar_sdk.exceptions import BadSignatureError


class SEP10Error(Exception):
    """Raised when SEP-10 challenge creation or verification fails."""
    pass


def build_challenge_transaction(
    server_secret: str,
    client_account_id: str,
    network_passphrase: str,
    home_domain: str = "solfaledger.app",
    timeout_seconds: int = 300,
) -> str:
    """
    Build a SEP-10 challenge transaction envelope signed by the server.

    Args:
        server_secret: Server Stellar private key (S...).
        client_account_id: Client public address (G...).
        network_passphrase: Stellar network passphrase.
        home_domain: Server domain name.
        timeout_seconds: Number of seconds the challenge is valid for.

    Returns:
        Base64 encoded TransactionEnvelope XDR.
    """
    try:
        server_keypair = Keypair.from_secret(server_secret)
        # Validate client address
        Keypair.from_public_key(client_account_id)
    except Exception as e:
        raise SEP10Error(f"Invalid Stellar keys: {e}") from e

    now = int(time.time())
    time_bounds = (now, now + timeout_seconds)

    # Server dummy source account with sequence -1 so TransactionBuilder produces sequence 0 per SEP-10
    server_account = Account(account=server_keypair.public_key, sequence=-1)

    # Cryptographically random 48-byte nonce encoded as base64 string
    nonce = base64.b64encode(os.urandom(48)).decode("utf-8")
    data_key = f"{home_domain} auth"

    # ManageData operation on behalf of client
    manage_data_op = ManageData(
        data_name=data_key,
        data_value=nonce.encode("utf-8"),
        source=client_account_id,
    )

    builder = (
        TransactionBuilder(
            source_account=server_account,
            network_passphrase=network_passphrase,
            base_fee=100,
        )
        .add_time_bounds(min_time=time_bounds[0], max_time=time_bounds[1])
        .append_operation(manage_data_op)
    )

    tx = builder.build()
    tx.sign(server_keypair)

    return tx.to_xdr()


def verify_challenge_transaction(
    challenge_xdr: str,
    server_public_key: str,
    network_passphrase: str,
    home_domain: str = "solfaledger.app",
) -> str:
    """
    Verify that the challenge transaction envelope is properly signed by both
    the server and the client, is within valid timebounds, and matches home_domain.

    Args:
        challenge_xdr: Base64-encoded TransactionEnvelope XDR.
        server_public_key: Expected server public key (G...).
        network_passphrase: Stellar network passphrase.
        home_domain: Expected server domain.

    Returns:
        Verified client public key (G...).
    """
    try:
        envelope = TransactionEnvelope.from_xdr(challenge_xdr, network_passphrase=network_passphrase)
        tx = envelope.transaction
    except Exception as e:
        raise SEP10Error(f"Failed to parse transaction envelope XDR: {e}") from e

    # 1. Verify sequence number is 0 (or 1 depending on builder)
    if tx.sequence not in (0, 1):
        raise SEP10Error("Transaction sequence number must be 0")

    # 2. Verify source account is server public key
    tx_source_id = getattr(tx.source, "account_id", str(tx.source))
    if tx_source_id != server_public_key:
        raise SEP10Error(f"Transaction source account mismatch: expected {server_public_key}, got {tx_source_id}")

    # 3. Verify time bounds
    now = int(time.time())
    tb = getattr(tx, "time_bounds", None)
    if not tb and hasattr(tx, "preconditions") and tx.preconditions:
        tb = tx.preconditions.time_bounds

    if not tb:
        raise SEP10Error("Transaction must have time bounds")
    if tb.min_time > now:
        raise SEP10Error("Transaction is not yet valid")
    if tb.max_time < now:
        raise SEP10Error("Transaction challenge has expired")

    # 4. Verify operations
    if len(tx.operations) != 1:
        raise SEP10Error("Challenge transaction must contain exactly 1 operation")

    op = tx.operations[0]
    if not isinstance(op, ManageData):
        raise SEP10Error("First operation must be a ManageData operation")

    expected_data_key = f"{home_domain} auth"
    if op.data_name != expected_data_key:
        raise SEP10Error(f"Operation data name mismatch: expected '{expected_data_key}', got '{op.data_name}'")

    op_source = op.source
    client_address = getattr(op_source, "account_id", str(op_source)) if op_source else None
    if not client_address:
        raise SEP10Error("ManageData operation must have client source account specified")

    # 5. Verify server signature
    tx_hash = envelope.hash()
    server_kp = Keypair.from_public_key(server_public_key)
    server_verified = False

    for sig in envelope.signatures:
        try:
            server_kp.verify(tx_hash, sig.signature)
            server_verified = True
            break
        except (BadSignatureError, Exception):
            continue

    if not server_verified:
        raise SEP10Error("Transaction was not signed by server")

    # 6. Verify client signature
    client_kp = Keypair.from_public_key(client_address)
    client_verified = False

    for sig in envelope.signatures:
        try:
            client_kp.verify(tx_hash, sig.signature)
            client_verified = True
            break
        except (BadSignatureError, Exception):
            continue

    if not client_verified:
        raise SEP10Error(f"Transaction missing valid signature from client {client_address}")

    return client_address
