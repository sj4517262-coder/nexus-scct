from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm, HTTPAuthorizationCredentials
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import Column, DateTime, String, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import Base, get_db
from core_modules import (
    UserRole,
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    verify_token,
    security,
)

router = APIRouter()


# ---------------------------------------------
# Database model
# ---------------------------------------------

class UserModel(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(30), nullable=False, default=UserRole.OPERATOR.value)
    is_active = Column(String(10), nullable=False, default="true")
    created_at = Column(DateTime(timezone=True), nullable=False)


# ---------------------------------------------
# Schemas
# ---------------------------------------------

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    role: UserRole = UserRole.OPERATOR


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: EmailStr
    role: str
    is_active: bool
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


# ---------------------------------------------
# Helpers
# ---------------------------------------------

def _user_response(user: UserModel) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        role=user.role,
        is_active=user.is_active == "true",
        created_at=user.created_at,
    )


async def _get_user_by_email(
    email: str,
    db: AsyncSession,
) -> Optional[UserModel]:
    result = await db.execute(
        select(UserModel).where(UserModel.email == email.lower())
    )
    return result.scalar_one_or_none()


# ---------------------------------------------
# Routes
# ---------------------------------------------

@router.get("/status")
async def auth_status():
    return {
        "status": "operational",
        "authentication": "JWT",
        "authorization": "RBAC",
        "access_token_expiry_minutes": 15,
        "refresh_token_expiry_days": 7,
    }


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    request: RegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    existing = await _get_user_by_email(request.email, db)

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists",
        )

    import uuid

    user = UserModel(
        id=str(uuid.uuid4()),
        email=request.email.lower(),
        hashed_password=hash_password(request.password),
        role=request.role.value,
        is_active="true",
        created_at=datetime.now(timezone.utc),
    )

    db.add(user)

    try:
        await db.commit()
        await db.refresh(user)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists",
        )

    return _user_response(user)


@router.post("/token", response_model=TokenResponse)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    user = await _get_user_by_email(form_data.username, db)

    if (
        user is None
        or user.is_active != "true"
        or not verify_password(form_data.password, user.hashed_password)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    role = UserRole(user.role)

    return TokenResponse(
        access_token=create_access_token(user.id, role=role),
        refresh_token=create_refresh_token(user.id),
    )


@router.post("/login", response_model=TokenResponse)
async def login_json(
    request: RegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    user = await _get_user_by_email(request.email, db)

    if (
        user is None
        or user.is_active != "true"
        or not verify_password(request.password, user.hashed_password)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    role = UserRole(user.role)

    return TokenResponse(
        access_token=create_access_token(user.id, role=role),
        refresh_token=create_refresh_token(user.id),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: RefreshRequest,
    db: AsyncSession = Depends(get_db),
):
    from jose import jwt, JWTError
    from core.config import settings

    try:
        payload = jwt.decode(
            request.refresh_token,
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )

        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token",
            )

        user_id = payload.get("sub")

        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token",
            )

    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    result = await db.execute(
        select(UserModel).where(UserModel.id == user_id)
    )
    user = result.scalar_one_or_none()

    if user is None or user.is_active != "true":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User is inactive or does not exist",
        )

    role = UserRole(user.role)

    return TokenResponse(
        access_token=create_access_token(user.id, role=role),
        refresh_token=create_refresh_token(user.id),
    )


@router.get("/me", response_model=UserResponse)
async def me(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
):
    payload = verify_token(credentials.credentials)
    user_id = payload.get("sub")

    result = await db.execute(
        select(UserModel).where(UserModel.id == user_id)
    )
    user = result.scalar_one_or_none()

    if user is None or user.is_active != "true":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    return _user_response(user)
