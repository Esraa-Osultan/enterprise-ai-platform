import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from app.auth.dependencies import get_current_user, get_user_store
from app.auth.schemas import (
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    TokenResponse,
)
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User, UserStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, user_store: UserStore = Depends(get_user_store)):
    if user_store.exists(payload.username):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already taken")

    user = User(
        username=payload.username,
        email=payload.email,
        hashed_password=hash_password(payload.password),
    )
    user_store.create(user)
    logger.info("New user registered: %s", payload.username)
    return MessageResponse(message="User registered successfully")


@router.post("/login", response_model=TokenResponse)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    user_store: UserStore = Depends(get_user_store),
):
    user = user_store.get(form_data.username)
    if user is None or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )

    token = create_access_token(subject=user.username)
    logger.info("User logged in: %s", user.username)
    return TokenResponse(access_token=token)


@router.post("/logout", response_model=MessageResponse)
def logout(current_user: User = Depends(get_current_user)):
    # JWTs are stateless, so "logout" server-side just means the client
    # should discard the token. If we needed real revocation we'd keep a
    # denylist of token ids -- noted here for anyone extending this.
    logger.info("User logged out: %s", current_user.username)
    return MessageResponse(message="Logged out successfully")


@router.get("/me")
def me(current_user: User = Depends(get_current_user)):
    return {"username": current_user.username, "email": current_user.email}
