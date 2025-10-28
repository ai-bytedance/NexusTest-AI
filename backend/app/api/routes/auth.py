from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.logging import get_logger
from app.models.user import User, UserRole
from app.schemas.user import UserCreate, UserLogin, UserRead

router = APIRouter(prefix="/auth", tags=["auth"])
logger = get_logger()


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register_user(user_in: UserCreate, db: Session = Depends(get_db)) -> UserRead:
    existing_user = db.execute(select(User).where(User.email == user_in.email)).scalar_one_or_none()
    if existing_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    role = user_in.role or UserRole.MEMBER
    user = User(email=user_in.email, hashed_password=hash_password(user_in.password), role=role)

    db.add(user)
    db.commit()
    db.refresh(user)

    logger.info("user_registered", user_id=user.id)
    return UserRead.model_validate(user)


@router.post("/login")
def login_user(payload: UserLogin, db: Session = Depends(get_db)) -> dict[str, str]:
    user = db.execute(select(User).where(User.email == payload.email)).scalar_one_or_none()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    access_token = create_access_token(subject=str(user.id))
    logger.info("user_authenticated", user_id=user.id)
    return {"access_token": access_token, "token_type": "bearer"}
