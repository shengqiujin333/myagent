# Physical Hardware Setup And Tool Limit Design

## Objective

Record the current board's real assembly and connections as explicit verification facts, so context, design, and test agents do not confuse PCB capabilities with hardware that is actually available. Increase the shared agent tool-step limit from 300 to 600 model turns.

## Configuration Shape

Add `hardware.physical_setup` to `configs/verification_env.myagent.yaml`:

```yaml
hardware:
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
```

Only known, relevant facts are listed. There is no cascade field because cascade hardware is not part of the current setup description.

## Agent Behavior

The verification-environment prompt must state that `hardware.physical_setup` describes the current real board and has priority over inferred wiring or generic board capabilities.

- `installed` and `connected` hardware may be used for hardware-in-the-loop verification.
- `not_connected` hardware must not be used as evidence of a successful hardware test.
- Missing entries remain unknown; agents must not invent their presence or absence.
- The setup describes test availability. It does not silently add business requirements or future modules.

The existing verification environment is already included in build-context, thinking-map, design, execution-design, and execution-test prompts. The implementation should strengthen the shared verification-environment wording instead of creating a second configuration path.

## Tool-Step Limit

Change the shared `MAX_TOOL_STEPS` constant from 300 to 600. Preserve the existing cleanup behavior after normal completion, model errors, and limit exhaustion. Update the focused unit test to assert 600.

## Validation

- Load `verification_env.myagent.yaml` and verify the physical setup values survive YAML parsing.
- Verify a representative generated prompt contains `physical_setup`, `ds18b20`, `usart1`, `not_connected`, `usart2`, and `connected`.
- Verify the prompt includes the rule that physical setup facts override inference and unavailable connections cannot count as HIL evidence.
- Verify `MAX_TOOL_STEPS == 600`.
- Run the focused agent-tool and prompt-building tests.

## Non-Goals

- No new hardware discovery mechanism.
- No cascade configuration.
- No change to UART pin assignments, baud rates, or firmware business logic.
- No automatic conversion of `not_connected` into a code or design failure.
