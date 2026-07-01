from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


class SessionMode(str, Enum):
    MEDIA = "media"
    CONFERENCE = "conference"


class AssistantMode(str, Enum):
    QA = "qa"
    PLAN = "plan"
    MODEL = "model"
    DEBUG = "debug"


@dataclass
class TranscriptSegment:
    start: float
    end: float
    text: str
    speaker: str | None = None
    confidence: float = 1.0

    def to_compact(self) -> str:
        spk = self.speaker or "?"
        return f't:{self.start:.0f}-{self.end:.0f}|spk:{spk}|text:"{self.text}"|conf:{self.confidence:.2f}'

    def to_dict(self) -> dict[str, Any]:
        return {
            "start": self.start,
            "end": self.end,
            "text": self.text,
            "speaker": self.speaker,
            "confidence": self.confidence,
        }


@dataclass
class SceneIR:
    chunk_id: int = 0
    time_start: float = 0.0
    time_end: float = 0.0
    entities: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    mood: str = ""
    tech_signals: list[str] = field(default_factory=list)
    delivery: str = ""
    dialogue_summary: str = ""
    confidence: float = 1.0
    static: bool = False

    def to_compact(self) -> str:
        parts = [
            f"t:{self.time_start:.0f}-{self.time_end:.0f}",
            f"e:{','.join(self.entities) or '-'}",
            f"a:{','.join(self.actions) or '-'}",
            f"m:{self.mood or '-'}",
            f"tech:{','.join(self.tech_signals) or '-'}",
            f"d:{self.delivery or '-'}",
            f"c:{self.confidence:.2f}",
        ]
        if self.dialogue_summary:
            parts.append(f'dlg:"{self.dialogue_summary}"')
        return "|".join(parts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "time_start": self.time_start,
            "time_end": self.time_end,
            "entities": self.entities,
            "actions": self.actions,
            "mood": self.mood,
            "tech_signals": self.tech_signals,
            "delivery": self.delivery,
            "dialogue_summary": self.dialogue_summary,
            "confidence": self.confidence,
            "static": self.static,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SceneIR:
        return cls(
            chunk_id=data.get("chunk_id", 0),
            time_start=data.get("time_start", 0.0),
            time_end=data.get("time_end", 0.0),
            entities=list(data.get("entities") or []),
            actions=list(data.get("actions") or []),
            mood=data.get("mood") or "",
            tech_signals=list(data.get("tech_signals") or []),
            dialogue_summary=data.get("dialogue_summary") or "",
            delivery=data.get("delivery") or "",
            confidence=float(data.get("confidence", 1.0)),
            static=bool(data.get("static", False)),
        )


@dataclass
class ChunkResult:
    chunk_id: int
    scene: SceneIR
    transcript: list[TranscriptSegment] = field(default_factory=list)
    captions: dict[str, str] = field(default_factory=dict)
    skipped_perception: bool = False


@dataclass
class ActionItem:
    task: str
    owner: str | None = None
    deadline: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"task": self.task, "owner": self.owner, "deadline": self.deadline}


@dataclass
class QAEntry:
    question: str
    answer: str
    citations: list[str] = field(default_factory=list)
    mode: AssistantMode = AssistantMode.QA
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "answer": self.answer,
            "citations": self.citations,
            "mode": self.mode.value,
            "timestamp": self.timestamp,
        }


@dataclass
class SessionMemory:
    session_id: str = field(default_factory=lambda: str(uuid4()))
    mode: SessionMode = SessionMode.MEDIA
    source_path: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    scenes: list[SceneIR] = field(default_factory=list)
    transcripts: list[TranscriptSegment] = field(default_factory=list)
    captions_by_style: dict[str, list[str]] = field(default_factory=dict)
    rolling_summary: str = ""
    action_items: list[ActionItem] = field(default_factory=list)
    qa_history: list[QAEntry] = field(default_factory=list)
    chunk_count: int = 0

    def compact_context(self, max_scenes: int = 20) -> str:
        lines = []
        for scene in self.scenes[-max_scenes:]:
            lines.append(f"SCENE: {scene.to_compact()}")
        for seg in self.transcripts[-max_scenes * 2 :]:
            lines.append(f"TRANS: {seg.to_compact()}")
        if self.rolling_summary:
            lines.append(f"SUMMARY: {self.rolling_summary}")
        return "\n".join(lines)

    def all_entities(self) -> set[str]:
        entities: set[str] = set()
        for scene in self.scenes:
            entities.update(e.lower() for e in scene.entities)
        return entities

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "mode": self.mode.value,
            "source_path": self.source_path,
            "created_at": self.created_at,
            "scenes": [s.to_dict() for s in self.scenes],
            "transcripts": [t.to_dict() for t in self.transcripts],
            "captions_by_style": self.captions_by_style,
            "rolling_summary": self.rolling_summary,
            "action_items": [a.to_dict() for a in self.action_items],
            "qa_history": [q.to_dict() for q in self.qa_history],
            "chunk_count": self.chunk_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionMemory:
        mem = cls(
            session_id=data["session_id"],
            mode=SessionMode(data.get("mode", "media")),
            source_path=data.get("source_path", ""),
            created_at=data.get("created_at", ""),
            rolling_summary=data.get("rolling_summary", ""),
            chunk_count=data.get("chunk_count", 0),
        )
        mem.scenes = [SceneIR.from_dict(s) for s in data.get("scenes") or []]
        mem.transcripts = [
            TranscriptSegment(
                start=t["start"],
                end=t["end"],
                text=t["text"],
                speaker=t.get("speaker"),
                confidence=float(t.get("confidence", 1.0)),
            )
            for t in data.get("transcripts") or []
        ]
        mem.captions_by_style = dict(data.get("captions_by_style") or {})
        mem.action_items = [
            ActionItem(task=a["task"], owner=a.get("owner"), deadline=a.get("deadline"))
            for a in data.get("action_items") or []
        ]
        mem.qa_history = [
            QAEntry(
                question=q["question"],
                answer=q["answer"],
                citations=list(q.get("citations") or []),
                mode=AssistantMode(q.get("mode", "qa")),
                timestamp=q.get("timestamp", ""),
            )
            for q in data.get("qa_history") or []
        ]
        return mem
