import json

from embedded_agent.codebase_tools import CODEBASE_MEMORY_TOOL_SCHEMAS
from embedded_agent.codebase_tools import run_codebase_memory_tool


def test_codebase_memory_tool_schemas_register_requested_tools():
    names = {schema["function"]["name"] for schema in CODEBASE_MEMORY_TOOL_SCHEMAS}

    assert names == {
        "codebase_memory_list_projects",
        "codebase_memory_index_repository",
        "codebase_memory_index_status",
        "codebase_memory_get_architecture",
        "codebase_memory_search_code",
        "codebase_memory_search_graph",
        "codebase_memory_get_graph_schema",
        "codebase_memory_query_graph",
        "codebase_memory_trace_path",
        "codebase_memory_detect_changes",
        "codebase_memory_get_code_snippet",
    }


def test_run_codebase_memory_tool_invokes_cli_with_json_payload(monkeypatch):
    captured = {}

    class Completed:
        returncode = 0
        stdout = "ok"
        stderr = ""

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return Completed()

    monkeypatch.setattr("embedded_agent.codebase_tools.subprocess.run", fake_run)

    output = run_codebase_memory_tool(
        "codebase_memory_search_code",
        {
            "project": "C-Users-123-Desktop-neizu-tasknew-battery_re",
            "pattern": "timer_scheduler",
            "limit": 10,
        },
    )

    assert captured["command"][:3] == ["codebase-memory-mcp", "cli", "search_code"]
    assert json.loads(captured["command"][3]) == {
        "project": "C-Users-123-Desktop-neizu-tasknew-battery_re",
        "pattern": "timer_scheduler",
        "limit": 10,
    }
    assert captured["kwargs"]["encoding"] == "utf-8"
    assert "exit_code=0" in output
    assert "ok" in output


def test_run_codebase_memory_list_projects_has_no_payload(monkeypatch):
    captured = {}

    class Completed:
        returncode = 0
        stdout = "[]"
        stderr = ""

    def fake_run(command, **_kwargs):
        captured["command"] = command
        return Completed()

    monkeypatch.setattr("embedded_agent.codebase_tools.subprocess.run", fake_run)

    run_codebase_memory_tool("codebase_memory_list_projects", {})

    assert captured["command"] == ["codebase-memory-mcp", "cli", "list_projects"]
