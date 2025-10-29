from __future__ import annotations

import secrets
from typing import Optional

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.errors import ErrorCode, http_exception
from app.core.security import create_access_token, hash_password
from app.models.organization import Organization, OrganizationMembership, OrganizationRole
from app.models.user import User
from app.models.user_identity import IdentityProvider, UserIdentity
from app.schemas.auth import OAuthCallbackResponse, OAuthStartResponse
from app.services.oauth.providers.github import OAuthProfile, OAuthTokens, github_provider
from app.services.oauth.state import create_oauth_state, parse_oauth_state

SUPPORTED_PROVIDERS: dict[str, IdentityProvider] = {
    "github": IdentityProvider.GITHUB,
}


def list_linked_identities(db: Session, user: User) -> list[UserIdentity]:
    stmt = select(UserIdentity).where(
        UserIdentity.user_id == user.id,
        UserIdentity.is_deleted.is_(False),
    )
    return db.execute(stmt).scalars().all()


def unlink_identity(db: Session, provider: str, user: User, account_id: str | None = None) -> None:
    _ensure_provider_configured(provider)
    provider_enum = SUPPORTED_PROVIDERS[provider]
    stmt = select(UserIdentity).where(
        UserIdentity.user_id == user.id,
        UserIdentity.provider == provider_enum,
        UserIdentity.is_deleted.is_(False),
    )
    identities = db.execute(stmt).scalars().all()
    if not identities:
        raise http_exception(404, ErrorCode.NOT_FOUND, "Identity not found")

    target: UserIdentity | None = None
    if account_id:
        for identity in identities:
            if identity.provider_account_id == account_id:
                target = identity
                break
        if target is None:
            raise http_exception(404, ErrorCode.NOT_FOUND, "Identity not found")
    else:
        if len(identities) > 1:
            raise http_exception(400, ErrorCode.BAD_REQUEST, "Multiple identities found; specify account id")
        target = identities[0]

    target.is_deleted = True
    db.add(target)
    db.commit()


def _ensure_provider_configured(provider: str) -> None:
    if provider not in SUPPORTED_PROVIDERS:
        raise http_exception(400, ErrorCode.BAD_REQUEST, "Unsupported OAuth provider")


def build_authorization_url(provider: str, redirect_uri: str | None, scopes: list[str] | None, link: bool,
                             user: User | None) -> OAuthStartResponse:
    _ensure_provider_configured(provider)
    if provider == "github":
        state = create_oauth_state(provider, "link" if link else "login", redirect_uri, str(user.id) if user else None)
        try:
            url = github_provider.build_authorize_url(state=state, redirect_uri=redirect_uri, scopes=scopes)
        except ValueError as exc:
            raise http_exception(400, ErrorCode.AUTH_SSO_NOT_CONFIGURED, str(exc)) from exc
        return OAuthStartResponse(provider=provider, authorization_url=url, state=state)
    raise http_exception(500, ErrorCode.BAD_REQUEST, "Unhandled OAuth provider")


def _exchange_and_fetch(provider: str, code: str, redirect_uri: str | None) -> tuple[OAuthTokens, OAuthProfile]:
    if provider == "github":
        try:
            tokens = github_provider.exchange_code(code, redirect_uri)
            profile = github_provider.fetch_profile(tokens)
        except ValueError as exc:
            raise http_exception(400, ErrorCode.AUTH_SSO_NOT_CONFIGURED, str(exc)) from exc
        return tokens, profile
    raise http_exception(500, ErrorCode.BAD_REQUEST, "Unhandled OAuth provider")


def _find_user_by_identity(db: Session, provider: IdentityProvider, account_id: str) -> UserIdentity | None:
    stmt: Select[tuple[UserIdentity]] = select(UserIdentity).where(
        UserIdentity.provider == provider,
        UserIdentity.provider_account_id == account_id,
        UserIdentity.is_deleted.is_(False),
    )
    return db.execute(stmt).scalar_one_or_none()


def _find_user_by_email(db: Session, email: str) -> User | None:
    stmt = select(User).where(func.lower(User.email) == email.lower(), User.is_deleted.is_(False))
    return db.execute(stmt).scalar_one_or_none()


def _auto_provision_memberships(db: Session, user: User, email: str | None) -> None:
    if not email:
        return
    domain = email.split("@")[-1].lower()
    org_stmt = select(Organization).where(
        Organization.auto_provision.is_(True),
        Organization.is_deleted.is_(False),
        Organization.domain_allowlist.contains([domain]),
    )
    organizations = db.execute(org_stmt).scalars().all()
    for org in organizations:
        existing = db.execute(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == org.id,
                OrganizationMembership.user_id == user.id,
                OrganizationMembership.is_deleted.is_(False),
            )
        ).scalar_one_or_none()
        if existing:
            continue
        membership = OrganizationMembership(
            organization_id=org.id,
            user_id=user.id,
            role=OrganizationRole.MEMBER,
        )
        db.add(membership)
        db.flush()


def _ensure_identity_available(db: Session, provider: IdentityProvider, account_id: str) -> None:
    existing = _find_user_by_identity(db, provider, account_id)
    if existing:
        raise http_exception(409, ErrorCode.AUTH_SSO_LINK_CONFLICT, "Identity already linked to another user")


def handle_callback(
    provider: str,
    code: str,
    state_token: str,
    redirect_uri: str | None,
    db: Session,
    current_user: Optional[User] = None,
) -> OAuthCallbackResponse:
    _ensure_provider_configured(provider)
    state = parse_oauth_state(state_token, provider)
    action = state.get("action")
    if redirect_uri and state.get("redirect_uri") and redirect_uri != state.get("redirect_uri"):
        raise http_exception(400, ErrorCode.AUTH_SSO_STATE_INVALID, "OAuth redirect URI mismatch")

    tokens, profile = _exchange_and_fetch(provider, code, redirect_uri)
    provider_enum = SUPPORTED_PROVIDERS[provider]

    if action == "link":
        if current_user is None:
            raise http_exception(401, ErrorCode.NOT_AUTHENTICATED, "Authentication required for linking")
        state_user_id = state.get("user_id")
        if state_user_id and state_user_id != str(current_user.id):
            raise http_exception(400, ErrorCode.AUTH_SSO_STATE_INVALID, "OAuth state user mismatch")
        _ensure_identity_available(db, provider_enum, profile.account_id)
        identity = UserIdentity(
            user_id=current_user.id,
            provider=provider_enum,
            provider_account_id=profile.account_id,
            email=profile.email,
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
            expires_at=tokens.expires_at,
        )
        db.add(identity)
        db.commit()
        return OAuthCallbackResponse(
            access_token="",
            token_type="bearer",
            user_id=current_user.id,
            user_role=current_user.role,
            is_new_user=False,
        )

    identity = _find_user_by_identity(db, provider_enum, profile.account_id)
    user: User | None
    is_new_user = False

    if identity:
        user = identity.user
        identity.email = profile.email
        identity.access_token = tokens.access_token
        identity.refresh_token = tokens.refresh_token
        identity.expires_at = tokens.expires_at
        db.add(identity)
    else:
        user = _find_user_by_email(db, profile.email) if profile.email else None
        if user is None:
            is_new_user = True
            random_password = secrets.token_urlsafe(32)
            user = User(email=profile.email or f"user-{secrets.token_hex(8)}@sso.local",
                        hashed_password=hash_password(random_password))
            db.add(user)
            db.flush()
            _auto_provision_memberships(db, user, profile.email)
        identity = UserIdentity(
            user_id=user.id,
            provider=provider_enum,
            provider_account_id=profile.account_id,
            email=profile.email,
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
            expires_at=tokens.expires_at,
        )
        db.add(identity)

    if user.is_deleted:
        raise http_exception(403, ErrorCode.NO_PERMISSION, "User account is disabled")

    db.commit()
    access_token = create_access_token(subject=str(user.id))
    return OAuthCallbackResponse(
        access_token=access_token,
        token_type="bearer",
        user_id=user.id,
        user_role=user.role,
        is_new_user=is_new_user,
    )
