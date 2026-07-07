from vicap.pipeline import Pipeline, ProgressCallback


def test_pipeline_init():
    p = Pipeline()
    assert p.perceive is not None
    assert p.compile is not None
    assert p.assistant is not None
    assert p.progress_callback is None


def test_pipeline_with_callback():
    calls = []

    async def cb(done: int, total: int) -> None:
        calls.append((done, total))

    p = Pipeline(progress_callback=cb)
    assert p.progress_callback is not None


def test_sse_cap_config_default():
    from vicap.config import get_settings

    s = get_settings()
    assert s.max_stream_events > 0
    assert isinstance(s.max_stream_events, int)
