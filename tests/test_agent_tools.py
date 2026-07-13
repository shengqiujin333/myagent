from pathlib import Path

from embedded_agent.artifacts import new_run_dir
from embedded_agent.agent_tools import AGENT_TOOL_SCHEMAS
from embedded_agent.agent_tools import _run_bash
from embedded_agent.agent_tools import invoke_with_agent_tools


class ToolCallingLLM:
    def __init__(self):
        self.bound_tools = None
        self.calls = 0

    def bind_tools(self, tools):
        self.bound_tools = tools
        return self

    def invoke(self, messages):
        self.calls += 1
        if self.calls == 1:
            class Response:
                content = ""
                tool_calls = [
                    {
                        "id": "read-1",
                        "name": "read_file",
                        "args": {"path": "input.txt"},
                    },
                    {
                        "id": "write-1",
                        "name": "write_file",
                        "args": {"path": "output.txt", "content": "generated"},
                    },
                ]

            return Response()

        class Response:
            content = "Finished after using shared tools."

        return Response()


def test_agent_registers_shared_tools_and_runs_them_for_any_state(tmp_path):
    names = {schema["function"]["name"] for schema in AGENT_TOOL_SCHEMAS}
    assert {"bash", "read_file", "write_file"}.issubset(names)
    assert "codebase_memory_search_code" in names

    (tmp_path / "input.txt").write_text("source material", encoding="utf-8")
    llm = ToolCallingLLM()
    output = invoke_with_agent_tools(
        llm,
        "use the shared tools",
        project_root=tmp_path,
        run_dir=tmp_path / "run-1",
        state_name="design",
    )

    assert output == "Finished after using shared tools."
    assert llm.bound_tools is not None
    assert (tmp_path / "output.txt").read_text(encoding="utf-8") == "generated"
    log = tmp_path / "run-1" / "design" / "tool_calls.jsonl"
    assert log.exists()
    assert "read_file" in log.read_text(encoding="utf-8")


def test_new_run_dir_returns_absolute_path_for_relative_run_root(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    run_dir = new_run_dir(Path("runs"))

    assert run_dir.is_absolute()
    assert run_dir.parent == (tmp_path / "runs").resolve()


def test_bash_preserves_utf8_output_from_python(tmp_path):
    output = _run_bash('python -c "print(\'电池内阻测试\')"', tmp_path)

    assert "电池内阻测试" in output
    assert "�" not in output
