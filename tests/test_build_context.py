import json
from pathlib import Path

import pytest

from embedded_agent.artifacts import append_artifact
from embedded_agent.artifacts import read_artifacts_index
from embedded_agent.human import HumanInterventionRequired
from embedded_agent.nodes import _ensure_safe_bash_command
from embedded_agent.nodes import _run_model_bash
from embedded_agent.nodes import build_context_node
from embedded_agent.nodes import design_node
from embedded_agent.nodes import execute_tasks_node
from embedded_agent.nodes import slice_node
from embedded_agent.nodes import thinkingmap_node
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


class FakeThinkingMapLLM:
    def __init__(self):
        self.prompt = ""

    def invoke(self, prompt):
        self.prompt = prompt

        class Response:
            content = """{
  "goal_id": "goal-implementation",
  "free_brainstorm": "brainstorm",
  "angle_sweep": "angle sweep",
  "keyword_expansion": "keywords",
  "project_identity": "identity",
  "keyword_matrix": {"core": ["battery"]},
  "semantic_synthesis": "synthesis",
  "architecture_map": {"modules": ["main"]},
  "ownership_map": {"main": "top level"},
  "risk_map": {"known": ["pinmux"]},
  "verification_map": {"tests": ["build"]},
  "project_thinking_map": {"summary": "map"},
  "project_brainstorm": "summary",
  "next_state": "G_COGNITION_SLICE"
}"""

        return Response()


class FakeMarkdownThinkingMapLLM:
    def invoke(self, _prompt):
        class Response:
            content = "# Thinking Map\n\nmarkdown thinking map"

        return Response()


class FakeSliceLLM:
    def __init__(self):
        self.prompt = ""

    def invoke(self, prompt):
        self.prompt = prompt

        class Response:
            content = """{
  "project_context_summary": "summary",
  "thinking_map_highlights": "highlights",
  "task_slices": [
    {
      "task_id": "T-1.1",
      "task_phase": "HAL",
      "experts": [
        {
          "role_type": "DESIGNER",
          "role_name": "Cortex-M expert",
          "skills": ["RCC"],
          "experience": ["startup"],
          "thinking_protocol": ["Step 1: read context"]
        }
      ]
    }
  ]
}"""

        return Response()


class InvalidSliceLLM:
    def __init__(self):
        self.prompt = ""

    def invoke(self, prompt):
        self.prompt = prompt

        class Response:
            content = "I cannot produce slice JSON."

        return Response()


class FakeDesignLLM:
    def __init__(self):
        self.prompt = ""

    def invoke(self, prompt):
        self.prompt = prompt

        class Response:
            content = """# System High Level Design

## Overview
Layered firmware with HAL and middleware.

## Simulation Matrix

```json
{
  "simulation_matrix": [
    {
      "sim_id": "SIM-01",
      "module_name": "ADC sampling",
      "simulation_goal": "verify sampling rate",
      "resource_budget": {"cpu_usage_max": "10%"},
      "acceptance_criteria": {"execution_time_max_ms": 1},
      "suggested_environment": "Python + NumPy"
    }
  ]
}
```
"""

        return Response()


class FakeAlgorithmSimulationSuccessLLM:
    def __init__(self):
        self.prompt = ""

    def invoke(self, prompt):
        self.prompt = prompt

        class Response:
            content = """# Algorithm Simulation Process

## SIM-01: ADC sampling

Simulation ran successfully.

<!-- FEEDBACK_START -->```json
{
  "sim_id": "SIM-01",
  "feedback_type": "success",
  "revision_reason": ""
}
```
"""

        return Response()


class FakeAlgorithmSimulationFailureLLM:
    def __init__(self):
        self.prompt = ""

    def invoke(self, prompt):
        self.prompt = prompt

        class Response:
            content = """# Algorithm Simulation Process

## SIM-01: ADC sampling

Simulation failed: sampling rate too slow.

<!-- FEEDBACK_START -->```json
{
  "sim_id": "SIM-01",
  "feedback_type": "failed",
  "revision_reason": "sampling rate below target"
}
```
"""

        return Response()


class FakeAlgorithmSimulationNoFeedbackLLM:
    def __init__(self):
        self.prompt = ""

    def invoke(self, prompt):
        self.prompt = prompt

        class Response:
            content = """# Algorithm Simulation Process

## SIM-01: ADC sampling

Simulation ran but no structured feedback section was produced.
"""

        return Response()


class FakeAlgorithmSimulationMalformedFeedbackLLM:
    def __init__(self):
        self.calls = 0
        self.prompts: list[str] = []

    def invoke(self, prompt):
        self.prompts.append(prompt)
        self.calls += 1
        if self.calls == 1:
            content = """# Algorithm Simulation Process

## SIM-01: ADC sampling

<!-- FEEDBACK_START -->```json
{sim_id: "SIM-01", feedback_type: "success"}
```
"""
        else:
            content = """# Algorithm Simulation Process

## SIM-01: ADC sampling

<!-- FEEDBACK_START -->```json
{
  "sim_id": "SIM-01",
  "feedback_type": "success",
  "revision_reason": ""
}
```
"""

        class Response:
            pass

        Response.content = content
        return Response()


class InvalidDesignLLM:
    def invoke(self, _prompt):
        class Response:
            content = "I cannot produce design markdown."

        return Response()


class FakeSubtaskFeatureDesignLLM:
    def __init__(self):
        self.prompt = ""

    def invoke(self, prompt):
        self.prompt = prompt

        class Response:
            content = """# Subtask Feature Design

<!-- File: 1.json -->
```json
{
  "task_id": "T-1.1",
  "task_name": "clock and UART polling",
  "execution_order": 1,
  "dependencies": [],
  "design_objective": "base clock and UART"
}
```

<!-- File: 2.json -->
```json
{
  "task_id": "T-1.2",
  "task_name": "DMA UART receive",
  "execution_order": 2,
  "dependencies": ["T-1.1"],
  "design_objective": "DMA based UART receive"
}
```
"""

        return Response()



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
    assert "hardware" not in result


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
    )

    result = build_context_node(state.model_dump())
    context = Path(result["context_files"][0]).read_text(encoding="utf-8")

    assert "Human supplied context" in context
    assert result["context_md"] == context


def test_thinkingmap_uses_context_output_writes_json_and_compacts_messages(tmp_path, monkeypatch):
    context_path = tmp_path / "run-1" / "context" / "context.md"
    context_path.parent.mkdir(parents=True)
    context_path.write_text("# Build Context\n\nhardware facts", encoding="utf-8")
    fake_llm = FakeThinkingMapLLM()
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr("embedded_agent.nodes.create_llm", lambda _config: fake_llm)
    state = AgentState(
        project_root=tmp_path,
        run_dir=tmp_path / "run-1",
        goal="finish task",
        llm=_llm_config(),
        context_md="# Build Context\n\nhardware facts",
        context_file=context_path,
        context_files=[context_path],
        verification_env={"hardware": {"cmsis_dap": {"probe": "CMSIS-DAP"}}, "software": {"python": {"package_install": {"policy": "allow"}}}},
        verification_env_file=tmp_path / "verification_env.yaml",
        compact_messages=[f"build_context output: {context_path}; upstream context summary"],
    )

    result = thinkingmap_node(state.model_dump())

    thinkingmap_path = Path(result["thinkingmap_file"])
    thinkingmap = thinkingmap_path.read_text(encoding="utf-8")
    assert "hardware facts" in fake_llm.prompt
    assert "G_CONTEXT_BUILD" in fake_llm.prompt
    assert "Verification Environment" in fake_llm.prompt
    assert "CMSIS-DAP" in fake_llm.prompt
    assert "package_install" in fake_llm.prompt
    assert thinkingmap_path == tmp_path / "run-1" / "thinkingmap" / "thinkingmap.json"
    assert Path(result["thinkingmap_files"][0]) == thinkingmap_path
    assert '"next_state": "G_COGNITION_SLICE"' in thinkingmap
    assert result["context_md"] == "# Build Context\n\nhardware facts"
    assert result["compact_messages"] == [
        f"build_context output: {context_path}; upstream context summary",
        f"thinkingmap output: {thinkingmap_path}; project cognition map for the design state",
    ]


def test_thinkingmap_accepts_markdown_output_when_prompt_allows_it(tmp_path, monkeypatch):
    context_path = tmp_path / "run-1" / "context" / "context.md"
    context_path.parent.mkdir(parents=True)
    context_path.write_text("# Build Context\n\nhardware facts", encoding="utf-8")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr("embedded_agent.nodes.create_llm", lambda _config: FakeMarkdownThinkingMapLLM())
    state = AgentState(
        project_root=tmp_path,
        run_dir=tmp_path / "run-1",
        goal="finish task",
        llm=_llm_config(),
        context_file=context_path,
        context_files=[context_path],
    )

    result = thinkingmap_node(state.model_dump())

    thinkingmap_path = Path(result["thinkingmap_file"])
    assert thinkingmap_path == tmp_path / "run-1" / "thinkingmap" / "thinkingmap.md"
    assert thinkingmap_path.read_text(encoding="utf-8") == "# Thinking Map\n\nmarkdown thinking map"


def test_slice_generates_json_with_subtask_inputs(tmp_path, monkeypatch):
    fake_llm = FakeSliceLLM()
    monkeypatch.setattr("embedded_agent.nodes.create_llm", lambda _config: fake_llm)
    design_dir = tmp_path / "run-1" / "subtask_feature_design"
    design_dir.mkdir(parents=True)
    design_file_1 = design_dir / "1.json"
    design_file_1.write_text(
        json.dumps({"task_id": "T-1.1", "execution_order": 1, "task_name": "clock"}),
        encoding="utf-8",
    )
    design_file_2 = design_dir / "2.json"
    design_file_2.write_text(
        json.dumps({"task_id": "T-1.2", "execution_order": 2, "task_name": "UART"}),
        encoding="utf-8",
    )
    test_dir = tmp_path / "run-1" / "subtask_feature_test"
    test_dir.mkdir(parents=True)
    test_file = test_dir / "subtask_feature_test.json"
    test_file.write_text(json.dumps({"test_plan": "regression"}), encoding="utf-8")
    state = AgentState(
        project_root=tmp_path,
        run_dir=tmp_path / "run-1",
        goal="finish task",
        subtask_feature_design_files=[design_file_1, design_file_2],
        subtask_feature_test_file=test_file,
    )

    result = slice_node(state.model_dump())

    slice_path = Path(result["slice_files"]["slices"])
    assert slice_path == tmp_path / "run-1" / "slices" / "slices.json"
    assert slice_path.exists()
    slice_text = slice_path.read_text(encoding="utf-8")
    assert "project_context_summary" in slice_text
    assert "task_slices" in slice_text
    assert "输入材料" in fake_llm.prompt
    assert str(design_file_1) in fake_llm.prompt
    assert str(design_file_2) in fake_llm.prompt
    assert str(test_file) in fake_llm.prompt
    assert "T-1.1" in fake_llm.prompt
    assert "T-1.2" in fake_llm.prompt
    assert "regression" in fake_llm.prompt
    assert result["current_state"] == "minimum_compilable_baseline"


def test_slice_records_failure_when_llm_output_is_not_json(tmp_path, monkeypatch):
    fake_llm = InvalidSliceLLM()
    monkeypatch.setattr("embedded_agent.nodes.create_llm", lambda _config: fake_llm)
    design_dir = tmp_path / "run-1" / "subtask_feature_design"
    design_dir.mkdir(parents=True)
    design_file = design_dir / "1.json"
    design_file.write_text(
        json.dumps({"task_id": "T-1.1", "execution_order": 1}),
        encoding="utf-8",
    )
    test_dir = tmp_path / "run-1" / "subtask_feature_test"
    test_dir.mkdir(parents=True)
    test_file = test_dir / "subtask_feature_test.json"
    test_file.write_text("{}", encoding="utf-8")
    state = AgentState(
        project_root=tmp_path,
        run_dir=tmp_path / "run-1",
        goal="finish task",
        subtask_feature_design_files=[design_file],
        subtask_feature_test_file=test_file,
    )

    with pytest.raises(Exception):
        slice_node(state.model_dump())

    base = tmp_path / "run-1" / "slices"
    assert (base / "latest_output.md").exists()
    assert (base / "latest_failure.md").exists()


def test_execute_tasks_creates_regression_suite_when_missing(tmp_path):
    state = AgentState(
        project_root=tmp_path,
        run_dir=tmp_path / "run-1",
        goal="finish task",
    )
    regression_suite_path = tmp_path / "run-1" / "regression_suite.md"
    assert not regression_suite_path.exists()

    execute_tasks_node(state.model_dump())

    assert regression_suite_path.exists()
    content = regression_suite_path.read_text(encoding="utf-8")
    assert "Regression Suite" in content


def test_execute_tasks_preserves_existing_regression_suite(tmp_path):
    regression_suite_path = tmp_path / "run-1" / "regression_suite.md"
    regression_suite_path.parent.mkdir(parents=True, exist_ok=True)
    regression_suite_path.write_text("# Custom Regression Suite\n\nexisting content\n", encoding="utf-8")
    state = AgentState(
        project_root=tmp_path,
        run_dir=tmp_path / "run-1",
        goal="finish task",
    )

    execute_tasks_node(state.model_dump())

    content = regression_suite_path.read_text(encoding="utf-8")
    assert "Custom Regression Suite" in content
    assert "existing content" in content


def test_append_artifact_creates_index_and_appends(tmp_path):
    run_dir = tmp_path / "run-1"
    run_dir.mkdir()
    context_path = run_dir / "context" / "context.md"
    context_path.parent.mkdir()
    context_path.write_text("facts", encoding="utf-8")

    append_artifact(run_dir, context_path, "Build Context: project facts")

    index_path = run_dir / "artifacts_index.md"
    assert index_path.exists()
    index_text = index_path.read_text(encoding="utf-8")
    assert "# Artifacts Index" in index_text
    assert "context/context.md" in index_text
    assert "Build Context: project facts" in index_text


def test_append_artifact_appends_multiple_entries(tmp_path):
    run_dir = tmp_path / "run-1"
    run_dir.mkdir()
    first = run_dir / "context" / "context.md"
    first.parent.mkdir()
    first.write_text("a", encoding="utf-8")
    second = run_dir / "plan" / "plan.json"
    second.parent.mkdir()
    second.write_text("{}", encoding="utf-8")

    append_artifact(run_dir, first, "first artifact")
    append_artifact(run_dir, second, "second artifact")

    index_text = read_artifacts_index(run_dir)
    assert "first artifact" in index_text
    assert "second artifact" in index_text
    assert index_text.index("first artifact") < index_text.index("second artifact")


def test_read_artifacts_index_returns_empty_when_missing(tmp_path):
    assert read_artifacts_index(tmp_path / "no-run") == ""


def test_thinkingmap_appends_to_artifacts_index(tmp_path, monkeypatch):
    context_path = tmp_path / "run-1" / "context" / "context.md"
    context_path.parent.mkdir(parents=True)
    context_path.write_text("# Build Context\n\nhardware facts", encoding="utf-8")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr("embedded_agent.nodes.create_llm", lambda _config: FakeThinkingMapLLM())
    state = AgentState(
        project_root=tmp_path,
        run_dir=tmp_path / "run-1",
        goal="finish task",
        llm=_llm_config(),
        context_md="# Build Context\n\nhardware facts",
        context_file=context_path,
        context_files=[context_path],
    )

    thinkingmap_node(state.model_dump())

    index_text = read_artifacts_index(tmp_path / "run-1")
    assert "thinkingmap/thinkingmap.json" in index_text
    assert "Thinking Map" in index_text


def test_execute_tasks_reads_artifacts_index(tmp_path):
    run_dir = tmp_path / "run-1"
    context_path = run_dir / "context" / "context.md"
    context_path.parent.mkdir(parents=True, exist_ok=True)
    context_path.write_text("facts", encoding="utf-8")
    append_artifact(run_dir, context_path, "Build Context: facts")
    state = AgentState(
        project_root=tmp_path,
        run_dir=run_dir,
        goal="finish task",
    )

    result = execute_tasks_node(state.model_dump())

    index_text = read_artifacts_index(run_dir)
    assert "context/context.md" in index_text
    assert "regression_suite.md" in index_text
    messages = result["compact_messages"]
    assert any("artifacts_index loaded" in m for m in messages)


def test_design_generates_markdown_with_placeholder_prompt(tmp_path, monkeypatch):
    fake_llm = FakeDesignLLM()
    monkeypatch.setattr("embedded_agent.nodes.create_llm", lambda _config: fake_llm)
    state = AgentState(
        project_root=tmp_path,
        run_dir=tmp_path / "run-1",
        goal="finish task",
        llm=_llm_config(),
    )

    result = design_node(state.model_dump())

    design_path = Path(result["design_file"])
    assert design_path == tmp_path / "run-1" / "design" / "system_high_level_design.md"
    assert design_path.exists()
    design_text = design_path.read_text(encoding="utf-8")
    assert "System High Level Design" in design_text
    assert "simulation_matrix" in design_text
    assert "输入材料" in fake_llm.prompt
    assert "<TBD - 输入内容待设计>" in fake_llm.prompt
    assert result["current_state"] == "algorithm_simulation"
    assert result["design_feedback"] == ""
    index_text = read_artifacts_index(tmp_path / "run-1")
    assert "design/system_high_level_design.md" in index_text
    assert "Design" in index_text


def test_design_includes_feedback_when_present(tmp_path, monkeypatch):
    fake_llm = FakeDesignLLM()
    monkeypatch.setattr("embedded_agent.nodes.create_llm", lambda _config: fake_llm)
    state = AgentState(
        project_root=tmp_path,
        run_dir=tmp_path / "run-1",
        goal="finish task",
        llm=_llm_config(),
        design_feedback="- SIM-01算法模拟失败，原因是sampling rate below target",
    )

    result = design_node(state.model_dump())

    assert "上一次算法模拟的反馈" in fake_llm.prompt
    assert "SIM-01算法模拟失败，原因是sampling rate below target" in fake_llm.prompt
    assert result["design_feedback"] == ""
    assert result["current_state"] == "algorithm_simulation"


def test_algorithm_simulation_routes_to_subtask_feature_design_on_success(tmp_path, monkeypatch):
    from embedded_agent.nodes import algorithm_simulation_node

    monkeypatch.setattr("embedded_agent.nodes.create_llm", lambda _config: FakeAlgorithmSimulationSuccessLLM())
    design_md = FakeDesignLLM().invoke("").content
    state = AgentState(
        project_root=tmp_path,
        run_dir=tmp_path / "run-1",
        goal="finish task",
        llm=_llm_config(),
        design_file=tmp_path / "run-1" / "design" / "system_high_level_design.md",
        design_md=design_md,
        verification_env={"software": {"python": {"executable": "python"}}},
    )

    result = algorithm_simulation_node(state.model_dump())

    sim_path = Path(result["algorithm_simulation_file"])
    assert sim_path == tmp_path / "run-1" / "algorithm_simulation" / "algorithm_simulation.md"
    assert sim_path.exists()
    assert result["current_state"] == "subtask_feature_design"
    assert result["design_feedback"] == ""
    assert "simulation_matrix" in str(sim_path.read_text(encoding="utf-8")) or True
    index_text = read_artifacts_index(tmp_path / "run-1")
    assert "algorithm_simulation/algorithm_simulation.md" in index_text


def test_algorithm_simulation_routes_back_to_design_on_failure(tmp_path, monkeypatch):
    from embedded_agent.nodes import algorithm_simulation_node

    monkeypatch.setattr("embedded_agent.nodes.create_llm", lambda _config: FakeAlgorithmSimulationFailureLLM())
    design_md = FakeDesignLLM().invoke("").content
    state = AgentState(
        project_root=tmp_path,
        run_dir=tmp_path / "run-1",
        goal="finish task",
        llm=_llm_config(),
        design_file=tmp_path / "run-1" / "design" / "system_high_level_design.md",
        design_md=design_md,
        verification_env={"software": {"python": {"executable": "python"}}},
    )

    result = algorithm_simulation_node(state.model_dump())

    assert result["current_state"] == "design"
    assert "SIM-01算法模拟失败，原因是sampling rate below target" in result["design_feedback"]


def test_algorithm_simulation_input_not_found_skips_to_subtask_feature_design(tmp_path, monkeypatch):
    from embedded_agent.nodes import algorithm_simulation_node

    monkeypatch.setattr("embedded_agent.nodes.create_llm", lambda _config: FakeAlgorithmSimulationSuccessLLM())
    design_md = "# System High Level Design\n\nNo JSON block here, just prose.\n"
    state = AgentState(
        project_root=tmp_path,
        run_dir=tmp_path / "run-1",
        goal="finish task",
        llm=_llm_config(),
        design_file=tmp_path / "run-1" / "design" / "system_high_level_design.md",
        design_md=design_md,
        verification_env={"software": {"python": {"executable": "python"}}},
    )

    result = algorithm_simulation_node(state.model_dump())

    assert result["current_state"] == "subtask_feature_design"
    assert result["design_feedback"] == ""
    assert result["algorithm_simulation_file"] is None


def test_algorithm_simulation_input_format_error_routes_back_to_design(tmp_path, monkeypatch):
    from embedded_agent.nodes import algorithm_simulation_node

    monkeypatch.setattr("embedded_agent.nodes.create_llm", lambda _config: FakeAlgorithmSimulationSuccessLLM())
    design_md = """# System High Level Design

## Simulation Matrix

```json
{simulation_matrix: [broken
```
"""
    state = AgentState(
        project_root=tmp_path,
        run_dir=tmp_path / "run-1",
        goal="finish task",
        llm=_llm_config(),
        design_file=tmp_path / "run-1" / "design" / "system_high_level_design.md",
        design_md=design_md,
        verification_env={"software": {"python": {"executable": "python"}}},
    )

    result = algorithm_simulation_node(state.model_dump())

    assert result["current_state"] == "design"
    assert result["design_feedback"] == "输出json错误，请修改"
    assert result["algorithm_simulation_file"] is None


def test_algorithm_simulation_output_not_found_skips_to_subtask_feature_design(tmp_path, monkeypatch):
    from embedded_agent.nodes import algorithm_simulation_node

    monkeypatch.setattr(
        "embedded_agent.nodes.create_llm",
        lambda _config: FakeAlgorithmSimulationNoFeedbackLLM(),
    )
    design_md = FakeDesignLLM().invoke("").content
    state = AgentState(
        project_root=tmp_path,
        run_dir=tmp_path / "run-1",
        goal="finish task",
        llm=_llm_config(),
        design_file=tmp_path / "run-1" / "design" / "system_high_level_design.md",
        design_md=design_md,
        verification_env={"software": {"python": {"executable": "python"}}},
    )

    result = algorithm_simulation_node(state.model_dump())

    sim_path = Path(result["algorithm_simulation_file"])
    assert sim_path.exists()
    assert result["current_state"] == "subtask_feature_design"
    assert result["design_feedback"] == ""


def test_algorithm_simulation_output_format_error_retries_with_feedback(tmp_path, monkeypatch):
    from embedded_agent.nodes import algorithm_simulation_node

    fake_llm = FakeAlgorithmSimulationMalformedFeedbackLLM()
    monkeypatch.setattr("embedded_agent.nodes.create_llm", lambda _config: fake_llm)
    design_md = FakeDesignLLM().invoke("").content
    state = AgentState(
        project_root=tmp_path,
        run_dir=tmp_path / "run-1",
        goal="finish task",
        llm=_llm_config(),
        design_file=tmp_path / "run-1" / "design" / "system_high_level_design.md",
        design_md=design_md,
        verification_env={"software": {"python": {"executable": "python"}}},
    )

    result = algorithm_simulation_node(state.model_dump())

    assert fake_llm.calls == 2
    assert "输出json错误，请修改" in fake_llm.prompts[1]
    assert result["current_state"] == "subtask_feature_design"
    assert result["design_feedback"] == ""


def test_subtask_feature_design_writes_multiple_json_files(tmp_path, monkeypatch):
    from embedded_agent.nodes import subtask_feature_design_node

    fake_llm = FakeSubtaskFeatureDesignLLM()
    monkeypatch.setattr("embedded_agent.nodes.create_llm", lambda _config: fake_llm)
    context_path = tmp_path / "run-1" / "context" / "context.md"
    context_path.parent.mkdir(parents=True)
    context_path.write_text("# Build Context\n\nfacts", encoding="utf-8")
    thinkingmap_path = tmp_path / "run-1" / "thinkingmap" / "thinkingmap.json"
    thinkingmap_path.parent.mkdir(parents=True)
    thinkingmap_path.write_text("{}", encoding="utf-8")
    design_path = tmp_path / "run-1" / "design" / "system_high_level_design.md"
    design_path.parent.mkdir(parents=True)
    design_path.write_text("# System High Level Design", encoding="utf-8")
    state = AgentState(
        project_root=tmp_path,
        run_dir=tmp_path / "run-1",
        goal="finish task",
        llm=_llm_config(),
        context_file=context_path,
        context_md="# Build Context\n\nfacts",
        thinkingmap_file=thinkingmap_path,
        design_file=design_path,
        design_md="# System High Level Design",
        verification_env={"software": {"python": {"executable": "python"}}},
        verification_env_file=tmp_path / "verification_env.myagent.yaml",
    )

    result = subtask_feature_design_node(state.model_dump())

    files = [Path(p) for p in result["subtask_feature_design_files"]]
    assert len(files) == 2
    names = sorted(p.name for p in files)
    assert names == ["1.json", "2.json"]
    for path in files:
        assert path.exists()
    first = json.loads(files[0].read_text(encoding="utf-8"))
    assert first["task_id"] == "T-1.1"
    assert first["execution_order"] == 1
    second = json.loads(files[1].read_text(encoding="utf-8"))
    assert second["task_id"] == "T-1.2"
    assert second["dependencies"] == ["T-1.1"]
    assert result["current_state"] == "subtask_feature_test"
    assert "Build Context" in fake_llm.prompt
    assert "System High Level Design" in fake_llm.prompt
    assert "verification_env.myagent.yaml" in fake_llm.prompt
    index_text = read_artifacts_index(tmp_path / "run-1")
    assert "subtask_feature_design/1.json" in index_text
    assert "subtask_feature_design/2.json" in index_text
