from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field


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
    verification_env_file: Path | None = None
    entrypoint: str = "main"
    context_file_limit: int = 200


def load_config(path: Path) -> AgentConfig:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data.setdefault("llm", {})
    return AgentConfig.model_validate(data)


def resolve_config_reference(config_path: Path, reference: Path) -> Path:
    if reference.is_absolute():
        return reference
    cwd_path = Path.cwd() / reference
    if cwd_path.exists():
        return cwd_path
    return config_path.parent / reference


def load_verification_env(config: AgentConfig, config_path: Path) -> tuple[Path | None, dict[str, object]]:
    if not config.verification_env_file:
        return None, {}
    env_path = resolve_config_reference(config_path, config.verification_env_file)
    data = yaml.safe_load(env_path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"verification env file must contain a YAML object: {env_path}")
    return env_path, data
