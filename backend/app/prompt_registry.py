import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


REGISTRY_PATH = Path(__file__).resolve().parents[1] / "prompts" / "registry.json"


@dataclass(frozen=True)
class PromptSpec:
    prompt_id: str
    version: str
    role: str
    input_schema: str
    output_schema: str
    tool_whitelist: list[str]
    system_prompt: str


@lru_cache(maxsize=1)
def load_registry() -> dict[str, PromptSpec]:
    raw = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    return {item["prompt_id"]: PromptSpec(**item) for item in raw["prompts"]}


def get_prompt(prompt_id: str) -> PromptSpec:
    try:
        return load_registry()[prompt_id]
    except KeyError as exc:
        raise RuntimeError(f"Prompt Registry 中不存在 {prompt_id}") from exc
