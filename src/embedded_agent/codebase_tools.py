from __future__ import annotations

import json
import subprocess


CODEBASE_MEMORY_TOOL_TIMEOUT_SEC = 60
CODEBASE_MEMORY_TOOL_OUTPUT_CHARS = 12000


def _tool_schema(name: str, description: str, properties: dict[str, object], required: list[str]) -> dict[str, object]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }


PROJECT_PROPERTY = {
    "type": "string",
    "description": "codebase-memory project id, for example C-Users-123-Desktop-neizu-tasknew-battery_re",
}


CODEBASE_MEMORY_TOOL_SCHEMAS = [
    _tool_schema("codebase_memory_list_projects", "List indexed codebase-memory projects.", {}, []),
    _tool_schema(
        "codebase_memory_index_repository",
        "Index or refresh a repository in codebase-memory.",
        {"repo_path": {"type": "string", "description": "Repository path to index."}},
        ["repo_path"],
    ),
    _tool_schema(
        "codebase_memory_index_status",
        "Get index status for a codebase-memory project.",
        {"project": PROJECT_PROPERTY},
        ["project"],
    ),
    _tool_schema(
        "codebase_memory_get_architecture",
        "Get architecture summary for a codebase-memory project.",
        {"project": PROJECT_PROPERTY},
        ["project"],
    ),
    _tool_schema(
        "codebase_memory_search_code",
        "Search indexed source text.",
        {
            "project": PROJECT_PROPERTY,
            "pattern": {"type": "string", "description": "Search pattern."},
            "limit": {"type": "integer", "description": "Maximum number of results."},
        },
        ["project", "pattern"],
    ),
    _tool_schema(
        "codebase_memory_search_graph",
        "Search code graph nodes by name pattern and optional label.",
        {
            "project": PROJECT_PROPERTY,
            "name_pattern": {"type": "string", "description": "Regex name pattern."},
            "label": {"type": "string", "description": "Optional graph label, for example Function."},
            "limit": {"type": "integer", "description": "Maximum number of results."},
        },
        ["project", "name_pattern"],
    ),
    _tool_schema(
        "codebase_memory_get_graph_schema",
        "Get graph schema for a codebase-memory project.",
        {"project": PROJECT_PROPERTY},
        ["project"],
    ),
    _tool_schema(
        "codebase_memory_query_graph",
        "Run a read-only Cypher query against the code graph.",
        {
            "project": PROJECT_PROPERTY,
            "query": {"type": "string", "description": "Cypher query."},
        },
        ["project", "query"],
    ),
    _tool_schema(
        "codebase_memory_trace_path",
        "Trace graph paths between two qualified names.",
        {
            "project": PROJECT_PROPERTY,
            "from": {"type": "string", "description": "Source qualified name."},
            "to": {"type": "string", "description": "Target qualified name."},
            "limit": {"type": "integer", "description": "Maximum number of paths."},
        },
        ["project", "from", "to"],
    ),
    _tool_schema(
        "codebase_memory_detect_changes",
        "Detect repository changes for a codebase-memory project.",
        {"project": PROJECT_PROPERTY},
        ["project"],
    ),
    _tool_schema(
        "codebase_memory_get_code_snippet",
        "Get the source snippet for an exact qualified name.",
        {
            "project": PROJECT_PROPERTY,
            "qualified_name": {"type": "string", "description": "Exact qualified name."},
        },
        ["project", "qualified_name"],
    ),
]


TOOL_TO_CLI = {
    "codebase_memory_list_projects": ("list_projects", []),
    "codebase_memory_index_repository": ("index_repository", ["repo_path"]),
    "codebase_memory_index_status": ("index_status", ["project"]),
    "codebase_memory_get_architecture": ("get_architecture", ["project"]),
    "codebase_memory_search_code": ("search_code", ["project", "pattern", "limit"]),
    "codebase_memory_search_graph": ("search_graph", ["project", "name_pattern", "label", "limit"]),
    "codebase_memory_get_graph_schema": ("get_graph_schema", ["project"]),
    "codebase_memory_query_graph": ("query_graph", ["project", "query"]),
    "codebase_memory_trace_path": ("trace_path", ["project", "from", "to", "limit"]),
    "codebase_memory_detect_changes": ("detect_changes", ["project"]),
    "codebase_memory_get_code_snippet": ("get_code_snippet", ["project", "qualified_name"]),
}


def is_codebase_memory_tool(name: str) -> bool:
    return name in TOOL_TO_CLI


def run_codebase_memory_tool(name: str, args: dict[str, object]) -> str:
    if name not in TOOL_TO_CLI:
        raise ValueError(f"unknown codebase-memory tool: {name}")
    cli_name, keys = TOOL_TO_CLI[name]
    payload = {key: args[key] for key in keys if key in args and args[key] is not None}
    command = ["codebase-memory-mcp", "cli", cli_name]
    if payload:
        command.append(json.dumps(payload, ensure_ascii=False))
    completed = subprocess.run(
        command,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=CODEBASE_MEMORY_TOOL_TIMEOUT_SEC,
    )
    return (
        f"exit_code={completed.returncode}\n"
        "stdout:\n"
        f"{completed.stdout[-CODEBASE_MEMORY_TOOL_OUTPUT_CHARS:]}\n"
        "stderr:\n"
        f"{completed.stderr[-CODEBASE_MEMORY_TOOL_OUTPUT_CHARS:]}"
    )
