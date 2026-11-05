"""StoragePort: content-addressed private files. File first (temp, fsync, atomic rename), row second.

Files are never deleted in the MVP (R18).
"""

from __future__ import annotations

import hashlib
import os
import tempfile
import uuid
from pathlib import Path

from common.settings import get_settings


class LocalStorage:
    def __init__(self, root: str | None = None) -> None:
        self.root = Path(root or get_settings().FILE_STORAGE_ROOT).resolve()

    def key_for(self, shop_id: uuid.UUID | str, sha256: str) -> str:
        return f"{shop_id}/{sha256[:2]}/{sha256}"

    def put(self, shop_id: uuid.UUID | str, data: bytes) -> tuple[str, str]:
        sha = hashlib.sha256(data).hexdigest()
        key = self.key_for(shop_id, sha)
        path = self.root / key
        if path.exists():
            return sha, key
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        return sha, key

    def put_artifact(self, shop_id: uuid.UUID | str, data: bytes) -> tuple[str, str]:
        return self.put(f"{shop_id}/artifacts", data)

    def get(self, key: str) -> bytes:
        path = (self.root / key).resolve()
        if self.root not in path.parents:
            raise PermissionError("storage key escapes the storage root")
        return path.read_bytes()

    def exists(self, key: str) -> bool:
        return (self.root / key).exists()
