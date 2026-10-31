import time
from collections import defaultdict
from threading import Lock

from app.exceptions import AppError


class RateLimitedError(AppError):
    status_code = 429

    def __init__(self, detail: str = "Too many attempts. Please wait before trying again."):
        super().__init__(detail)


class SlidingWindowLimiter:
    """
    In-process, in-memory sliding-window limiter - defense-in-depth against
    credential stuffing on /auth/login, nothing more. Explicitly NOT a
    complete solution: state is per-process, so with more than one backend
    replica behind a load balancer an attacker is only throttled against
    whichever instance happens to receive each request, not globally.
    Before any multi-instance production deployment, replace this with a
    shared store (Redis INCR + TTL is the standard pattern) - see
    docs/DEPLOYMENT.md's "Remaining risks" section. Do not remove this
    comment when swapping the implementation; the next engineer needs to
    know why a single-instance limiter is insufficient.
    """

    def __init__(self, *, max_attempts: int, window_seconds: float):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._attempts: dict[str, list[float]] = defaultdict(list)
        self._lock = Lock()

    def check(self, key: str) -> None:
        """Raises RateLimitedError if `key` has already made max_attempts
        within the window; otherwise records this attempt."""
        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            attempts = [t for t in self._attempts[key] if t > cutoff]
            if len(attempts) >= self.max_attempts:
                self._attempts[key] = attempts
                raise RateLimitedError()
            attempts.append(now)
            self._attempts[key] = attempts

    def reset(self, key: str) -> None:
        with self._lock:
            self._attempts.pop(key, None)


# 10 attempts per 5 minutes per (email, client IP) - generous enough not to
# lock out a real user who mistypes a password a few times, tight enough to
# meaningfully slow a credential-stuffing script.
login_limiter = SlidingWindowLimiter(max_attempts=10, window_seconds=300)
