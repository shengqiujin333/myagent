from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from embedded_agent.artifacts import write_json, write_text
from embedded_agent.codebase_tools import CODEBASE_MEMORY_TOOL_SCHEMAS, is_codebase_memory_tool, run_codebase_memory_tool
from embedded_agent.config import LLMConfig
from embedded_agent.hardware import HardwareAdapter, HardwareConfig
from embedded_agent.human import request_human_intervention
from embedded_agent.llm import create_llm
from embedded_agent.state import AcceptanceCheck, AgentState, PlanDocument, PlanTask


PROMPT_DIR = Path(__file__).with_name("prompts")
MAX_BUILD_CONTEXT_TOOL_STEPS = 80
BASH_TOOL_TIMEOUT_SEC = 20
BASH_TOOL_OUTPUT_CHARS = 12000
BASH_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "bash",
        "description": "Run a bounded non-interactive shell command inside task_directory.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Command to run. Must not use glob, recurse flags, grep, find, or interactive programs.",
                }
            },
            "required": ["command"],
        },
    },
}


def _load_prompt_template(name: str) -> str:
    return (PROMPT_DIR / name).read_text(encoding="utf-8")


def _append_jsonl(path: Path, record: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _build_context_prompt(agent: AgentState, target_dir: Path) -> str:
    return _load_prompt_template("build_context.md").format(
        goal=agent.goal,
        task_directory=target_dir,
        hardware_config=agent.hardware,
    )


def _response_text(response: object) -> str:
    content = getattr(response, "content", response)
    return str(content).strip()


def _extract_tool_calls(response: object) -> list[dict[str, object]]:
    calls = getattr(response, "tool_calls", None)
    if calls:
        return list(calls)
    additional = getattr(response, "additional_kwargs", {}) or {}
    raw_calls = additional.get("tool_calls") or []
    parsed_calls = []
    for raw_call in raw_calls:
        function = raw_call.get("function", {})
        arguments = function.get("arguments") or "{}"
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                arguments = {}
        parsed_calls.append(
            {
                "id": raw_call.get("id"),
                "name": function.get("name"),
                "args": arguments,
            }
        )
    return parsed_calls


def _ensure_safe_bash_command(command: str) -> None:
    lowered = command.lower()
    blocked_patterns = (
        r"\bgrep\b",
        r"^\s*find\b",
        r"\bget-childitem\b.*-recurse\b",
        r"\bgci\b.*-recurse\b",
        r"\bdir\b.*(?:^|\s)/s(?:\s|$|\"|')",
        r"\b(fd|rg)\b.*\b--hidden\b",
        r"\b(fd|rg)\b.*\b--no-ignore\b",
        r"\b(fd|rg)\b.*\s-[^\s]*[hH][^\s]*",
        r"\b(vim|nvim|nano|emacs|less|more)\b",
    )
    if any(re.search(pattern, lowered) for pattern in blocked_patterns):
        raise ValueError(f"blocked bash command: {command}")
    if any(char in command for char in ("*", "?")):
        raise ValueError(f"blocked glob pattern in bash command: {command}")


def _normalize_model_bash_command(command: str) -> str:
    return re.sub(r'^\s*cd\s+"[^"]+"\s*&&\s*', "", command, count=1, flags=re.IGNORECASE).strip()


def _run_model_bash(command: str, cwd: Path) -> str:
    command = _normalize_model_bash_command(command)
    _ensure_safe_bash_command(command)
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=BASH_TOOL_TIMEOUT_SEC,
        cwd=cwd,
    )
    return (
        f"exit_code={completed.returncode}\n"
        "stdout:\n"
        f"{completed.stdout[-BASH_TOOL_OUTPUT_CHARS:]}\n"
        "stderr:\n"
        f"{completed.stderr[-BASH_TOOL_OUTPUT_CHARS:]}"
    )


def _tool_call_id(call: dict[str, object], index: int) -> str:
    value = call.get("id")
    return str(value) if value else f"call_{index}"


def _tool_call_name(call: dict[str, object]) -> str:
    return str(call.get("name") or "")


def _tool_call_args(call: dict[str, object]) -> dict[str, object]:
    args = call.get("args") or {}
    return args if isinstance(args, dict) else {}


def _generate_context_with_llm(agent: AgentState, target_dir: Path, prompt: str, context_dir: Path) -> str:
    llm = create_llm(LLMConfig.model_validate(agent.llm))
    if not hasattr(llm, "bind_tools"):
        text = _response_text(llm.invoke(prompt))
        if not text:
            raise RuntimeError("build_context LLM returned an empty context")
        return text

    tool_llm = llm.bind_tools([BASH_TOOL_SCHEMA, *CODEBASE_MEMORY_TOOL_SCHEMAS])
    messages: list[object] = [{"role": "user", "content": prompt}]
    for _ in range(MAX_BUILD_CONTEXT_TOOL_STEPS):
        response = tool_llm.invoke(messages)
        tool_calls = _extract_tool_calls(response)
        if not tool_calls:
            text = _response_text(response)
            if not text:
                raise RuntimeError("build_context LLM returned an empty context")
            return text
        messages.append(response)
        for index, call in enumerate(tool_calls):
            name = _tool_call_name(call)
            args = _tool_call_args(call)
            if name == "bash":
                command = str(args.get("command") or "")
                try:
                    content = _run_model_bash(command, target_dir)
                except Exception as exc:
                    content = f"Tool error: {exc}"
                _append_jsonl(
                    context_dir / "tool_calls.jsonl",
                    {
                        "tool": "bash",
                        "command": command,
                        "result_tail": content[-BASH_TOOL_OUTPUT_CHARS:],
                    },
                )
            elif is_codebase_memory_tool(name):
                try:
                    content = run_codebase_memory_tool(name, args)
                except Exception as exc:
                    content = f"Tool error: {exc}"
                _append_jsonl(
                    context_dir / "tool_calls.jsonl",
                    {
                        "tool": name,
                        "args": args,
                        "result_tail": content[-BASH_TOOL_OUTPUT_CHARS:],
                    },
                )
            else:
                content = f"Unknown tool: {name}"
            messages.append({"role": "tool", "tool_call_id": _tool_call_id(call, index), "content": content})
    raise RuntimeError(f"build_context LLM exceeded bash tool step limit ({MAX_BUILD_CONTEXT_TOOL_STEPS} model turns)")


def _coerce_human_context(response: object) -> str:
    if isinstance(response, dict):
        for key in ("context_md", "context", "markdown", "content"):
            value = response.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    if isinstance(response, str) and response.strip():
        return response.strip()
    raise RuntimeError("human intervention did not provide context_md")


def build_context_node(state: dict) -> dict:
    agent = AgentState.model_validate(state)
    context_dir = agent.run_dir / "context"
    target_dir = agent.project_root
    agent.project_root = target_dir
    agent.hardware["project_root"] = str(target_dir)
    prompt = _build_context_prompt(agent, target_dir)
    try:
        summary = _generate_context_with_llm(agent, target_dir, prompt, context_dir)
    except Exception as exc:
        write_text(context_dir / "latest_failure.md", f"build_context failed before context.md was produced:\n{exc}\n")
        human_response = request_human_intervention(
            agent,
            "build_context",
            f"LLM context generation failed: {exc}",
            "Provide a complete context.md as `context_md`, or fix the model/API issue and resume this state.",
            {
                "target_dir": str(target_dir),
            },
        )
        summary = _coerce_human_context(human_response)
    path = write_text(context_dir / "context.md", summary)
    agent.context_md = summary
    agent.context_file = path
    agent.context_files = [path]
    agent.current_state = "thinkingmap"
    agent.add_compact_message(f"build_context complete; context file: {path}")
    return agent.model_dump()


def thinkingmap_node(state: dict) -> dict:
    agent = AgentState.model_validate(state)
    keywords = {
        "modules": ["main", "drivers", "hal", "bsp", "interrupts"],
        "hardware": ["cmsis-dap", "serial", "firmware", "flash", "reset"],
        "tests": ["build", "download", "serial-observe", "host-script"],
        "risks": ["pinmux", "clock", "linker", "startup", "timing"],
        "planning": ["directly-completable", "dependency-aware", "no-subtasks"],
    }
    base = agent.run_dir / "thinkingmap"
    md = "# Thinking Map\n\n" + "\n".join(
        f"## {name}\n\n" + "\n".join(f"- {item}" for item in items)
        for name, items in keywords.items()
    )
    md_path = write_text(base / "keywords.md", md + "\n")
    json_path = write_json(base / "keywords.json", keywords)
    agent.thinkingmap_files = [md_path, json_path]
    agent.current_state = "plan"
    agent.add_compact_message(f"thinkingmap complete; keyword files: {md_path}, {json_path}")
    return agent.model_dump()


def plan_node(state: dict) -> dict:
    agent = AgentState.model_validate(state)
    task = PlanTask(
        id="goal-implementation",
        title="Complete requested embedded firmware goal",
        kind="code",
        objective=agent.goal,
        dependencies=[],
        target_files=["main"],
        acceptance=[
            AcceptanceCheck(kind="build", command=str(agent.hardware.get("build_command", "cmake --build build"))),
            AcceptanceCheck(kind="flash", command=str(agent.hardware.get("flash_command", "pyocd flash build/firmware.elf"))),
            AcceptanceCheck(kind="serial"),
        ],
    )
    plan = PlanDocument(tasks=[task])
    base = agent.run_dir / "plan"
    json_path = write_json(base / "plan.json", plan.model_dump())
    md = (
        "# Plan\n\n"
        "Every task is directly completable and must not be split again.\n\n"
        "## goal-implementation\n\n"
        f"- Objective: {agent.goal}\n"
        "- Files: project entrypoint and directly related modules\n"
        "- Acceptance: build, CMSIS-DAP flash, and serial or host test observation.\n"
    )
    write_text(base / "plan.md", md)
    agent.plan_file = json_path
    agent.current_state = "slice"
    agent.add_compact_message(f"plan complete; atomic plan file: {json_path}")
    return agent.model_dump()


def slice_node(state: dict) -> dict:
    agent = AgentState.model_validate(state)
    if not agent.plan_file:
        raise ValueError("plan_file missing")
    plan = PlanDocument.model_validate_json(Path(agent.plan_file).read_text(encoding="utf-8"))
    slice_files: dict[str, Path] = {}
    for task in plan.tasks:
        content = (
            f"# Slice: {task.id}\n\n"
            "## Role\n\nEmbedded firmware engineer focused on finishing one directly executable task.\n\n"
            "## Protocol\n\n"
            "- Do not create child tasks.\n"
            "- Keep model messages compact; read artifact files by path.\n"
            "- Integrate code into the configured main entrypoint.\n"
            "- Verify by build, CMSIS-DAP flash, and serial or host-test observation.\n\n"
            f"## Context Files\n\n{chr(10).join(f'- `{path}`' for path in agent.context_files)}\n"
        )
        path = write_text(agent.run_dir / "slices" / f"{task.id}.md", content)
        slice_files[task.id] = path
    agent.slice_files = slice_files
    agent.current_state = "execute_tasks"
    agent.add_compact_message(f"slice complete; generated {len(slice_files)} slice file(s)")
    return agent.model_dump()


def execute_tasks_node(state: dict) -> dict:
    agent = AgentState.model_validate(state)
    if not agent.plan_file:
        raise ValueError("plan_file missing")
    plan = PlanDocument.model_validate_json(Path(agent.plan_file).read_text(encoding="utf-8"))
    hardware = HardwareAdapter(HardwareConfig.model_validate(agent.hardware))
    for task_id in plan.ready_task_ids(agent.completed_task_ids):
        task = plan.get_task(task_id)
        result = hardware.verify_with_retries(task, agent.run_dir / "execution" / task.id)
        if not result.ok:
            agent.failed_task_id = task.id
            agent.add_compact_message(f"task {task.id} failed: {result.reason}")
            return agent.model_dump()
        agent.completed_task_ids.add(task.id)
    agent.current_state = "done"
    agent.add_compact_message("execution complete")
    return agent.model_dump()
