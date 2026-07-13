from __future__ import annotations

from pathlib import Path

import pytest

import embedded_agent.verification_tools as verification_tools


@pytest.fixture
def verification_env() -> dict[str, object]:
    return {
        "hardware": {
            "serial": {"default_baudrate": 115200, "timeout_sec": 30},
            "cmsis_dap": {
                "openocd": {
                    "executable": "openocd",
                    "cmsis_dap_backend": "hid",
                    "interface_cfg": "interface/cmsis-dap.cfg",
                    "target_cfg": "target/stm32g0x.cfg",
                    "firmware_path": "battery_re/MDK-ARM/battery_re/battery_re.axf",
                },
                "gdb": {"executable": "arm-none-eabi-gdb", "server_address": "localhost:3333"},
            },
        },
        "software": {
            "mdk": {
                "uv4_exe": "C:/Keil_v5/UV4/UV4.exe",
                "project_file": "battery_re/MDK-ARM/battery_re.uvprojx",
                "log_file": "battery_re/MDK-ARM/build_log.txt",
            },
            "python": {
                "executable": "python",
                "package_install": {"policy": "allow"},
            },
            "system_package_manager": {
                "executable": "choco",
                "package_install": {"policy": "allow", "timeout_sec": 600},
                "packages": {
                    "openocd": {
                        "package": "openocd",
                        "executable": "openocd",
                        "version_command": "openocd --version",
                    }
                },
            },
        },
    }


class RecordingRunner:
    def __init__(self):
        self.calls: list[tuple[str, Path, float]] = []

    def __call__(self, command: str, *, cwd: Path, timeout_sec: float, output_chars: int) -> str:
        self.calls.append((command, cwd, timeout_sec))
        return "exit_code=0\nstdout:\nok\nstderr:\n"


def test_install_system_package_uses_allowlisted_chocolatey_package(tmp_path, verification_env):
    runner = RecordingRunner()

    output = verification_tools.run_verification_tool(
        "install_system_package",
        {"package": "openocd", "reason": "flash target"},
        verification_env=verification_env,
        project_root=tmp_path,
        run_dir=tmp_path / "run",
        command_runner=runner,
    )

    assert output.startswith("exit_code=0")
    assert "choco" in runner.calls[0][0]
    assert "install" in runner.calls[0][0]
    assert "openocd" in runner.calls[0][0]
    assert "--no-progress" in runner.calls[0][0]
    assert runner.calls[0][2] == 600
    assert "openocd --version" in runner.calls[1][0]


def test_install_system_package_rejects_undeclared_package(tmp_path, verification_env):
    with pytest.raises(ValueError, match="not declared"):
        verification_tools.run_verification_tool(
            "install_system_package",
            {"package": "unapproved", "reason": "test"},
            verification_env=verification_env,
            project_root=tmp_path,
            run_dir=tmp_path / "run",
            command_runner=RecordingRunner(),
        )


def test_install_python_package_uses_configured_runtime(tmp_path, verification_env):
    runner = RecordingRunner()

    verification_tools.run_verification_tool(
        "install_python_package",
        {"packages": ["pyserial", "pytest"]},
        verification_env=verification_env,
        project_root=tmp_path,
        run_dir=tmp_path / "run",
        command_runner=runner,
    )

    assert runner.calls[0][0] == "& 'python' '-m' 'pip' 'install' 'pyserial' 'pytest'"


def test_mdk_build_resolves_project_and_log_paths(tmp_path, verification_env):
    project = tmp_path / "battery_re" / "MDK-ARM" / "battery_re.uvprojx"
    project.parent.mkdir(parents=True)
    project.write_text("project", encoding="utf-8")
    build_log = tmp_path / "battery_re" / "MDK-ARM" / "build_log.txt"
    build_log.write_text("0 Error(s), 0 Warning(s)", encoding="utf-8")
    runner = RecordingRunner()

    output = verification_tools.run_verification_tool(
        "mdk_build",
        {"action": "rebuild"},
        verification_env=verification_env,
        project_root=tmp_path,
        run_dir=tmp_path / "run",
        command_runner=runner,
    )

    command = runner.calls[0][0]
    assert "UV4.exe" in command
    assert "'-r'" in command
    assert str(project) in command
    assert str(build_log) in command
    assert "0 Error(s), 0 Warning(s)" in output


def test_openocd_flash_builds_configured_probe_command(tmp_path, verification_env):
    firmware = tmp_path / "battery_re" / "MDK-ARM" / "battery_re" / "battery_re.axf"
    firmware.parent.mkdir(parents=True)
    firmware.write_bytes(b"axf")
    runner = RecordingRunner()

    verification_tools.run_verification_tool(
        "openocd_flash",
        {},
        verification_env=verification_env,
        project_root=tmp_path,
        run_dir=tmp_path / "run",
        command_runner=runner,
    )

    command = runner.calls[0][0]
    assert "openocd" in command
    assert "interface/cmsis-dap.cfg" in command
    assert "target/stm32g0x.cfg" in command
    assert command.index("interface/cmsis-dap.cfg") < command.index("cmsis-dap backend hid")
    assert command.index("cmsis-dap backend hid") < command.index("target/stm32g0x.cfg")
    assert f'program "{firmware}" verify reset exit' in command


def test_openocd_reset_and_gdb_server_use_noninteractive_commands(tmp_path, verification_env):
    runner = RecordingRunner()

    verification_tools.run_verification_tool(
        "openocd_reset",
        {},
        verification_env=verification_env,
        project_root=tmp_path,
        run_dir=tmp_path / "run",
        command_runner=runner,
    )
    verification_tools.run_verification_tool(
        "openocd_gdb_server",
        {"startup_timeout_sec": 0.1},
        verification_env=verification_env,
        project_root=tmp_path,
        run_dir=tmp_path / "run",
        command_runner=runner,
    )

    assert "init; reset run; shutdown" in runner.calls[0][0]
    server_command = runner.calls[1][0]
    assert "Start-Process" in server_command
    assert "-WindowStyle Hidden" in server_command
    assert "Start-Sleep -Milliseconds 100" in server_command
    assert "openocd.pid" in server_command
    assert "openocd.stdout.log" in server_command


def test_gdb_batch_uses_configured_firmware_and_remote_target(tmp_path, verification_env):
    firmware = tmp_path / "battery_re" / "MDK-ARM" / "battery_re" / "battery_re.axf"
    firmware.parent.mkdir(parents=True)
    firmware.write_bytes(b"axf")
    runner = RecordingRunner()

    verification_tools.run_verification_tool(
        "gdb_batch",
        {"commands": ["monitor reset halt", "info registers"], "connect_openocd": True},
        verification_env=verification_env,
        project_root=tmp_path,
        run_dir=tmp_path / "run",
        command_runner=runner,
    )

    command = runner.calls[0][0]
    assert "arm-none-eabi-gdb" in command
    assert str(firmware) in command
    assert "target extended-remote localhost:3333" in command
    assert "monitor reset halt" in command
    assert "info registers" in command


def test_cleanup_stops_recorded_openocd_server(tmp_path):
    run_dir = tmp_path / "run"
    pid_path = run_dir / "verification_tools" / "openocd.pid"
    pid_path.parent.mkdir(parents=True)
    pid_path.write_text("4321", encoding="utf-8")
    runner = RecordingRunner()

    verification_tools.cleanup_verification_processes(
        project_root=tmp_path,
        run_dir=run_dir,
        command_runner=runner,
    )

    assert "Stop-Process" in runner.calls[0][0]
    assert "openocd.pid" in runner.calls[0][0]


class FakePort:
    device = "COM3"
    description = "CMSIS-DAP UART"
    hwid = "USB VID:PID=1234:5678"
    vid = 0x1234
    pid = 0x5678
    serial_number = "ABC"


class FakeSerial:
    response = b"READY\r\n"
    writes: list[bytes] = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.buffer = bytearray(self.response)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    @property
    def in_waiting(self):
        return len(self.buffer)

    def read(self, size):
        data = bytes(self.buffer[:size])
        del self.buffer[:size]
        return data

    def write(self, data):
        self.writes.append(data)
        return len(data)

    def flush(self):
        return None


def test_serial_tools_list_exchange_and_persist_capture(tmp_path, verification_env, monkeypatch):
    FakeSerial.writes = []
    monkeypatch.setattr(verification_tools.list_ports, "comports", lambda: [FakePort()])
    monkeypatch.setattr(verification_tools.serial, "Serial", FakeSerial)

    listed = verification_tools.run_verification_tool(
        "serial_list_ports",
        {},
        verification_env=verification_env,
        project_root=tmp_path,
        run_dir=tmp_path / "run",
        command_runner=RecordingRunner(),
    )
    exchanged = verification_tools.run_verification_tool(
        "serial_exchange",
        {"port": "COM3", "baudrate": 115200, "send_hex": "A5 01", "read_timeout_sec": 0.01},
        verification_env=verification_env,
        project_root=tmp_path,
        run_dir=tmp_path / "run",
        command_runner=RecordingRunner(),
    )
    captured = verification_tools.run_verification_tool(
        "serial_capture",
        {"port": "COM3", "baudrate": 115200, "duration_sec": 0.01},
        verification_env=verification_env,
        project_root=tmp_path,
        run_dir=tmp_path / "run",
        command_runner=RecordingRunner(),
    )

    assert '"port": "COM3"' in listed
    assert FakeSerial.writes == [b"\xA5\x01"]
    assert "READY" in exchanged
    assert "response_path=" in exchanged
    assert "capture_path=" in captured
    captures = list((tmp_path / "run" / "verification_tools").glob("serial-capture-*.bin"))
    exchanges = list((tmp_path / "run" / "verification_tools").glob("serial-exchange-*.bin"))
    assert len(captures) == 1
    assert len(exchanges) == 1
    assert captures[0].read_bytes() == b"READY\r\n"
    assert exchanges[0].read_bytes() == b"READY\r\n"
