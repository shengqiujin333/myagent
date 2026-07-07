from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from embedded_agent.hardware import HardwareConfig


class LLMConfig(BaseModel):
    provider: str = "deepseek"
    model: str = "deepseek-v4-flash"
    base_url: str = "https://api.deepseek.com"
    api_key_env: str = "DEEPSEEK_API_KEY"
    temperature: float = 0.2
    timeout_sec: int = 120
    max_tokens: int = 4096


class AgentConfig(BaseModel):
    project_root: Path
    run_root: Path = Path("runs")
    goal: str | None = None
    llm: LLMConfig = Field(default_factory=LLMConfig)
    hardware: HardwareConfig
    entrypoint: str = "main"
    context_file_limit: int = 200


def load_config(path: Path) -> AgentConfig:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data.setdefault("llm", {})
    data.setdefault("hardware", {})
    data["hardware"].setdefault("project_root", data["project_root"])
    return AgentConfig.model_validate(data)
