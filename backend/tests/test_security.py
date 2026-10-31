import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.config import get_settings
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)

settings = get_settings()


def test_password_hash_round_trip():
    hashed = hash_password("a-strong-password-123")
    assert hashed != "a-strong-password-123"
    assert verify_password("a-strong-password-123", hashed)


def test_password_hash_rejects_wrong_password():
    hashed = hash_password("a-strong-password-123")
    assert not verify_password("totally-wrong-password", hashed)


def test_access_token_round_trip():
    user_id = uuid.uuid4()
    token = create_access_token(user_id)
    payload = decode_access_token(token)
    assert payload["sub"] == str(user_id)


def test_expired_access_token_is_rejected():
    now = datetime.now(timezone.utc)
    expired_payload = {
        "sub": str(uuid.uuid4()),
        "type": "access",
        "iat": now - timedelta(minutes=30),
        "exp": now - timedelta(minutes=15),
    }
    token = jwt.encode(expired_payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    with pytest.raises(jwt.PyJWTError):
        decode_access_token(token)


def test_tampered_access_token_is_rejected():
    user_id = uuid.uuid4()
    token = create_access_token(user_id)
    tampered = token[:-4] + ("A" if token[-4] != "A" else "B") + token[-3:]
    with pytest.raises(jwt.PyJWTError):
        decode_access_token(tampered)


def test_refresh_token_only_the_hash_is_derived_deterministically():
    from app.core.security import generate_refresh_token, hash_refresh_token

    raw, token_hash, _expires_at = generate_refresh_token()
    assert hash_refresh_token(raw) == token_hash
    assert raw != token_hash
