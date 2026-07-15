import sys
import types

from pathlib import Path

from embedded_agent.config import AgentConfig, LLMConfig, load_config
from embedded_agent.llm import compact_system_prompt, create_llm
from embedded_agent.state import AgentState


def test_default_llm_uses_deepseek_v4_flash():
    config = LLMConfig()

    assert config.provider == "deepseek"
    assert config.model == "deepseek-v4-flash"
    assert config.base_url == "https://api.deepseek.com"
    assert config.api_key_env == "DEEPSEEK_API_KEY"


def test_create_llm_uses_deepseek_openai_compatible_settings(monkeypatch):
    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            self.model_name = kwargs["model"]
            self.openai_api_base = kwargs["base_url"]
            self.kwargs = kwargs

    fake_module = types.SimpleNamespace(ChatOpenAI=FakeChatOpenAI)
    monkeypatch.setitem(sys.modules, "langchain_openai", fake_module)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    llm = create_llm(LLMConfig())

    assert llm.model_name == "deepseek-v4-flash"
    assert str(llm.openai_api_base).rstrip("/") == "https://api.deepseek.com"
    assert llm.kwargs["api_key"] == "test-key"


def test_compact_system_prompt_mentions_disk_first_messages():
    prompt = compact_system_prompt()

    assert "disk-first" in prompt
    assert "paths" in prompt
    assert "latest failure summary" in prompt


def test_load_config_keeps_deepseek_llm_defaults():
    config = load_config(Path("configs/agent_config.myagent.yaml"))

    assert config.llm.provider == "deepseek"
    assert config.llm.model == "deepseek-v4-flash"
    assert config.verification_env_file == Path("configs/verification_env.myagent.yaml")


def test_task_attempt_limit_defaults_and_local_config_are_five(tmp_path):
    config = AgentConfig(project_root=tmp_path)
    state = AgentState(project_root=tmp_path, run_dir=tmp_path / "run", goal="test")
    local_config = load_config(Path("configs/agent_config.myagent.yaml"))

    assert config.max_task_attempts == 5
    assert state.max_task_attempts == 5
    assert local_config.max_task_attempts == 5
