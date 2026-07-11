from __future__ import annotations

import argparse
import json
from pathlib import Path

from embedded_agent.artifacts import append_artifact
from embedded_agent.artifacts import new_run_dir
from embedded_agent.artifacts import write_text
from embedded_agent.config import load_config, load_verification_env
from embedded_agent.graph import build_graph, build_node_map, MAX_GRAPH_STEPS
from embedded_agent.human import HumanInterventionRequired, request_human_intervention
from embedded_agent.state import AgentState

RESUMABLE_STATES = (
    "build_context",
    "thinkingmap",
    "design",
    "algorithm_simulation",
    "subtask_feature_design",
    "subtask_feature_test",
    "slice",
    "minimum_compilable_baseline",
    "material_summary",
    "execute_tasks",
    "task_design",
    "task_test",
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run embedded LangGraph coding agent")
    parser.add_argument("--config", required=True, help="Path to agent_config.yaml")
    parser.add_argument("--goal", help="Concrete task goal for this run. Overrides config goal.")
    parser.add_argument("--resume-run", type=Path, help="Existing run directory to resume from.")
    parser.add_argument(
        "--from-state",
        choices=RESUMABLE_STATES,
        default="build_context",
        help="State to start from when resuming. Defaults to build_context.",
    )
    return parser.parse_args(argv)


def render_run_report(result: dict) -> str:
    run_dir = Path(result["run_dir"])
    lines = [f"run_dir={run_dir}"]

    messages = result.get("compact_messages") or []
    if messages:
        lines.append("")
        lines.append("progress:")
        for message in messages:
            lines.append(f"- {message}")

    failed_task_id = result.get("failed_task_id")
    if failed_task_id:
        lines.append("")
        lines.append(f"failed_task_id={failed_task_id}")
        failure_dir = run_dir / "execution" / failed_task_id
        latest_failure = failure_dir / "latest_failure.md"
        result_json = failure_dir / "result.json"
        attempts_jsonl = failure_dir / "attempts.jsonl"
        if latest_failure.exists():
            summary = latest_failure.read_text(encoding="utf-8").strip()
            lines.append(f"failure_summary={summary}")
            lines.append(f"latest_failure={latest_failure}")
        if result_json.exists():
            lines.append(f"result_json={result_json}")
        if attempts_jsonl.exists():
            lines.append(f"attempts_jsonl={attempts_jsonl}")

    return "\n".join(lines)


def invoke_graph(graph, state: AgentState) -> dict:
    return graph.invoke(
        state.model_dump(),
        config={"configurable": {"thread_id": state.run_dir.name}},
    )


def _first_existing(paths: list[Path]) -> Path | None:
    for path in paths:
        if path.exists():
            return path
    return None


def _run_state_loop(state_dict: dict) -> dict:
    current = state_dict
    node_map = build_node_map()
    for _ in range(MAX_GRAPH_STEPS):
        current_state = current.get("current_state")
        if current_state == "done":
            break
        node = node_map.get(current_state)
        if node is None:
            raise RuntimeError(f"no node registered for state: {current_state}")
        current = node(current)
        if current.get("failed_task_id"):
            break
    return current


def restore_state_from_run(
    config,
    run_dir: Path,
    goal: str,
    from_state: str,
    verification_env_file: Path | None,
    verification_env: dict[str, object],
) -> AgentState:
    if not run_dir.exists() or not run_dir.is_dir():
        raise SystemExit(f"resume run directory does not exist: {run_dir}")

    context_file = run_dir / "context" / "context.md"
    thinkingmap_file = _first_existing([run_dir / "thinkingmap" / "thinkingmap.json", run_dir / "thinkingmap" / "thinkingmap.md"])
    design_file = run_dir / "design" / "system_high_level_design.md"
    algorithm_simulation_file = run_dir / "algorithm_simulation" / "algorithm_simulation.md"
    subtask_feature_design_dir = run_dir / "subtask_feature_design"
    subtask_design_all_file = run_dir / "subtask_feature_design" / "all_subtasks.json"
    subtask_manifest_file = run_dir / "subtask_feature_design" / "subtask_manifest.json"
    subtask_feature_design_files = sorted(subtask_feature_design_dir.glob("*D.json")) if subtask_feature_design_dir.is_dir() else []
    if not subtask_feature_design_files and subtask_feature_design_dir.is_dir():
        subtask_feature_design_files = sorted(
            path for path in subtask_feature_design_dir.glob("*.json")
            if path.name not in {"all_subtasks.json", "subtask_manifest.json"}
        )
    subtask_feature_test_all_file = run_dir / "subtask_feature_test" / "all_tests.json"
    subtask_feature_test_dir = run_dir / "subtask_feature_test"
    subtask_feature_test_files = sorted(subtask_feature_test_dir.glob("*T.json")) if subtask_feature_test_dir.is_dir() else []
    subtask_feature_test_file = run_dir / "subtask_feature_test" / "subtask_feature_test.json"
    if not subtask_feature_test_file.exists() and subtask_feature_test_all_file.exists():
        subtask_feature_test_file = subtask_feature_test_all_file
    slice_all_file = run_dir / "slices" / "all_slices.json"
    slice_file = run_dir / "slices" / "slices.json"
    minimum_compilable_baseline_file = run_dir / "minimum_compilable_baseline" / "minimum_compilable_baseline.json"
    material_summary_file = run_dir / "material_summary" / "material_summary.json"
    material_summary_all_file = run_dir / "material_summary" / "all_tasks.json"
    material_summary_dir = run_dir / "material_summary"
    material_summary_files = sorted(material_summary_dir.glob("*/material_summary.*")) if material_summary_dir.is_dir() else []
    if not material_summary_file.exists() and material_summary_all_file.exists():
        material_summary_file = material_summary_all_file

    manifest_entries: list[dict[str, object]] = []
    if subtask_manifest_file.exists():
        try:
            data = json.loads(subtask_manifest_file.read_text(encoding="utf-8"))
            if isinstance(data, list):
                manifest_entries = [item for item in data if isinstance(item, dict)]
        except json.JSONDecodeError:
            manifest_entries = []
    if manifest_entries:
        subtask_feature_test_files = [
            run_dir / str(item["test_file"])
            for item in manifest_entries
            if item.get("test_file")
        ]
        manifest_slice_files: dict[str, Path] = {}
        manifest_task_prompt_files: dict[str, Path] = {}
        for item in manifest_entries:
            key = str(item.get("task_id") or item.get("index"))
            if item.get("design_slice_file"):
                manifest_slice_files[f"{key}:design"] = run_dir / str(item["design_slice_file"])
            if item.get("test_slice_file"):
                manifest_slice_files[f"{key}:test"] = run_dir / str(item["test_slice_file"])
            if item.get("design_prompt_file"):
                manifest_task_prompt_files[f"{key}:design"] = run_dir / str(item["design_prompt_file"])
            if item.get("test_prompt_file"):
                manifest_task_prompt_files[f"{key}:test"] = run_dir / str(item["test_prompt_file"])
    else:
        manifest_slice_files = {}
        manifest_task_prompt_files = {}

    current_task_file = run_dir / "execution" / "current_task.json"
    current_task_data: dict[str, object] = {}
    if current_task_file.exists():
        try:
            loaded = json.loads(current_task_file.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                current_task_data = loaded
        except json.JSONDecodeError:
            current_task_data = {}

    states_needing_context = {
        "thinkingmap", "design", "algorithm_simulation", "subtask_feature_design",
        "subtask_feature_test", "slice", "minimum_compilable_baseline", "material_summary",
        "execute_tasks", "task_design", "task_test",
    }
    if from_state in states_needing_context and not context_file.exists():
        raise SystemExit(f"cannot resume from {from_state}: missing {context_file}")

    states_needing_design = {
        "algorithm_simulation", "subtask_feature_design", "subtask_feature_test", "slice",
        "minimum_compilable_baseline", "material_summary", "execute_tasks",
    }
    if from_state in states_needing_design and not design_file.exists():
        raise SystemExit(f"cannot resume from {from_state}: missing {design_file}")

    execution_states = {"execute_tasks", "task_design", "task_test"}
    if from_state in execution_states and not material_summary_all_file.exists():
        raise SystemExit(f"cannot resume from {from_state}: missing {material_summary_all_file}")
    if from_state in {"task_design", "task_test"}:
        if not current_task_file.exists() or not current_task_data.get("task_id") or not current_task_data.get("index"):
            raise SystemExit(f"cannot resume from {from_state}: missing valid {current_task_file}")
        task_key = str(current_task_data["task_id"])
        prompt_role = "design" if from_state == "task_design" else "test"
        prompt_path = manifest_task_prompt_files.get(f"{task_key}:{prompt_role}")
        if not prompt_path or not prompt_path.exists():
            raise SystemExit(f"cannot resume from {from_state}: missing {prompt_role} prompt for {task_key}")

    context_md = context_file.read_text(encoding="utf-8") if context_file.exists() else ""
    design_md = design_file.read_text(encoding="utf-8") if design_file.exists() else ""

    return AgentState(
        project_root=config.project_root,
        run_dir=run_dir,
        goal=goal,
        llm=config.llm.model_dump(),
        verification_env=verification_env,
        verification_env_file=verification_env_file,
        current_state=from_state,
        context_md=context_md,
        context_file=context_file if context_file.exists() else None,
        context_files=[context_file] if context_file.exists() else [],
        thinkingmap_file=thinkingmap_file,
        thinkingmap_files=[thinkingmap_file] if thinkingmap_file else [],
        design_file=design_file if design_file.exists() else None,
        design_md=design_md,
        algorithm_simulation_file=algorithm_simulation_file if algorithm_simulation_file.exists() else None,
        subtask_design_all_file=subtask_design_all_file if subtask_design_all_file.exists() else None,
        subtask_manifest_file=subtask_manifest_file if subtask_manifest_file.exists() else None,
        subtask_feature_design_files=subtask_feature_design_files,
        subtask_feature_test_all_file=subtask_feature_test_all_file if subtask_feature_test_all_file.exists() else None,
        subtask_feature_test_file=subtask_feature_test_file if subtask_feature_test_file.exists() else None,
        subtask_feature_test_files=subtask_feature_test_files,
        slice_all_file=slice_all_file if slice_all_file.exists() else None,
        slice_files=manifest_slice_files or ({"slices": slice_file} if slice_file.exists() else {}),
        minimum_compilable_baseline_file=minimum_compilable_baseline_file if minimum_compilable_baseline_file.exists() else None,
        material_summary_all_file=material_summary_all_file if material_summary_all_file.exists() else None,
        material_summary_file=material_summary_file if material_summary_file.exists() else None,
        material_summary_files=material_summary_files,
        task_prompt_files=manifest_task_prompt_files,
        current_task_index=current_task_data.get("index") if isinstance(current_task_data.get("index"), int) else None,
        current_task_id=str(current_task_data["task_id"]) if current_task_data.get("task_id") else None,
        current_task_folder=Path(str(current_task_data["task_folder"])) if current_task_data.get("task_folder") else None,
        current_child_state=str(current_task_data["child_state"]) if current_task_data.get("child_state") else None,
        current_attempt=int(current_task_data.get("attempt", 0)),
        max_task_attempts=getattr(config, "max_task_attempts", 3),
        completed_task_ids={str(item) for item in current_task_data.get("completed_task_ids", [])}
        if isinstance(current_task_data.get("completed_task_ids", []), list)
        else set(),
        latest_test_failure_file=Path(str(current_task_data["latest_test_failure_file"]))
        if current_task_data.get("latest_test_failure_file")
        else None,
        compact_messages=[f"resumed from {from_state}; run_dir: {run_dir}"],
    )


def run_from_state(state: AgentState, from_state: str) -> dict:
    if from_state == "build_context":
        graph = build_graph()
        return invoke_graph(graph, state)

    state.current_state = from_state
    return _run_state_loop(state.model_dump())


def read_multiline_input(prompt: str) -> str:
    print(prompt)
    print("Finish input with a line containing only EOF.")
    lines: list[str] = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line == "EOF":
            break
        lines.append(line)
    return "\n".join(lines).strip()


def continue_after_build_context_human(state: AgentState, context_md: str) -> dict:
    if not context_md:
        raise SystemExit("empty context_md; cannot continue")
    context_dir = state.run_dir / "context"
    context_path = context_dir / "context.md"
    context_dir.mkdir(parents=True, exist_ok=True)
    context_path.write_text(context_md, encoding="utf-8")
    append_artifact(state.run_dir, context_path, "Build Context: 项目的业务需求、硬件约束、引脚与外设信息")
    state.context_md = context_md
    state.context_file = context_path
    state.context_files = [context_path]
    state.current_state = "thinkingmap"
    state.add_compact_message(f"build_context completed by human; context file: {context_path}")

    return _run_state_loop(state.model_dump())


def handle_human_intervention(exc: HumanInterventionRequired, state: AgentState) -> dict:
    payload = exc.payload
    print("human_intervention_required")
    print(f"state={payload.get('state')}")
    print(f"issue={payload.get('issue')}")
    print(f"request={payload.get('request')}")
    print(f"run_dir={payload.get('run_dir')}")
    context_dir = state.run_dir / "context"
    failure_path = context_dir / "latest_failure.md"
    if failure_path.exists():
        print(f"latest_failure={failure_path}")

    if payload.get("state") == "build_context":
        context_md = read_multiline_input("Paste the complete context.md content now.")
        return continue_after_build_context_human(state, context_md)
    replacement_text = read_multiline_input(
        "Paste a replacement AgentState JSON object, or enter RETRY to rerun this state after fixing files."
    )
    payload_state = payload.get("payload", {}).get("state") if isinstance(payload.get("payload"), dict) else None
    base_state = payload_state if isinstance(payload_state, dict) else state.model_dump(mode="json")
    if replacement_text.upper() == "RETRY":
        replacement = dict(base_state)
    else:
        try:
            parsed = json.loads(replacement_text)
        except json.JSONDecodeError as exc_json:
            raise SystemExit(f"invalid replacement AgentState JSON: {exc_json}") from exc_json
        candidate = parsed.get("state", parsed) if isinstance(parsed, dict) else None
        if not isinstance(candidate, dict):
            raise SystemExit("replacement input must be an AgentState JSON object")
        replacement = {**base_state, **candidate}
    replacement["current_state"] = str(payload.get("state") or replacement.get("current_state"))
    replacement_state = AgentState.model_validate(replacement)
    replacement_state.add_compact_message(f"human intervention resumed state {replacement_state.current_state}")
    return _run_state_loop(replacement_state.model_dump())


def main() -> None:
    args = parse_args()

    config_path = Path(args.config)
    config = load_config(config_path)
    verification_env_file, verification_env = load_verification_env(config, config_path)
    goal = args.goal or config.goal
    if not goal:
        raise SystemExit('missing --goal. Example: embedded-agent --config configs/agent_config.myagent.yaml --goal "implement UART echo"')
    if args.resume_run:
        run_dir = args.resume_run
        state = restore_state_from_run(config, run_dir, goal, args.from_state, verification_env_file, verification_env)
    else:
        if args.from_state != "build_context":
            raise SystemExit("--from-state requires --resume-run unless starting from build_context")
        run_dir = new_run_dir(config.run_root)
        state = AgentState(
            project_root=config.project_root,
            run_dir=run_dir,
            goal=goal,
            llm=config.llm.model_dump(),
            verification_env=verification_env,
            verification_env_file=verification_env_file,
            max_task_attempts=config.max_task_attempts,
        )
    print(f"starting embedded-agent")
    print(f"project_root={config.project_root}")
    print(f"run_dir={run_dir}")
    print(f"goal={goal}")
    if args.resume_run:
        print(f"resume_from={args.from_state}")
    pending_intervention: HumanInterventionRequired | None = None
    while True:
        try:
            if pending_intervention is None:
                result = run_from_state(state, args.from_state)
            else:
                result = handle_human_intervention(pending_intervention, state)
            break
        except HumanInterventionRequired as exc:
            pending_intervention = exc
    print(render_run_report(result))
    if result.get("failed_task_id"):
        raise SystemExit(f"failed_task_id={result['failed_task_id']}")
