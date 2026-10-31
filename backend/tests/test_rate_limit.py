import pytest
from httpx import AsyncClient

from app.core.rate_limit import RateLimitedError, SlidingWindowLimiter
from tests.conftest import login

# Only the two HTTP-level tests below are async; the SlidingWindowLimiter
# unit tests are plain sync functions, so this is applied per-test rather
# than as a module-level pytestmark (which would wrongly flag them).


def test_sliding_window_limiter_blocks_after_max_attempts():
    limiter = SlidingWindowLimiter(max_attempts=3, window_seconds=60)
    limiter.check("a@b.com:1.2.3.4")
    limiter.check("a@b.com:1.2.3.4")
    limiter.check("a@b.com:1.2.3.4")
    with pytest.raises(RateLimitedError):
        limiter.check("a@b.com:1.2.3.4")


def test_sliding_window_limiter_keys_are_independent():
    limiter = SlidingWindowLimiter(max_attempts=1, window_seconds=60)
    limiter.check("a@b.com:1.2.3.4")
    # A different key (different email, or a different client IP for the
    # same email) must not be affected by another key's attempts.
    limiter.check("a@b.com:5.6.7.8")
    limiter.check("c@d.com:1.2.3.4")


def test_reset_clears_attempts():
    limiter = SlidingWindowLimiter(max_attempts=1, window_seconds=60)
    limiter.check("a@b.com:1.2.3.4")
    limiter.reset("a@b.com:1.2.3.4")
    limiter.check("a@b.com:1.2.3.4")  # does not raise - the slot was freed


@pytest.mark.asyncio
async def test_repeated_failed_logins_are_eventually_rate_limited(
    client: AsyncClient, owner_user, org
):
    for _ in range(10):
        resp = await client.post(
            "/auth/login", json={"email": "owner@acmefuel-dev.com", "password": "wrong-password"}
        )
        assert resp.status_code == 401

    blocked = await client.post(
        "/auth/login", json={"email": "owner@acmefuel-dev.com", "password": "wrong-password"}
    )
    assert blocked.status_code == 429


@pytest.mark.asyncio
async def test_a_successful_login_resets_the_limiter(client: AsyncClient, owner_user, org):
    for _ in range(5):
        resp = await client.post(
            "/auth/login", json={"email": "owner@acmefuel-dev.com", "password": "wrong-password"}
        )
        assert resp.status_code == 401

    token = await login(client, "owner@acmefuel-dev.com")
    assert token

    # The slot was freed by the successful login above, so this user can
    # immediately make more failed attempts without being blocked by the
    # earlier, now-irrelevant failures.
    resp = await client.post(
        "/auth/login", json={"email": "owner@acmefuel-dev.com", "password": "wrong-password"}
    )
    assert resp.status_code == 401
