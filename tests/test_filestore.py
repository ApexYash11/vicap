from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from vicap.core.filestore import FileStore, LocalFileStore, S3FileStore


def test_filestore_abc():
    """FileStore ABC cannot be instantiated directly."""
    try:
        FileStore()  # type: ignore[abstract]
        assert False, "Should have raised TypeError"
    except TypeError:
        pass


@pytest.mark.asyncio
async def test_local_filestore(tmp_path):
    fs = LocalFileStore(tmp_path)

    path = "sub/file.txt"
    data = b"hello world"

    saved = await fs.save(path, data)
    assert saved == str(tmp_path / path)

    assert await fs.exists(path) is True

    read = await fs.read(path)
    assert read == data

    await fs.delete(path)
    assert await fs.exists(path) is False


@pytest.mark.asyncio
async def test_local_filestore_read_missing(tmp_path):
    fs = LocalFileStore(tmp_path)
    assert await fs.read("nonexistent.txt") is None


@pytest.mark.asyncio
async def test_local_filestore_delete_missing(tmp_path):
    fs = LocalFileStore(tmp_path)
    assert await fs.delete("nonexistent.txt") is False


class TestS3FileStore:
    def test_key_with_prefix(self):
        fs = S3FileStore(bucket="test-bucket", prefix="vicap")
        assert fs._key("path/file.txt") == "vicap/path/file.txt"

    def test_key_without_prefix(self):
        fs = S3FileStore(bucket="test-bucket")
        assert fs._key("path/file.txt") == "path/file.txt"

    @pytest.mark.asyncio
    @patch("boto3.client")
    async def test_save(self, mock_boto3):
        client = MagicMock()
        mock_boto3.return_value = client

        fs = S3FileStore(bucket="my-bucket", prefix="vicap")

        result = await fs.save("test/file.bin", b"data")

        client.put_object.assert_called_once_with(
            Bucket="my-bucket", Key="vicap/test/file.bin", Body=b"data"
        )
        assert result == "s3://my-bucket/vicap/test/file.bin"

    @pytest.mark.asyncio
    @patch("boto3.client")
    async def test_read_found(self, mock_boto3):
        client = MagicMock()
        mock_boto3.return_value = client
        client.get_object.return_value = {"Body": MagicMock(read=MagicMock(return_value=b"data"))}

        fs = S3FileStore(bucket="my-bucket")
        result = await fs.read("test/file.bin")

        assert result == b"data"

    @pytest.mark.asyncio
    @patch("boto3.client")
    async def test_read_not_found(self, mock_boto3):
        from botocore.exceptions import ClientError

        client = MagicMock()
        mock_boto3.return_value = client
        client.get_object.side_effect = ClientError({"Error": {"Code": "NoSuchKey"}}, "get_object")

        fs = S3FileStore(bucket="my-bucket")
        result = await fs.read("test/file.bin")

        assert result is None

    @pytest.mark.asyncio
    @patch("boto3.client")
    async def test_exists(self, mock_boto3):
        client = MagicMock()
        mock_boto3.return_value = client

        fs = S3FileStore(bucket="my-bucket")
        assert await fs.exists("test/file.bin") is True
        client.head_object.assert_called_once_with(Bucket="my-bucket", Key="test/file.bin")

    @pytest.mark.asyncio
    @patch("boto3.client")
    async def test_exists_not_found(self, mock_boto3):
        from botocore.exceptions import ClientError

        client = MagicMock()
        mock_boto3.return_value = client
        client.head_object.side_effect = ClientError({"Error": {"Code": "404"}}, "head")

        fs = S3FileStore(bucket="my-bucket")
        assert await fs.exists("test/file.bin") is False

    @pytest.mark.asyncio
    @patch("boto3.client")
    async def test_delete(self, mock_boto3):
        client = MagicMock()
        mock_boto3.return_value = client

        fs = S3FileStore(bucket="my-bucket")
        assert await fs.delete("test/file.bin") is True
        client.delete_object.assert_called_once_with(Bucket="my-bucket", Key="test/file.bin")

    @pytest.mark.asyncio
    @patch("boto3.client")
    async def test_delete_failure(self, mock_boto3):
        client = MagicMock()
        mock_boto3.return_value = client
        client.delete_object.side_effect = Exception("fail")

        fs = S3FileStore(bucket="my-bucket")
        assert await fs.delete("test/file.bin") is False
