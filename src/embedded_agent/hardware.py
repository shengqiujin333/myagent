from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Callable

from pydantic import BaseModel

from embedded_agent.safe_shell import run_command
from embedded_agent.state import PlanTask


CommandRunner = Callable[[str, int, Path | None], tuple[int, str, str]]
SerialReader = Callable[[str, int, int], str]


class HardwareConfig(BaseModel):
    build_command: str
    flash_command: str
    serial_port: str
    project_root: Path | None = None
    serial_baudrate: int = 115200
    serial_timeout_sec: int = 30
    build_timeout_sec: int = 120
    flash_timeout_sec: int = 120
    host_test_command: str | None = None
    host_test_timeout_sec: int = 120
    max_attempts: int = 10


class VerificationResult(BaseModel):
    ok: bool
    attempt: int
    reason: str
    serial_output: str = ""


def read_serial(port: str, baudrate: int, timeout_sec: int) -> str:
    import serial

    deadline = time.time() + timeout_sec
    chunks: list[str] = []
    with serial.Serial(port=port, baudrate=baudrate, timeout=0.25) as ser:
        while time.time() < deadline:
            data = ser.read(1024)
            if data:
                chunks.append(data.decode(errors="replace"))
    return "".join(chunks)


class HardwareAdapter:
    def __init__(
        self,
        config: HardwareConfig,
        runner: CommandRunner = run_command,
        serial_reader: SerialReader = read_serial,
    ) -> None:
        self.config = config
        self.runner = runner
        self.serial_reader = serial_reader

    def verify_with_retries(self, task: PlanTask, artifact_dir: Path) -> VerificationResult:
        artifact_dir.mkdir(parents=True, exist_ok=True)
        latest = VerificationResult(ok=False, attempt=0, reason="not started")
        for attempt in range(1, self.config.max_attempts + 1):
            latest = self.verify_task(task, artifact_dir, attempt=attempt)
            if latest.ok:
                return latest
        reason = f"stopped after {self.config.max_attempts} attempts: {latest.reason}"
        failure = artifact_dir / "latest_failure.md"
        failure.write_text(reason, encoding="utf-8")
        return VerificationResult(ok=False, attempt=self.config.max_attempts, reason=reason)

    def verify_task(self, task: PlanTask, artifact_dir: Path, attempt: int = 1) -> VerificationResult:
        artifact_dir.mkdir(parents=True, exist_ok=True)
        checks = {check.kind: check for check in task.acceptance}

        build_code, build_out, build_err = self.runner(
            checks.get("build").command if checks.get("build") and checks["build"].command else self.config.build_command,
            self.config.build_timeout_sec,
            self.config.project_root,
        )
        if build_code != 0:
            return self._record(artifact_dir, attempt, False, "build failed", build_out, build_err)

        flash_code, flash_out, flash_err = self.runner(
            checks.get("flash").command if checks.get("flash") and checks["flash"].command else self.config.flash_command,
            self.config.flash_timeout_sec,
            self.config.project_root,
        )
        if flash_code != 0:
            return self._record(artifact_dir, attempt, False, "flash failed", flash_out, flash_err)

        serial_output = self.serial_reader(
            self.config.serial_port,
            self.config.serial_baudrate,
            self.config.serial_timeout_sec,
        )
        serial_expected = checks["serial"].expected if "serial" in checks else None
        if serial_expected and serial_expected not in serial_output:
            return self._record(
                artifact_dir,
                attempt,
                False,
                f"serial output missing expected text: {serial_expected}",
                serial_output,
                "",
                serial_output,
            )

        if self.config.host_test_command or "host_test" in checks:
            command = checks["host_test"].command if "host_test" in checks and checks["host_test"].command else self.config.host_test_command
            if command:
                code, out, err = self.runner(command, self.config.host_test_timeout_sec, self.config.project_root)
                if code != 0:
                    return self._record(artifact_dir, attempt, False, "host test failed", out, err, serial_output)

        return self._record(artifact_dir, attempt, True, "verification passed", "", "", serial_output)

    def _record(
        self,
        artifact_dir: Path,
        attempt: int,
        ok: bool,
        reason: str,
        stdout: str,
        stderr: str,
        serial_output: str = "",
    ) -> VerificationResult:
        result = VerificationResult(ok=ok, attempt=attempt, reason=reason, serial_output=serial_output)
        record = {
            "attempt": attempt,
            "ok": ok,
            "reason": reason,
            "stdout_tail": stdout[-2000:],
            "stderr_tail": stderr[-2000:],
            "serial_tail": serial_output[-2000:],
        }
        with (artifact_dir / "attempts.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        (artifact_dir / "result.json").write_text(result.model_dump_json(indent=2), encoding="utf-8")
        if not ok:
            (artifact_dir / "latest_failure.md").write_text(reason, encoding="utf-8")
        return result
