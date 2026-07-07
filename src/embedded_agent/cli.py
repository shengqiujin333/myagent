from __future__ import annotations

import argparse
from pathlib import Path

from embedded_agent.artifacts import new_run_dir
from embedded_agent.config import load_config
from embedded_agent.graph import build_graph
from embedded_agent.human import HumanInterventionRequired
from embedded_agent.nodes import execute_tasks_node, plan_node, slice_node, thinkingmap_node
from embedded_agent.state import AgentState


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run embedded LangGraph coding agent")
    parser.add_argument("--config", required=True, help="Path to agent_config.yaml")
    parser.add_argument("--goal", help="Concrete task goal for this run. Overrides config goal.")
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
    state.context_md = context_md
    state.context_file = context_path
    state.context_files = [context_path]
    state.current_state = "thinkingmap"
    state.add_compact_message(f"build_context completed by human; context file: {context_path}")

    current = state.model_dump()
    for node in (thinkingmap_node, plan_node, slice_node, execute_tasks_node):
        current = node(current)
        if current.get("failed_task_id"):
            break
    return current


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
    raise SystemExit(2)


def main() -> None:
    args = parse_args()

    config = load_config(Path(args.config))
    goal = args.goal or config.goal
    if not goal:
        raise SystemExit('missing --goal. Example: embedded-agent --config configs/agent_config.myagent.yaml --goal "implement UART echo"')
    run_dir = new_run_dir(config.run_root)
    state = AgentState(
        project_root=config.project_root,
        run_dir=run_dir,
        goal=goal,
        llm=config.llm.model_dump(),
        hardware=config.hardware.model_dump(),
    )
    graph = build_graph()
    print(f"starting embedded-agent")
    print(f"project_root={config.project_root}")
    print(f"run_dir={run_dir}")
    print(f"goal={goal}")
    try:
        result = invoke_graph(graph, state)
    except HumanInterventionRequired as exc:
        result = handle_human_intervention(exc, state)
    print(render_run_report(result))
    if result.get("failed_task_id"):
        raise SystemExit(f"failed_task_id={result['failed_task_id']}")
