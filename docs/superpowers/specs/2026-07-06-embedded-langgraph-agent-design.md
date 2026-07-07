# Embedded LangGraph Agent Design

## Goal

Build a LangGraph-based embedded coding agent that reads a firmware project, writes compact project context, brainstorms design keywords, creates directly executable task plans, generates task-specific slices, and executes each task against real local hardware through build, CMSIS-DAP flash, serial observation, and optional host-side tests.

## Core Rule

The agent keeps chat/model messages small. Large context lives on disk. Messages should carry only:

- Current state name.
- Current task id and objective.
- Paths to required context files.
- The smallest relevant excerpt.
- Latest failure summary when retrying.

## State Flow

1. `build_context`
   - Understand the target project.
   - Read the task directory named in the goal.
   - Describe each task file and extract hardware connection notes.
   - Write context files under `runs/<run_id>/context/`.

2. `thinkingmap`
   - Read context outputs.
   - Generate keywords for modules, hardware, risks, tests, interfaces, and integration.
   - Write `runs/<run_id>/thinkingmap/keywords.md` and `keywords.json`.

3. `plan`
   - Generate `plan.json` and `plan.md`.
   - Each child task must be directly completable.
   - Child tasks must not say "split", "decompose", "research later", "design later", "subtask", "TBD", or similar placeholders.
   - Each task records dependencies and exact acceptance checks.

4. `slice`
   - Create one slice per plan task.
   - Each slice contains role, skills, experience, thinking protocol, relevant context paths, thinkingmap keywords, and hardware verification rules.
   - Slices are written under `runs/<run_id>/slices/`.

5. `execute_tasks`
   - Loop through ready plan tasks in dependency order.
   - Load the task slice and context outputs.
   - Modify code, integrate modules into `main` or the configured entrypoint, build, flash with CMSIS-DAP, observe serial output, and run host test scripts when configured.
   - A failing code task can be modified at most 10 times.
   - Every attempt writes a record. If a task still fails after 10 attempts, execution stops and later tasks are not started.

## Hardware Interface

Hardware commands are configured in `agent_config.yaml`:

- build command and timeout.
- flash command and timeout.
- serial port, baudrate, timeout, and expected patterns.
- optional host test command.

The implementation calls real commands. It does not mock hardware during agent execution. Unit tests use injected runners so local tests do not require a board.

## Plan Atomicity

The plan state validates each task before writing it:

- The task objective must describe a finished code/documentation/test change.
- The task may include implementation notes, but the notes cannot require another planning phase.
- Dependencies must reference existing task ids.
- Acceptance checks must include concrete commands or observable outputs.
- Code tasks must include build, flash, and serial or host-test acceptance checks unless explicitly marked as non-code.

## Failure Records

Each task writes:

- `execution/<task_id>/attempts.jsonl`
- `execution/<task_id>/latest_failure.md`
- `execution/<task_id>/result.json`

Records include command, exit code, stdout/stderr tail, serial tail, host-test output, diagnosis, and next change summary.

## Deliverables

- Python package under `src/embedded_agent`.
- Tests under `tests`.
- Example config under `configs/agent_config.example.yaml`.
- README with setup and hardware usage.
