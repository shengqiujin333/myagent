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
