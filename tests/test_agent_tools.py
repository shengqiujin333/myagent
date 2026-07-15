import subprocess
from pathlib import Path

import embedded_agent.agent_tools as agent_tools
from embedded_agent.artifacts import new_run_dir
from embedded_agent.agent_tools import AGENT_TOOL_SCHEMAS
from embedded_agent.agent_tools import MAX_TOOL_STEPS
from embedded_agent.agent_tools import _run_bash
from embedded_agent.agent_tools import _run_file_tool
from embedded_agent.agent_tools import invoke_with_agent_tools
from embedded_agent.agent_tools import run_powershell_command


class ToolCallingLLM:
    def __init__(self):
        self.bound_tools = None
        self.calls = 0

    def bind_tools(self, tools):
        self.bound_tools = tools
        return self

    def invoke(self, messages):
        self.calls += 1
        if self.calls == 1:
            class Response:
                content = ""
                tool_calls = [
                    {
                        "id": "read-1",
                        "name": "read_file",
                        "args": {"path": "input.txt"},
                    },
                    {
                        "id": "write-1",
                        "name": "write_file",
                        "args": {"path": "output.txt", "content": "generated"},
                    },
                ]

            return Response()

        class Response:
            content = "Finished after using shared tools."

        return Response()


class RepeatingFailedToolLLM:
    def __init__(self):
        self.calls = 0

    def bind_tools(self, _tools):
        return self

    def invoke(self, _messages):
        self.calls += 1
        if self.calls <= 3:
            class Response:
                content = ""
                tool_calls = [{"id": f"fail-{self.calls}", "name": "bash", "args": {"command": "bad-command"}}]

            return Response()

        class Response:
            content = "used another approach"

        return Response()


class VerificationToolLLM:
    def __init__(self):
        self.calls = 0

    def bind_tools(self, _tools):
        return self

    def invoke(self, _messages):
        self.calls += 1
        if self.calls == 1:
            class Response:
                content = ""
                tool_calls = [{"id": "ports-1", "name": "serial_list_ports", "args": {}}]

            return Response()

        class Response:
            content = "ports checked"

        return Response()


def test_shared_agent_tool_turn_limit_is_300():
    assert MAX_TOOL_STEPS == 300


def test_agent_registers_shared_tools_and_runs_them_for_any_state(tmp_path):
    names = {schema["function"]["name"] for schema in AGENT_TOOL_SCHEMAS}
    assert {"bash", "read_file", "write_file"}.issubset(names)
    assert {
        "install_system_package",
        "install_python_package",
        "serial_list_ports",
        "serial_capture",
        "serial_exchange",
        "mdk_build",
        "openocd_flash",
        "openocd_reset",
        "openocd_gdb_server",
        "gdb_batch",
    }.issubset(names)
    assert "codebase_memory_search_code" in names

    (tmp_path / "input.txt").write_text("source material", encoding="utf-8")
    llm = ToolCallingLLM()
    output = invoke_with_agent_tools(
        llm,
        "use the shared tools",
        project_root=tmp_path,
        run_dir=tmp_path / "run-1",
        state_name="design",
    )

    assert output == "Finished after using shared tools."
    assert llm.bound_tools is not None
    assert (tmp_path / "output.txt").read_text(encoding="utf-8") == "generated"
    log = tmp_path / "run-1" / "design" / "tool_calls.jsonl"
    assert log.exists()
    assert "read_file" in log.read_text(encoding="utf-8")


def test_read_file_accepts_gb18030_text(tmp_path):
    source = tmp_path / "legacy.c"
    source.write_bytes("/* 中文注释 */\nint value = 1;\n".encode("gb18030"))

    output = _run_file_tool("read_file", {"path": str(source)}, tmp_path, tmp_path / "run-1")

    assert "中文注释" in output


def test_agent_blocks_third_identical_failed_tool_call(tmp_path, monkeypatch):
    executions = []

    def fail_tool(name, args, _project_root, _run_dir, _verification_env=None):
        executions.append((name, args))
        return "exit_code=1\nstdout:\n\nstderr:\nfailed"

    monkeypatch.setattr(agent_tools, "_run_tool", fail_tool)
    output = invoke_with_agent_tools(
        RepeatingFailedToolLLM(),
        "try a tool",
        project_root=tmp_path,
        run_dir=tmp_path / "run-1",
        state_name="test",
    )

    assert output == "used another approach"
    assert len(executions) == 2
    assert "identical failing tool call blocked" in (tmp_path / "run-1" / "test" / "tool_calls.jsonl").read_text(
        encoding="utf-8"
    )


def test_agent_dispatches_verification_tool_with_loaded_environment(tmp_path, monkeypatch):
    received = {}

    def fake_verification_tool(name, args, **kwargs):
        received.update(name=name, args=args, **kwargs)
        return "exit_code=0\nstdout:\nCOM3\nstderr:\n"

    monkeypatch.setattr(agent_tools, "run_verification_tool", fake_verification_tool, raising=False)
    verification_env = {"hardware": {"serial": {"configured_port": "COM3"}}}

    output = invoke_with_agent_tools(
        VerificationToolLLM(),
        "inspect serial",
        project_root=tmp_path,
        run_dir=tmp_path / "run-1",
        state_name="test",
        verification_env=verification_env,
    )

    assert output == "ports checked"
    assert received["name"] == "serial_list_ports"
    assert received["verification_env"] == verification_env
    assert received["project_root"] == tmp_path
    assert received["run_dir"] == tmp_path / "run-1"


def test_new_run_dir_returns_absolute_path_for_relative_run_root(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    run_dir = new_run_dir(Path("runs"))

    assert run_dir.is_absolute()
    assert run_dir.parent == (tmp_path / "runs").resolve()


def test_bash_returns_timeout_result_instead_of_raising(tmp_path, monkeypatch):
    monkeypatch.setattr("embedded_agent.agent_tools.TOOL_TIMEOUT_SEC", 0.1)

    output = _run_bash("Start-Sleep -Seconds 5", tmp_path)

    assert "exit_code=124" in output
    assert "timed out" in output


def test_bash_timeout_terminates_child_process_tree(tmp_path, monkeypatch):
    monkeypatch.setattr("embedded_agent.agent_tools.TOOL_TIMEOUT_SEC", 2)
    pid_file = tmp_path / "child.pid"
    command = (
        "$child = Start-Process -FilePath powershell -WindowStyle Hidden -PassThru "
        "-ArgumentList '-NoProfile -NonInteractive -Command Start-Sleep -Seconds 30'; "
        f"Set-Content -LiteralPath '{pid_file}' -Value $child.Id; "
        "Wait-Process -Id $child.Id"
    )

    output = _run_bash(command, tmp_path)
    child_pid = int(pid_file.read_text(encoding="utf-8").strip())
    probe = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", f"Get-Process -Id {child_pid} -ErrorAction Stop"],
        capture_output=True,
        timeout=5,
    )

    assert "exit_code=124" in output
    assert probe.returncode != 0


def test_uv4_command_terminates_new_lingering_gui_process(tmp_path, monkeypatch):
    class FinishedPowerShell:
        pid = 101
        returncode = 0
        stdout = None
        stderr = None

        def communicate(self, timeout):
            return "", ""

    snapshots = iter([{11}, {11, 22}])
    terminated = []
    monkeypatch.setattr(agent_tools.subprocess, "Popen", lambda *_args, **_kwargs: FinishedPowerShell())
    monkeypatch.setattr(agent_tools, "_process_ids_by_image", lambda _image: next(snapshots), raising=False)
    monkeypatch.setattr(agent_tools, "_terminate_pid_tree", terminated.append, raising=False)

    output = run_powershell_command(
        '& "C:\\Keil_v5\\UV4\\UV4.exe" -j0 -b "project.uvprojx"',
        cwd=tmp_path,
        timeout_sec=20,
        output_chars=12000,
    )

    assert "exit_code=124" in output
    assert "left a running UV4.exe process" in output
    assert terminated == [22]


def test_bash_preserves_utf8_output_from_python(tmp_path):
    output = _run_bash('python -c "print(\'电池内阻测试\')"', tmp_path)

    assert "电池内阻测试" in output
    assert "�" not in output
