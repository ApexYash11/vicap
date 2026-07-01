from __future__ import annotations

import json
import logging

from vicap.config import get_settings, load_models_config
from vicap.fireworks.client import FireworksClient
from vicap.models import ActionItem, AssistantMode, QAEntry, SessionMemory

logger = logging.getLogger(__name__)

MODE_PROMPTS = {
    AssistantMode.QA: (
        "Answer the user's question using ONLY the session context. "
        "Cite transcript timestamps like t:12-15. If unknown, say so."
    ),
    AssistantMode.PLAN: (
        "Create a numbered action plan from the discussion: next steps, milestones, dependencies, risks."
    ),
    AssistantMode.MODEL: (
        "Describe the architecture/system discussed. Include a Mermaid diagram in a ```mermaid block."
    ),
    AssistantMode.DEBUG: (
        "The discussion involves a technical issue. Provide: (1) likely root causes, "
        "(2) repro steps, (3) suggested fixes. Be specific and grounded in transcript."
    ),
}


class AssistantWorker:
    def __init__(self, client: FireworksClient | None = None) -> None:
        self.client = client or FireworksClient()
        self.settings = get_settings()
        self.models_cfg = load_models_config()

    async def rolling_summary(self, memory: SessionMemory) -> str:
        minimax_cfg = self.models_cfg.get("minimax", {})
        result = await self.client.chat_completion(
            model=self.settings.minimax_model,
            messages=[
                {
                    "role": "system",
                    "content": "Summarize the session in 3-5 sentences. Be factual.",
                },
                {
                    "role": "user",
                    "content": f"SESSION:\n{memory.compact_context()}",
                },
            ],
            model_kind="minimax",
            max_tokens=512,
            temperature=0.2,
        )
        return result.content.strip()

    async def extract_action_items(self, memory: SessionMemory) -> list[ActionItem]:
        minimax_cfg = self.models_cfg.get("minimax", {})
        result = await self.client.chat_completion(
            model=self.settings.minimax_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        'Extract action items as JSON array: '
                        '[{"task":"...","owner":"...|null","deadline":"...|null"}]'
                    ),
                },
                {"role": "user", "content": memory.compact_context()},
            ],
            model_kind="minimax",
            max_tokens=1024,
            temperature=0.1,
        )
        try:
            data = self.client.parse_json_response(result.content)
            if isinstance(data, dict) and "items" in data:
                data = data["items"]
            if not isinstance(data, list):
                return []
            return [
                ActionItem(
                    task=str(item.get("task", "")),
                    owner=item.get("owner"),
                    deadline=item.get("deadline"),
                )
                for item in data
                if item.get("task")
            ]
        except Exception as exc:
            logger.warning("action item parse failed: %s", exc)
            return []

    async def ask(
        self,
        memory: SessionMemory,
        question: str,
        mode: AssistantMode = AssistantMode.QA,
    ) -> QAEntry:
        system = MODE_PROMPTS.get(mode, MODE_PROMPTS[AssistantMode.QA])
        result = await self.client.chat_completion(
            model=self.settings.minimax_model,
            messages=[
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": f"CONTEXT:\n{memory.compact_context()}\n\nQUESTION:\n{question}",
                },
            ],
            model_kind="minimax",
            max_tokens=self.models_cfg.get("minimax", {}).get("max_tokens", 4096),
            temperature=0.3,
        )

        citations = []
        for seg in memory.transcripts:
            if any(word.lower() in seg.text.lower() for word in question.split() if len(word) > 4):
                citations.append(f"t:{seg.start:.0f}-{seg.end:.0f}")

        entry = QAEntry(
            question=question,
            answer=result.content.strip(),
            citations=citations[:5],
            mode=mode,
        )
        memory.qa_history.append(entry)
        return entry

    def suggest_debug_mode(self, memory: SessionMemory) -> bool:
        debug_signals = {"error", "bug", "crash", "500", "stacktrace", "down", "fail", "exception"}
        for scene in memory.scenes:
            for sig in scene.tech_signals:
                if any(d in sig.lower() for d in debug_signals):
                    return True
        for seg in memory.transcripts:
            lower = seg.text.lower()
            if any(d in lower for d in debug_signals):
                return True
        return False
