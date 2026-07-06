from __future__ import annotations

import abc
import shutil
from pathlib import Path


class FileStore(abc.ABC):
    @abc.abstractmethod
    async def save(self, path: str, data: bytes) -> str: ...

    @abc.abstractmethod
    async def read(self, path: str) -> bytes | None: ...

    @abc.abstractmethod
    async def delete(self, path: str) -> bool: ...

    @abc.abstractmethod
    async def exists(self, path: str) -> bool: ...


class LocalFileStore(FileStore):
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir

    def _resolve(self, path: str) -> Path:
        full = self.base_dir / path
        full.parent.mkdir(parents=True, exist_ok=True)
        return full

    async def save(self, path: str, data: bytes) -> str:
        dest = self._resolve(path)
        dest.write_bytes(data)
        return str(dest)

    async def read(self, path: str) -> bytes | None:
        dest = self._resolve(path)
        if not dest.exists():
            return None
        return dest.read_bytes()

    async def delete(self, path: str) -> bool:
        dest = self._resolve(path)
        if not dest.exists():
            return False
        if dest.is_dir():
            shutil.rmtree(dest)
        else:
            dest.unlink()
        return True

    async def exists(self, path: str) -> bool:
        return self._resolve(path).exists()
