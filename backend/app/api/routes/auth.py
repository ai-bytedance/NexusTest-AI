import json
from typing import Any, Optional
from urllib.parse import parse_qsl

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import ValidationError
from sqlalchemy import select
from structlog.contextvars import get_contextvars
from sqlalchemy.orm import Session

from app.api.response import ResponseEnvelope, success_response
from app.core.authz import get_current_user, oauth2_scheme
from app.core.errors import ErrorCode, http_exception
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.logging import get_logger
from app.models.user import User, UserRole
from app.schemas.auth import (
    LinkedIdentity,
    LoginRequest,
    OAuthCallbackRequest,
    OAuthStartRequest,
)
from app.schemas.user import UserCreate, UserRead
from app.services.oauth import service as oauth_service

router = APIRouter(prefix="/auth", tags=["auth"])
logger = get_logger()

LOGIN_PAYLOAD_SCHEMA = {
    "type": "object",
    "properties": {
        "identifier": {
            "type": "string",
            "description": "Email address or username used to authenticate.",
        },
        "email": {
            "type": "string",
            "format": "email",
            "description": "Email alias for identifier.",
        },
        "username": {
            "type": "string",
            "description": "Username alias for identifier, typically used with form submissions.",
        },
        "password": {
            "type": "string",
            "minLength": 1,
            "description": "Account password. Must not be blank.",
        },
    },
    "required": ["password"],
    "anyOf": [
        {"required": ["identifier"]},
        {"required": ["email"]},
        {"required": ["username"]},
    ],
}

LOGIN_PAYLOAD_EXAMPLES = {
    "email": {
        "summary": "Email login",
        "value": {"email": "admin@example.com", "password": "changeme123"},
    },
    "identifier": {
        "summary": "Identifier login",
        "value": {"identifier": "admin", "password": "changeme123"},
    },
    "form": {
        "summary": "Form login",
        "value": {"username": "admin@example.com", "password": "changeme123"},
    },
}

LOGIN_REQUEST_OPENAPI_EXTRA = {
    "requestBody": {
        "required": True,
        "content": {
            "application/json": {
                "schema": LOGIN_PAYLOAD_SCHEMA,
                "examples": LOGIN_PAYLOAD_EXAMPLES,
            },
            "application/x-www-form-urlencoded": {
                "schema": LOGIN_PAYLOAD_SCHEMA,
                "examples": LOGIN_PAYLOAD_EXAMPLES,
            },
            "multipart/form-data": {
                "schema": LOGIN_PAYLOAD_SCHEMA,
                "examples": LOGIN_PAYLOAD_EXAMPLES,
            },
        },
    }
}


def _parse_json_payload(body: bytes) -> tuple[dict[str, Any] | None, dict[str, str] | None]:
    if not body:
        return {}, None
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        return None, {"parser": "json", "error": "decode_error", "message": exc.msg}
    if isinstance(payload, dict):
        return payload, None
    return None, {"parser": "json", "error": "invalid_type", "type": type(payload).__name__}


def _parse_form_payload(body: bytes) -> tuple[dict[str, Any] | None, dict[str, str] | None]:
    if not body:
        return {}, None
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as exc:
        return None, {"parser": "form", "error": "decode_error", "message": exc.reason}
    parsed_form = dict(parse_qsl(text, keep_blank_values=True))
    return parsed_form, None


async def _parse_request_form(request: Request) -> tuple[dict[str, Any] | None, dict[str, str] | None]:
    try:
        form = await request.form()
    except Exception as exc:  # pragma: no cover - defensive parsing
        return None, {"parser": "form", "error": "parse_error", "message": str(exc)}
    form_data: dict[str, Any] = {}
    for key, value in form.multi_items():
        if hasattr(value, "filename"):
            continue
        form_data[key] = value
    return form_data, None


def _normalize_non_empty(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        candidate = value.strip()
    else:
        candidate = str(value).strip()
    if not candidate:
        return None
    return candidate


def _extract_identifier_from_payload(raw_data: dict[str, Any]) -> tuple[str | None, str | None]:
    for key in ("identifier", "email", "username"):
        candidate = _normalize_non_empty(raw_data.get(key))
        if candidate is not None:
            return candidate.lower(), key
    return None, None


def _collect_provided_fields(raw_data: dict[str, Any]) -> list[str]:
    provided = {
        key
        for key, value in raw_data.items()
        if key != "password" and _normalize_non_empty(value) is not None
    }
    return sorted(provided)


async def parse_login_payload(request: Request) -> LoginRequest:
    content_type = (request.headers.get("content-type") or "").lower()
    parse_reasons: list[dict[str, str]] = []
    raw_data: dict[str, Any] | None = None

    if "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
        raw_data, error = await _parse_request_form(request)
        if error:
            parse_reasons.append(error)
    else:
        body = await request.body()
        if "application/json" in content_type or not content_type:
            raw_data, error = _parse_json_payload(body)
            if error:
                parse_reasons.append(error)
            if raw_data is None:
                fallback_data, fallback_error = _parse_form_payload(body)
                if fallback_error:
                    parse_reasons.append(fallback_error)
                raw_data = fallback_data
        else:
            raw_data, error = _parse_json_payload(body)
            if error:
                parse_reasons.append(error)
            if raw_data is None:
                fallback_data, fallback_error = _parse_form_payload(body)
                if fallback_error:
                    parse_reasons.append(fallback_error)
                raw_data = fallback_data

    request_context = get_contextvars()
    request_id = request_context.get("request_id") if request_context else None

    if raw_data is None:
        log_payload: dict[str, Any] = {
            "path": str(request.url.path),
            "content_type": content_type or "missing",
        }
        if parse_reasons:
            log_payload["reasons"] = parse_reasons
        if request_id:
            log_payload["request_id"] = request_id
        logger.warning("login_payload_parse_error", **log_payload)
        raise http_exception(status.HTTP_400_BAD_REQUEST, ErrorCode.BAD_REQUEST, "Invalid login payload")

    raw_payload = raw_data or {}
    identifier_value, identifier_field = _extract_identifier_from_payload(raw_payload)
    password_raw_value = raw_payload.get("password")
    normalized_password = _normalize_non_empty(password_raw_value)
    if normalized_password is not None:
        if isinstance(password_raw_value, str):
            password_value = password_raw_value
        else:
            password_value = str(password_raw_value)
    else:
        password_value = None

    provided_fields = _collect_provided_fields(raw_payload)
    password_provided = password_value is not None

    log_kwargs: dict[str, Any] = {
        "path": str(request.url.path),
        "content_type": content_type or "missing",
        "provided_fields": provided_fields,
        "password_provided": password_provided,
    }
    if parse_reasons:
        log_kwargs["reasons"] = parse_reasons
    if request_id:
        log_kwargs["request_id"] = request_id

    if identifier_value is None:
        logger.warning("login_payload_missing_identifier", **log_kwargs)
        raise http_exception(
            status.HTTP_400_BAD_REQUEST,
            ErrorCode.BAD_REQUEST,
            "identifier required",
        )

    if identifier_field is not None:
        log_kwargs["identifier_field"] = identifier_field

    if password_value is None:
        logger.warning("login_payload_missing_password", **log_kwargs)
        raise http_exception(
            status.HTTP_400_BAD_REQUEST,
            ErrorCode.BAD_REQUEST,
            "password required",
        )

    payload_data = dict(raw_payload)
    payload_data["identifier"] = identifier_value
    payload_data["password"] = password_value

    try:
        return LoginRequest.model_validate(payload_data)
    except ValidationError as exc:
        error_fields = sorted(
            {
                ".".join(str(part) for part in error.get("loc", ())) or "unknown"
                for error in exc.errors()
            }
        )
        log_kwargs["error_fields"] = error_fields
        logger.warning("login_payload_validation_failed", **log_kwargs)
        raise http_exception(
            status.HTTP_400_BAD_REQUEST,
            ErrorCode.BAD_REQUEST,
            "Invalid login payload",
        ) from exc


def _get_optional_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> Optional[User]:
    if not token:
        return None
    try:
        return get_current_user(token, db)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_401_UNAUTHORIZED:
            return None
        raise


@router.post("/register", response_model=ResponseEnvelope, status_code=status.HTTP_201_CREATED)
def register_user(user_in: UserCreate, db: Session = Depends(get_db)) -> dict:
    normalized_email = user_in.email.lower()
    existing_user = db.execute(select(User).where(User.email == normalized_email)).scalar_one_or_none()
    if existing_user:
        raise http_exception(status.HTTP_409_CONFLICT, ErrorCode.AUTH_EMAIL_EXISTS, "Email already registered")

    role = user_in.role or UserRole.MEMBER
    user = User(email=normalized_email, hashed_password=hash_password(user_in.password), role=role)

    db.add(user)
    db.commit()
    db.refresh(user)

    logger.info("user_registered", user_id=user.id)
    return success_response(UserRead.model_validate(user), message="User registered")


@router.post("/login", response_model=ResponseEnvelope, openapi_extra=LOGIN_REQUEST_OPENAPI_EXTRA)
def login_user(
    payload: LoginRequest = Depends(parse_login_payload),
    db: Session = Depends(get_db),
) -> dict:
    normalized_identifier = payload.normalized_identifier()
    user = db.execute(select(User).where(User.email == normalized_identifier)).scalar_one_or_none()
    password_value = payload.password.get_secret_value()
    if not user or not verify_password(password_value, user.hashed_password):
        raise http_exception(
            status.HTTP_401_UNAUTHORIZED,
            ErrorCode.AUTH_INVALID_CREDENTIALS,
            "incorrect email/username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(subject=str(user.id))
    logger.info("user_authenticated", user_id=user.id)
    return success_response({"access_token": access_token, "token_type": "bearer"}, message="Authenticated")


@router.post("/oauth/{provider}/start", response_model=ResponseEnvelope)
def start_oauth_flow(
    provider: str,
    payload: OAuthStartRequest,
    current_user: Optional[User] = Depends(_get_optional_current_user),
) -> dict:
    if payload.link and current_user is None:
        raise http_exception(status.HTTP_401_UNAUTHORIZED, ErrorCode.NOT_AUTHENTICATED, "Authentication required")
    result = oauth_service.build_authorization_url(
        provider=provider,
        redirect_uri=payload.redirect_uri,
        scopes=payload.scopes,
        link=payload.link,
        user=current_user,
    )
    logger.info(
        "oauth_flow_started",
        provider=provider,
        link=payload.link,
        user_id=current_user.id if current_user else None,
    )
    return success_response(result.model_dump())


@router.post("/oauth/{provider}/callback", response_model=ResponseEnvelope)
def complete_oauth_flow(
    provider: str,
    payload: OAuthCallbackRequest,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(_get_optional_current_user),
) -> dict:
    result = oauth_service.handle_callback(
        provider=provider,
        code=payload.code,
        state_token=payload.state,
        redirect_uri=payload.redirect_uri,
        db=db,
        current_user=current_user,
    )
    logger.info(
        "oauth_flow_completed",
        provider=provider,
        user_id=result.user_id,
        is_new_user=result.is_new_user,
    )
    return success_response(result.model_dump())


@router.get("/oauth/identities", response_model=ResponseEnvelope)
def list_oauth_identities(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    identities = oauth_service.list_linked_identities(db, current_user)
    data = [
        LinkedIdentity(provider=identity.provider.value, provider_account_id=identity.provider_account_id, email=identity.email)
        for identity in identities
    ]
    return success_response([item.model_dump() for item in data])


@router.delete("/oauth/{provider}", response_model=ResponseEnvelope)
def unlink_oauth_identity(
    provider: str,
    account_id: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    oauth_service.unlink_identity(db, provider, current_user, account_id)
    logger.info("oauth_identity_unlinked", provider=provider, user_id=current_user.id, account_id=account_id)
    return success_response({"provider": provider, "unlinked": True})
