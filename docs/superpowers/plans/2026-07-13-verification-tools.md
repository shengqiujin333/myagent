# Verification Tools Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Register the software provisioning, serial, Keil, OpenOCD, and GDB capabilities described by the verification environment as callable tools for every agent state.

**Architecture:** Keep generic file/bash/codebase tools in `agent_tools.py` and place verification-specific schemas and execution in a focused `verification_tools.py`. The runtime passes the loaded verification environment into tool execution; commands are assembled and validated in Python, and every result uses the existing `exit_code/stdout/stderr` contract and tool log.

**Tech Stack:** Python 3.11+, PySerial, Chocolatey, Keil UV4, OpenOCD, GNU Arm GDB, pytest.

## Global Constraints

- Do not modify workflow prompt files.
- Tools are globally registered for every state.
- Package names come from `verification_env` declarations, not arbitrary shell text.
- Serial captures are persisted below the current run directory as evidence.
- Hardware commands must be non-interactive, timeout-bounded, and report nonzero exits as failures.

---

### Task 1: Verification Tool Schemas And Dispatch

**Files:**
- Create: `src/embedded_agent/verification_tools.py`
- Modify: `src/embedded_agent/agent_tools.py`
- Test: `tests/test_verification_tools.py`

**Interfaces:**
- Consumes: loaded `verification_env`, target `project_root`, and current `run_dir`.
- Produces: `VERIFICATION_TOOL_SCHEMAS`, `is_verification_tool(name)`, and `run_verification_tool(...)`.

- [ ] Write failing tests asserting all package, serial, build, flash, reset, server, and GDB tools are globally registered and dispatched with the runtime verification environment.
- [ ] Run `python -m pytest tests/test_verification_tools.py -q` and confirm failure before implementation.
- [ ] Implement schemas, dispatch, structured results, path resolution, and shared subprocess execution.
- [ ] Pass `agent.verification_env` through every `invoke_with_agent_tools` call.
- [ ] Run focused tests and confirm they pass.

### Task 2: Package And Serial Tools

**Files:**
- Modify: `src/embedded_agent/verification_tools.py`
- Test: `tests/test_verification_tools.py`

**Interfaces:**
- Produces: `install_system_package`, `install_python_package`, `serial_list_ports`, `serial_capture`, and `serial_exchange`.

- [ ] Write failing tests for allowlisted Chocolatey installation, pip installation, serial discovery, persisted capture logs, text/hex exchange, and invalid arguments.
- [ ] Run focused tests and confirm the expected failures.
- [ ] Implement package policy checks and PySerial-backed serial operations.
- [ ] Run focused tests and confirm they pass.

### Task 3: Keil, OpenOCD, And GDB Tools

**Files:**
- Modify: `src/embedded_agent/verification_tools.py`
- Modify: `configs/verification_env.myagent.yaml`
- Modify: `configs/verification_env.example.yaml`
- Test: `tests/test_verification_tools.py`

**Interfaces:**
- Produces: `mdk_build`, `openocd_flash`, `openocd_reset`, `openocd_gdb_server`, and `gdb_batch`.

- [ ] Write failing command-construction tests using subprocess mocks, including Windows path and quoting cases.
- [ ] Run focused tests and confirm the expected failures.
- [ ] Implement deterministic argv construction, process timeout cleanup, background GDB-server startup, and evidence logging.
- [ ] Correct the real target-relative project and firmware paths in `verification_env.myagent.yaml` and repair the malformed package list in the example.
- [ ] Run focused tests and confirm they pass.

### Task 4: Regression Verification

**Files:**
- Test: `tests/test_agent_tools.py`
- Test: `tests/test_build_context.py`
- Test: `tests/test_verification_tools.py`

- [ ] Run `python -m pytest -q`.
- [ ] Run `python -m compileall -q src/embedded_agent`.
- [ ] Run `git diff --check`.
- [ ] Review the final diff and exclude run artifacts, caches, and unrelated user prompt changes.
