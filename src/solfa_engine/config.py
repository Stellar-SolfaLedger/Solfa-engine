"""Application settings and configuration module."""

from pathlib import Path
from typing import Literal
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration settings for SolfaLedger Engine."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # General Service Info
    app_name: str = "SolfaLedger Engine"
    app_version: str = "0.1.0"
    environment: Literal["development", "production", "test"] = "development"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000

    # Authentication & Security
    secret_key: str = Field(
        default="solfaledger-super-secure-jwt-signing-secret-key-32-chars-min",
        description="JWT signature secret key",
    )
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 60
    server_home_domain: str = "solfaledger.app"

    # Server SEP-10 Signing Key (Server identity for challenge auth)
    # Default is a valid testnet test secret key (generate/override in prod)
    server_signing_secret: str = Field(
        default="SB227ZKHEJPMPDW7KQVM5YUV2HR7CDFCATBP67XLL56TK5HBCE4YDAAM",
        description="Server Stellar private key (S...) for signing SEP-10 challenges",
    )

    # Stellar & Soroban
    stellar_network: Literal["TESTNET", "PUBLIC"] = "TESTNET"
    stellar_network_passphrase: str = "Test SDF Network ; September 2015"
    soroban_rpc_url: str = "https://soroban-testnet.stellar.org"
    horizon_url: str = "https://horizon-testnet.stellar.org"

    # SolfaPayments Contract ID (Valid Stellar Soroban Contract Address)
    payments_contract_id: str = "CAAU3BUYOH7464VPCE26ONCSHQRR3O6VLR7SVN5UPDK4ZLMT47EW2Q33"

    # Operator Identity (Used by backend worker to call consume_credit)
    operator_secret_key: str = Field(
        default="SC3DHGTWGGKA5AGSEFWGJGD6YVRAH5HQHUDW7XQFVWU3UQNBDKKFIGU3",
        description="Operator Stellar private key (S...) for calling consume_credit",
    )

    # Storage & Upload Limits
    max_upload_size_bytes: int = 50 * 1024 * 1024  # 50 MB
    storage_dir: Path = Path("data")
    upload_dir: Path = Path("uploads")
    export_dir: Path = Path("exports")
    audio_retention_days: int = 7

    # Rate Limiting & Safety
    rate_limit_per_minute: int = 60
    virus_scan_enabled: bool = False
    virus_scan_webhook_url: str | None = None

    # Async Pipeline & Worker Mode
    worker_mode: Literal["in_process", "celery"] = "in_process"
    database_url: str = "sqlite:///./solfa_engine.db"
    redis_url: str = "redis://localhost:6379/0"

    @property
    def is_mainnet(self) -> bool:
        """Return True if configured for Stellar Public Mainnet."""
        return self.stellar_network == "PUBLIC"


settings = Settings()
