from __future__ import annotations

import asyncio
import json
import logging
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from vicap.assistant.worker import AssistantWorker
from vicap.compile.worker import STYLE_KEYS, CompileWorker
from vicap.config import get_settings
from vicap.fireworks.client import FireworksClient
from vicap.ingest.video import (
    chunk_video,
    encode_video_b64,
    get_video_duration,
    normalize_media,
)
from vicap.models import ChunkResult, SceneIR, SessionMemory, SessionMode
from vicap.perceive.worker import PerceiveWorker
from vicap.session.store import SessionStore

logger = logging.getLogger(__name__)


class Pipeline:
    def __init__(
        self,
        client: FireworksClient | None = None,
        store: SessionStore | None = None,
    ) -> None:
        self.client = client or FireworksClient()
        self.store = store or SessionStore(get_settings().redis_url)
        self.perceive = PerceiveWorker(self.client)
        self.compile = CompileWorker(self.client)
        self.assistant = AssistantWorker(self.client)
        self.settings = get_settings()

    async def create_session(
        self,
        source_path: Path,
        mode: SessionMode = SessionMode.MEDIA,
    ) -> SessionMemory:
        memory = SessionMemory(mode=mode, source_path=str(source_path))
        await self.store.save(memory)
        return memory

    async def process_batch(
        self,
        source_path: Path,
        session_id: str | None = None,
        mode: SessionMode = SessionMode.MEDIA,
    ) -> SessionMemory:
        """Process entire clip: batch single-pass for short clips, else chunked."""
        settings = self.settings
        settings.output_dir.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory() as tmp:
            normalized = Path(tmp) / "normalized.mp4"
            normalize_media(source_path, normalized)
            duration = get_video_duration(normalized)

            if session_id:
                memory = await self.store.get(session_id)
                if not memory:
                    raise ValueError(f"Session {session_id} not found")
            else:
                memory = await self.create_session(source_path, mode)

            # Short clip: single Kimi + single Persona Council
            if duration <= 15.0:
                b64 = encode_video_b64(normalized)
                scene, segments = await self.perceive.perceive_full_clip(b64, duration)
                memory.scenes.append(scene)
                memory.transcripts.extend(segments)
                captions = await self.compile.persona_council(scene, segments)
                captions = self.compile.validate_captions(captions, scene)
                memory.captions_by_style = {k: [v] for k, v in captions.items()}
                memory.chunk_count = 1
            else:
                chunks = chunk_video(normalized)
                prior: dict[str, str] = {}
                for chunk in chunks:
                    if chunk.is_static:
                        scene = SceneIR(
                            chunk_id=chunk.chunk_id,
                            time_start=chunk.start_sec,
                            time_end=chunk.end_sec,
                            static=True,
                        )
                        if memory.scenes:
                            prev = memory.scenes[-1]
                            scene.entities = list(prev.entities)
                            scene.actions = list(prev.actions)
                            scene.tech_signals = list(prev.tech_signals)
                        segments: list = []
                    else:
                        scene, segments = await self.perceive.perceive_chunk(
                            chunk.video_b64,
                            chunk.chunk_id,
                            chunk.start_sec,
                            chunk.end_sec,
                        )
                    memory.scenes.append(scene)
                    memory.transcripts.extend(segments)

                    if not chunk.is_static:
                        captions = await self.compile.persona_council(
                            scene, segments, prior, delta_only=bool(prior)
                        )
                        captions = self.compile.validate_captions(captions, scene)
                        prior = captions
                        for k, v in captions.items():
                            memory.captions_by_style.setdefault(k, []).append(v)

                    memory.chunk_count += 1

            memory.rolling_summary = await self.assistant.rolling_summary(memory)
            memory.action_items = await self.assistant.extract_action_items(memory)
            await self.store.save(memory)

            out_path = settings.output_dir / f"{memory.session_id}_captions.json"
            out_path.write_text(json.dumps(memory.to_dict(), indent=2), encoding="utf-8")
            return memory

    async def stream_session(
        self,
        source_path: Path,
        mode: SessionMode = SessionMode.MEDIA,
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield SSE-style events while processing chunks live."""
        with tempfile.TemporaryDirectory() as tmp:
            normalized = Path(tmp) / "normalized.mp4"
            normalize_media(source_path, normalized)

            memory = await self.create_session(source_path, mode)
            yield {"event": "session_start", "session_id": memory.session_id}

            chunks = chunk_video(normalized)
            prior: dict[str, str] = {}

            for chunk in chunks:
                if chunk.is_static and memory.scenes:
                    scene = SceneIR(
                        chunk_id=chunk.chunk_id,
                        time_start=chunk.start_sec,
                        time_end=chunk.end_sec,
                        static=True,
                    )
                    prev = memory.scenes[-1]
                    scene.entities = list(prev.entities)
                    scene.actions = list(prev.actions)
                    scene.tech_signals = list(prev.tech_signals)
                    segments = []
                    skipped = True
                else:
                    scene, segments = await self.perceive.perceive_chunk(
                        chunk.video_b64,
                        chunk.chunk_id,
                        chunk.start_sec,
                        chunk.end_sec,
                    )
                    skipped = False

                memory.scenes.append(scene)
                memory.transcripts.extend(segments)
                memory.chunk_count += 1

                yield {
                    "event": "transcript",
                    "chunk_id": chunk.chunk_id,
                    "segments": [s.to_dict() for s in segments],
                    "scene": scene.to_compact(),
                    "skipped_perception": skipped,
                }

                if not skipped:
                    captions = await self.compile.persona_council(
                        scene, segments, prior, delta_only=bool(prior)
                    )
                    captions = self.compile.validate_captions(captions, scene)
                    prior = captions
                    for k, v in captions.items():
                        memory.captions_by_style.setdefault(k, []).append(v)

                    yield {
                        "event": "captions",
                        "chunk_id": chunk.chunk_id,
                        "captions": captions,
                    }

                await self.store.save(memory)

            memory.rolling_summary = await self.assistant.rolling_summary(memory)
            memory.action_items = await self.assistant.extract_action_items(memory)
            await self.store.save(memory)

            suggest_debug = self.assistant.suggest_debug_mode(memory)
            yield {
                "event": "session_complete",
                "session_id": memory.session_id,
                "summary": memory.rolling_summary,
                "action_items": [a.to_dict() for a in memory.action_items],
                "suggest_debug_mode": suggest_debug,
                "ledger": self.client.ledger.to_dict(),
            }

    async def ask_session(
        self,
        session_id: str,
        question: str,
        mode: str = "qa",
    ) -> dict[str, Any]:
        from vicap.models import AssistantMode

        memory = await self.store.get(session_id)
        if not memory:
            raise ValueError(f"Session {session_id} not found")
        assistant_mode = AssistantMode(mode)
        entry = await self.assistant.ask(memory, question, assistant_mode)
        await self.store.save(memory)
        return entry.to_dict()
