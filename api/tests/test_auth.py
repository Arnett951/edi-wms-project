import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

import main


def test_require_auth_raises_500_when_not_configured(monkeypatch):
    monkeypatch.setattr(main, "AZURE_AD_TENANT_ID", None)
    monkeypatch.setattr(main, "AZURE_AD_CLIENT_ID", None)

    with pytest.raises(HTTPException) as exc_info:
        main.require_auth(credentials=None)

    assert exc_info.value.status_code == 500


def test_require_auth_raises_401_when_no_token(monkeypatch):
    monkeypatch.setattr(main, "AZURE_AD_TENANT_ID", "tenant-1")
    monkeypatch.setattr(main, "AZURE_AD_CLIENT_ID", "client-1")

    with pytest.raises(HTTPException) as exc_info:
        main.require_auth(credentials=None)

    assert exc_info.value.status_code == 401


def test_require_auth_raises_401_on_invalid_token(monkeypatch):
    monkeypatch.setattr(main, "AZURE_AD_TENANT_ID", "tenant-1")
    monkeypatch.setattr(main, "AZURE_AD_CLIENT_ID", "client-1")

    class FakeJwksClient:
        def get_signing_key_from_jwt(self, token):
            raise main.jwt.PyJWTError("bad token")

    monkeypatch.setattr(main, "_jwks_client", FakeJwksClient())

    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="bad.token.value")

    with pytest.raises(HTTPException) as exc_info:
        main.require_auth(credentials=creds)

    assert exc_info.value.status_code == 401


def test_require_auth_returns_payload_for_valid_token(monkeypatch):
    monkeypatch.setattr(main, "AZURE_AD_TENANT_ID", "tenant-1")
    monkeypatch.setattr(main, "AZURE_AD_CLIENT_ID", "client-1")

    class FakeSigningKey:
        key = "fake-key"

    class FakeJwksClient:
        def get_signing_key_from_jwt(self, token):
            return FakeSigningKey()

    monkeypatch.setattr(main, "_jwks_client", FakeJwksClient())
    monkeypatch.setattr(main.jwt, "decode", lambda *args, **kwargs: {"sub": "user-1"})

    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="good.token.value")

    payload = main.require_auth(credentials=creds)

    assert payload == {"sub": "user-1"}


def test_protected_endpoint_rejects_missing_token(unauthenticated_client, monkeypatch):
    monkeypatch.setattr(main, "AZURE_AD_TENANT_ID", "tenant-1")
    monkeypatch.setattr(main, "AZURE_AD_CLIENT_ID", "client-1")

    response = unauthenticated_client.get("/api/dashboard/summary")

    assert response.status_code == 401


def test_health_endpoint_stays_open_without_a_token(unauthenticated_client):
    response = unauthenticated_client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
