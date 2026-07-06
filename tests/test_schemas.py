from vicap.models.schemas import (
    HealthResponse,
    BatchProcessResponse,
    SessionResponse,
    JobResponse,
    JobCreateResponse,
    AskRequest,
    AskResponse,
    ClipListResponse,
    ErrorResponse,
)


def test_health_response():
    r = HealthResponse(status="ok", has_api_key=True, kimi_model="kimi", minimax_model="minimax")
    assert r.status == "ok"
    assert r.db_connected is False


def test_batch_process_response():
    r = BatchProcessResponse(
        session_id="abc",
        captions={"formal": ["hello"]},
        summary="test",
        action_items=[{"task": "fix"}],
        ledger={"total_calls": 1},
    )
    assert r.session_id == "abc"
    assert r.captions["formal"] == ["hello"]


def test_session_response_defaults():
    r = SessionResponse(
        session_id="abc",
        mode="media",
        source_path=None,
        created_at="2026-01-01",
        status="completed",
    )
    assert r.captions_by_style == {}
    assert r.scenes == []


def test_job_response():
    r = JobResponse(
        job_id="abc",
        session_id="def",
        job_type="batch",
        status="running",
        progress={"chunks_done": 5, "chunks_total": 10},
    )
    assert r.status == "running"
    assert r.progress["chunks_done"] == 5


def test_job_create_response():
    r = JobCreateResponse(job_id="j1", session_id="s1", status="queued", poll_url="/jobs/j1")
    assert r.status == "queued"
    assert r.poll_url == "/jobs/j1"


def test_ask_request():
    r = AskRequest(question="What is this?")
    assert r.question == "What is this?"
    assert r.mode == "qa"


def test_ask_request_invalid_mode():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        AskRequest(question="test", mode="invalid")


def test_ask_response():
    r = AskResponse(question="q", answer="a", mode="qa", timestamp="now")
    assert r.answer == "a"
    assert r.citations == []


def test_clip_list_response():
    r = ClipListResponse(clips=["a.mp4", "b.mp4"])
    assert len(r.clips) == 2


def test_error_response():
    r = ErrorResponse(error_code="E404", detail="Not found")
    assert r.error is True
    assert r.detail == "Not found"
