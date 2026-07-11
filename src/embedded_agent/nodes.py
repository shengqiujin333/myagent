from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import yaml

from embedded_agent.artifacts import append_artifact, read_artifacts_index, write_json, write_text
from embedded_agent.codebase_tools import CODEBASE_MEMORY_TOOL_SCHEMAS, is_codebase_memory_tool, run_codebase_memory_tool
from embedded_agent.config import LLMConfig
from embedded_agent.human import request_human_intervention
from embedded_agent.llm import create_llm
from embedded_agent.state import AgentState


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
    )


def _build_thinkingmap_prompt(context_md: str, verification_env: dict[str, object], verification_env_path: Path | None) -> str:
    template = _load_prompt_template("thinkingmap.md").strip()
    env_path_text = f"`{verification_env_path}`" if verification_env_path else "`<not configured>`"
    return (
        f"{template}\n\n"
        "---\n\n"
        "## Inputs\n\n"
        "Use both inputs as thinkingmap material. Build context describes the target project; verification environment describes available HIL, build, flash, serial, shell, and Python test capabilities.\n\n"
        "## G_CONTEXT_BUILD Output\n\n"
        "```markdown\n"
        f"{context_md}\n"
        "```\n\n"
        "## Verification Environment\n\n"
        f"- Verification environment path: {env_path_text}\n\n"
        "```yaml\n"
        f"{_format_verification_env(verification_env)}\n"
        "```\n"
    )


def _format_verification_env(verification_env: dict[str, object]) -> str:
    if not verification_env:
        return "{}"
    return yaml.safe_dump(verification_env, allow_unicode=True, sort_keys=False).strip()


def _build_placeholder_prompt(state_name: str) -> str:
    template = _load_prompt_template(f"{state_name}.md").strip()
    return (
        f"{template}\n\n"
        "---\n\n"
        "## 输入材料\n\n"
        "<TBD - 输入内容待设计>\n"
    )


def _invoke_placeholder_state(
    agent: AgentState,
    state_name: str,
    base_dirname: str,
    output_filename: str,
    description: str,
) -> tuple[Path, str]:
    prompt = _build_placeholder_prompt(state_name)
    llm = create_llm(LLMConfig.model_validate(agent.llm))
    base = agent.run_dir / base_dirname
    output = _response_text(llm.invoke(prompt))
    try:
        data = _parse_json_object(output)
    except Exception as exc:
        write_text(base / "latest_output.md", output)
        write_text(base / "latest_failure.md", f"{state_name} failed before {output_filename} was produced:\n{exc}\n")
        raise
    json_path = write_json(base / output_filename, data)
    append_artifact(agent.run_dir, json_path, description)
    return json_path, output


def _parse_subtask_blocks(output: str) -> list[dict[str, object]]:
    """Parse multiple subtask JSON objects from LLM output.

    Supports multiple ```json``` fenced blocks (each a subtask) or a single
    JSON array/object containing the subtask list.
    """
    blocks = re.findall(r"```json\s*(.*?)\s*```", output, re.DOTALL)
    subtasks: list[dict[str, object]] = []
    for block in blocks:
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            subtasks.append(data)
    if subtasks:
        return subtasks

    stripped = output.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```\w*\n?", "", stripped)
        stripped = re.sub(r"\n?```$", "", stripped).strip()
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        return []
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        items = data.get("subtasks")
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
        return [data]
    return []


def _build_subtask_feature_design_prompt(agent: AgentState) -> str:
    template = _load_prompt_template("subtask_feature_design.md").strip()
    context_md = agent.context_md or ""
    if not context_md and agent.context_file:
        context_md = Path(agent.context_file).read_text(encoding="utf-8")

    thinkingmap_text = ""
    if agent.thinkingmap_file:
        thinkingmap_text = Path(agent.thinkingmap_file).read_text(encoding="utf-8")

    design_md = agent.design_md or ""
    if not design_md and agent.design_file:
        design_md = Path(agent.design_file).read_text(encoding="utf-8")

    env_path_text = f"`{agent.verification_env_file}`" if agent.verification_env_file else "`<not configured>`"
    return (
        f"{template}\n\n"
        "---\n\n"
        "## 输入材料\n\n"
        "请基于以下四份输入材料执行子任务划分与详细设计：\n\n"
        "1. **项目信息 (Build Context)**：项目的业务需求、硬件约束与物理边界。\n"
        "2. **知识语料 (Thinking Map)**：系统沉淀的设计规范、代码片段与避坑指南。\n"
        "3. **总体设计 (Overall Design)**：上一阶段产出的系统级架构、模块划分与接口契约。\n"
        "4. **验证环境配置 (Verification Environment)**：可用的测试工具链。\n\n"
        "## Build Context\n\n"
        f"```markdown\n{context_md}\n```\n\n"
        "## Thinking Map\n\n"
        f"```json\n{thinkingmap_text}\n```\n\n"
        "## Overall Design\n\n"
        f"```markdown\n{design_md}\n```\n\n"
        "## Verification Environment\n\n"
        f"- Verification environment path: {env_path_text}\n\n"
        f"```yaml\n{_format_verification_env(agent.verification_env)}\n```\n"
    )


def _build_slice_prompt(agent: AgentState) -> str:
    template = _load_prompt_template("slice.md").strip()
    parts: list[str] = [
        f"{template}\n\n",
        "---\n\n",
        "## 输入材料\n\n",
        "以下是子任务功能设计与子任务功能测试的 JSON 输出文件，遍历其中的每一个子任务为其生成虚拟专家切片：\n\n",
        "## 子任务功能设计 (Subtask Feature Design)\n\n",
    ]
    if agent.subtask_feature_design_files:
        for path in agent.subtask_feature_design_files:
            parts.append(f"- 文件路径：`{path}`\n")
            content = Path(path).read_text(encoding="utf-8") if Path(path).exists() else "<file not found>"
            parts.append(f"\n```json\n{content}\n```\n\n")
    else:
        parts.append("无子任务功能设计文件。\n\n")

    parts.append("## 子任务功能测试 (Subtask Feature Test)\n\n")
    if agent.subtask_feature_test_file:
        test_path = Path(agent.subtask_feature_test_file)
        parts.append(f"- 文件路径：`{test_path}`\n")
        content = test_path.read_text(encoding="utf-8") if test_path.exists() else "<file not found>"
        parts.append(f"\n```json\n{content}\n```\n")
    else:
        parts.append("无子任务功能测试文件。\n")

    return "".join(parts)


def _response_text(response: object) -> str:
    content = getattr(response, "content", response)
    return str(content).strip()


def _parse_json_object(text: str) -> dict[str, object]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, count=1, flags=re.IGNORECASE)
        stripped = re.sub(r"\s*```$", "", stripped, count=1)
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        for index, char in enumerate(stripped):
            if char != "{":
                continue
            try:
                data, _end = decoder.raw_decode(stripped[index:])
                break
            except json.JSONDecodeError:
                continue
        else:
            raise
    if not isinstance(data, dict):
        raise ValueError("LLM output must be a JSON object")
    return data


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
    append_artifact(agent.run_dir, path, "Build Context: 项目的业务需求、硬件约束、引脚与外设信息")
    agent.context_md = summary
    agent.context_file = path
    agent.context_files = [path]
    agent.current_state = "thinkingmap"
    agent.add_compact_message(f"build_context complete; context file: {path}")
    return agent.model_dump()


def thinkingmap_node(state: dict) -> dict:
    agent = AgentState.model_validate(state)
    if not agent.context_file:
        raise ValueError("context_file missing")
    context_path = Path(agent.context_file)
    context_md = context_path.read_text(encoding="utf-8")
    prompt = _build_thinkingmap_prompt(context_md, agent.verification_env, agent.verification_env_file)
    llm = create_llm(LLMConfig.model_validate(agent.llm))
    output = _response_text(llm.invoke(prompt))
    try:
        thinkingmap = _parse_json_object(output)
        output_path = write_json(agent.run_dir / "thinkingmap" / "thinkingmap.json", thinkingmap)
    except (json.JSONDecodeError, ValueError):
        output_path = write_text(agent.run_dir / "thinkingmap" / "thinkingmap.md", output)
    append_artifact(agent.run_dir, output_path, "Thinking Map: 系统沉淀的专业知识、代码片段、设计模式与避坑指南")
    agent.thinkingmap_file = output_path
    agent.thinkingmap_files = [output_path]
    agent.add_compact_message(f"thinkingmap output: {output_path}; project cognition map for the design state")
    agent.current_state = "design"
    return agent.model_dump()


def slice_node(state: dict) -> dict:
    agent = AgentState.model_validate(state)
    if not agent.subtask_feature_design_files:
        raise ValueError("subtask_feature_design_files missing")
    prompt = _build_slice_prompt(agent)
    llm = create_llm(LLMConfig.model_validate(agent.llm))
    base = agent.run_dir / "slices"
    output = _response_text(llm.invoke(prompt))
    try:
        data = _parse_json_object(output)
    except Exception as exc:
        write_text(base / "latest_output.md", output)
        write_text(base / "latest_failure.md", f"slice failed before slices.json was produced:\n{exc}\n")
        raise
    json_path = write_json(base / "slices.json", data)
    append_artifact(agent.run_dir, json_path, "Slices: 虚拟专家切片，包含每个任务的 DESIGNER 和 VERIFIER 及其思考协议")
    agent.slice_files = {"slices": json_path}
    agent.current_state = "minimum_compilable_baseline"
    agent.add_compact_message(f"slice output: {json_path}; virtual expert slices for the work loop")
    return agent.model_dump()


def design_node(state: dict) -> dict:
    agent = AgentState.model_validate(state)
    template = _load_prompt_template("design.md").strip()
    prompt = (
        f"{template}\n\n"
        "---\n\n"
        "## 输入材料\n\n"
        "<TBD - 输入内容待设计>\n"
    )
    if agent.design_feedback:
        prompt += (
            "\n## 上一次算法模拟的反馈\n\n"
            "以下算法模拟失败，请在重新生成总体设计时针对这些问题进行修正：\n\n"
            f"{agent.design_feedback}\n"
        )
    llm = create_llm(LLMConfig.model_validate(agent.llm))
    base = agent.run_dir / "design"
    output = _response_text(llm.invoke(prompt))
    md_path = write_text(base / "system_high_level_design.md", output)
    append_artifact(
        agent.run_dir,
        md_path,
        "Design: 总体设计文档，包含架构分层、模块接口、通讯协议、算法模型，是后续实现子任务的唯一设计基准",
    )
    agent.design_file = md_path
    agent.design_md = output
    agent.design_feedback = ""
    agent.current_state = "algorithm_simulation"
    agent.add_compact_message(f"design output: {md_path}; overall system design as single source of truth")
    return agent.model_dump()


MAX_ALGORITHM_SIMULATION_ITERATIONS = 5


def _extract_simulation_matrix(design_md: str) -> tuple[str, list[dict[str, object]] | None]:
    """Extract simulation_matrix from design markdown.

    Returns:
        ("success", matrix) - simulation_matrix found and valid
        ("not_found", None) - no JSON block mentioning simulation_matrix found
        ("format_error", None) - block mentions simulation_matrix but JSON is malformed
    """
    json_blocks = re.findall(r"```json\s*(.*?)\s*```", design_md, re.DOTALL)
    for block in json_blocks:
        if "simulation_matrix" not in block:
            continue
        candidates = [block, "{" + block + "}"]
        for candidate in candidates:
            try:
                data = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict) and "simulation_matrix" in data:
                matrix = data["simulation_matrix"]
                if isinstance(matrix, list):
                    return ("success", matrix)
        return ("format_error", None)
    return ("not_found", None)


def _parse_feedback_sections(output: str) -> tuple[str, list[dict[str, object]] | None]:
    """Parse FEEDBACK_START sections from algorithm_simulation output.

    Returns:
        ("success", feedbacks) - feedbacks found and valid
        ("not_found", None) - no FEEDBACK_START sections found
        ("format_error", None) - FEEDBACK_START section exists but JSON is malformed
    """
    pattern = r"<!--\s*FEEDBACK_START\s*-->\s*```json\s*(.*?)\s*```"
    matches = re.findall(pattern, output, re.DOTALL)
    if not matches:
        return ("not_found", None)
    feedbacks: list[dict[str, object]] = []
    for match in matches:
        try:
            data = json.loads(match)
        except json.JSONDecodeError:
            return ("format_error", None)
        if isinstance(data, dict):
            feedbacks.append(data)
    return ("success", feedbacks)


def _format_simulation_failures(failures: list[dict[str, object]]) -> str:
    lines: list[str] = []
    for failure in failures:
        sim_id = str(failure.get("sim_id") or "<unknown>")
        reason = str(failure.get("revision_reason") or "<no reason provided>")
        lines.append(f"- {sim_id}算法模拟失败，原因是{reason}")
    return "\n".join(lines)


def _build_algorithm_simulation_prompt(
    simulation_matrix: list[dict[str, object]],
    verification_env: dict[str, object],
    verification_env_path: Path | None,
    output_feedback: str = "",
) -> str:
    template = _load_prompt_template("algorithm_simulation.md").strip()
    env_path_text = f"`{verification_env_path}`" if verification_env_path else "`<not configured>`"
    prompt = (
        f"{template}\n\n"
        "---\n\n"
        "## 输入材料\n\n"
        "请基于以下两份输入材料执行算法模拟验证：\n\n"
        "1. **算法模拟矩阵 (Simulation Matrix)**：从总体设计文档中提取的 JSON，包含所有需要模拟验证的算法模块及其验收标准。\n"
        "2. **验证环境 (Verification Environment)**：agent 可操作的硬件工具和软件环境。\n\n"
        "## 算法模拟矩阵 (Simulation Matrix)\n\n"
        "```json\n"
        f"{json.dumps({'simulation_matrix': simulation_matrix}, ensure_ascii=False, indent=2)}\n"
        "```\n\n"
        "## 验证环境 (Verification Environment)\n\n"
        f"- Verification environment path: {env_path_text}\n\n"
        "```yaml\n"
        f"{_format_verification_env(verification_env)}\n"
        "```\n"
    )
    if output_feedback:
        prompt += (
            "\n## 上一次输出的反馈\n\n"
            "上一次输出的 JSON 格式错误，请修正：\n\n"
            f"{output_feedback}\n"
        )
    return prompt


def algorithm_simulation_node(state: dict) -> dict:
    agent = AgentState.model_validate(state)
    if not agent.design_file:
        raise ValueError("design_file missing")
    design_md = agent.design_md or Path(agent.design_file).read_text(encoding="utf-8")

    input_status, simulation_matrix = _extract_simulation_matrix(design_md)
    if input_status == "not_found":
        agent.design_feedback = ""
        agent.current_state = "subtask_feature_design"
        agent.add_compact_message("algorithm_simulation: no simulation_matrix found, no simulation needed")
        return agent.model_dump()
    if input_status == "format_error":
        agent.design_feedback = "输出json错误，请修改"
        agent.current_state = "design"
        agent.add_compact_message("algorithm_simulation: simulation_matrix JSON format error, routing back to design")
        return agent.model_dump()
    if not simulation_matrix:
        agent.design_feedback = ""
        agent.current_state = "subtask_feature_design"
        agent.add_compact_message("algorithm_simulation: empty simulation_matrix, no simulation needed")
        return agent.model_dump()

    llm = create_llm(LLMConfig.model_validate(agent.llm))
    base = agent.run_dir / "algorithm_simulation"
    output_feedback = ""
    md_path: Path | None = None
    feedbacks: list[dict[str, object]] | None = None

    for iteration in range(MAX_ALGORITHM_SIMULATION_ITERATIONS):
        prompt = _build_algorithm_simulation_prompt(
            simulation_matrix,
            agent.verification_env,
            agent.verification_env_file,
            output_feedback,
        )
        output = _response_text(llm.invoke(prompt))
        md_path = write_text(base / "algorithm_simulation.md", output)
        output_status, feedbacks = _parse_feedback_sections(output)
        if output_status == "not_found":
            append_artifact(
                agent.run_dir,
                md_path,
                "Algorithm Simulation: 算法模拟验证过程文档，包含每个算法模块的模拟结果与反馈",
            )
            agent.algorithm_simulation_file = md_path
            agent.design_feedback = ""
            agent.current_state = "subtask_feature_design"
            agent.add_compact_message(
                f"algorithm_simulation output: {md_path}; no FEEDBACK_START sections, skipping"
            )
            return agent.model_dump()
        if output_status == "format_error":
            output_feedback = "输出json错误，请修改"
            continue
        break
    else:
        append_artifact(
            agent.run_dir,
            md_path,
            "Algorithm Simulation: 算法模拟验证过程文档，包含每个算法模块的模拟结果与反馈",
        )
        agent.algorithm_simulation_file = md_path
        write_text(base / "latest_failure.md", "algorithm_simulation output JSON format error not fixed after max iterations\n")
        raise RuntimeError("algorithm_simulation output JSON format error not fixed after max iterations")

    append_artifact(
        agent.run_dir,
        md_path,
        "Algorithm Simulation: 算法模拟验证过程文档，包含每个算法模块的模拟结果与反馈",
    )
    agent.algorithm_simulation_file = md_path
    failures = [f for f in feedbacks if str(f.get("feedback_type")).lower() == "failed"]
    if not failures:
        agent.design_feedback = ""
        agent.current_state = "subtask_feature_design"
        agent.add_compact_message(
            f"algorithm_simulation output: {md_path}; all {len(feedbacks)} simulations passed"
        )
        return agent.model_dump()
    feedback_text = _format_simulation_failures(failures)
    agent.design_feedback = feedback_text
    agent.current_state = "design"
    agent.add_compact_message(
        f"algorithm_simulation output: {md_path}; {len(failures)}/{len(feedbacks)} simulations failed, routing back to design"
    )
    return agent.model_dump()


def subtask_feature_design_node(state: dict) -> dict:
    agent = AgentState.model_validate(state)
    if not agent.context_file:
        raise ValueError("context_file missing")
    if not agent.design_file:
        raise ValueError("design_file missing")
    prompt = _build_subtask_feature_design_prompt(agent)
    llm = create_llm(LLMConfig.model_validate(agent.llm))
    base = agent.run_dir / "subtask_feature_design"
    output = _response_text(llm.invoke(prompt))
    subtasks = _parse_subtask_blocks(output)
    if not subtasks:
        write_text(base / "latest_output.md", output)
        write_text(
            base / "latest_failure.md",
            "subtask_feature_design produced no parseable JSON subtask blocks\n",
        )
        raise RuntimeError("subtask_feature_design produced no parseable JSON subtask blocks")
    json_paths: list[Path] = []
    for index, subtask in enumerate(subtasks, 1):
        execution_order = subtask.get("execution_order")
        if isinstance(execution_order, (int, str)) and str(execution_order).strip():
            filename = f"{execution_order}.json"
        else:
            filename = f"{index}.json"
        json_path = write_json(base / filename, subtask)
        append_artifact(
            agent.run_dir,
            json_path,
            f"Subtask Feature Design: 子任务 {filename} 功能详细设计",
        )
        json_paths.append(json_path)
    agent.subtask_feature_design_files = json_paths
    agent.current_state = "subtask_feature_test"
    agent.add_compact_message(
        f"subtask_feature_design output: {len(json_paths)} subtask files in {base}"
    )
    return agent.model_dump()


def subtask_feature_test_node(state: dict) -> dict:
    agent = AgentState.model_validate(state)
    json_path, _output = _invoke_placeholder_state(
        agent,
        "subtask_feature_test",
        "subtask_feature_test",
        "subtask_feature_test.json",
        "Subtask Feature Test: 子任务功能测试设计",
    )
    agent.subtask_feature_test_file = json_path
    agent.current_state = "slice"
    agent.add_compact_message(f"subtask_feature_test output: {json_path}")
    return agent.model_dump()


def minimum_compilable_baseline_node(state: dict) -> dict:
    agent = AgentState.model_validate(state)
    json_path, _output = _invoke_placeholder_state(
        agent,
        "minimum_compilable_baseline",
        "minimum_compilable_baseline",
        "minimum_compilable_baseline.json",
        "Minimum Compilable Baseline: 最小可编译基线",
    )
    agent.minimum_compilable_baseline_file = json_path
    agent.current_state = "material_summary"
    agent.add_compact_message(f"minimum_compilable_baseline output: {json_path}")
    return agent.model_dump()


def material_summary_node(state: dict) -> dict:
    agent = AgentState.model_validate(state)
    json_path, _output = _invoke_placeholder_state(
        agent,
        "material_summary",
        "material_summary",
        "material_summary.json",
        "Material Summary: 资料总结",
    )
    agent.material_summary_file = json_path
    agent.current_state = "execute_tasks"
    agent.add_compact_message(f"material_summary output: {json_path}")
    return agent.model_dump()


def execute_tasks_node(state: dict) -> dict:
    agent = AgentState.model_validate(state)
    regression_suite_path = agent.run_dir / "regression_suite.md"
    if not regression_suite_path.exists():
        write_text(
            regression_suite_path,
            "# Regression Suite\n\n本文件记录本次运行中各任务归档的回归测试用例，供后续增量任务提取并执行全量回归测试。\n",
        )
        append_artifact(agent.run_dir, regression_suite_path, "Regression Suite: 回归测试用例库，供增量任务提取并执行全量回归测试")
        agent.add_compact_message(f"regression_suite created: {regression_suite_path}")
    artifacts_index = read_artifacts_index(agent.run_dir)
    agent.current_state = "done"
    agent.add_compact_message(
        f"execution ready; artifacts_index loaded ({len(artifacts_index.splitlines())} lines); "
        f"downstream task prompts should include artifacts_index"
    )
    return agent.model_dump()
