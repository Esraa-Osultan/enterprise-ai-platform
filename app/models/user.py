"""
Very small JSON-file "database" for users.

For a real deployment you'd swap this for Postgres + SQLAlchemy, but the
rest of the app only talks to `UserStore`, so that swap would touch this
one file only -- everything else (routers, JWT, tests) stays the same.
"""

import json
import os
import threading
from dataclasses import asdict, dataclass

from app.core.config import get_settings


@dataclass
class User:
    username: str
    email: str
    hashed_password: str


class UserStore:
    def __init__(self, path: str | None = None):
        self.path = path or get_settings().users_db_path
        self._lock = threading.Lock()
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        if not os.path.exists(self.path):
            self._write({})

    def _read(self) -> dict:
        with open(self.path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _write(self, data: dict) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def get(self, username: str) -> User | None:
        data = self._read()
        record = data.get(username)
        return User(**record) if record else None

    def exists(self, username: str) -> bool:
        return username in self._read()

    def create(self, user: User) -> None:
        with self._lock:
            data = self._read()
            if user.username in data:
                raise ValueError(f"User '{user.username}' already exists")
            data[user.username] = asdict(user)
            self._write(data)
