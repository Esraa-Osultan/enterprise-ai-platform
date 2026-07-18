"""
`get_current_user` is what protected endpoints depend on. It pulls the
bearer token from the Authorization header, decodes it, and makes sure
the user still exists.
"""

from functools import lru_cache

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.core.security import decode_access_token
from app.models.user import User, UserStore

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


@lru_cache
def get_user_store() -> UserStore:
    # Cached so every request shares one UserStore (and one threading.Lock).
    # A fresh instance per request each had its own uncontended lock, so
    # two concurrent /auth/register calls with a not-yet-existing username
    # could both pass the `exists()` check before either write landed --
    # a check-then-act race that could lose one of the two accounts.
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
