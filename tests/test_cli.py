from pathlib import Path
from types import SimpleNamespace

import embedded_agent.cli as cli_module
from embedded_agent.cli import continue_after_build_context_human
from embedded_agent.cli import handle_human_intervention
from embedded_agent.cli import invoke_graph
from embedded_agent.cli import parse_args
from embedded_agent.cli import read_multiline_input
from embedded_agent.cli import render_run_report
from embedded_agent.cli import restore_state_from_run
from embedded_agent.cli import run_from_state
from embedded_agent.human import HumanInterventionRequired
from embedded_agent.state import AgentState


class FakeWorkflowLLM:
    def __init__(self):
        self.calls = 0

    def invoke(self, _prompt):
        self.calls += 1
        if self.calls == 1:
            content = """{
  "goal_id": "goal-implementation",
  "free_brainstorm": "brainstorm",
  "angle_sweep": "angle sweep",
  "keyword_expansion": "keywords",
  "project_identity": "identity",
  "keyword_matrix": {},
  "semantic_synthesis": "synthesis",
  "architecture_map": {},
  "ownership_map": {},
  "risk_map": {},
  "verification_map": {},
  "project_thinking_map": {},
  "project_brainstorm": "summary",
  "next_state": "G_COGNITION_SLICE"
}"""
        elif self.calls == 2:
            content = "# System High Level Design\n\n```json\n{\n  \"simulation_matrix\": []\n}\n```\n"
        else:
            content = "{}"

        class Response:
            pass

        Response.content = content
        return Response()


def test_cli_accepts_goal_argument():
    args = parse_args(["--config", "configs/agent_config.myagent.yaml", "--goal", "finish board task"])

    assert args.config == "configs/agent_config.myagent.yaml"
    assert args.goal == "finish board task"


def test_cli_accepts_resume_arguments():
    args = parse_args(
        [
            "--config",
            "configs/agent_config.myagent.yaml",
            "--goal",
            "finish board task",
            "--resume-run",
            "runs/20260709-090019",
            "--from-state",
            "design",
        ]
    )

    assert args.resume_run == Path("runs/20260709-090019")
    assert args.from_state == "design"


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
    )

    invoke_graph(graph, state)

    assert graph.config == {"configurable": {"thread_id": "20260707-150000"}}


def test_restore_state_from_run_loads_artifact_paths(tmp_path):
    config = SimpleNamespace(
        project_root=tmp_path / "project",
        llm=SimpleNamespace(model_dump=lambda: {"provider": "test"}),
    )

    run_dir = tmp_path / "runs" / "run-1"
    context_file = run_dir / "context" / "context.md"
    thinkingmap_file = run_dir / "thinkingmap" / "thinkingmap.json"
    design_file = run_dir / "design" / "system_high_level_design.md"
    context_file.parent.mkdir(parents=True)
    thinkingmap_file.parent.mkdir(parents=True)
    design_file.parent.mkdir(parents=True)
    context_file.write_text("# Build Context\n\nfacts", encoding="utf-8")
    thinkingmap_file.write_text("{}", encoding="utf-8")
    design_file.write_text("# System High Level Design", encoding="utf-8")

    state = restore_state_from_run(config, run_dir, "finish task", "algorithm_simulation", tmp_path / "verification_env.yaml", {"software": {"python": {}}})

    assert state.run_dir == run_dir
    assert state.current_state == "algorithm_simulation"
    assert state.context_md == "# Build Context\n\nfacts"
    assert state.context_file == context_file
    assert state.thinkingmap_file == thinkingmap_file
    assert state.design_file == design_file
    assert state.verification_env_file == tmp_path / "verification_env.yaml"
    assert state.verification_env == {"software": {"python": {}}}


def test_run_from_state_starts_at_requested_node(tmp_path, monkeypatch):
    calls = []

    def fake_design(state):
        calls.append("design")
        state["current_state"] = "algorithm_simulation"
        return state

    def fake_algorithm_simulation(state):
        calls.append("algorithm_simulation")
        state["current_state"] = "subtask_feature_design"
        return state

    def fake_subtask_feature_design(state):
        calls.append("subtask_feature_design")
        state["current_state"] = "done"
        return state

    monkeypatch.setattr("embedded_agent.graph.design_node", fake_design)
    monkeypatch.setattr("embedded_agent.graph.algorithm_simulation_node", fake_algorithm_simulation)
    monkeypatch.setattr("embedded_agent.graph.subtask_feature_design_node", fake_subtask_feature_design)
    state = AgentState(project_root=tmp_path, run_dir=tmp_path / "run-1", goal="finish task")

    result = run_from_state(state, "design")

    assert calls == ["design", "algorithm_simulation", "subtask_feature_design"]
    assert result["current_state"] == "done"


def test_run_from_state_converts_node_failure_to_human_intervention(tmp_path, monkeypatch):
    def fake_design(_state):
        raise RuntimeError("bad model output")

    monkeypatch.setattr("embedded_agent.graph.design_node", fake_design)
    state = AgentState(project_root=tmp_path, run_dir=tmp_path / "run-1", goal="finish task")

    try:
        run_from_state(state, "design")
    except HumanInterventionRequired as exc:
        assert exc.payload["state"] == "design"
        assert "bad model output" in exc.payload["issue"]
    else:
        raise AssertionError("expected HumanInterventionRequired")


def test_read_multiline_input_until_eof(monkeypatch):
    values = iter(["# Build Context", "", "content", "EOF"])
    monkeypatch.setattr("builtins.input", lambda: next(values))

    assert read_multiline_input("paste") == "# Build Context\n\ncontent"


def test_continue_after_build_context_human_writes_context_and_continues(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    fake_llm = FakeWorkflowLLM()
    monkeypatch.setattr("embedded_agent.nodes.create_llm", lambda _config: fake_llm)
    state = AgentState(
        project_root=tmp_path,
        run_dir=tmp_path / "run-1",
        goal="finish task",
    )

    result = continue_after_build_context_human(state, "# Build Context\n\nhuman context")

    context_path = tmp_path / "run-1" / "context" / "context.md"
    assert context_path.read_text(encoding="utf-8") == "# Build Context\n\nhuman context"
    assert result["context_md"] == "# Build Context\n\nhuman context"
    assert Path(result["context_file"]) == context_path
    assert Path(result["thinkingmap_file"]).exists()
    assert Path(result["design_file"]).exists()


def test_handle_human_intervention_does_not_print_prompt_path(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    fake_llm = FakeWorkflowLLM()
    monkeypatch.setattr("embedded_agent.nodes.create_llm", lambda _config: fake_llm)
    state = AgentState(
        project_root=tmp_path,
        run_dir=tmp_path / "run-1",
        goal="finish task",
    )
    context_dir = state.run_dir / "context"
    context_dir.mkdir(parents=True)
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
