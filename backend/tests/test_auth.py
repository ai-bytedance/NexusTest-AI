from fastapi.testclient import TestClient


def test_register_duplicate_email_returns_auth002(client: TestClient) -> None:
    payload = {"email": "duplicate@example.com", "password": "changeme123"}
    first_response = client.post("/api/v1/auth/register", json=payload)
    assert first_response.status_code == 201

    duplicate_response = client.post("/api/v1/auth/register", json=payload)
    assert duplicate_response.status_code == 409
    body = duplicate_response.json()
    assert body["code"] == "AUTH002"
    assert body["message"] == "Email already registered"


def test_login_invalid_credentials_returns_auth001(client: TestClient) -> None:
    register_response = client.post(
        "/api/v1/auth/register",
        json={"email": "login@example.com", "password": "changeme123"},
    )
    assert register_response.status_code == 201

    invalid_login = client.post(
        "/api/v1/auth/login",
        json={"email": "login@example.com", "password": "wrongpass123"},
    )
    assert invalid_login.status_code == 401
    body = invalid_login.json()
    assert body["code"] == "AUTH001"
    assert body["message"] == "Invalid credentials"


def test_login_with_json_email_returns_token(client: TestClient) -> None:
    register_response = client.post(
        "/api/v1/auth/register",
        json={"email": "json-login@example.com", "password": "changeme123"},
    )
    assert register_response.status_code == 201

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "json-login@example.com", "password": "changeme123"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == "SUCCESS"
    assert body["data"]["token_type"] == "bearer"
    assert isinstance(body["data"]["access_token"], str) and body["data"]["access_token"].strip()


def test_login_with_form_username_returns_token(client: TestClient) -> None:
    register_response = client.post(
        "/api/v1/auth/register",
        json={"email": "form-login@example.com", "password": "changeme123"},
    )
    assert register_response.status_code == 201

    response = client.post(
        "/api/v1/auth/login",
        data={"username": "FORM-LOGIN@example.com", "password": "changeme123"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == "SUCCESS"
    assert body["data"]["token_type"] == "bearer"
    assert isinstance(body["data"]["access_token"], str) and body["data"]["access_token"].strip()


def test_login_missing_password_returns_bad_request(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "missing-password@example.com"},
    )
    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "B001"
    assert body["message"] == "Invalid login payload"


def test_invalid_token_returns_auth003(client: TestClient) -> None:
    response = client.get("/api/v1/projects", headers={"Authorization": "Bearer invalid"})
    assert response.status_code == 401
    body = response.json()
    assert body["code"] == "AUTH003"
    assert body["message"] == "Invalid authentication token"


def test_version_endpoint_returns_expected_payload(client: TestClient) -> None:
    response = client.get("/api/v1/version")
    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == "SUCCESS"
    assert payload["data"] == {
        "version": "test-version",
        "git_sha": "test-sha",
        "build_time": "2024-01-01T00:00:00Z",
    }
