from pathlib import Path

import pytest

from embedded_agent.human import HumanInterventionRequired
from embedded_agent.nodes import _ensure_safe_bash_command
from embedded_agent.nodes import _run_model_bash
from embedded_agent.nodes import build_context_node
from embedded_agent.state import AgentState


class FakeContextLLM:
    def __init__(self):
        self.prompt = ""

    def invoke(self, prompt):
        self.prompt = prompt

        class Response:
            content = "# Build Context\n\n## Goal\n\nSummarized by model.\n"

        return Response()


class ToolCallingLLM:
    def __init__(self):
        self.tools = None
        self.messages = []
        self.calls = 0

    def bind_tools(self, tools):
        self.tools = tools
        return self

    def invoke(self, messages):
        self.messages.append(messages)
        self.calls += 1
        if self.calls == 1:
            class ToolResponse:
                content = ""
                tool_calls = [
                    {
                        "id": "tool-1",
                        "name": "bash",
                        "args": {"command": "python -c \"print('tool-output')\""},
                    }
                ]

            return ToolResponse()

        class FinalResponse:
            content = "# Build Context\n\n## Goal\n\nTool-informed summary.\n"

        return FinalResponse()


def _llm_config():
    return {
        "provider": "deepseek",
        "model": "deepseek-v4-flash",
        "base_url": "https://api.deepseek.com",
        "api_key_env": "DEEPSEEK_API_KEY",
        "temperature": 0.2,
        "timeout_sec": 120,
        "max_tokens": 4096,
    }


def test_build_context_sends_goal_and_bash_tool_rules_without_python_file_materials(tmp_path, monkeypatch):
    target = tmp_path / "tasknew"
    target.mkdir()
    (target / "user_req.txt").write_text("Need LED blink. Hardware: PA5 -> LED anode.\n", encoding="utf-8")
    wrong_target = tmp_path / "wrong-target"
    wrong_target.mkdir()

    fake_llm = FakeContextLLM()
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr("embedded_agent.nodes.create_llm", lambda _config: fake_llm)

    state = AgentState(
        project_root=target,
        run_dir=tmp_path / "runs" / "run-1",
        goal=f"finish {wrong_target} task",
        llm=_llm_config(),
        hardware={"build_command": "build", "flash_command": "flash", "serial_port": "COM3"},
    )

    result = build_context_node(state.model_dump())
    context = Path(result["context_files"][0]).read_text(encoding="utf-8")

    assert f"finish {wrong_target} task" in fake_llm.prompt
    assert str(target) in fake_llm.prompt
    assert "Available Tool" in fake_llm.prompt
    assert "bash" in fake_llm.prompt
    assert "Prefer `fd` for file discovery" in fake_llm.prompt
    assert "Do not use `grep`" in fake_llm.prompt
    assert "file_manifest" not in fake_llm.prompt
    assert "directory_manifest" not in fake_llm.prompt
    assert "file_contents" not in fake_llm.prompt
    assert "PA5 -> LED anode" not in fake_llm.prompt
    assert "Summarized by model" in context
    assert result["context_md"] == context
    assert Path(result["context_file"]) == Path(result["context_files"][0])
    assert Path(result["project_root"]) == target
    assert Path(result["hardware"]["project_root"]) == target


def test_build_context_executes_model_requested_bash_tool(tmp_path, monkeypatch):
    target = tmp_path / "tasknew"
    target.mkdir()

    tool_llm = ToolCallingLLM()
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr("embedded_agent.nodes.create_llm", lambda _config: tool_llm)

    state = AgentState(
        project_root=target,
        run_dir=tmp_path / "runs" / "run-1",
        goal="finish task",
        llm=_llm_config(),
        hardware={"build_command": "build", "flash_command": "flash", "serial_port": "COM3"},
    )

    result = build_context_node(state.model_dump())
    context = Path(result["context_files"][0]).read_text(encoding="utf-8")

    assert tool_llm.tools
    tool_names = {tool["function"]["name"] for tool in tool_llm.tools}
    assert "bash" in tool_names
    assert "codebase_memory_search_code" in tool_names
    assert "codebase_memory_query_graph" in tool_names
    assert "Tool-informed summary" in context
    assert not (tmp_path / "runs" / "run-1" / "context" / "prompt.md").exists()
    assert (tmp_path / "runs" / "run-1" / "context" / "tool_calls.jsonl").exists()
    assert result["context_md"] == context
    assert Path(result["context_file"]).exists()
    second_messages = tool_llm.messages[-1]
    assert any(isinstance(message, dict) and "tool-output" in message.get("content", "") for message in second_messages)


@pytest.mark.parametrize(
    "command",
    [
        "grep UART user_req.txt",
        "grep -R UART .",
        "Get-ChildItem -Recurse .",
        "find . -type f",
        "Get-Content *.txt",
        'cmd /c "dir /b /s"',
    ],
)
def test_build_context_bash_tool_blocks_disallowed_commands(command):
    with pytest.raises(ValueError):
        _ensure_safe_bash_command(command)


def test_build_context_bash_tool_allows_powershell_line_ranges():
    _ensure_safe_bash_command("(Get-Content document.md)[10..20]")


def test_build_context_bash_tool_runs_powershell_commands(tmp_path):
    (tmp_path / "user_req.txt").write_text("hello\n", encoding="utf-8")

    result = _run_model_bash("Get-Content user_req.txt -TotalCount 1", tmp_path)

    assert "exit_code=0" in result
    assert "hello" in result


def test_build_context_bash_tool_normalizes_cd_prefix(tmp_path):
    (tmp_path / "user_req.txt").write_text("hello\n", encoding="utf-8")

    result = _run_model_bash(f'cd "{tmp_path}" && Get-Content user_req.txt -TotalCount 1', tmp_path)

    assert "exit_code=0" in result
    assert "hello" in result


def test_build_context_requests_human_when_llm_fails_without_writing_fallback(tmp_path, monkeypatch):
    target = tmp_path / "tasknew"
    target.mkdir()

    def broken_create_llm(_config):
        raise RuntimeError("missing API key environment variable: DEEPSEEK_API_KEY")

    monkeypatch.setattr("embedded_agent.nodes.create_llm", broken_create_llm)

    state = AgentState(
        project_root=target,
        run_dir=tmp_path / "runs" / "run-1",
        goal="finish task",
        llm=_llm_config(),
        hardware={"build_command": "build", "flash_command": "flash", "serial_port": "COM3"},
    )

    with pytest.raises(HumanInterventionRequired) as error:
        build_context_node(state.model_dump())

    assert error.value.payload["type"] == "human_intervention_required"
    assert error.value.payload["state"] == "build_context"
    assert "DEEPSEEK_API_KEY" in error.value.payload["issue"]
    assert not (tmp_path / "runs" / "run-1" / "context" / "context.md").exists()
    assert not (tmp_path / "runs" / "run-1" / "context" / "prompt.md").exists()
    assert (tmp_path / "runs" / "run-1" / "context" / "latest_failure.md").exists()


def test_build_context_can_resume_with_human_context_markdown(tmp_path, monkeypatch):
    target = tmp_path / "tasknew"
    target.mkdir()

    def broken_create_llm(_config):
        raise RuntimeError("model returned invalid output")

    def fake_human_intervention(*_args, **_kwargs):
        return {"context_md": "# Build Context\n\n## Goal\n\nHuman supplied context.\n"}

    monkeypatch.setattr("embedded_agent.nodes.create_llm", broken_create_llm)
    monkeypatch.setattr("embedded_agent.nodes.request_human_intervention", fake_human_intervention)

    state = AgentState(
        project_root=target,
        run_dir=tmp_path / "runs" / "run-1",
        goal="finish task",
        llm=_llm_config(),
        hardware={"build_command": "build", "flash_command": "flash", "serial_port": "COM3"},
    )

    result = build_context_node(state.model_dump())
    context = Path(result["context_files"][0]).read_text(encoding="utf-8")

    assert "Human supplied context" in context
    assert result["context_md"] == context
