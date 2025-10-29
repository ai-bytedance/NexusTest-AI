from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import httpx

from app.core.config import get_settings
from app.core.http import get_http_client
from app.logging import get_logger

logger = get_logger().bind(component="oauth.github")


@dataclass(slots=True)
class OAuthTokens:
    access_token: str
    refresh_token: str | None = None
    expires_at: datetime | None = None


@dataclass(slots=True)
class OAuthProfile:
    account_id: str
    email: str | None


class GitHubOAuthProvider:
    authorize_endpoint = "https://github.com/login/oauth/authorize"
    token_endpoint = "https://github.com/login/oauth/access_token"
    user_endpoint = "https://api.github.com/user"
    user_emails_endpoint = "https://api.github.com/user/emails"

    scope_default = ["read:user", "user:email"]

    def build_authorize_url(self, state: str, redirect_uri: str | None, scopes: list[str] | None) -> str:
        settings = get_settings()
        client_id = settings.github_client_id
        if not client_id:
            raise ValueError("GitHub OAuth client id not configured")
        params = {
            "client_id": client_id,
            "state": state,
        }
        if redirect_uri:
            params["redirect_uri"] = redirect_uri
        requested_scopes = scopes or self.scope_default
        params["scope"] = " ".join(requested_scopes)
        query = httpx.QueryParams(params)
        url = f"{self.authorize_endpoint}?{query}"
        logger.debug("github_authorize_url", url=url, redirect_uri=redirect_uri, scopes=requested_scopes)
        return url

    def exchange_code(self, code: str, redirect_uri: str | None) -> OAuthTokens:
        settings = get_settings()
        client_id = settings.github_client_id
        client_secret = settings.github_client_secret
        if not client_id or not client_secret:
            raise ValueError("GitHub OAuth client credentials not configured")

        data: Dict[str, Any] = {
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
        }
        if redirect_uri:
            data["redirect_uri"] = redirect_uri

        headers = {"Accept": "application/json"}
        client = get_http_client()
        response = client.post(self.token_endpoint, data=data, headers=headers, timeout=30)
        response.raise_for_status()
        payload = response.json()
        logger.debug("github_exchange_code_success", has_refresh=bool(payload.get("refresh_token")))
        access_token = payload.get("access_token")
        if not access_token:
            raise ValueError("GitHub OAuth response missing access token")
        expires_in = payload.get("expires_in")
        expires_at = None
        if isinstance(expires_in, int):
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        refresh_token = payload.get("refresh_token")
        return OAuthTokens(access_token=access_token, refresh_token=refresh_token, expires_at=expires_at)

    def fetch_profile(self, tokens: OAuthTokens) -> OAuthProfile:
        headers = {
            "Authorization": f"Bearer {tokens.access_token}",
            "Accept": "application/json",
        }
        client = get_http_client()
        user_response = client.get(self.user_endpoint, headers=headers, timeout=30)
        user_response.raise_for_status()
        user_payload = user_response.json()
        account_id = str(user_payload.get("id"))
        if not account_id or account_id == "None":
            raise ValueError("GitHub user info missing id")

        email = user_payload.get("email")
        if not email:
            emails_response = client.get(self.user_emails_endpoint, headers=headers, timeout=30)
            emails_response.raise_for_status()
            email_payload = emails_response.json()
            for item in email_payload:
                if item.get("primary") and item.get("verified"):
                    email = item.get("email")
                    break
            if not email and email_payload:
                email = email_payload[0].get("email")
        logger.debug("github_fetch_profile", account_id=account_id, has_email=bool(email))
        return OAuthProfile(account_id=account_id, email=email)


github_provider = GitHubOAuthProvider()
