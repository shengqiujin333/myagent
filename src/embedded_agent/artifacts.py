from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


def new_run_dir(run_root: Path) -> Path:
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = run_root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def write_text(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def write_json(path: Path, data: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def append_artifact(run_dir: Path, artifact_path: Path, description: str) -> Path:
    index_path = run_dir / "artifacts_index.md"
    try:
        relative = artifact_path.relative_to(run_dir)
    except ValueError:
        relative = artifact_path
    if not index_path.exists():
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_text(
            "# Artifacts Index\n\n本文件记录本次运行中各阶段产出的文件路径，供 execute_tasks 阶段自动组装进 prompt。\n\n",
            encoding="utf-8",
        )
    line = f"- `{relative.as_posix()}` - {description}\n"
    with index_path.open("a", encoding="utf-8") as handle:
        handle.write(line)
    return index_path


def read_artifacts_index(run_dir: Path) -> str:
    index_path = run_dir / "artifacts_index.md"
    if not index_path.exists():
        return ""
    return index_path.read_text(encoding="utf-8")
