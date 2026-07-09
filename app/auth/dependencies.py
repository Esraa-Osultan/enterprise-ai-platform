"""
`get_current_user` is what protected endpoints depend on. It pulls the
bearer token from the Authorization header, decodes it, and makes sure
the user still exists.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.core.security import decode_access_token
from app.models.user import User, UserStore

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_user_store() -> UserStore:
    return UserStore()


def get_current_user(
    token: str = Depends(oauth2_scheme),
    user_store: UserStore = Depends(get_user_store),
) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    username = decode_access_token(token)
    if username is None:
        raise credentials_error

    user = user_store.get(username)
    if user is None:
        raise credentials_error

    return user
