# Embedded LangGraph Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a runnable LangGraph embedded coding agent with disk-first context, atomic plan generation, task slices, and real hardware verification commands.

**Architecture:** A Python package exposes a CLI and a LangGraph state graph. Nodes write durable run artifacts and pass compact references through state. Hardware access is isolated behind an adapter that runs configured local commands.

**Tech Stack:** Python 3.11+, LangGraph, Pydantic, PyYAML, pyserial, pytest.

---

## File Structure

- Create `pyproject.toml`: package metadata and dependencies.
- Create `README.md`: usage, hardware config, state outputs.
- Create `configs/agent_config.example.yaml`: editable project/hardware commands.
- Create `src/embedded_agent/state.py`: Pydantic schemas and plan atomicity validation.
- Create `src/embedded_agent/config.py`: config loader.
- Create `src/embedded_agent/safe_shell.py`: command guard and subprocess runner.
- Create `src/embedded_agent/hardware.py`: build, flash, serial, host-test adapter.
- Create `src/embedded_agent/artifacts.py`: run directory writer helpers.
- Create `src/embedded_agent/nodes.py`: five LangGraph node functions.
- Create `src/embedded_agent/graph.py`: graph wiring.
- Create `src/embedded_agent/cli.py`: command-line entrypoint.
- Create `tests/test_plan_validation.py`: atomic plan rules.
- Create `tests/test_safe_shell.py`: blocked command rules.
- Create `tests/test_hardware.py`: retry and command adapter behavior.
- Create `tests/test_graph.py`: graph construction and initial run shape.

## Tasks

### Task 1: Schemas and Plan Atomicity

- [ ] Write tests that reject decomposable plan tasks and invalid dependencies.
- [ ] Implement `state.py` with `PlanTask`, `PlanDocument`, `AgentState`, and validators.
- [ ] Verify with `pytest tests/test_plan_validation.py -q`.

### Task 2: Safe Shell and Config

- [ ] Write tests for forbidden commands and allowed bounded commands.
- [ ] Implement config loading and safe command checks.
- [ ] Verify with `pytest tests/test_safe_shell.py -q`.

### Task 3: Hardware Adapter

- [ ] Write tests with injected command runner and serial reader.
- [ ] Implement build, flash, serial observe, host-test, and 10-attempt result recording helpers.
- [ ] Verify with `pytest tests/test_hardware.py -q`.

### Task 4: LangGraph Nodes

- [ ] Write graph tests for node names, run directory creation, plan/slice artifact paths, and compact state references.
- [ ] Implement context, thinkingmap, plan, slice, and execution nodes.
- [ ] Verify with `pytest tests/test_graph.py -q`.

### Task 5: CLI and Documentation

- [ ] Add CLI entrypoint and example config.
- [ ] Update README with real hardware command examples.
- [ ] Run `pytest -q`.
