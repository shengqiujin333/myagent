from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path
from typing import Callable

import serial
from serial.tools import list_ports


CommandRunner = Callable[..., str]
TOOL_OUTPUT_CHARS = 12000


def _tool_schema(name: str, description: str, properties: dict[str, object], required: list[str] | None = None) -> dict[str, object]:
    parameters: dict[str, object] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        parameters["required"] = required
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": parameters,
        },
    }


VERIFICATION_TOOL_SCHEMAS = [
    _tool_schema(
        "install_system_package",
        "Install an allowlisted native tool with the system package manager declared by the verification environment.",
        {
            "package": {"type": "string", "description": "Logical package name declared in verification_env."},
            "reason": {"type": "string", "description": "Why this package is required for the current work."},
        },
        ["package", "reason"],
    ),
    _tool_schema(
        "install_python_package",
        "Install one or more Python packages allowed by the verification environment into its configured Python runtime.",
        {"packages": {"type": "array", "items": {"type": "string"}, "minItems": 1}},
        ["packages"],
    ),
    _tool_schema(
        "serial_list_ports",
        "List serial ports with device descriptions, hardware IDs, VID/PID, and serial numbers for port negotiation.",
        {},
    ),
    _tool_schema(
        "serial_capture",
        "Capture raw serial data for a bounded duration and persist the complete capture in the current run directory.",
        {
            "port": {"type": "string"},
            "baudrate": {"type": "integer", "minimum": 1},
            "duration_sec": {"type": "number", "exclusiveMinimum": 0},
        },
        ["port", "baudrate", "duration_sec"],
    ),
    _tool_schema(
        "serial_exchange",
        "Write text or hexadecimal bytes to a serial port and return the bounded response.",
        {
            "port": {"type": "string"},
            "baudrate": {"type": "integer", "minimum": 1},
            "send_text": {"type": "string"},
            "send_hex": {"type": "string"},
            "read_timeout_sec": {"type": "number", "exclusiveMinimum": 0},
        },
        ["port", "baudrate", "read_timeout_sec"],
    ),
    _tool_schema(
        "mdk_build",
        "Build or rebuild the configured Keil MDK project and return the UV4 exit code and build log.",
        {"action": {"type": "string", "enum": ["build", "rebuild"]}},
        ["action"],
    ),
    _tool_schema(
        "openocd_flash",
        "Flash and verify the configured firmware through the configured CMSIS-DAP probe and OpenOCD target.",
        {"firmware_path": {"type": "string", "description": "Optional target-project-relative ELF/AXF path."}},
    ),
    _tool_schema("openocd_reset", "Reset the configured target and let it run through OpenOCD.", {}),
    _tool_schema(
        "openocd_gdb_server",
        "Start a bounded-lifetime OpenOCD GDB server in the background and persist its log in the current run directory.",
        {"startup_timeout_sec": {"type": "number", "exclusiveMinimum": 0}},
    ),
    _tool_schema("openocd_stop", "Stop the OpenOCD GDB server started for the current run.", {}),
    _tool_schema(
        "gdb_batch",
        "Run non-interactive GNU Arm GDB commands against the configured firmware, optionally connecting to OpenOCD.",
        {
            "commands": {"type": "array", "items": {"type": "string"}, "minItems": 1},
            "connect_openocd": {"type": "boolean"},
            "firmware_path": {"type": "string"},
        },
        ["commands"],
    ),
]


_VERIFICATION_TOOL_NAMES = {str(schema["function"]["name"]) for schema in VERIFICATION_TOOL_SCHEMAS}


def is_verification_tool(name: str) -> bool:
    return name in _VERIFICATION_TOOL_NAMES


def _mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"verification_env is missing {label}")
    return value


def _section(root: dict[str, object], *keys: str) -> dict[str, object]:
    current: object = root
    traversed: list[str] = []
    for key in keys:
        traversed.append(key)
        current = _mapping(current, ".".join(traversed)).get(key)
    return _mapping(current, ".".join(keys))


def _ps_quote(value: object) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _ps_command(executable: object, *args: object) -> str:
    return "& " + " ".join(_ps_quote(item) for item in (executable, *args))


def _exit_code(output: str) -> int:
    match = re.search(r"^exit_code=(-?\d+)", output)
    return int(match.group(1)) if match else 1


def _run(
    runner: CommandRunner,
    command: str,
    *,
    cwd: Path,
    timeout_sec: float,
) -> str:
    return runner(command, cwd=cwd, timeout_sec=timeout_sec, output_chars=TOOL_OUTPUT_CHARS)


def _project_path(project_root: Path, raw_path: object, *, must_exist: bool = False) -> Path:
    candidate = Path(str(raw_path))
    if not candidate.is_absolute():
        candidate = project_root / candidate
    resolved = candidate.resolve()
    root = project_root.resolve()
    if resolved != root and root not in resolved.parents:
        raise ValueError(f"configured path is outside target project: {raw_path}")
    if must_exist and not resolved.exists():
        raise ValueError(f"configured target path does not exist: {resolved}")
    return resolved


def _validate_package_name(package: object) -> str:
    value = str(package).strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]+(?:==[A-Za-z0-9_.+-]+)?", value):
        raise ValueError(f"invalid package name: {package}")
    return value


def _install_system_package(
    args: dict[str, object],
    env: dict[str, object],
    project_root: Path,
    runner: CommandRunner,
) -> str:
    manager = _section(env, "software", "system_package_manager")
    policy = _mapping(manager.get("package_install"), "software.system_package_manager.package_install")
    if policy.get("policy") != "allow":
        raise ValueError("system package installation is not allowed by verification_env")
    packages = _mapping(manager.get("packages"), "software.system_package_manager.packages")
    logical_name = str(args.get("package") or "").strip()
    package_config = packages.get(logical_name)
    if not isinstance(package_config, dict):
        raise ValueError(f"system package is not declared in verification_env: {logical_name}")
    package_id = _validate_package_name(package_config.get("package") or logical_name)
    timeout = float(policy.get("timeout_sec") or 600)
    install = _ps_command(manager.get("executable") or "choco", "install", package_id, "-y", "--no-progress")
    install_output = _run(runner, install, cwd=project_root, timeout_sec=timeout)
    if _exit_code(install_output) != 0:
        return install_output
    version_command = str(package_config.get("version_command") or "").strip()
    if not version_command:
        return install_output
    verify_output = _run(runner, version_command, cwd=project_root, timeout_sec=30)
    return (
        f"exit_code={_exit_code(verify_output)}\nstdout:\ninstallation:\n{install_output}\n"
        f"verification:\n{verify_output}\nstderr:\n"
    )


def _install_python_package(
    args: dict[str, object],
    env: dict[str, object],
    project_root: Path,
    runner: CommandRunner,
) -> str:
    python = _section(env, "software", "python")
    policy = _mapping(python.get("package_install"), "software.python.package_install")
    if policy.get("policy") != "allow":
        raise ValueError("Python package installation is not allowed by verification_env")
    raw_packages = args.get("packages")
    if not isinstance(raw_packages, list) or not raw_packages:
        raise ValueError("packages must be a non-empty list")
    packages = [_validate_package_name(item) for item in raw_packages]
    command = _ps_command(python.get("executable") or "python", "-m", "pip", "install", *packages)
    return _run(runner, command, cwd=project_root, timeout_sec=float(policy.get("timeout_sec") or 600))


def _serial_list_ports() -> str:
    ports = [
        {
            "port": port.device,
            "description": port.description,
            "hwid": port.hwid,
            "vid": port.vid,
            "pid": port.pid,
            "serial_number": port.serial_number,
        }
        for port in list_ports.comports()
    ]
    return f"exit_code=0\nstdout:\n{json.dumps(ports, ensure_ascii=False, indent=2)}\nstderr:\n"


def _serial_settings(args: dict[str, object]) -> tuple[str, int]:
    port = str(args.get("port") or "").strip()
    baudrate = int(args.get("baudrate") or 0)
    if not re.fullmatch(r"COM\d+", port, re.IGNORECASE):
        raise ValueError(f"invalid Windows serial port: {port}")
    if baudrate <= 0:
        raise ValueError("baudrate must be positive")
    return port, baudrate


def _serial_capture(args: dict[str, object], run_dir: Path) -> str:
    port, baudrate = _serial_settings(args)
    duration = float(args.get("duration_sec") or 0)
    if duration <= 0 or duration > 300:
        raise ValueError("duration_sec must be greater than 0 and at most 300")
    output_dir = run_dir / "verification_tools"
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.time_ns()
    capture_path = output_dir / f"serial-capture-{stamp}.bin"
    captured = bytearray()
    deadline = time.monotonic() + duration
    with serial.Serial(port=port, baudrate=baudrate, timeout=min(duration, 0.1)) as connection:
        while time.monotonic() < deadline:
            waiting = int(connection.in_waiting)
            if waiting:
                captured.extend(connection.read(waiting))
            else:
                time.sleep(min(0.01, max(0.0, deadline - time.monotonic())))
    capture_path.write_bytes(captured)
    preview = bytes(captured[-2000:]).decode("utf-8", errors="replace")
    return (
        f"exit_code=0\nstdout:\ncapture_path={capture_path}\nbytes_received={len(captured)}\n"
        f"preview:\n{preview}\nstderr:\n"
    )


def _serial_exchange(args: dict[str, object], run_dir: Path) -> str:
    port, baudrate = _serial_settings(args)
    timeout = float(args.get("read_timeout_sec") or 0)
    if timeout <= 0 or timeout > 300:
        raise ValueError("read_timeout_sec must be greater than 0 and at most 300")
    has_text = "send_text" in args
    has_hex = "send_hex" in args
    if has_text == has_hex:
        raise ValueError("provide exactly one of send_text or send_hex")
    if has_hex:
        compact_hex = re.sub(r"\s+", "", str(args.get("send_hex") or ""))
        if not compact_hex or len(compact_hex) % 2 or not re.fullmatch(r"[0-9A-Fa-f]+", compact_hex):
            raise ValueError("send_hex must contain complete hexadecimal bytes")
        payload = bytes.fromhex(compact_hex)
    else:
        payload = str(args.get("send_text") or "").encode("utf-8")
    response = bytearray()
    deadline = time.monotonic() + timeout
    with serial.Serial(port=port, baudrate=baudrate, timeout=min(timeout, 0.1)) as connection:
        connection.write(payload)
        connection.flush()
        while time.monotonic() < deadline:
            waiting = int(connection.in_waiting)
            if waiting:
                response.extend(connection.read(waiting))
            else:
                time.sleep(min(0.01, max(0.0, deadline - time.monotonic())))
    output_dir = run_dir / "verification_tools"
    output_dir.mkdir(parents=True, exist_ok=True)
    response_path = output_dir / f"serial-exchange-{time.time_ns()}.bin"
    response_path.write_bytes(response)
    return (
        f"exit_code=0\nstdout:\nbytes_sent={len(payload)}\nbytes_received={len(response)}\n"
        f"response_path={response_path}\n"
        f"response_hex={bytes(response).hex(' ')}\nresponse_text={bytes(response).decode('utf-8', errors='replace')}\n"
        "stderr:\n"
    )


def _mdk_build(
    args: dict[str, object],
    env: dict[str, object],
    project_root: Path,
    runner: CommandRunner,
) -> str:
    mdk = _section(env, "software", "mdk")
    action = str(args.get("action") or "")
    action_flag = {"build": "-b", "rebuild": "-r"}.get(action)
    if not action_flag:
        raise ValueError("mdk_build action must be build or rebuild")
    project = _project_path(project_root, mdk.get("project_file"), must_exist=True)
    log_path = _project_path(project_root, mdk.get("log_file"))
    log_path.parent.mkdir(parents=True, exist_ok=True)
    command = _ps_command(mdk.get("uv4_exe"), "-j0", action_flag, project, "-o", log_path)
    output = _run(runner, command, cwd=project_root, timeout_sec=float(mdk.get("timeout_sec") or 300))
    if not log_path.exists():
        return output
    build_log = log_path.read_text(encoding="utf-8", errors="replace")[-TOOL_OUTPUT_CHARS:]
    return f"{output}\nbuild_log_path={log_path}\nbuild_log:\n{build_log}"


def _openocd_config(env: dict[str, object]) -> dict[str, object]:
    cmsis_dap = _section(env, "hardware", "cmsis_dap")
    return _mapping(cmsis_dap.get("openocd"), "hardware.cmsis_dap.openocd")


def _openocd_base(openocd: dict[str, object]) -> tuple[object, list[object]]:
    args: list[object] = ["-f", openocd.get("interface_cfg")]
    backend = str(openocd.get("cmsis_dap_backend") or "").strip()
    if backend:
        if backend not in {"hid", "usb_bulk"}:
            raise ValueError(f"unsupported CMSIS-DAP backend: {backend}")
        args.extend(["-c", f"cmsis-dap backend {backend}"])
    args.extend(["-f", openocd.get("target_cfg")])
    return openocd.get("executable") or "openocd", args


def _openocd_action(
    name: str,
    args: dict[str, object],
    env: dict[str, object],
    project_root: Path,
    run_dir: Path,
    runner: CommandRunner,
) -> str:
    openocd = _openocd_config(env)
    executable, base_args = _openocd_base(openocd)
    timeout = float(openocd.get("timeout_sec") or 120)
    if name == "openocd_flash":
        firmware = _project_path(
            project_root,
            args.get("firmware_path") or openocd.get("firmware_path"),
            must_exist=True,
        )
        command = _ps_command(executable, *base_args, "-c", f'program "{firmware}" verify reset exit')
        return _run(runner, command, cwd=project_root, timeout_sec=timeout)
    if name == "openocd_reset":
        command = _ps_command(executable, *base_args, "-c", "init; reset run; shutdown")
        return _run(runner, command, cwd=project_root, timeout_sec=timeout)
    server_dir = run_dir / "verification_tools"
    server_dir.mkdir(parents=True, exist_ok=True)
    pid_path = server_dir / "openocd.pid"
    stdout_path = server_dir / "openocd.stdout.log"
    stderr_path = server_dir / "openocd.stderr.log"
    if name == "openocd_gdb_server":
        startup_timeout = float(args.get("startup_timeout_sec") or 3)
        stdout_handle = stdout_path.open("w", encoding="utf-8")
        stderr_handle = stderr_path.open("w", encoding="utf-8")
        try:
            process = subprocess.Popen(
                [str(executable), *(str(item) for item in base_args)],
                cwd=project_root,
                stdout=stdout_handle,
                stderr=stderr_handle,
                text=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        finally:
            stdout_handle.close()
            stderr_handle.close()
        pid_path.write_text(str(process.pid), encoding="utf-8")
        time.sleep(startup_timeout)
        if process.poll() is not None:
            return (
                f"exit_code={process.returncode or 1}\nstdout:\n"
                f"{stdout_path.read_text(encoding='utf-8', errors='replace')[-TOOL_OUTPUT_CHARS:]}\n"
                f"stderr:\n{stderr_path.read_text(encoding='utf-8', errors='replace')[-TOOL_OUTPUT_CHARS:]}"
            )
        return f"exit_code=0\nstdout:\nopenocd_pid={process.pid}\nstderr:\n"
    if name == "openocd_stop":
        if not pid_path.exists():
            return "exit_code=0\nstdout:\nno OpenOCD server recorded for this run\nstderr:\n"
        command = (
            f"$pidValue = Get-Content -LiteralPath {_ps_quote(pid_path)}; "
            "Stop-Process -Id $pidValue -Force -ErrorAction SilentlyContinue; "
            f"Remove-Item -LiteralPath {_ps_quote(pid_path)} -Force -ErrorAction SilentlyContinue"
        )
        return _run(runner, command, cwd=project_root, timeout_sec=15)
    raise ValueError(f"unsupported OpenOCD action: {name}")


def _gdb_batch(
    args: dict[str, object],
    env: dict[str, object],
    project_root: Path,
    runner: CommandRunner,
) -> str:
    cmsis_dap = _section(env, "hardware", "cmsis_dap")
    openocd = _mapping(cmsis_dap.get("openocd"), "hardware.cmsis_dap.openocd")
    gdb = _mapping(cmsis_dap.get("gdb"), "hardware.cmsis_dap.gdb")
    commands = args.get("commands")
    if not isinstance(commands, list) or not commands or not all(isinstance(item, str) and item.strip() for item in commands):
        raise ValueError("gdb_batch commands must be a non-empty string list")
    firmware = _project_path(
        project_root,
        args.get("firmware_path") or openocd.get("firmware_path"),
        must_exist=True,
    )
    gdb_args: list[object] = ["--batch", firmware]
    if bool(args.get("connect_openocd")):
        gdb_args.extend(["-ex", f"target extended-remote {gdb.get('server_address') or 'localhost:3333'}"])
    for command in commands:
        gdb_args.extend(["-ex", command])
    command_text = _ps_command(gdb.get("executable") or "arm-none-eabi-gdb", *gdb_args)
    return _run(runner, command_text, cwd=project_root, timeout_sec=float(gdb.get("timeout_sec") or 120))


def run_verification_tool(
    name: str,
    args: dict[str, object],
    *,
    verification_env: dict[str, object],
    project_root: Path,
    run_dir: Path,
    command_runner: CommandRunner,
) -> str:
    if name == "install_system_package":
        return _install_system_package(args, verification_env, project_root, command_runner)
    if name == "install_python_package":
        return _install_python_package(args, verification_env, project_root, command_runner)
    if name == "serial_list_ports":
        return _serial_list_ports()
    if name == "serial_capture":
        return _serial_capture(args, run_dir)
    if name == "serial_exchange":
        return _serial_exchange(args, run_dir)
    if name == "mdk_build":
        return _mdk_build(args, verification_env, project_root, command_runner)
    if name in {"openocd_flash", "openocd_reset", "openocd_gdb_server", "openocd_stop"}:
        return _openocd_action(name, args, verification_env, project_root, run_dir, command_runner)
    if name == "gdb_batch":
        return _gdb_batch(args, verification_env, project_root, command_runner)
    raise ValueError(f"unknown verification tool: {name}")


def cleanup_verification_processes(
    *,
    project_root: Path,
    run_dir: Path,
    command_runner: CommandRunner,
) -> None:
    pid_path = run_dir / "verification_tools" / "openocd.pid"
    if not pid_path.exists():
        return
    command = (
        f"$pidValue = Get-Content -LiteralPath {_ps_quote(pid_path)}; "
        "Stop-Process -Id $pidValue -Force -ErrorAction SilentlyContinue; "
        f"Remove-Item -LiteralPath {_ps_quote(pid_path)} -Force -ErrorAction SilentlyContinue"
    )
    _run(command_runner, command, cwd=project_root, timeout_sec=15)
