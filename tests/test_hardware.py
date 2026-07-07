from pathlib import Path

from embedded_agent.hardware import HardwareAdapter, HardwareConfig
from embedded_agent.state import AcceptanceCheck, PlanTask


class FakeRunner:
    def __init__(self, codes):
        self.codes = list(codes)
        self.commands = []

    def __call__(self, command, timeout, cwd=None):
        self.commands.append((command, timeout, cwd))
        code = self.codes.pop(0) if self.codes else 0
        return code, f"out {command}", ""


def code_task():
    return PlanTask(
        id="task-1",
        title="Implement LED blink",
        kind="code",
        objective="Add a complete LED blink module wired into main.",
        dependencies=[],
        target_files=["src/main.c"],
        acceptance=[
            AcceptanceCheck(kind="build", command="cmake --build build"),
            AcceptanceCheck(kind="flash", command="pyocd flash firmware.elf"),
            AcceptanceCheck(kind="serial", expected="BLINK OK"),
        ],
    )


def test_hardware_verification_runs_build_flash_and_serial(tmp_path):
    runner = FakeRunner([0, 0])
    adapter = HardwareAdapter(
        HardwareConfig(
            build_command="cmake --build build",
            flash_command="pyocd flash firmware.elf",
            serial_port="COM7",
            project_root=tmp_path,
            serial_baudrate=115200,
            serial_timeout_sec=1,
        ),
        runner=runner,
        serial_reader=lambda *_args, **_kwargs: "boot\nBLINK OK\n",
    )

    result = adapter.verify_task(code_task(), tmp_path)

    assert result.ok is True
    assert [(item[0], item[2]) for item in runner.commands] == [
        ("cmake --build build", tmp_path),
        ("pyocd flash firmware.elf", tmp_path),
    ]
    assert (tmp_path / "attempts.jsonl").exists()


def test_hardware_commands_default_to_configured_project_root(tmp_path):
    runner = FakeRunner([0, 0])
    adapter = HardwareAdapter(
        HardwareConfig(
            build_command="cmake --build build",
            flash_command="pyocd flash firmware.elf",
            serial_port="COM7",
            project_root=tmp_path,
        ),
        runner=runner,
        serial_reader=lambda *_args, **_kwargs: "BLINK OK\n",
    )

    result = adapter.verify_task(code_task(), tmp_path)

    assert result.ok is True
    assert [(item[0], item[2]) for item in runner.commands] == [
        ("cmake --build build", tmp_path),
        ("pyocd flash firmware.elf", tmp_path),
    ]


def test_retry_stops_after_ten_failed_attempts(tmp_path):
    runner = FakeRunner([1] * 20)
    adapter = HardwareAdapter(
        HardwareConfig(
            build_command="cmake --build build",
            flash_command="pyocd flash firmware.elf",
            serial_port="COM7",
        ),
        runner=runner,
        serial_reader=lambda *_args, **_kwargs: "",
    )

    result = adapter.verify_with_retries(code_task(), tmp_path)

    assert result.ok is False
    assert result.attempt == 10
    assert len(runner.commands) == 10
    assert "stopped after 10 attempts" in (Path(tmp_path) / "latest_failure.md").read_text()
