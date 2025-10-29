from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class InvalidTokenError(Exception):
    """Raised when a JWT cannot be decoded or validated."""


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(subject: str, expires_minutes: int | None = None) -> str:
    settings = get_settings()
    minutes = expires_minutes if expires_minutes is not None else settings.access_token_expire_minutes
    if minutes <= 0:
        raise ValueError("Token expiry must be greater than zero minutes")

    expire_delta = timedelta(minutes=minutes)
    now = datetime.now(timezone.utc)
    payload: Dict[str, Any] = {"sub": subject, "iat": int(now.timestamp()), "exp": int((now + expire_delta).timestamp())}
    encoded_jwt = jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)
    return encoded_jwt


def decode_access_token(token: str) -> Dict[str, Any]:
    settings = get_settings()
    try:
        return jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.algorithm],
            leeway=settings.token_clock_skew_seconds,
        )
    except JWTError as exc:
        raise InvalidTokenError("Invalid token") from exc
