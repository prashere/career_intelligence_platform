"""Authentication routes — register, login, current user."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserResponse
from app.services.auth import authenticate_user, create_access_token, get_or_create_profile, register_user

router = APIRouter(prefix="/auth", tags=["auth"])


def _user_response(user: User, name: str | None = None) -> UserResponse:
    return UserResponse(id=user.id, email=user.email, role=user.role.value, name=name)


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    try:
        user = await register_user(db, email=body.email, password=body.password, name=body.name)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    profile = await get_or_create_profile(db, user)
    token = create_access_token(user.id, user.role)
    return TokenResponse(access_token=token, user=_user_response(user, profile.name))


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    user = await authenticate_user(db, body.email, body.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    profile = await get_or_create_profile(db, user)
    token = create_access_token(user.id, user.role)
    return TokenResponse(access_token=token, user=_user_response(user, profile.name))


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    profile = await get_or_create_profile(db, user)
    return _user_response(user, profile.name)
