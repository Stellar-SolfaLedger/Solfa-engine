"""In-memory sliding-window rate limiter for API endpoints."""

from collections import defaultdict
import time
import threading
from fastapi import HTTPException, Request, status
from solfa_engine.config import settings


class RateLimiter:
    """Thread-safe sliding window rate limiter."""

    def __init__(self, requests_per_minute: int | None = None):
        self.limit = requests_per_minute or settings.rate_limit_per_minute
        self._lock = threading.Lock()
        self._history: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, client_key: str) -> tuple[bool, int]:
        """
        Check if client_key has remaining request capacity.

        Returns:
            (allowed: bool, retry_after_seconds: int)
        """
        now = time.time()
        window_start = now - 60.0

        with self._lock:
            # Filter timestamps outside the 60 second window
            timestamps = [t for t in self._history[client_key] if t > window_start]
            if len(timestamps) >= self.limit:
                oldest = timestamps[0]
                retry_after = max(1, int(60.0 - (now - oldest)))
                self._history[client_key] = timestamps
                return False, retry_after

            timestamps.append(now)
            self._history[client_key] = timestamps
            return True, 0

    def reset(self) -> None:
        """Clear rate limit history (used for tests)."""
        with self._lock:
            self._history.clear()


limiter = RateLimiter()


async def check_rate_limit(request: Request) -> None:
    """FastAPI dependency to rate limit requests based on client IP or auth header."""
    client_ip = request.client.host if request.client else "unknown"
    auth_header = request.headers.get("Authorization", "")
    key = f"{client_ip}:{auth_header[:16]}" if auth_header else client_ip

    allowed, retry_after = limiter.is_allowed(key)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Try again in {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)},
        )
