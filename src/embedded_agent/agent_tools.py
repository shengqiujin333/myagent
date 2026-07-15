from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

from embedded_agent.artifacts import read_text_compatible
from embedded_agent.codebase_tools import CODEBASE_MEMORY_TOOL_SCHEMAS
from embedded_agent.codebase_tools import is_codebase_memory_tool
from embedded_agent.codebase_tools import run_codebase_memory_tool
from embedded_agent.verification_tools import VERIFICATION_TOOL_SCHEMAS
from embedded_agent.verification_tools import cleanup_verification_processes
from embedded_agent.verification_tools import is_verification_tool
from embedded_agent.verification_tools import run_verification_tool


MAX_TOOL_STEPS = 300
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
    *VERIFICATION_TOOL_SCHEMAS,
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
    return run_powershell_command(
        command,
        cwd=project_root,
        timeout_sec=TOOL_TIMEOUT_SEC,
        output_chars=TOOL_OUTPUT_CHARS,
    )


def _terminate_process_tree(process: subprocess.Popen[str]) -> None:
    if os.name == "nt":
        try:
            _terminate_pid_tree(process.pid)
        except (OSError, subprocess.TimeoutExpired):
            process.kill()
        return
    process.kill()


def _terminate_pid_tree(pid: int) -> None:
    subprocess.run(
        ["taskkill", "/PID", str(pid), "/T", "/F"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=10,
        check=False,
    )


def _process_ids_by_image(image_name: str) -> set[int]:
    if os.name != "nt":
        return set()
    completed = subprocess.run(
        ["tasklist", "/FI", f"IMAGENAME eq {image_name}", "/FO", "CSV", "/NH"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        timeout=5,
        check=False,
    )
    output = completed.stdout.decode(errors="ignore")
    return {int(pid) for pid in re.findall(rf'"{re.escape(image_name)}","(\d+)"', output, re.IGNORECASE)}


def run_powershell_command(
    command: str,
    *,
    cwd: Path,
    timeout_sec: float,
    output_chars: int,
) -> str:
    watches_uv4 = "uv4.exe" in command.lower()
    uv4_before = _process_ids_by_image("UV4.exe") if watches_uv4 else set()
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "utf-8"
    environment["PYTHONUTF8"] = "1"
    powershell_command = (
        "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
        "$OutputEncoding = [Console]::OutputEncoding; "
        f"{command}"
    )
    process = subprocess.Popen(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", powershell_command],
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=cwd,
        env=environment,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout_sec)
        returncode = process.returncode
    except subprocess.TimeoutExpired:
        _terminate_process_tree(process)
        try:
            stdout, stderr = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            for stream in (process.stdout, process.stderr):
                if stream is not None:
                    stream.close()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
            stdout, stderr = "", ""
        returncode = 124
        stderr = f"{stderr}\ncommand timed out after {timeout_sec:g} seconds; process tree terminated"
    if watches_uv4:
        lingering_uv4 = sorted(_process_ids_by_image("UV4.exe") - uv4_before)
        for pid in lingering_uv4:
            _terminate_pid_tree(pid)
        if lingering_uv4:
            returncode = 124
            stderr = (
                f"{stderr}\nUV4 command left a running UV4.exe process; "
                f"terminated new process IDs {lingering_uv4}"
            )
    return (
        f"exit_code={returncode}\nstdout:\n{stdout[-output_chars:]}"
        f"\nstderr:\n{stderr[-output_chars:]}"
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
        return read_text_compatible(path)[-TOOL_OUTPUT_CHARS:]
    content = args.get("content")
    if not isinstance(content, str):
        raise ValueError("write_file requires string content")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return f"wrote {path} ({len(content)} characters)"


def _run_tool(
    name: str,
    args: dict[str, object],
    project_root: Path,
    run_dir: Path,
    verification_env: dict[str, object] | None = None,
) -> str:
    if name == "bash":
        return _run_bash(str(args.get("command") or ""), project_root)
    if name in {"read_file", "write_file"}:
        return _run_file_tool(name, args, project_root, run_dir)
    if is_verification_tool(name):
        return run_verification_tool(
            name,
            args,
            verification_env=verification_env or {},
            project_root=project_root,
            run_dir=run_dir,
            command_runner=run_powershell_command,
        )
    if is_codebase_memory_tool(name):
        return run_codebase_memory_tool(name, args)
    return f"Unknown tool: {name}"


def _tool_result_failed(name: str, content: str) -> bool:
    if content.startswith("Tool error:") or content.startswith("Unknown tool:"):
        return True
    if name == "bash" or is_verification_tool(name):
        match = re.search(r"^exit_code=(-?\d+)", content)
        return match is None or int(match.group(1)) != 0
    return False


def invoke_with_agent_tools(
    llm: object,
    prompt: str,
    *,
    project_root: Path,
    run_dir: Path,
    state_name: str,
    allow_empty_response: bool = False,
    verification_env: dict[str, object] | None = None,
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
    failed_call_counts: dict[str, int] = {}
    for _ in range(MAX_TOOL_STEPS):
        try:
            response = tool_llm.invoke(messages)
        except BaseException:
            cleanup_verification_processes(
                project_root=project_root,
                run_dir=run_dir,
                command_runner=run_powershell_command,
            )
            raise
        calls = _extract_tool_calls(response)
        if not calls:
            cleanup_verification_processes(
                project_root=project_root,
                run_dir=run_dir,
                command_runner=run_powershell_command,
            )
            output = getattr(response, "content", response)
            text = str(output).strip()
            if not text and not allow_empty_response:
                raise RuntimeError(f"{state_name} LLM returned an empty response")
            return text
        messages.append(response)
        for index, call in enumerate(calls):
            name = _tool_name(call)
            args = _tool_args(call)
            call_key = json.dumps({"name": name, "args": args}, ensure_ascii=False, sort_keys=True)
            if failed_call_counts.get(call_key, 0) >= 2:
                content = "Tool error: identical failing tool call blocked after 2 attempts; change the command or approach"
            else:
                try:
                    content = _run_tool(name, args, project_root, run_dir, verification_env)
                except Exception as exc:
                    content = f"Tool error: {exc}"
            if _tool_result_failed(name, content):
                failed_call_counts[call_key] = failed_call_counts.get(call_key, 0) + 1
                content = (
                    f"TOOL_STATUS: ERROR\n{content}\n"
                    "Do not report success from this result. Diagnose the failure and use a corrected command or approach."
                )
            else:
                failed_call_counts.pop(call_key, None)
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
    cleanup_verification_processes(
        project_root=project_root,
        run_dir=run_dir,
        command_runner=run_powershell_command,
    )
    raise RuntimeError(f"{state_name} LLM exceeded shared tool step limit ({MAX_TOOL_STEPS} model turns)")
