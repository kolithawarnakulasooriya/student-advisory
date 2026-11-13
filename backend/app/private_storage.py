"""Private local objects. Keys never contain user-controlled path components."""

import os
from pathlib import Path
from uuid import UUID, uuid4

from app.security import ApiError


class PrivateStorage:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)

    def path(self, key: str) -> Path:
        parts = key.split("/")
        if len(parts) != 2 or parts[0] not in {"quarantine", "artifacts"}:
            raise ApiError(503, "STORAGE_UNAVAILABLE", "Private storage is unavailable.")
        try:
            UUID(parts[1])
        except ValueError:
            raise ApiError(503, "STORAGE_UNAVAILABLE", "Private storage is unavailable.") from None
        path = self.root / parts[0] / parts[1]
        if path.is_symlink() or not path.resolve().is_relative_to(self.root):
            raise ApiError(503, "STORAGE_UNAVAILABLE", "Private storage is unavailable.")
        return path

    def write(self, data: bytes, area: str = "quarantine") -> str:
        key = f"{area}/{uuid4()}"
        path = self.path(key)
        path.parent.mkdir(mode=0o700, exist_ok=True)
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
        return key

    def read(self, key: str) -> bytes:
        return self.path(key).read_bytes()
