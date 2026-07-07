import pytest

from embedded_agent.safe_shell import CommandBlocked, ensure_safe_discovery_command, run_command


@pytest.mark.parametrize(
    "command",
    [
        "Get-ChildItem -Recurse",
        "grep -R TODO .",
        "find . -type f",
        "vim src/main.c",
        "python -i",
    ],
)
def test_blocks_commands_that_can_hang_or_explode(command):
    with pytest.raises(CommandBlocked):
        ensure_safe_discovery_command(command)


@pytest.mark.parametrize(
    "command",
    [
        "fd -t f .",
        "rg --files",
        "codebase_memory_cli --help",
        "Get-Content src/main.c -TotalCount 200",
    ],
)
def test_allows_bounded_discovery_commands(command):
    ensure_safe_discovery_command(command)


def test_run_command_executes_in_requested_working_directory(tmp_path):
    code, stdout, stderr = run_command(
        "python -c \"import pathlib; print(pathlib.Path.cwd())\"",
        10,
        cwd=tmp_path,
    )

    assert code == 0
    assert stderr == ""
    assert stdout.strip() == str(tmp_path)


def test_run_command_replaces_invalid_output_bytes(tmp_path):
    code, stdout, stderr = run_command(
        "python -c \"import sys; sys.stdout.buffer.write(bytes([0x80, 0x81]))\"",
        10,
        cwd=tmp_path,
    )

    assert code == 0
    assert stderr == ""
    assert stdout
