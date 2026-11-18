import asyncio

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from utils import apple_signin


def _pem() -> str:
    key = ec.generate_private_key(ec.SECP256R1())
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv("APPLE_SIWA_TEAM_ID", "TEAM123456")
    monkeypatch.setenv("APPLE_SIWA_KEY_ID", "KEY1234567")
    monkeypatch.setenv("APPLE_SIWA_PRIVATE_KEY", _pem())


def test_not_configured_until_the_key_is_set(monkeypatch):
    for name in ("APPLE_SIWA_TEAM_ID", "APPLE_SIWA_KEY_ID", "APPLE_SIWA_PRIVATE_KEY"):
        monkeypatch.delenv(name, raising=False)
    assert not apple_signin.configured()
    assert asyncio.run(apple_signin.revoke_with_code("a-code")) == "not_configured"


def test_no_code_means_nothing_to_revoke(configured):
    assert asyncio.run(apple_signin.revoke_with_code(None)) == "no_code"
    assert asyncio.run(apple_signin.revoke_with_code("   ")) == "no_code"


def test_the_client_secret_carries_what_apple_checks(configured):
    secret = apple_signin.client_secret(now=1_700_000_000)
    claims = jwt.decode(secret, options={"verify_signature": False})
    assert claims["iss"] == "TEAM123456"
    assert claims["sub"] == "com.causalme.thegap"
    assert claims["aud"] == "https://appleid.apple.com"
    assert claims["exp"] - claims["iat"] == 300
    assert jwt.get_unverified_header(secret)["kid"] == "KEY1234567"
    assert jwt.get_unverified_header(secret)["alg"] == "ES256"


def test_a_key_pasted_with_escaped_newlines_still_works(monkeypatch, configured):
    monkeypatch.setenv("APPLE_SIWA_PRIVATE_KEY", _pem().replace("\n", "\\n"))
    assert apple_signin.client_secret(now=1_700_000_000)
