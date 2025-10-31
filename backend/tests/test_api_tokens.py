from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models import Project, ProjectMember, ProjectRole, User


def _create_user(db: Session, email: str | None = None) -> User:
    user = User(
        email=email or f"user-{uuid4().hex}@example.com",
        hashed_password="hashed",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _create_project(db: Session, owner: User, *, key_prefix: str = "PRJ") -> Project:
    project = Project(
        name=f"Project {uuid4().hex[:6]}",
        key=f"{key_prefix}{uuid4().hex[:4].upper()}",
        created_by=owner.id,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    membership = ProjectMember(project_id=project.id, user_id=owner.id, role=ProjectRole.ADMIN)
    db.add(membership)
    db.commit()
    return project


def _auth_headers(user: User) -> dict[str, str]:
    token = create_access_token(subject=str(user.id))
    return {"Authorization": f"Bearer {token}"}


def _pat_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_pat(
    client: TestClient,
    user: User,
    project: Project,
    *,
    scopes: list[str] | None = None,
    expires_in_days: int = 1,
) -> dict:
    payload = {
        "name": "CI Token",
        "scopes": scopes or ["read:projects"],
        "project_ids": [str(project.id)],
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=expires_in_days)).isoformat(),
    }
    response = client.post("/api/v1/tokens", json=payload, headers=_auth_headers(user))
    assert response.status_code == 201, response.text
    return response.json()["data"]


def test_personal_access_token_crud_and_scope_enforcement(client: TestClient, db_session: Session) -> None:
    user = _create_user(db_session)
    project = _create_project(db_session, user)
    other_project = _create_project(db_session, user, key_prefix="OTH")

    token_data = _create_pat(client, user, project, scopes=["read:projects"])
    secret_token = token_data["token"]

    # Token appears in listing without secret
    list_response = client.get("/api/v1/tokens", headers=_auth_headers(user))
    assert list_response.status_code == 200
    tokens = list_response.json()["data"]
    assert len(tokens) == 1
    assert tokens[0]["token_prefix"] == token_data["token_prefix"]
    assert "token" not in tokens[0]

    # PAT can read project information
    project_resp = client.get(f"/api/v1/projects/{project.id}", headers=_pat_headers(secret_token))
    assert project_resp.status_code == 200

    # PAT cannot perform write operations without write scope
    create_resp = client.post(
        "/api/v1/projects",
        json={"name": "New", "key": "NEW01"},
        headers=_pat_headers(secret_token),
    )
    assert create_resp.status_code == 403

    # PAT is restricted to declared projects
    other_project_resp = client.get(
        f"/api/v1/projects/{other_project.id}", headers=_pat_headers(secret_token)
    )
    assert other_project_resp.status_code == 403

    # Rotate token returns a new secret and keeps the previous one valid for a short grace period
    rotate_resp = client.patch(
        f"/api/v1/tokens/{token_data['id']}",
        json={"action": "rotate"},
        headers=_auth_headers(user),
    )
    assert rotate_resp.status_code == 200
    rotated_secret = rotate_resp.json()["data"]["token"]

    # During grace window both old and new secrets are valid
    old_resp = client.get(f"/api/v1/projects/{project.id}", headers=_pat_headers(secret_token))
    assert old_resp.status_code == 200
    rotated_resp = client.get(f"/api/v1/projects/{project.id}", headers=_pat_headers(rotated_secret))
    assert rotated_resp.status_code == 200

    # After grace window, old token is rejected
    import time

    time.sleep(3)
    old_after = client.get(f"/api/v1/projects/{project.id}", headers=_pat_headers(secret_token))
    assert old_after.status_code == 401
    new_after = client.get(f"/api/v1/projects/{project.id}", headers=_pat_headers(rotated_secret))
    assert new_after.status_code == 200

    # Revoke token blocks further requests
    revoke_resp = client.patch(
        f"/api/v1/tokens/{token_data['id']}",
        json={"action": "revoke"},
        headers=_auth_headers(user),
    )
    assert revoke_resp.status_code == 200
    revoked_check = client.get(f"/api/v1/projects/{project.id}", headers=_pat_headers(rotated_secret))
    assert revoked_check.status_code == 401

    # Deleting token removes it from listings
    delete_resp = client.delete(f"/api/v1/tokens/{token_data['id']}", headers=_auth_headers(user))
    assert delete_resp.status_code == 200
    final_list = client.get("/api/v1/tokens", headers=_auth_headers(user))
    assert final_list.status_code == 200
    assert final_list.json()["data"] == []


def test_rate_limit_enforced_for_project_requests(client: TestClient, db_session: Session) -> None:
    user = _create_user(db_session)
    project = _create_project(db_session, user)

    # Create a strict rate limit policy via API and set as default
    policy_payload = {
        "name": "strict",
        "enabled": True,
        "rules": [
            {
                "per_minute": 2,
                "path_patterns": [f"/api/v1/projects/{project.id}"],
                "methods": ["GET"],
            }
        ],
    }
    policy_resp = client.post(
        f"/api/v1/projects/{project.id}/rate-limit-policies",
        json=policy_payload,
        headers=_auth_headers(user),
    )
    assert policy_resp.status_code == 201
    policy_id = policy_resp.json()["data"]["id"]

    default_resp = client.put(
        f"/api/v1/projects/{project.id}/rate-limit-policies/default",
        json={"policy_id": policy_id},
        headers=_auth_headers(user),
    )
    assert default_resp.status_code == 200

    token_data = _create_pat(client, user, project, scopes=["read:projects"], expires_in_days=1)
    pat_secret = token_data["token"]

    first = client.get(f"/api/v1/projects/{project.id}", headers=_pat_headers(pat_secret))
    second = client.get(f"/api/v1/projects/{project.id}", headers=_pat_headers(pat_secret))
    third = client.get(f"/api/v1/projects/{project.id}", headers=_pat_headers(pat_secret))

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429
    retry_after = third.headers.get("Retry-After")
    assert retry_after is not None
    assert int(retry_after) >= 0
