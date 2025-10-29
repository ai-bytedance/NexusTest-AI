from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
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
    OAuthCallbackRequest,
    OAuthStartRequest,
)
from app.schemas.user import UserCreate, UserLogin, UserRead
from app.services.oauth import service as oauth_service

router = APIRouter(prefix="/auth", tags=["auth"])
logger = get_logger()


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


@router.post("/login", response_model=ResponseEnvelope)
def login_user(payload: UserLogin, db: Session = Depends(get_db)) -> dict:
    normalized_email = payload.email.lower()
    user = db.execute(select(User).where(User.email == normalized_email)).scalar_one_or_none()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise http_exception(
            status.HTTP_401_UNAUTHORIZED,
            ErrorCode.AUTH_INVALID_CREDENTIALS,
            "Invalid credentials",
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
