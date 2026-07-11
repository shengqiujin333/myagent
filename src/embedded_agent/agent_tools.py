from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from embedded_agent.codebase_tools import CODEBASE_MEMORY_TOOL_SCHEMAS
from embedded_agent.codebase_tools import is_codebase_memory_tool
from embedded_agent.codebase_tools import run_codebase_memory_tool


MAX_TOOL_STEPS = 80
TOOL_TIMEOUT_SEC = 20
TOOL_OUTPUT_CHARS = 12000


BASH_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "bash",
        "description": "Run a non-interactive PowerShell command in the target project directory. Use fd or rg without glob/recurse flags; grep, find, glob patterns, and interactive programs are forbidden.",
        "parameters": {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
        },
    },
}


READ_FILE_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "read_file",
        "description": "Read a UTF-8 text file from the target project or current run directory.",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
}


WRITE_FILE_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "write_file",
        "description": "Write UTF-8 text to a file in the target project or current run directory, creating parent directories.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
    },
}


AGENT_TOOL_SCHEMAS = [
    BASH_TOOL_SCHEMA,
    READ_FILE_TOOL_SCHEMA,
    WRITE_FILE_TOOL_SCHEMA,
    *CODEBASE_MEMORY_TOOL_SCHEMAS,
]


def _extract_tool_calls(response: object) -> list[dict[str, object]]:
    calls = getattr(response, "tool_calls", None)
    if calls:
        return list(calls)
    additional = getattr(response, "additional_kwargs", {}) or {}
    parsed: list[dict[str, object]] = []
    for raw in additional.get("tool_calls") or []:
        function = raw.get("function", {})
        arguments = function.get("arguments") or "{}"
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                arguments = {}
        parsed.append({"id": raw.get("id"), "name": function.get("name"), "args": arguments})
    return parsed


def _tool_name(call: dict[str, object]) -> str:
    return str(call.get("name") or "")


def _tool_args(call: dict[str, object]) -> dict[str, object]:
    args = call.get("args") or {}
    return args if isinstance(args, dict) else {}


def _tool_id(call: dict[str, object], index: int) -> str:
    return str(call.get("id") or f"call_{index}")


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


def _run_bash(command: str, project_root: Path) -> str:
    _ensure_safe_bash_command(command)
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=TOOL_TIMEOUT_SEC,
        cwd=project_root,
    )
    return (
        f"exit_code={completed.returncode}\nstdout:\n{completed.stdout[-TOOL_OUTPUT_CHARS:]}"
        f"\nstderr:\n{completed.stderr[-TOOL_OUTPUT_CHARS:]}"
    )


def _allowed_path(path: str, project_root: Path, run_dir: Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = project_root / candidate
    resolved = candidate.resolve()
    roots = [project_root.resolve(), run_dir.resolve()]
    if not any(resolved == root or root in resolved.parents for root in roots):
        raise ValueError(f"path is outside project/run directories: {path}")
    return resolved


def _run_file_tool(name: str, args: dict[str, object], project_root: Path, run_dir: Path) -> str:
    path = _allowed_path(str(args.get("path") or ""), project_root, run_dir)
    if name == "read_file":
        return path.read_text(encoding="utf-8")[-TOOL_OUTPUT_CHARS:]
    content = args.get("content")
    if not isinstance(content, str):
        raise ValueError("write_file requires string content")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return f"wrote {path} ({len(content)} characters)"


def _run_tool(name: str, args: dict[str, object], project_root: Path, run_dir: Path) -> str:
    if name == "bash":
        return _run_bash(str(args.get("command") or ""), project_root)
    if name in {"read_file", "write_file"}:
        return _run_file_tool(name, args, project_root, run_dir)
    if is_codebase_memory_tool(name):
        return run_codebase_memory_tool(name, args)
    return f"Unknown tool: {name}"


def invoke_with_agent_tools(
    llm: object,
    prompt: str,
    *,
    project_root: Path,
    run_dir: Path,
    state_name: str,
    allow_empty_response: bool = False,
) -> str:
    if not hasattr(llm, "bind_tools"):
        output = getattr(llm.invoke(prompt), "content", None)
        text = str(output if output is not None else "").strip()
        if not text and not allow_empty_response:
            raise RuntimeError(f"{state_name} LLM returned an empty response")
        return text

    tool_llm = llm.bind_tools(AGENT_TOOL_SCHEMAS)
    messages: list[object] = [{"role": "user", "content": prompt}]
    log_path = run_dir / state_name / "tool_calls.jsonl"
    for _ in range(MAX_TOOL_STEPS):
        response = tool_llm.invoke(messages)
        calls = _extract_tool_calls(response)
        if not calls:
            output = getattr(response, "content", response)
            text = str(output).strip()
            if not text and not allow_empty_response:
                raise RuntimeError(f"{state_name} LLM returned an empty response")
            return text
        messages.append(response)
        for index, call in enumerate(calls):
            name = _tool_name(call)
            args = _tool_args(call)
            try:
                content = _run_tool(name, args, project_root, run_dir)
            except Exception as exc:
                content = f"Tool error: {exc}"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(
                        {"tool": name, "args": args, "result_tail": content[-TOOL_OUTPUT_CHARS:]},
                        ensure_ascii=False,
                    )
                    + "\n"
                )
            messages.append({"role": "tool", "tool_call_id": _tool_id(call, index), "content": content})
    raise RuntimeError(f"{state_name} LLM exceeded shared tool step limit ({MAX_TOOL_STEPS} model turns)")
