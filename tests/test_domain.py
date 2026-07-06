import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from vicap.models.sql import ApiKey, Session, Job
from vicap.core.security import hash_api_key
from vicap.core.auth import generate_api_key


class TestApiKeyService:
    @pytest.mark.asyncio
    async def test_create_key(self):
        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        from vicap.domain.api_key_service import ApiKeyService

        svc = ApiKeyService(mock_db)
        svc.generate_api_key = lambda: ("raw_test_key", hash_api_key("raw_test_key"))

        with patch.object(
            svc, "generate_api_key", return_value=("raw_test_key", hash_api_key("raw_test_key"))
        ):
            raw, key = await svc.create_key("test-key")
            assert raw == "raw_test_key"
            mock_db.add.assert_called_once()


class TestSessionService:
    @pytest.mark.asyncio
    async def test_create_session_record(self):
        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        from vicap.domain.session_service import SessionService

        svc = SessionService(mock_db)
        session = await svc.create_session_record(mode="media", source_path="/test.mp4")
        mock_db.add.assert_called_once()
        assert session is not None

    @pytest.mark.asyncio
    async def test_delete_not_found(self):
        mock_db = AsyncMock()
        mock_execute = AsyncMock()
        mock_db.execute = mock_execute
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_execute.return_value = mock_result

        from vicap.domain.session_service import SessionService

        svc = SessionService(mock_db)
        result = await svc.delete_session_record("nonexistent")
        assert result is False


class TestJobService:
    @pytest.mark.asyncio
    async def test_create_job(self):
        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        from vicap.domain.job_service import JobService

        svc = JobService(mock_db)
        job = await svc.create_job("00000000-0000-0000-0000-000000000000")
        mock_db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancel_nonexistent(self):
        mock_db = AsyncMock()
        mock_execute = AsyncMock()
        mock_db.execute = mock_execute
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_execute.return_value = mock_result

        from vicap.domain.job_service import JobService

        svc = JobService(mock_db)
        result = await svc.cancel_job("00000000-0000-0000-0000-000000000000")
        assert result is None


class TestFireworksClient:
    def test_parse_json_response(self):
        from vicap.fireworks.client import FireworksClient

        text = '{"key": "value"}'
        assert FireworksClient.parse_json_response(text) == {"key": "value"}

    def test_parse_json_with_code_fence(self):
        from vicap.fireworks.client import FireworksClient

        text = '```json\n{"key": "value"}\n```'
        assert FireworksClient.parse_json_response(text) == {"key": "value"}

    def test_parse_json_braces_only(self):
        from vicap.fireworks.client import FireworksClient

        text = 'Some text {"key": "value"} trailing'
        assert FireworksClient.parse_json_response(text) == {"key": "value"}


class TestAuth:
    def test_hash_api_key(self):
        h = hash_api_key("hello")
        assert len(h) == 64  # SHA256 hex

    def test_generate_api_key(self):
        raw, h = generate_api_key()
        assert raw.startswith("vicap_")
        assert len(raw) > 32
        assert h == hash_api_key(raw)
