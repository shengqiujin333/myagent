from __future__ import annotations

import re
import subprocess
from pathlib import Path


class CommandBlocked(ValueError):
    """Raised when a discovery command can hang, recurse too broadly, or turn interactive."""


FORBIDDEN_PATTERNS = (
    r"\bget-childitem\b.*(?:^|\s)-recurse\b",
    r"\bgci\b.*(?:^|\s)-recurse\b",
    r"\bdir\b.*\b/s\b",
    r"\bgrep\b.*\s-r\b",
    r"\bgrep\b.*\s-R\b",
    r"^\s*find\s+",
    r"\bvim\b|\bnvim\b|\bnano\b|\bemacs\b",
    r"\bpython\b.*\s-i\b",
    r"\bnode\b.*\s-i\b",
)


def ensure_safe_discovery_command(command: str) -> None:
    normalized = command.strip()
    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, normalized, flags=re.IGNORECASE):
            raise CommandBlocked(f"blocked discovery command: {command}")


def run_command(command: str, timeout: int, cwd: Path | None = None) -> tuple[int, str, str]:
    completed = subprocess.run(
        command,
        shell=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=timeout,
        cwd=cwd,
    )
    return completed.returncode, completed.stdout, completed.stderr
