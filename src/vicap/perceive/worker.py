from __future__ import annotations

import logging

from vicap.config import get_settings, load_models_config
from vicap.fireworks.client import FireworksClient
from vicap.models import SceneIR, TranscriptSegment

logger = logging.getLogger(__name__)

PERCEIVE_SYSTEM = """You analyze video/audio chunks for a caption compiler.
Return ONLY valid JSON with this schema:
{
  "entities": ["string"],
  "actions": ["string"],
  "mood": "string",
  "tech_signals": ["string"],
  "delivery": "string",
  "dialogue_summary": "string",
  "confidence": 0.0-1.0,
  "transcript": [{"start": float, "end": float, "text": "string", "speaker": "string|null"}]
}
Rules:
- Neutral factual extraction only. No styled captions.
- tech_signals: IDE, error, API, code, stacktrace, server, etc. Empty array if none.
- transcript: verbatim or close paraphrase of spoken words in this chunk.
- delivery: tone e.g. deadpan, excited, frustrated.
"""


class PerceiveWorker:
    def __init__(self, client: FireworksClient | None = None) -> None:
        self.client = client or FireworksClient()
        self.settings = get_settings()
        self.models_cfg = load_models_config()

    async def perceive_chunk(
        self,
        video_b64: str,
        chunk_id: int,
        time_start: float,
        time_end: float,
    ) -> tuple[SceneIR, list[TranscriptSegment]]:
        kimi_cfg = self.models_cfg.get("kimi", {})
        messages = [
            {"role": "system", "content": PERCEIVE_SYSTEM},
            {
                "role": "user",
                "content": [
                    {
                        "type": "video_url",
                        "video_url": {"url": f"data:video/mp4;base64,{video_b64}"},
                    },
                    {
                        "type": "text",
                        "text": (
                            f"Chunk {chunk_id}, time {time_start:.1f}s to {time_end:.1f}s. "
                            "Extract scene facts and transcript."
                        ),
                    },
                ],
            },
        ]

        extra: dict = {}
        if kimi_cfg.get("instant_mode", True):
            extra = {"thinking": {"type": "disabled"}}

        result = await self.client.chat_completion(
            model=self.settings.kimi_model,
            messages=messages,
            model_kind="kimi",
            max_tokens=kimi_cfg.get("max_tokens", 2048),
            temperature=kimi_cfg.get("temperature", 0.3),
            extra_body=extra,
        )

        data = self.client.parse_json_response(result.content)
        scene = SceneIR(
            chunk_id=chunk_id,
            time_start=time_start,
            time_end=time_end,
            entities=list(data.get("entities") or []),
            actions=list(data.get("actions") or []),
            mood=data.get("mood") or "",
            tech_signals=list(data.get("tech_signals") or []),
            delivery=data.get("delivery") or "",
            dialogue_summary=data.get("dialogue_summary") or "",
            confidence=float(data.get("confidence", 0.9)),
        )

        segments: list[TranscriptSegment] = []
        for item in data.get("transcript") or []:
            if not item.get("text"):
                continue
            segments.append(
                TranscriptSegment(
                    start=float(item.get("start", time_start)),
                    end=float(item.get("end", time_end)),
                    text=str(item["text"]),
                    speaker=item.get("speaker"),
                    confidence=float(item.get("confidence", 0.9)),
                )
            )

        return scene, segments

    async def perceive_full_clip(self, video_b64: str, duration: float) -> tuple[SceneIR, list[TranscriptSegment]]:
        """Single-pass perception for short clips (batch mode)."""
        return await self.perceive_chunk(video_b64, 0, 0.0, duration)
