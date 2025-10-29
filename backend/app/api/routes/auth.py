from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.response import ResponseEnvelope, success_response
from app.core.errors import ErrorCode, http_exception
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.logging import get_logger
from app.models.user import User, UserRole
from app.schemas.user import UserCreate, UserLogin, UserRead

router = APIRouter(prefix="/auth", tags=["auth"])
logger = get_logger()


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
