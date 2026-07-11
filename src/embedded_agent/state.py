from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


TaskKind = Literal["code", "doc", "test", "analysis", "config"]
CheckKind = Literal["build", "flash", "serial", "host_test", "inspect", "file"]

BLOCKED_PLAN_WORDS = (
    "split",
    "decompose",
    "subtask",
    "sub-task",
    "break down",
    "research later",
    "design later",
    "tbd",
    "todo",
    "later",
    "\u518d\u5206",
    "\u62c6\u5206",
    "\u5b50\u4efb\u52a1",
    "\u5f85\u5b9a",
)


class AcceptanceCheck(BaseModel):
    kind: CheckKind
    command: str | None = None
    expected: str | None = None


class PlanTask(BaseModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$")
    title: str
    kind: TaskKind
    objective: str
    dependencies: list[str] = Field(default_factory=list)
    target_files: list[str] = Field(default_factory=list)
    acceptance: list[AcceptanceCheck]

    @field_validator("title", "objective")
    @classmethod
    def reject_decomposable_wording(cls, value: str) -> str:
        lowered = value.lower()
        if any(word in lowered for word in BLOCKED_PLAN_WORDS):
            raise ValueError("plan task must be directly completable and cannot require more subtasks")
        return value

    @model_validator(mode="after")
    def validate_code_acceptance(self) -> "PlanTask":
        if self.kind != "code":
            return self
        kinds = {check.kind for check in self.acceptance}
        has_observation = bool({"serial", "host_test"} & kinds)
        if not {"build", "flash"}.issubset(kinds) or not has_observation:
            raise ValueError("code task acceptance must include build, flash, and observation")
        return self


class PlanDocument(BaseModel):
    architecture_strategy: str = ""
    critical_path_and_dependency: dict[str, object] = Field(default_factory=dict)
    wbs_tasks: list[dict[str, object]] = Field(default_factory=list)
    cross_module_interfaces_and_risks: list[str] = Field(default_factory=list)
    tasks: list[PlanTask] = Field(default_factory=list)


class AgentState(BaseModel):
    project_root: Path
    run_dir: Path
    goal: str
    llm: dict[str, object] = Field(default_factory=dict)
    verification_env: dict[str, object] = Field(default_factory=dict)
    verification_env_file: Path | None = None
    current_state: str = "build_context"
    context_md: str = ""
    context_file: Path | None = None
    context_files: list[Path] = Field(default_factory=list)
    thinkingmap_file: Path | None = None
    thinkingmap_files: list[Path] = Field(default_factory=list)
    plan_file: Path | None = None
    design_file: Path | None = None
    design_md: str = ""
    design_feedback: str = ""
    algorithm_simulation_file: Path | None = None
    subtask_feature_design_files: list[Path] = Field(default_factory=list)
    subtask_feature_test_file: Path | None = None
    slice_files: dict[str, Path] = Field(default_factory=dict)
    minimum_compilable_baseline_file: Path | None = None
    material_summary_file: Path | None = None
    completed_task_ids: set[str] = Field(default_factory=set)
    failed_task_id: str | None = None
    compact_messages: list[str] = Field(default_factory=list)

    def add_compact_message(self, message: str) -> None:
        if len(message) > 500:
            message = message[:497] + "..."
        self.compact_messages.append(message)
