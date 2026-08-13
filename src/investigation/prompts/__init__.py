"""Versioned Gemini system instructions for the three logical AML agents."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PromptSpec:
    version: str
    system_instruction: str


_ROOT = Path(__file__).parent
_SPECS = {
    "investigation_supervisor": ("investigation-supervisor-v2-vi", "investigation_supervisor.txt"),
    "explanation_agent": ("risk-explanation-v4-vi", "explanation_agent.txt"),
    "evidence_critic": ("evidence-critic-v2-vi", "evidence_critic.txt"),
}


def get_prompt(agent_name: str) -> PromptSpec:
    try:
        version, filename = _SPECS[agent_name]
    except KeyError as exc:
        raise ValueError(f"No versioned prompt is registered for {agent_name!r}") from exc
    return PromptSpec(version=version, system_instruction=(_ROOT / filename).read_text(encoding="utf-8").strip())
