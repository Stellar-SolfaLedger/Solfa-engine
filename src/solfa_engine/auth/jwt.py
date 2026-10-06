"""JWT token issuance, verification, and FastAPI authentication dependencies."""

from datetime import datetime, timezone, timedelta
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from solfa_engine.config import settings
from solfa_engine.schemas import JWTPayload

security_scheme = HTTPBearer(auto_error=True)
optional_security_scheme = HTTPBearer(auto_error=False)


def create_access_token(address: str, expires_delta: timedelta | None = None) -> tuple[str, int]:
    """
    Issue a signed JWT access token bound to a Stellar public key (G-address).

    Returns:
        (encoded_token_str, expires_in_seconds)
    """
    if expires_delta is None:
        expires_delta = timedelta(minutes=settings.jwt_expiration_minutes)

    now = datetime.now(timezone.utc)
    expire = now + expires_delta
    expires_in_sec = int(expires_delta.total_seconds())

    payload = {
        "sub": address,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "iss": settings.server_home_domain,
    }

    token = jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)
    return token, expires_in_sec


def decode_access_token(token: str) -> JWTPayload:
    """
    Decode and validate a JWT access token.
    Raises HTTPException 401 if invalid or expired.
    """
    try:
        data = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm],
            issuer=settings.server_home_domain,
        )
        return JWTPayload(
            sub=data["sub"],
            exp=data["exp"],
            iat=data["iat"],
            iss=data["iss"],
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except (jwt.InvalidTokenError, Exception) as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication token: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
) -> str:
    """
    FastAPI dependency: Extract and verify Bearer JWT from Authorization header.
    Returns the authenticated user's Stellar public key (G...).
    """
    token = credentials.credentials
    payload = decode_access_token(token)
    return payload.sub


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(optional_security_scheme),
) -> str | None:
    """
    FastAPI dependency: Optional authentication; returns user address or None.
    """
    if not credentials:
        return None
    try:
        payload = decode_access_token(credentials.credentials)
        return payload.sub
    except HTTPException:
        return None
