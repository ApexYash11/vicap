from __future__ import annotations

import abc
import asyncio
import logging
import shutil
from pathlib import Path
from typing import Any

from botocore.exceptions import ClientError as S3ClientError

logger = logging.getLogger(__name__)


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


class S3FileStore(FileStore):
    """S3-backed FileStore using boto3 in a thread pool for async compatibility.

    Also compatible with GCS via S3-compatible endpoint URLs.
    """

    def __init__(
        self,
        bucket: str,
        prefix: str = "",
        endpoint_url: str | None = None,
        region: str = "us-east-1",
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
    ) -> None:
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self.endpoint_url = endpoint_url
        self.region = region
        self.access_key_id = access_key_id
        self.secret_access_key = secret_access_key
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            import boto3

            kwargs: dict[str, Any] = {"region_name": self.region}
            if self.endpoint_url:
                kwargs["endpoint_url"] = self.endpoint_url
            if self.access_key_id and self.secret_access_key:
                kwargs["aws_access_key_id"] = self.access_key_id
                kwargs["aws_secret_access_key"] = self.secret_access_key
            self._client = boto3.client("s3", **kwargs)
        return self._client

    def _key(self, path: str) -> str:
        return f"{self.prefix}/{path}" if self.prefix else path

    async def _run(self, method: str, **kwargs: Any) -> Any:
        client = self._get_client()
        fn = getattr(client, method)
        return await asyncio.to_thread(fn, **kwargs)

    async def save(self, path: str, data: bytes) -> str:
        key = self._key(path)
        await self._run("put_object", Bucket=self.bucket, Key=key, Body=data)
        return f"s3://{self.bucket}/{key}"

    async def read(self, path: str) -> bytes | None:
        key = self._key(path)
        try:
            resp = await self._run("get_object", Bucket=self.bucket, Key=key)
            body = resp["Body"].read()
            return body
        except S3ClientError as exc:
            if exc.response["Error"]["Code"] in ("NoSuchKey", "404"):
                return None
            raise

    async def delete(self, path: str) -> bool:
        key = self._key(path)
        try:
            await self._run("delete_object", Bucket=self.bucket, Key=key)
            return True
        except Exception:
            return False

    async def exists(self, path: str) -> bool:
        key = self._key(path)
        try:
            await self._run("head_object", Bucket=self.bucket, Key=key)
            return True
        except S3ClientError as exc:
            if exc.response["Error"]["Code"] == "404":
                return False
            raise
