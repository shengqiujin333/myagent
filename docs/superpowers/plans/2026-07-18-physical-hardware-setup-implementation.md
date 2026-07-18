# Physical Hardware Setup And Tool Limit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Inject explicit current-board assembly facts into every verification-environment prompt and increase the shared agent tool-step limit to 600.

**Architecture:** Keep physical setup in the existing verification-environment YAML so all stages use one source of truth. Add behavioral guidance in the shared verification-environment formatter, then update the single shared tool-loop constant without changing cleanup behavior.

**Tech Stack:** Python 3.11, PyYAML, pytest, Markdown prompt composition.

## Global Constraints

- Record only DS18B20 installed/soldered, USART1 not connected, and USART2 connected with temporary `printf` debug-output use.
- Do not add cascade configuration or infer unspecified hardware facts.
- Physical setup facts override model inference but do not silently create business requirements.
- Keep existing tool cleanup and repeated-failure blocking behavior unchanged.

---

### Task 1: Physical Setup Configuration And Prompt Contract

**Files:**
- Modify: `configs/verification_env.myagent.yaml`
- Modify: `src/embedded_agent/nodes.py`
- Test: `tests/test_build_context.py`

**Interfaces:**
- Consumes: `AgentState.verification_env: dict[str, object]`
- Produces: `_verification_environment_section(agent: AgentState) -> str` containing setup facts and interpretation rules.

- [ ] **Step 1: Write the failing prompt test**

Add a test that builds an `AgentState` with `physical_setup` entries and asserts the generated design prompt contains `ds18b20`, `installed`, `usart1`, `not_connected`, `usart2`, `connected`, `printf_debug_output`, and explicit language that setup facts override inference and cannot invent missing hardware.

- [ ] **Step 2: Run the prompt test and verify RED**

Run: `python -m pytest tests/test_build_context.py::test_verification_prompt_prioritizes_physical_setup_facts -q`

Expected: FAIL because the shared prompt does not yet contain the interpretation rules.

- [ ] **Step 3: Add the physical setup and shared guidance**

Add this structure under `hardware` in the local verification YAML:

```yaml
physical_setup:
  description: "Current physical assembly and connections; treat these as explicit facts."
  devices:
    ds18b20:
      status: "installed"
      connection: "soldered"
  interfaces:
    usart1:
      status: "not_connected"
    usart2:
      status: "connected"
      temporary_use: "printf_debug_output"
```

Update `_verification_environment_section` to explain that these facts override inference, unlisted hardware remains unknown, disconnected interfaces cannot prove HIL success, and USART2's temporary use does not create a permanent business requirement.

- [ ] **Step 4: Run the prompt test and verify GREEN**

Run: `python -m pytest tests/test_build_context.py::test_verification_prompt_prioritizes_physical_setup_facts -q`

Expected: PASS.

### Task 2: Shared Tool-Step Limit

**Files:**
- Modify: `src/embedded_agent/agent_tools.py`
- Test: `tests/test_agent_tools.py`

**Interfaces:**
- Consumes: `MAX_TOOL_STEPS` in `invoke_with_agent_tools`.
- Produces: a maximum of 600 model/tool turns before existing cleanup and `RuntimeError` behavior runs.

- [ ] **Step 1: Update the focused expectation and verify RED**

Rename the test to `test_shared_agent_tool_turn_limit_is_600`, assert `MAX_TOOL_STEPS == 600`, and run:

`python -m pytest tests/test_agent_tools.py::test_shared_agent_tool_turn_limit_is_600 -q`

Expected: FAIL with `300 != 600`.

- [ ] **Step 2: Apply the minimal limit change**

Change only:

```python
MAX_TOOL_STEPS = 600
```

- [ ] **Step 3: Run the focused test and verify GREEN**

Run: `python -m pytest tests/test_agent_tools.py::test_shared_agent_tool_turn_limit_is_600 -q`

Expected: PASS.

### Task 3: Regression Verification

**Files:**
- Verify only; no additional production files.

**Interfaces:**
- Consumes the completed changes from Tasks 1 and 2.
- Produces evidence that prompt construction, YAML loading, and the shared tool loop remain compatible.

- [ ] **Step 1: Run focused regression tests**

Run: `python -m pytest tests/test_agent_tools.py tests/test_build_context.py tests/test_llm_config.py -q`

Expected: all tests pass.

- [ ] **Step 2: Validate configuration and diff hygiene**

Run a small Python command using `load_verification_env` and assert the three physical setup entries and USART2 temporary use. Run `git diff --check` on all modified implementation files.

Expected: parsed values match the YAML and diff check exits zero.
