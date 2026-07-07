from embedded_agent.cli import continue_after_build_context_human
from embedded_agent.cli import handle_human_intervention
from embedded_agent.cli import invoke_graph
from embedded_agent.cli import parse_args
from embedded_agent.cli import read_multiline_input
from embedded_agent.cli import render_run_report
from embedded_agent.human import HumanInterventionRequired
from embedded_agent.state import AgentState


def test_cli_accepts_goal_argument():
    args = parse_args(["--config", "configs/agent_config.myagent.yaml", "--goal", "finish board task"])

    assert args.config == "configs/agent_config.myagent.yaml"
    assert args.goal == "finish board task"


def test_render_run_report_includes_progress_and_failure_summary(tmp_path):
    failure_dir = tmp_path / "execution" / "task-1"
    failure_dir.mkdir(parents=True)
    (failure_dir / "latest_failure.md").write_text("stopped after 10 attempts: build failed", encoding="utf-8")

    report = render_run_report(
        {
            "run_dir": tmp_path,
            "compact_messages": [
                "build_context complete; context file: context.md",
                "task task-1 failed: build failed",
            ],
            "failed_task_id": "task-1",
        }
    )

    assert "run_dir=" in report
    assert "build_context complete" in report
    assert "failed_task_id=task-1" in report
    assert "stopped after 10 attempts: build failed" in report
    assert "latest_failure=" in report


def test_invoke_graph_passes_langgraph_thread_id(tmp_path):
    class FakeGraph:
        def __init__(self):
            self.config = None

        def invoke(self, _state, config=None):
            self.config = config
            return {"run_dir": tmp_path}

    graph = FakeGraph()
    state = AgentState(
        project_root=tmp_path,
        run_dir=tmp_path / "20260707-150000",
        goal="finish task",
        hardware={},
    )

    invoke_graph(graph, state)

    assert graph.config == {"configurable": {"thread_id": "20260707-150000"}}


def test_read_multiline_input_until_eof(monkeypatch):
    values = iter(["# Build Context", "", "content", "EOF"])
    monkeypatch.setattr("builtins.input", lambda: next(values))

    assert read_multiline_input("paste") == "# Build Context\n\ncontent"


def test_continue_after_build_context_human_writes_context_and_continues_until_failure(tmp_path):
    state = AgentState(
        project_root=tmp_path,
        run_dir=tmp_path / "run-1",
        goal="finish task",
        hardware={"build_command": "bad-build", "flash_command": "bad-flash", "serial_port": "COM3", "max_attempts": 1},
    )

    result = continue_after_build_context_human(state, "# Build Context\n\nhuman context")

    context_path = tmp_path / "run-1" / "context" / "context.md"
    assert context_path.read_text(encoding="utf-8") == "# Build Context\n\nhuman context"
    assert result["context_md"] == "# Build Context\n\nhuman context"
    assert result["plan_file"]


def test_handle_human_intervention_does_not_print_prompt_path(tmp_path, monkeypatch, capsys):
    state = AgentState(
        project_root=tmp_path,
        run_dir=tmp_path / "run-1",
        goal="finish task",
        hardware={"build_command": "bad-build", "flash_command": "bad-flash", "serial_port": "COM3", "max_attempts": 1},
    )
    context_dir = state.run_dir / "context"
    context_dir.mkdir(parents=True)
    (context_dir / "prompt.md").write_text("user-owned prompt", encoding="utf-8")
    (context_dir / "latest_failure.md").write_text("model failed", encoding="utf-8")
    values = iter(["# Build Context", "", "human context", "EOF"])
    monkeypatch.setattr("builtins.input", lambda: next(values))

    exc = HumanInterventionRequired(
        {
            "type": "human_intervention_required",
            "state": "build_context",
            "issue": "model failed",
            "request": "Provide context_md",
            "run_dir": state.run_dir,
        }
    )

    handle_human_intervention(exc, state)

    output = capsys.readouterr().out
    assert "prompt=" not in output
    assert "latest_failure=" in output
    assert "Paste the complete context.md content now." in output
