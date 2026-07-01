from vicap.models import SceneIR, SessionMemory, TranscriptSegment


def test_scene_ir_compact():
    scene = SceneIR(
        chunk_id=1,
        time_start=3.0,
        time_end=6.0,
        entities=["person", "laptop"],
        actions=["typing"],
        mood="tense",
        tech_signals=["ide"],
        confidence=0.91,
    )
    compact = scene.to_compact()
    assert "e:person,laptop" in compact
    assert "tech:ide" in compact
    assert "c:0.91" in compact


def test_transcript_compact():
    seg = TranscriptSegment(start=1.0, end=3.0, text="hello world", speaker="A")
    assert 'text:"hello world"' in seg.to_compact()


def test_session_memory_roundtrip():
    mem = SessionMemory(source_path="/test.mp4")
    mem.scenes.append(SceneIR(entities=["cat"]))
    mem.transcripts.append(TranscriptSegment(start=0, end=1, text="meow"))
    restored = SessionMemory.from_dict(mem.to_dict())
    assert restored.session_id == mem.session_id
    assert restored.scenes[0].entities == ["cat"]
    assert restored.transcripts[0].text == "meow"


def test_compact_context():
    mem = SessionMemory()
    mem.scenes.append(SceneIR(entities=["dog"], actions=["running"]))
    mem.transcripts.append(TranscriptSegment(start=0, end=2, text="fetch"))
    mem.rolling_summary = "A dog runs."
    ctx = mem.compact_context()
    assert "SCENE:" in ctx
    assert "TRANS:" in ctx
    assert "SUMMARY:" in ctx
