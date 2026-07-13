from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import yaml

from embedded_agent.artifacts import append_artifact, read_artifacts_index, write_json, write_text
from embedded_agent.agent_tools import invoke_with_agent_tools
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


def _file_signature(path: Path) -> tuple[int, int] | None:
    if not path.exists() or not path.is_file():
        return None
    stat = path.stat()
    return stat.st_mtime_ns, stat.st_size


def _artifact_delivery_contract(prompt: str, output_path: Path) -> str:
    delivery = _load_prompt_template("artifact_delivery.md").replace("{{OUTPUT_PATH}}", str(output_path))
    return f"{prompt.rstrip()}\n\n---\n\n{delivery.strip()}\n"


def _invoke_state_artifact(
    llm: object,
    prompt: str,
    *,
    agent: AgentState,
    state_name: str,
    output_path: Path,
) -> str:
    before = _file_signature(output_path)
    output = invoke_with_agent_tools(
        llm,
        _artifact_delivery_contract(prompt, output_path),
        project_root=agent.project_root,
        run_dir=agent.run_dir,
        state_name=state_name,
        allow_empty_response=True,
    )
    after = _file_signature(output_path)
    if after is not None and after != before:
        artifact = output_path.read_text(encoding="utf-8").strip()
        if artifact:
            return artifact
    if output.strip():
        return output.strip()
    raise RuntimeError(f"{state_name} produced neither a written artifact nor a final response")


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


def _state_text(value: str, path: Path | None, label: str) -> str:
    if value:
        return value
    if path and Path(path).exists():
        return Path(path).read_text(encoding="utf-8")
    raise ValueError(f"{label} missing")


def _json_file_sections(paths: list[Path], title: str) -> str:
    if not paths:
        raise ValueError(f"{title} missing")
    sections = [f"## {title}\n\n"]
    for path in paths:
        source = Path(path)
        if not source.exists():
            raise ValueError(f"{title} file missing: {source}")
        sections.extend(
            (
                f"### `{source.name}`\n\n",
                f"```json\n{source.read_text(encoding='utf-8')}\n```\n\n",
            )
        )
    return "".join(sections)


def _verification_environment_section(agent: AgentState) -> str:
    env_path_text = f"`{agent.verification_env_file}`" if agent.verification_env_file else "`<not configured>`"
    return (
        "## Verification Environment\n\n"
        f"- Verification environment path: {env_path_text}\n\n"
        f"```yaml\n{_format_verification_env(agent.verification_env)}\n```\n"
    )


def _build_design_prompt(agent: AgentState) -> str:
    context_md = _state_text(agent.context_md, agent.context_file, "build context")
    thinkingmap_text = _state_text("", agent.thinkingmap_file, "thinkingmap")
    return (
        f"{_load_prompt_template('design.md').strip()}\n\n"
        "---\n\n"
        "## Build Context\n\n"
        f"```markdown\n{context_md}\n```\n\n"
        "## Thinking Map\n\n"
        f"```markdown\n{thinkingmap_text}\n```\n\n"
        f"{_verification_environment_section(agent)}"
    )


def _build_subtask_feature_test_prompt(agent: AgentState) -> str:
    context_md = _state_text(agent.context_md, agent.context_file, "build context")
    thinkingmap_text = _state_text("", agent.thinkingmap_file, "thinkingmap")
    design_md = _state_text(agent.design_md, agent.design_file, "overall design")
    if agent.subtask_design_all_file and Path(agent.subtask_design_all_file).exists():
        design_section = f"```json\n{Path(agent.subtask_design_all_file).read_text(encoding='utf-8')}\n```\n"
    else:
        design_section = _json_file_sections(agent.subtask_feature_design_files, "Subtask Feature Design Files")
    return (
        f"{_load_prompt_template('subtask_feature_test.md').strip()}\n\n"
        "---\n\n"
        "## Inputs Provided By The Workflow\n\n"
        "Build Context, Thinking Map, Overall Design, Verification Environment, and the complete subtask design JSON collection are provided below.\n\n"
        "## Build Context\n\n"
        f"```markdown\n{context_md}\n```\n\n"
        "## Thinking Map\n\n"
        f"```markdown\n{thinkingmap_text}\n```\n\n"
        "## Overall Design\n\n"
        f"```markdown\n{design_md}\n```\n\n"
        f"{_verification_environment_section(agent)}\n\n"
        "## Subtask Feature Design Aggregate JSON\n\n"
        f"{design_section}"
    )


def _build_minimum_compilable_baseline_prompt(agent: AgentState) -> str:
    context_md = _state_text(agent.context_md, agent.context_file, "build context")
    return (
        f"{_load_prompt_template('minimum_compilable_baseline.md').strip()}\n\n"
        "---\n\n"
        "## Build Context\n\n"
        f"```markdown\n{context_md}\n```\n\n"
        f"{_verification_environment_section(agent)}"
    )


def _build_material_summary_prompt(agent: AgentState) -> str:
    test_path = agent.subtask_feature_test_all_file or agent.subtask_feature_test_file
    slice_path = agent.slice_all_file or agent.slice_files.get("slices")
    if not test_path or not Path(test_path).exists() or not slice_path or not Path(slice_path).exists():
        raise ValueError("material summary requires a task-specific manifest entry")
    return (
        f"{_load_prompt_template('material_summary.md').strip()}\n\n"
        "---\n\n"
        f"{_json_file_sections(agent.subtask_feature_design_files, 'Subtask Feature Design Files')}"
        "## Subtask Feature Test\n\n"
        f"```json\n{Path(test_path).read_text(encoding='utf-8')}\n```\n\n"
        "## Task Slices\n\n"
        f"```json\n{Path(slice_path).read_text(encoding='utf-8')}\n```\n"
    )


def _safe_task_folder(index: int, task_id: object) -> str:
    value = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(task_id or f"task-{index}"))
    return f"{index}-{value}"


def _render_prompt_template(name: str, values: dict[str, object]) -> str:
    text = _load_prompt_template(name)
    for key, value in values.items():
        if isinstance(value, str):
            rendered = value
        else:
            rendered = json.dumps(value, ensure_ascii=False, indent=2)
        text = text.replace("{{" + key + "}}", rendered)
    return text


def _render_task_prompts(
    agent: AgentState,
    entry: dict[str, object],
    summary: dict[str, object],
    task_folder: Path,
) -> tuple[Path, Path]:
    implementation = summary.get("implementation_material", {})
    verification = summary.get("verification_material", {})
    work_loop = summary.get("work_loop", {})
    task_id = str(summary.get("task_id") or entry.get("task_id") or "")
    execution_order = summary.get("execution_order", entry.get("execution_order", entry.get("index", "")))
    task_goal = summary.get("task_goal", "")
    design_path = write_text(
        task_folder / "prompts" / "design_prompt.md",
        _render_prompt_template(
            "task_design_execution.md",
            {
                "TASK_ID": task_id,
                "EXECUTION_ORDER": execution_order,
                "TASK_GOAL": task_goal,
                "DESIGN_OBJECTIVE": implementation.get("design_objective", "") if isinstance(implementation, dict) else "",
                "DETAILED_DESIGN_SCOPE": implementation.get("detailed_design_scope", {}) if isinstance(implementation, dict) else {},
                "TARGET_FILES": implementation.get("target_files", []) if isinstance(implementation, dict) else [],
                "COMPATIBILITY_STRATEGY": implementation.get("compatibility_strategy", "") if isinstance(implementation, dict) else "",
                "DESIGNER_SLICE": implementation.get("designer_slice", {}) if isinstance(implementation, dict) else {},
                "FULL_MATERIAL_SUMMARY": summary,
            },
        ),
    )
    test_path = write_text(
        task_folder / "prompts" / "test_prompt.md",
        _render_prompt_template(
            "task_test_execution.md",
            {
                "TASK_ID": task_id,
                "EXECUTION_ORDER": execution_order,
                "TASK_GOAL": task_goal,
                "TEST_DESIGN": verification.get("test_design", {}) if isinstance(verification, dict) else {},
                "TEST_CASES": verification.get("test_cases", []) if isinstance(verification, dict) else [],
                "REGRESSION_REQUIREMENTS": verification.get("regression_requirements", "") if isinstance(verification, dict) else "",
                "VERIFIER_SLICE": verification.get("verifier_slice", {}) if isinstance(verification, dict) else {},
                "FULL_MATERIAL_SUMMARY": summary,
            },
        ),
    )
    return design_path, test_path


def _build_task_material_summary_prompt(
    agent: AgentState,
    entry: dict[str, object],
) -> str:
    def read_run_file(relative_path: object, label: str) -> str:
        if not relative_path:
            return f"<{label} not available>"
        path = agent.run_dir / str(relative_path)
        if not path.exists():
            return f"<{label} not available: {path}>"
        return path.read_text(encoding="utf-8")

    design = read_run_file(entry.get("design_file"), "design")
    test = read_run_file(entry.get("test_file"), "test")
    design_slice = read_run_file(entry.get("design_slice_file"), "design expert slice")
    test_slice = read_run_file(entry.get("test_slice_file"), "test expert slice")
    return (
        f"{_load_prompt_template('material_summary.md').strip()}\n\n"
        "---\n\n"
        f"## Current Task\n\n- task_id: `{entry.get('task_id')}`\n"
        f"- execution_order: `{entry.get('execution_order')}`\n"
        f"- dependencies: `{json.dumps(entry.get('dependencies', []), ensure_ascii=False)}`\n\n"
        "## Subtask Design\n\n"
        f"```json\n{design}\n```\n\n"
        "## Subtask Test Design\n\n"
        f"```json\n{test}\n```\n\n"
        "## Design Expert Slice\n\n"
        f"```json\n{design_slice}\n```\n\n"
        "## Test Expert Slice\n\n"
        f"```json\n{test_slice}\n```\n"
    )


def _invoke_json_state(
    agent: AgentState,
    prompt: str,
    state_name: str,
    base_dirname: str,
    output_filename: str,
    description: str,
) -> tuple[Path, str]:
    llm = create_llm(LLMConfig.model_validate(agent.llm))
    base = agent.run_dir / base_dirname
    output_path = base / output_filename
    output = _invoke_state_artifact(
        llm,
        prompt,
        agent=agent,
        state_name=state_name,
        output_path=output_path,
    )
    try:
        data = _parse_json_object(output)
    except Exception as exc:
        write_text(base / "latest_output.md", output)
        write_text(base / "latest_failure.md", f"{state_name} failed before {output_filename} was produced:\n{exc}\n")
        raise
    json_path = write_json(output_path, data)
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


def _parse_aggregate_items(output: str, key: str) -> tuple[dict[str, object], list[dict[str, object]]]:
    data = _parse_json_object(output)
    items = data.get(key)
    if isinstance(items, list):
        return data, [item for item in items if isinstance(item, dict)]
    raise ValueError(f"LLM output must contain a {key} array")


def _relative_run_path(agent: AgentState, path: Path) -> str:
    return path.relative_to(agent.run_dir).as_posix()


def _load_manifest(agent: AgentState) -> list[dict[str, object]]:
    if not agent.subtask_manifest_file or not Path(agent.subtask_manifest_file).exists():
        return []
    data = json.loads(Path(agent.subtask_manifest_file).read_text(encoding="utf-8"))
    return data if isinstance(data, list) else []


def _write_manifest(agent: AgentState, entries: list[dict[str, object]]) -> Path:
    path = agent.run_dir / "subtask_feature_design" / "subtask_manifest.json"
    path = write_json(path, entries)
    append_artifact(agent.run_dir, path, "Subtask Manifest: 子任务总表与设计、测试、slice 文件映射")
    agent.subtask_manifest_file = path
    return path


def _split_subtask_designs(agent: AgentState, items: list[dict[str, object]]) -> list[Path]:
    base = agent.run_dir / "subtask_feature_design"
    paths: list[Path] = []
    entries: list[dict[str, object]] = []
    for index, item in enumerate(items, 1):
        path = write_json(base / f"{index}D.json", item)
        append_artifact(agent.run_dir, path, f"Subtask Feature Design: 子任务 {index}D.json 功能详细设计")
        paths.append(path)
        entries.append(
            {
                "index": index,
                "execution_order": item.get("execution_order", index),
                "task_id": item.get("task_id", f"task-{index}"),
                "dependencies": item.get("dependencies", []),
                "design_file": _relative_run_path(agent, path),
                "test_file": f"subtask_feature_test/{index}T.json",
                "design_slice_file": f"slices/{index}-design-expert.json",
                "test_slice_file": f"slices/{index}-test-expert.json",
            }
        )
    _validate_manifest_dependencies(entries)
    _write_manifest(agent, entries)
    return paths


def _dependency_ids(value: object, task_id: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"task {task_id} dependencies must be an array")
    dependencies = [str(item).strip() for item in value]
    if any(not item for item in dependencies):
        raise ValueError(f"task {task_id} contains an empty dependency")
    if len(set(dependencies)) != len(dependencies):
        raise ValueError(f"task {task_id} contains duplicate dependencies")
    return dependencies


def _validate_manifest_dependencies(entries: list[dict[str, object]]) -> None:
    task_ids = [str(entry.get("task_id") or "").strip() for entry in entries]
    if any(not task_id for task_id in task_ids) or len(set(task_ids)) != len(task_ids):
        raise ValueError("subtask manifest requires unique non-empty task_id values")
    known = set(task_ids)
    for entry, task_id in zip(entries, task_ids):
        dependencies = _dependency_ids(entry.get("dependencies", []), task_id)
        unknown = sorted(set(dependencies) - known)
        if unknown:
            raise ValueError(f"task {task_id} has unknown dependencies: {unknown}")
        if task_id in dependencies:
            raise ValueError(f"task {task_id} cannot depend on itself")
        entry["dependencies"] = dependencies


def _update_manifest(agent: AgentState, updates: dict[int, dict[str, str]]) -> None:
    entries = _load_manifest(agent)
    for entry in entries:
        index = entry.get("index")
        if isinstance(index, int) and index in updates:
            entry.update(updates[index])
    _write_manifest(agent, entries)


def _items_by_task_id(
    items: list[object],
    manifest: list[dict[str, object]],
    label: str,
) -> dict[str, dict[str, object]]:
    expected_ids = [str(entry.get("task_id") or "").strip() for entry in manifest]
    if not expected_ids or any(not task_id for task_id in expected_ids):
        raise ValueError("subtask manifest contains a missing task_id")
    if len(set(expected_ids)) != len(expected_ids):
        raise ValueError("subtask manifest contains duplicate task_id values")

    indexed: dict[str, dict[str, object]] = {}
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(f"{label} contains a non-object item")
        task_id = str(item.get("task_id") or "").strip()
        if not task_id:
            raise ValueError(f"{label} item missing task_id")
        if task_id in indexed:
            raise ValueError(f"{label} contains duplicate task_id: {task_id}")
        indexed[task_id] = item

    expected = set(expected_ids)
    actual = set(indexed)
    if expected != actual:
        missing = sorted(expected - actual)
        unknown = sorted(actual - expected)
        raise ValueError(f"{label} task_id mismatch; missing={missing}, unknown={unknown}")
    return indexed


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
    context_md = agent.context_md or (
        Path(agent.context_file).read_text(encoding="utf-8")
        if agent.context_file and Path(agent.context_file).exists()
        else "<build context not available>"
    )
    thinkingmap_text = (
        Path(agent.thinkingmap_file).read_text(encoding="utf-8")
        if agent.thinkingmap_file and Path(agent.thinkingmap_file).exists()
        else "<thinking map not available>"
    )
    env_section = _verification_environment_section(agent)
    regression_path = agent.run_dir / "regression_suite.md"
    regression = regression_path.read_text(encoding="utf-8") if regression_path.exists() else "<regression suite not created yet>"
    parts: list[str] = [
        f"{template}\n\n",
        "---\n\n",
        "## Build Context\n\n",
        f"```markdown\n{context_md}\n```\n\n",
        "## Thinking Map\n\n",
        f"```markdown\n{thinkingmap_text}\n```\n\n",
        f"{env_section}\n\n",
        "## Regression Suite\n\n",
        f"```markdown\n{regression}\n```\n\n",
        "## Subtask Feature Design Aggregate JSON\n\n",
    ]
    if agent.subtask_design_all_file and Path(agent.subtask_design_all_file).exists():
        parts.append(f"```json\n{Path(agent.subtask_design_all_file).read_text(encoding='utf-8')}\n```\n\n")
    elif agent.subtask_feature_design_files:
        for path in agent.subtask_feature_design_files:
            parts.append(f"- 文件路径：`{path}`\n")
            content = Path(path).read_text(encoding="utf-8") if Path(path).exists() else "<file not found>"
            parts.append(f"\n```json\n{content}\n```\n\n")
    else:
        parts.append("无子任务功能设计文件。\n\n")

    parts.append("## Subtask Feature Test Aggregate JSON\n\n")
    test_path = agent.subtask_feature_test_all_file or agent.subtask_feature_test_file
    if test_path:
        test_path = Path(test_path)
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
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "utf-8"
    environment["PYTHONUTF8"] = "1"
    powershell_command = (
        "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
        "$OutputEncoding = [Console]::OutputEncoding; "
        f"{command}"
    )
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", powershell_command],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=BASH_TOOL_TIMEOUT_SEC,
        cwd=cwd,
        env=environment,
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
    return _invoke_state_artifact(
        llm,
        prompt,
        agent=agent,
        state_name="context",
        output_path=context_dir / "context.md",
    )


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
    markdown_path = agent.run_dir / "thinkingmap" / "thinkingmap.md"
    output = _invoke_state_artifact(
        llm,
        prompt,
        agent=agent,
        state_name="thinkingmap",
        output_path=markdown_path,
    )
    try:
        thinkingmap = _parse_json_object(output)
        output_path = write_json(agent.run_dir / "thinkingmap" / "thinkingmap.json", thinkingmap)
    except (json.JSONDecodeError, ValueError):
        output_path = write_text(markdown_path, output)
    append_artifact(agent.run_dir, output_path, "Thinking Map: 系统沉淀的专业知识、代码片段、设计模式与避坑指南")
    agent.thinkingmap_file = output_path
    agent.thinkingmap_files = [output_path]
    agent.add_compact_message(f"thinkingmap output: {output_path}; project cognition map for the design state")
    agent.current_state = "design"
    return agent.model_dump()


def slice_node(state: dict) -> dict:
    agent = AgentState.model_validate(state)
    if not agent.subtask_feature_design_files and not agent.subtask_design_all_file:
        raise ValueError("subtask_feature_design_files missing")
    prompt = _build_slice_prompt(agent)
    llm = create_llm(LLMConfig.model_validate(agent.llm))
    base = agent.run_dir / "slices"
    output = _invoke_state_artifact(
        llm,
        prompt,
        agent=agent,
        state_name="slice",
        output_path=base / "all_slices.json",
    )
    try:
        data = _parse_json_object(output)
    except Exception as exc:
        write_text(base / "latest_output.md", output)
        write_text(base / "latest_failure.md", f"slice failed before slices.json was produced:\n{exc}\n")
        raise
    if isinstance(data.get("slices"), list):
        manifest = _load_manifest(agent)
        slices_by_task = _items_by_task_id(data["slices"], manifest, "slices")
        all_path = write_json(base / "all_slices.json", data)
        append_artifact(agent.run_dir, all_path, "Slices Aggregate: 所有子任务的设计专家与测试专家总 JSON")
        agent.slice_all_file = all_path
        slice_files: dict[str, Path] = {}
        updates: dict[int, dict[str, str]] = {}
        for entry in manifest:
            index = int(entry["index"])
            task_id = str(entry["task_id"])
            item = slices_by_task[task_id]
            design_expert = item.get("design_expert", {})
            test_expert = item.get("test_expert", {})
            design_path = write_json(base / f"{index}-design-expert.json", design_expert)
            test_path = write_json(base / f"{index}-test-expert.json", test_expert)
            append_artifact(agent.run_dir, design_path, f"Slice Design Expert: 子任务 {index} 设计专家配置")
            append_artifact(agent.run_dir, test_path, f"Slice Test Expert: 子任务 {index} 测试专家配置")
            key = task_id
            slice_files[f"{key}:design"] = design_path
            slice_files[f"{key}:test"] = test_path
            updates[index] = {
                "design_slice_file": _relative_run_path(agent, design_path),
                "test_slice_file": _relative_run_path(agent, test_path),
            }
        agent.slice_files = slice_files
        _update_manifest(agent, updates)
        json_path = all_path
    else:
        json_path = write_json(base / "slices.json", data)
        append_artifact(agent.run_dir, json_path, "Slices: 虚拟专家切片，包含每个任务的 DESIGNER 和 VERIFIER 及其思考协议")
        agent.slice_files = {"slices": json_path}
    agent.current_state = "minimum_compilable_baseline"
    agent.add_compact_message(f"slice output: {json_path}; virtual expert slices for the work loop")
    return agent.model_dump()


def design_node(state: dict) -> dict:
    agent = AgentState.model_validate(state)
    prompt = _build_design_prompt(agent)
    if agent.design_feedback:
        prompt += (
            "\n## 上一次算法模拟的反馈\n\n"
            "以下算法模拟失败，请在重新生成总体设计时针对这些问题进行修正：\n\n"
            f"{agent.design_feedback}\n"
    )
    llm = create_llm(LLMConfig.model_validate(agent.llm))
    base = agent.run_dir / "design"
    md_path = base / "system_high_level_design.md"
    output = _invoke_state_artifact(
        llm,
        prompt,
        agent=agent,
        state_name="design",
        output_path=md_path,
    )
    md_path = write_text(md_path, output)
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
        output = _invoke_state_artifact(
            llm,
            prompt,
            agent=agent,
            state_name="algorithm_simulation",
            output_path=base / "algorithm_simulation.md",
        )
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
    all_path = base / "all_subtasks.json"
    output = _invoke_state_artifact(
        llm,
        prompt,
        agent=agent,
        state_name="subtask_feature_design",
        output_path=all_path,
    )
    try:
        aggregate, subtasks = _parse_aggregate_items(output, "subtasks")
    except Exception:
        subtasks = _parse_subtask_blocks(output)
        aggregate = {"subtasks": subtasks}
    if not subtasks and aggregate.get("subtasks") != []:
        write_text(base / "latest_output.md", output)
        write_text(
            base / "latest_failure.md",
            "subtask_feature_design produced no parseable JSON subtask blocks\n",
        )
        raise RuntimeError("subtask_feature_design produced no parseable JSON subtask blocks")
    all_path = write_json(all_path, aggregate)
    append_artifact(agent.run_dir, all_path, "Subtask Design Aggregate: 所有子任务详细设计总 JSON")
    json_paths = _split_subtask_designs(agent, subtasks)
    agent.subtask_design_all_file = all_path
    agent.subtask_feature_design_files = json_paths
    agent.current_state = "subtask_feature_test"
    agent.add_compact_message(
        f"subtask_feature_design output: {len(json_paths)} subtask files in {base}"
    )
    return agent.model_dump()


def subtask_feature_test_node(state: dict) -> dict:
    agent = AgentState.model_validate(state)
    all_path, _output = _invoke_json_state(
        agent,
        _build_subtask_feature_test_prompt(agent),
        "subtask_feature_test",
        "subtask_feature_test",
        "all_tests.json",
        "Subtask Test Aggregate: 所有子任务测试设计总 JSON",
    )
    data = json.loads(all_path.read_text(encoding="utf-8"))
    tests = data.get("tests", [])
    if not isinstance(tests, list):
        raise ValueError("subtask_feature_test output must contain a tests array")
    manifest = _load_manifest(agent)
    tests_by_task = _items_by_task_id(tests, manifest, "tests")
    base = agent.run_dir / "subtask_feature_test"
    paths: list[Path] = []
    updates: dict[int, dict[str, str]] = {}
    inherited_test_cases: list[object] = []
    cumulative_task_tests: list[dict[str, object]] = []
    for entry in manifest:
        index = int(entry["index"])
        item = tests_by_task[str(entry["task_id"])]
        cumulative_item = dict(item)
        current_test_cases = cumulative_item.get("test_cases")
        if not isinstance(current_test_cases, list):
            current_test_cases = []
        cumulative_item["test_cases"] = [*inherited_test_cases, *current_test_cases]
        inherited_test_cases.extend(current_test_cases)
        cumulative_task_tests.append(dict(item))
        cumulative_item["cumulative_task_tests"] = [dict(test) for test in cumulative_task_tests]
        path = write_json(base / f"{index}T.json", cumulative_item)
        append_artifact(agent.run_dir, path, f"Subtask Feature Test: 子任务 {index}T.json 测试设计")
        paths.append(path)
        updates[index] = {"test_file": _relative_run_path(agent, path)}
    agent.subtask_feature_test_all_file = all_path
    agent.subtask_feature_test_file = all_path
    agent.subtask_feature_test_files = paths
    _update_manifest(agent, updates)
    agent.current_state = "slice"
    agent.add_compact_message(f"subtask_feature_test output: {all_path}; split {len(paths)} task files")
    return agent.model_dump()


def minimum_compilable_baseline_node(state: dict) -> dict:
    agent = AgentState.model_validate(state)
    llm = create_llm(LLMConfig.model_validate(agent.llm))
    invoke_with_agent_tools(
        llm,
        _build_minimum_compilable_baseline_prompt(agent),
        project_root=agent.project_root,
        run_dir=agent.run_dir,
        state_name="minimum_compilable_baseline",
        allow_empty_response=True,
    )
    tool_log = agent.run_dir / "minimum_compilable_baseline" / "tool_calls.jsonl"
    if not tool_log.exists() or not tool_log.read_text(encoding="utf-8").strip():
        raise RuntimeError("minimum_compilable_baseline produced no tool activity")
    agent.minimum_compilable_baseline_file = None
    agent.current_state = "material_summary"
    agent.add_compact_message("minimum_compilable_baseline prepared the target project through shared tools")
    return agent.model_dump()


def material_summary_node(state: dict) -> dict:
    agent = AgentState.model_validate(state)
    entries = _load_manifest(agent)
    if not entries:
        raise ValueError("subtask_manifest_file missing or empty")

    base = agent.run_dir / "material_summary"
    summaries: list[dict[str, object]] = []
    summary_paths: list[Path] = []
    task_prompt_files: dict[str, Path] = {}
    manifest_updates: dict[int, dict[str, str]] = {}
    llm = create_llm(LLMConfig.model_validate(agent.llm))
    for entry in entries:
        index = int(entry.get("index") or len(summary_paths) + 1)
        task_folder = base / _safe_task_folder(index, entry.get("task_id"))
        prompt = _build_task_material_summary_prompt(agent, entry)
        expected_summary_path = task_folder / "material_summary.json"
        output = _invoke_state_artifact(
            llm,
            prompt,
            agent=agent,
            state_name=f"material_summary/{task_folder.name}",
            output_path=expected_summary_path,
        )
        try:
            summary_data = _parse_json_object(output)
        except (json.JSONDecodeError, ValueError) as exc:
            write_text(task_folder / "latest_output.md", output)
            write_text(task_folder / "latest_failure.md", f"material_summary JSON parse failed: {exc}\n")
            raise ValueError(f"material_summary for {entry.get('task_id')} must be valid JSON") from exc
        expected_task_id = str(entry.get("task_id") or "")
        actual_task_id = str(summary_data.get("task_id") or "")
        if actual_task_id != expected_task_id:
            write_text(task_folder / "latest_output.md", output)
            write_text(
                task_folder / "latest_failure.md",
                f"material_summary task_id mismatch: expected={expected_task_id}, actual={actual_task_id}\n",
            )
            raise ValueError(
                f"material_summary task_id mismatch: expected={expected_task_id}, actual={actual_task_id}"
            )
        summary_path = write_json(expected_summary_path, summary_data)
        summary_record: dict[str, object] = dict(summary_data)
        append_artifact(agent.run_dir, summary_path, f"Material Summary: 子任务 {entry.get('task_id')} 执行材料")
        summary_paths.append(summary_path)
        design_prompt_path, test_prompt_path = _render_task_prompts(agent, entry, summary_record, task_folder)
        append_artifact(agent.run_dir, design_prompt_path, f"Task Design Prompt: 子任务 {entry.get('task_id')} 设计执行 prompt")
        append_artifact(agent.run_dir, test_prompt_path, f"Task Test Prompt: 子任务 {entry.get('task_id')} 测试执行 prompt")
        task_key = str(entry.get("task_id") or f"task-{index}")
        task_prompt_files[f"{task_key}:design"] = design_prompt_path
        task_prompt_files[f"{task_key}:test"] = test_prompt_path
        manifest_updates[index] = {
            "material_file": _relative_run_path(agent, summary_path),
            "design_prompt_file": _relative_run_path(agent, design_prompt_path),
            "test_prompt_file": _relative_run_path(agent, test_prompt_path),
        }
        summaries.append(
            {
                "index": index,
                "execution_order": entry.get("execution_order", index),
                "task_id": entry.get("task_id", f"task-{index}"),
                "dependencies": entry.get("dependencies", []),
                "material_file": _relative_run_path(agent, summary_path),
                "design_prompt_file": _relative_run_path(agent, design_prompt_path),
                "test_prompt_file": _relative_run_path(agent, test_prompt_path),
                "summary": summary_record,
            }
        )

    all_path = write_json(base / "all_tasks.json", {"tasks": summaries})
    append_artifact(agent.run_dir, all_path, "Material Summary Aggregate: 按子任务整理的全部执行材料")
    _update_manifest(agent, manifest_updates)
    agent.material_summary_all_file = all_path
    agent.material_summary_file = all_path
    agent.material_summary_files = summary_paths
    agent.task_prompt_files = task_prompt_files
    agent.current_state = "execute_tasks"
    agent.add_compact_message(f"material_summary output: {all_path}; packaged {len(summary_paths)} task materials")
    return agent.model_dump()


def _execution_tasks(agent: AgentState) -> list[dict[str, object]]:
    path = agent.material_summary_all_file or agent.run_dir / "material_summary" / "all_tasks.json"
    if not Path(path).exists():
        return []
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    tasks = data.get("tasks") if isinstance(data, dict) else None
    return [item for item in tasks if isinstance(item, dict)] if isinstance(tasks, list) else []


def _execution_task_folder(agent: AgentState, task: dict[str, object], index: int) -> Path:
    return agent.run_dir / "execution" / _safe_task_folder(index, task.get("task_id"))


def _write_current_execution_task(agent: AgentState, task: dict[str, object], index: int) -> None:
    write_json(
        agent.run_dir / "execution" / "current_task.json",
        {
            "index": index,
            "task_id": task.get("task_id", f"task-{index}"),
            "execution_order": task.get("execution_order", index),
            "task_folder": str(_execution_task_folder(agent, task, index)),
            "child_state": agent.current_child_state,
            "attempt": agent.current_attempt,
            "completed_task_ids": sorted(agent.completed_task_ids),
            "latest_test_failure_file": str(agent.latest_test_failure_file) if agent.latest_test_failure_file else None,
        },
    )


def _task_prompt_path(agent: AgentState, task: dict[str, object], role: str) -> Path:
    key = str(task.get("task_id") or f"task-{task.get('index')}")
    path = agent.task_prompt_files.get(f"{key}:{role}")
    if path:
        return Path(path)
    field = "design_prompt_file" if role == "design" else "test_prompt_file"
    return agent.run_dir / str(task.get(field) or "")


def _build_execution_prompt(
    agent: AgentState,
    task: dict[str, object],
    role: str,
    attempt_dir: Path,
) -> str:
    prompt_path = _task_prompt_path(agent, task, role)
    task_prompt = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else "<task prompt not available>"
    context = _state_text(agent.context_md, agent.context_file, "build context")
    text = (
        f"You are the {role} child task for task {task.get('task_id')}.\n\n"
        "## Build Context\n\n"
        f"```markdown\n{context}\n```\n\n"
        f"## Rendered Task {role.title()} Prompt\n\n{task_prompt}\n"
    )
    if role == "design" and agent.latest_test_failure_file and Path(agent.latest_test_failure_file).exists():
        failure = Path(agent.latest_test_failure_file).read_text(encoding="utf-8")
        text += (
            "\n## Previous Test Failure\n\n"
            f"The previous test attempt failed. Read and address this failure before changing the design:\n\n"
            f"```markdown\n{failure}\n```\n"
        )
    if role == "test":
        result_path = attempt_dir / "result.json"
        text += (
            "\n## Test Result Contract\n\n"
            "Use the shared tools to execute the test material. At the end, either write a JSON result to "
            f"`{result_path}` or return one line with `TEST_STATUS: PASS` or `TEST_STATUS: FAIL`. "
            "For FAIL, include the failure reason and evidence paths.\n"
        )
    return text


def _parse_test_status(output: str, result_path: Path) -> tuple[str, str]:
    if result_path.exists():
        try:
            data = json.loads(result_path.read_text(encoding="utf-8"))
            status = str(data.get("status", "")).lower()
            reason = str(data.get("reason", data.get("failure_reason", "")))
            if status in {"pass", "passed", "success"}:
                return "pass", reason
            if status in {"fail", "failed", "error", "execution_error"}:
                return "fail", reason
        except (json.JSONDecodeError, AttributeError):
            pass
    match = re.search(r"TEST_STATUS\s*:\s*(PASS|FAIL)\b(?:[\s-]*(.*))?", output, re.IGNORECASE)
    if match:
        return match.group(1).lower(), (match.group(2) or "").strip()
    return "fail", "测试 agent 未提供可识别的通过结果"


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
    tasks = _execution_tasks(agent)
    if not tasks:
        artifacts_index = read_artifacts_index(agent.run_dir)
        agent.current_state = "done"
        agent.add_compact_message(f"execution ready; artifacts_index loaded ({len(artifacts_index.splitlines())} lines)")
        return agent.model_dump()
    task_ids = [str(task.get("task_id") or f"task-{index}") for index, task in enumerate(tasks, 1)]
    if len(set(task_ids)) != len(task_ids):
        raise ValueError("execution task list contains duplicate task_id values")
    known_task_ids = set(task_ids)
    dependencies_by_id: dict[str, list[str]] = {}
    for task_id, task in zip(task_ids, tasks):
        dependencies = _dependency_ids(task.get("dependencies", []), task_id)
        unknown = sorted(set(dependencies) - known_task_ids)
        if unknown:
            raise ValueError(f"task {task_id} has unknown dependencies: {unknown}")
        dependencies_by_id[task_id] = dependencies

    def order_key(pair: tuple[int, dict[str, object]]) -> tuple[int, float | str, int]:
        index, task = pair
        value = task.get("execution_order", index)
        try:
            return (0, float(value), index)
        except (TypeError, ValueError):
            return (1, str(value), index)

    ordered = sorted(enumerate(tasks, 1), key=order_key)
    pending: list[str] = []
    for index, task in ordered:
        task_id = str(task.get("task_id") or f"task-{index}")
        if task_id in agent.completed_task_ids:
            continue
        pending.append(task_id)
        if not set(dependencies_by_id[task_id]).issubset(agent.completed_task_ids):
            continue
        agent.current_task_index = index
        agent.current_task_id = task_id
        agent.current_task_folder = _execution_task_folder(agent, task, index)
        agent.current_child_state = "design"
        agent.current_attempt = max(agent.current_attempt, 1)
        agent.latest_test_failure_file = None
        _write_current_execution_task(agent, task, index)
        agent.current_state = "task_design"
        agent.add_compact_message(f"selected task {task_id} in execution order {task.get('execution_order', index)}")
        return agent.model_dump()
    if pending:
        blocked = {task_id: dependencies_by_id[task_id] for task_id in pending}
        raise ValueError(f"no executable task; blocked dependencies: {blocked}")
    agent.current_task_index = None
    agent.current_task_id = None
    agent.current_task_folder = None
    agent.current_child_state = None
    agent.current_state = "done"
    agent.add_compact_message("all material summary tasks completed")
    return agent.model_dump()


def task_design_node(state: dict) -> dict:
    agent = AgentState.model_validate(state)
    tasks = _execution_tasks(agent)
    if agent.current_task_index is None or agent.current_task_index > len(tasks):
        raise ValueError("current execution task missing")
    task = tasks[agent.current_task_index - 1]
    attempt = max(agent.current_attempt, 1)
    attempt_dir = _execution_task_folder(agent, task, agent.current_task_index) / "design" / f"attempt-{attempt:03d}"
    prompt_path = write_text(attempt_dir / "prompt.md", _build_execution_prompt(agent, task, "design", attempt_dir))
    llm = create_llm(LLMConfig.model_validate(agent.llm))
    invoke_with_agent_tools(
        llm,
        prompt_path.read_text(encoding="utf-8"),
        project_root=agent.project_root,
        run_dir=agent.run_dir,
        state_name=f"execution/{_safe_task_folder(agent.current_task_index, agent.current_task_id)}/design/attempt-{attempt:03d}",
        allow_empty_response=True,
    )
    tool_log = attempt_dir / "tool_calls.jsonl"
    if not tool_log.exists() or not tool_log.read_text(encoding="utf-8").strip():
        raise RuntimeError("design child produced no tool activity")
    write_json(attempt_dir / "result.json", {"status": "completed", "prompt_file": str(prompt_path)})
    agent.current_child_state = "test"
    agent.current_state = "task_test"
    _write_current_execution_task(agent, task, agent.current_task_index)
    agent.add_compact_message(f"design child completed for {agent.current_task_id}; starting test child")
    return agent.model_dump()


def task_test_node(state: dict) -> dict:
    agent = AgentState.model_validate(state)
    tasks = _execution_tasks(agent)
    if agent.current_task_index is None or agent.current_task_index > len(tasks):
        raise ValueError("current execution task missing")
    task = tasks[agent.current_task_index - 1]
    attempt = max(agent.current_attempt, 1)
    attempt_dir = _execution_task_folder(agent, task, agent.current_task_index) / "test" / f"attempt-{attempt:03d}"
    prompt_path = write_text(attempt_dir / "prompt.md", _build_execution_prompt(agent, task, "test", attempt_dir))
    llm = create_llm(LLMConfig.model_validate(agent.llm))
    output = invoke_with_agent_tools(
        llm,
        prompt_path.read_text(encoding="utf-8"),
        project_root=agent.project_root,
        run_dir=agent.run_dir,
        state_name=f"execution/{_safe_task_folder(agent.current_task_index, agent.current_task_id)}/test/attempt-{attempt:03d}",
        allow_empty_response=True,
    )
    result_path = attempt_dir / "result.json"
    status, reason = _parse_test_status(output, result_path)
    result_data: dict[str, object] = {}
    if result_path.exists():
        try:
            loaded_result = json.loads(result_path.read_text(encoding="utf-8"))
            if isinstance(loaded_result, dict):
                result_data = loaded_result
        except json.JSONDecodeError:
            result_data = {}
    result_data.setdefault("status", status)
    result_data.setdefault("reason", reason)
    result_data.setdefault("output", output)
    result_data.setdefault("task_id", str(agent.current_task_id))
    result_data.setdefault("attempt", attempt)
    result_path = write_json(result_path, result_data)
    if status == "fail":
        failure_path = write_text(
            attempt_dir / "latest_failure.md",
            f"task_id: {agent.current_task_id}\nreason: {reason}\n\n{output}\n",
        )
        agent.latest_test_failure_file = failure_path
        if attempt >= agent.max_task_attempts:
            agent.failed_task_id = str(agent.current_task_id)
            agent.current_child_state = None
            agent.current_state = "done"
            _write_current_execution_task(agent, task, agent.current_task_index)
            agent.add_compact_message(
                f"test failed for {agent.current_task_id} after {attempt} attempts; failure: {failure_path}"
            )
            return agent.model_dump()
        agent.current_attempt = attempt + 1
        agent.current_child_state = "design"
        agent.current_state = "task_design"
        _write_current_execution_task(agent, task, agent.current_task_index)
        agent.add_compact_message(f"test failed for {agent.current_task_id}; failure: {failure_path}")
        return agent.model_dump()
    agent.completed_task_ids.add(str(agent.current_task_id))
    agent.current_child_state = None
    agent.current_attempt = 0
    agent.latest_test_failure_file = None
    agent.current_state = "execute_tasks"
    _write_current_execution_task(agent, task, agent.current_task_index)
    agent.add_compact_message(f"test passed for {agent.current_task_id}; task closed")
    return agent.model_dump()
