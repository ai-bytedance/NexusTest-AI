from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user_identity import UserIdentity
from app.services.oauth.providers.github import OAuthProfile, OAuthTokens


def test_oauth_start_link_requires_auth(client: TestClient) -> None:
    response = client.post(
        "/api/auth/oauth/github/start",
        json={"link": True},
    )
    assert response.status_code == 401
    payload = response.json()
    assert payload["code"] == "A001"


def test_oauth_start_login_flow_returns_url(
    client: TestClient,
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(
        "app.services.oauth.service.create_oauth_state",
        lambda *args, **kwargs: "STATE",
    )
    monkeypatch.setattr(
        "app.services.oauth.service.github_provider.build_authorize_url",
        lambda **kwargs: "https://example.com/auth",
    )

    response = client.post(
        "/api/auth/oauth/github/start",
        json={"redirect_uri": "http://localhost/callback"},
    )
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload == {
        "provider": "github",
        "authorization_url": "https://example.com/auth",
        "state": "STATE",
    }


def test_oauth_callback_login_creates_user_and_identity(
    client: TestClient,
    db_session: Session,
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(
        "app.services.oauth.service.parse_oauth_state",
        lambda state, expected_provider: {
            "provider": expected_provider,
            "action": "login",
        },
    )
    monkeypatch.setattr(
        "app.services.oauth.service.github_provider.exchange_code",
        lambda code, redirect_uri: OAuthTokens(access_token="token-123"),
    )
    monkeypatch.setattr(
        "app.services.oauth.service.github_provider.fetch_profile",
        lambda tokens: OAuthProfile(account_id="acct-1", email="oauth-user@example.com"),
    )

    response = client.post(
        "/api/auth/oauth/github/callback",
        json={"code": "abc", "state": "STATE"},
    )
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["token_type"] == "bearer"
    assert payload["is_new_user"] is True
    assert payload["access_token"]

    identities = db_session.execute(select(UserIdentity)).scalars().all()
    assert len(identities) == 1
    identity = identities[0]
    assert identity.provider_account_id == "acct-1"
    assert identity.email == "oauth-user@example.com"


def test_oauth_link_and_unlink_flow(
    client: TestClient,
    db_session: Session,
    monkeypatch: Any,
) -> None:
    register_response = client.post(
        "/api/auth/register",
        json={"email": "link-user@example.com", "password": "changeme123"},
    )
    assert register_response.status_code == 201
    user_id = register_response.json()["data"]["id"]

    login_response = client.post(
        "/api/auth/login",
        json={"email": "link-user@example.com", "password": "changeme123"},
    )
    assert login_response.status_code == 200
    access_token = login_response.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}

    monkeypatch.setattr(
        "app.services.oauth.service.parse_oauth_state",
        lambda state, expected_provider: {
            "provider": expected_provider,
            "action": "link",
            "user_id": user_id,
        },
    )
    monkeypatch.setattr(
        "app.services.oauth.service.github_provider.exchange_code",
        lambda code, redirect_uri: OAuthTokens(access_token="token-321"),
    )
    monkeypatch.setattr(
        "app.services.oauth.service.github_provider.fetch_profile",
        lambda tokens: OAuthProfile(account_id="acct-link", email="link-user@example.com"),
    )

    callback_response = client.post(
        "/api/auth/oauth/github/callback",
        headers=headers,
        json={"code": "xyz", "state": "STATE"},
    )
    assert callback_response.status_code == 200
    callback_payload = callback_response.json()["data"]
    assert callback_payload["user_id"] == user_id

    list_response = client.get("/api/auth/oauth/identities", headers=headers)
    assert list_response.status_code == 200
    identities_payload = list_response.json()["data"]
    assert identities_payload == [
        {
            "provider": "github",
            "provider_account_id": "acct-link",
            "email": "link-user@example.com",
        }
    ]

    delete_response = client.delete(
        "/api/auth/oauth/github",
        headers=headers,
        params={"account_id": "acct-link"},
    )
    assert delete_response.status_code == 200

    identity_row = db_session.execute(select(UserIdentity)).scalar_one()
    assert identity_row.is_deleted is True
