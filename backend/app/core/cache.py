"""
Thin, fail-open cache wrapper around Redis.

Scope rule (deliberately conservative - see callers for the actual
decisions): this cache is for read-heavy, slow-changing, NON-FINANCIAL,
NON-STOCK configuration data only (role/permission catalog, fuel grades,
payment methods, expense categories, shift templates). It must never hold
money, stock, balances, or anything a request reads and then uses to make
a financial/stock decision in the same flow - a stale value there is a
correctness bug, not a performance detail.

Every call here degrades gracefully: if Redis is unreachable, slow to
connect, or simply not configured (REDIS_URL unset, e.g. in the pytest
suite), get() returns None and set()/delete() are no-ops, after logging a
warning. A cache outage must never turn into a request failure - callers
always have a DB fallback path and should treat this purely as a
best-effort accelerator.
"""

import json
import logging
import time
from typing import Any

from app.config import get_settings

logger = logging.getLogger("cynvexa.cache")

_client: Any = None
_client_init_attempted = False
_client_unavailable = False

# Circuit breaker: once a Redis operation actually fails (timeout, refused
# connection, etc.), stop retrying it for this long. Without this, every
# single request during a Redis outage would still pay the full
# socket_connect_timeout on each of get()/set() - turning "Redis is down"
# into "every request is ~1s slower", which defeats the entire point of
# adding a cache for speed. Short deliberately: a real outage still gets
# retried often enough to recover the moment Redis comes back.
_BREAKER_COOLDOWN_SECONDS = 10.0
_breaker_tripped_at: float | None = None


def _breaker_open() -> bool:
    if _breaker_tripped_at is None:
        return False
    if time.monotonic() - _breaker_tripped_at >= _BREAKER_COOLDOWN_SECONDS:
        return False
    return True


def _trip_breaker() -> None:
    global _breaker_tripped_at
    _breaker_tripped_at = time.monotonic()


def _get_client():
    """Lazily creates a single shared redis.asyncio client. Returns None
    if REDIS_URL isn't configured, the redis package can't be imported, or
    the breaker above is currently open - all are "skip the cache this
    time" conditions, not errors."""
    global _client, _client_init_attempted, _client_unavailable

    if _breaker_open():
        return None
    if _client is not None:
        return _client
    if _client_init_attempted and _client_unavailable:
        return None
    _client_init_attempted = True

    redis_url = get_settings().redis_url
    if not redis_url:
        _client_unavailable = True
        return None

    try:
        import redis.asyncio as redis_asyncio
    except ImportError:
        logger.warning("redis package not installed - caching disabled.")
        _client_unavailable = True
        return None

    try:
        _client = redis_asyncio.from_url(
            redis_url,
            socket_connect_timeout=0.5,
            socket_timeout=0.5,
            decode_responses=True,
        )
    except Exception as exc:
        logger.warning("Could not create Redis client (%s) - caching disabled.", exc)
        _client_unavailable = True
        return None
    return _client


async def cache_get(key: str) -> Any | None:
    """Returns the deserialized value, or None on a miss OR any failure
    (bad connection, bad JSON, Redis down) - callers treat both the same
    way: fall through to the database."""
    client = _get_client()
    if client is None:
        return None
    try:
        raw = await client.get(key)
    except Exception as exc:
        logger.warning("Redis GET failed for %s (%s) - falling back to DB.", key, exc)
        _trip_breaker()
        return None
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None


async def cache_set(key: str, value: Any, *, ttl_seconds: int) -> None:
    """Best-effort write. Never raises - a failed cache write just means
    the next read is a cache miss, which is always a safe outcome."""
    client = _get_client()
    if client is None:
        return
    try:
        await client.set(key, json.dumps(value), ex=ttl_seconds)
    except Exception as exc:
        logger.warning("Redis SET failed for %s (%s) - continuing without caching it.", key, exc)
        _trip_breaker()


async def cache_delete(*keys: str) -> None:
    """Invalidation. Best-effort: if this fails, the cached entry will
    simply serve a stale value until its TTL expires rather than forever -
    every cached key in this app uses a short TTL for exactly this reason."""
    if not keys:
        return
    client = _get_client()
    if client is None:
        return
    try:
        await client.delete(*keys)
    except Exception as exc:
        logger.warning("Redis DELETE failed for %s (%s).", keys, exc)
        _trip_breaker()
