import pytest
from pydantic import ValidationError

from embedded_agent.state import AcceptanceCheck, PlanDocument, PlanTask


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


def test_plan_rejects_unknown_dependency():
    task = PlanTask(
        id="task-1",
        title="Implement LED blink",
        kind="code",
        objective="Add a complete LED blink module wired into main.",
        dependencies=["task-0"],
        target_files=["src/main.c"],
        acceptance=[
            AcceptanceCheck(kind="build", command="cmake --build build"),
            AcceptanceCheck(kind="flash", command="pyocd flash firmware.elf"),
            AcceptanceCheck(kind="serial", expected="BLINK OK"),
        ],
    )

    with pytest.raises(ValidationError, match="unknown dependencies"):
        PlanDocument(tasks=[task])


def test_valid_direct_code_task_is_accepted():
    task = PlanTask(
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

    plan = PlanDocument(tasks=[task])

    assert plan.ready_task_ids(completed=set()) == ["task-1"]
