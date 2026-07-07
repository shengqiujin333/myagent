from __future__ import annotations

import os

from embedded_agent.config import LLMConfig


def compact_system_prompt() -> str:
    return (
        "You are a disk-first embedded coding agent. Keep messages compact: "
        "include only the current state, task id, objective, required artifact paths, "
        "small excerpts, and the latest failure summary. Read large context from files."
    )


def create_llm(config: LLMConfig):
    api_key = os.getenv(config.api_key_env)
    if not api_key:
        raise RuntimeError(f"missing API key environment variable: {config.api_key_env}")

    try:
        from langchain_openai import ChatOpenAI
    except ImportError as exc:
        raise RuntimeError("langchain-openai is required for DeepSeek OpenAI-compatible chat") from exc

    return ChatOpenAI(
        model=config.model,
        api_key=api_key,
        base_url=config.base_url,
        temperature=config.temperature,
        timeout=config.timeout_sec,
        max_tokens=config.max_tokens,
    )
