import pytest
from pydantic import ValidationError

from embedded_agent.state import AcceptanceCheck, PlanTask


def test_plan_task_rejects_decomposable_wording():
    with pytest.raises(ValidationError, match="directly completable"):
        PlanTask(
            id="task-1",
            title="Implement UART driver",
            kind="code",
            objective="Split the UART work into smaller subtasks.",
            dependencies=[],
            target_files=["src/uart.c"],
            acceptance=[
                AcceptanceCheck(kind="build", command="cmake --build build"),
                AcceptanceCheck(kind="flash", command="pyocd flash firmware.elf"),
                AcceptanceCheck(kind="serial", expected="UART OK"),
            ],
        )


def test_code_task_requires_build_flash_and_observation():
    with pytest.raises(ValidationError, match="build, flash, and observation"):
        PlanTask(
            id="task-1",
            title="Implement LED blink",
            kind="code",
            objective="Add a complete LED blink module wired into main.",
            dependencies=[],
            target_files=["src/main.c"],
            acceptance=[AcceptanceCheck(kind="build", command="cmake --build build")],
        )
