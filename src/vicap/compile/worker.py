from __future__ import annotations

import logging

from vicap.config import get_settings, load_models_config, load_styles
from vicap.fireworks.client import FireworksClient
from vicap.models import SceneIR, SessionMemory, TranscriptSegment

logger = logging.getLogger(__name__)

STYLE_KEYS = ["formal", "sarcastic", "humorous_tech", "humorous_non_tech"]


STYLE_YAML_KEYS = {
    "formal": "formal",
    "sarcastic": "sarcastic",
    "humorous_tech": "humorous-tech",
    "humorous_non_tech": "humorous-non-tech",
}


def _build_council_prompt(
    scene: SceneIR,
    transcript: list[TranscriptSegment],
    prior_captions: dict[str, str] | None = None,
    delta_only: bool = False,
) -> str:
    styles = load_styles()
    style_block = []
    for key in STYLE_KEYS:
        yaml_key = STYLE_YAML_KEYS[key]
        cfg = styles.get(yaml_key, {})
        style_block.append(f"- {key}: {cfg.get('voice', key)} | {cfg.get('guardrails', '')}")

    tech_note = ""
    if not scene.tech_signals and "humorous_tech" in STYLE_KEYS:
        tech_note = (
            "\nNOTE: tech_signals empty — humorous_tech must use dry universal wit, not forced jargon."
        )

    trans_lines = "\n".join(t.to_compact() for t in transcript) or "(no speech)"
    prior = ""
    if prior_captions and delta_only:
        prior = f"\nPrior captions (append new content only):\n{prior_captions}"

    return f"""Persona Council: write one caption per style for this chunk.
Return ONLY JSON: {{"formal":"...","sarcastic":"...","humorous_tech":"...","humorous_non_tech":"..."}}
Max 30 words per caption. Ground strictly in scene facts and transcript.

SCENE IR: {scene.to_compact()}
TRANSCRIPT:
{trans_lines}
{tech_note}
{prior}

Style definitions:
{chr(10).join(style_block)}
"""


class CompileWorker:
    def __init__(self, client: FireworksClient | None = None) -> None:
        self.client = client or FireworksClient()
        self.settings = get_settings()
        self.models_cfg = load_models_config()

    async def persona_council(
        self,
        scene: SceneIR,
        transcript: list[TranscriptSegment],
        prior_captions: dict[str, str] | None = None,
        delta_only: bool = False,
    ) -> dict[str, str]:
        minimax_cfg = self.models_cfg.get("minimax", {})
        prompt = _build_council_prompt(scene, transcript, prior_captions, delta_only)

        result = await self.client.chat_completion(
            model=self.settings.minimax_model,
            messages=[
                {
                    "role": "system",
                    "content": "You are the Persona Council. Output valid JSON only.",
                },
                {"role": "user", "content": prompt},
            ],
            model_kind="minimax",
            max_tokens=minimax_cfg.get("max_tokens", 4096),
            temperature=minimax_cfg.get("temperature", 0.2),
        )

        data = self.client.parse_json_response(result.content)
        return {k: str(data.get(k, "")).strip() for k in STYLE_KEYS if data.get(k)}

    async def compile_session_batch(self, memory: SessionMemory) -> dict[str, str]:
        """Full-clip captions from accumulated session context."""
        if not memory.scenes:
            return {}
        combined_scene = memory.scenes[-1]
        combined_scene.time_start = memory.scenes[0].time_start
        combined_scene.time_end = memory.scenes[-1].time_end
        all_entities: list[str] = []
        all_actions: list[str] = []
        all_tech: list[str] = []
        for s in memory.scenes:
            all_entities.extend(s.entities)
            all_actions.extend(s.actions)
            all_tech.extend(s.tech_signals)
        combined_scene.entities = list(dict.fromkeys(all_entities))
        combined_scene.actions = list(dict.fromkeys(all_actions))
        combined_scene.tech_signals = list(dict.fromkeys(all_tech))

        return await self.persona_council(combined_scene, memory.transcripts)

    def validate_captions(self, captions: dict[str, str], scene: SceneIR) -> dict[str, str]:
        """Simple anti-hallucination: log if caption has no overlap with known entities/actions."""
        known = {e.lower() for e in scene.entities} | {a.lower() for a in scene.actions}
        if not known:
            return captions
        validated = {}
        for style, text in captions.items():
            text_lower = text.lower()
            if any(k in text_lower for k in known) or len(text.split()) <= 8:
                validated[style] = text
            else:
                logger.warning("Caption failed entity gate for %s: %s", style, text[:80])
                validated[style] = text
        return validated
