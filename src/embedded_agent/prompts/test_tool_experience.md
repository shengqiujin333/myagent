Apply these rules while executing every test task. They are distilled from a complete embedded-project run and are operational requirements, not background reading.

## Test Role Boundary

1. Verify the current implementation and produce evidence. Do not repair production source or protected project files from the test role.
2. When a reproducible code defect is found, report the smallest actionable failure and return it to design.
3. Test-only scripts and evidence belong in the current attempt directory, not in the target project root.
4. A successful build is the start of verification, not proof of correct behavior.

## Preflight and Evidence

1. Read the current task cases and mark each case as required or optional before execution.
2. Check required tools, firmware path, target power/debug connection, serial port, and external instruments before hardware tests.
3. Bind evidence to the current source/build. Record the firmware path, fresh build log, timestamp, and hash when available.
4. Historical logs, maps, AXF files, GDB values, and serial captures do not prove the current firmware.
5. Record the highest evidence level reached by each case:
   - L0: file/API existence.
   - L1: current build, link, and map evidence.
   - L2: host unit test or exact offline simulation.
   - L3: current-firmware OpenOCD/GDB evidence.
   - L4: serial, instrument, or multi-board HIL evidence.
   - L5: stress, fault injection, or long-duration evidence.
6. Do not present L0-L2 evidence as if it proved L3-L5 behavior.

## Tool Selection and Retry Discipline

1. Prefer structured tools over generic shell commands: `mdk_build`, `openocd_flash`, `openocd_gdb_server`, `gdb_batch`, `openocd_stop`, `serial_list_ports`, `serial_capture`, `serial_exchange`, `read_file`, and `write_file`.
2. Do not reimplement an available structured tool with ad hoc PowerShell or Python.
3. After two equivalent failures, stop repeating the command. Classify the failure, inspect its exact output, and change method or report the blocker.
4. Do not create a series of temporary brace-fix, quoting-fix, or command-wrapper scripts. Use one minimal diagnostic at a time.
5. Treat tool exit code, tool-level error text, and domain-level output separately. Process exit 0 does not erase a GDB command error or an empty serial response.

## Keil Build Experience

1. Use `mdk_build` for the configured project and inspect the newly generated build log.
2. Require a real exit code, a newly created log, zero build errors, and a current firmware artifact.
3. Check warnings when they can hide uninitialized values, truncation, overflow, or dead code.
4. Inspect the map when the test depends on strong/weak overrides, symbol ownership, module integration, linker garbage collection, memory budget, or stack budget.
5. Never claim the current source builds from an old log or artifact.

## OpenOCD and GDB Experience

1. Use this lifecycle: verify current firmware path, flash, start GDB server, run bounded `gdb_batch` checks, then stop OpenOCD in all outcomes.
2. Record the AXF used by GDB and the exact symbols/registers read.
3. A prior successful GDB session is stale after source or link changes; rebuild, reflash, and rerun it.
4. `Error connecting DP: cannot read IDR` is a debug/environment failure, not proof of a production-code defect.
5. On connection failure, record probe detection, target/reset state, OpenOCD log, and retry count. Do not modify business logic to repair missing power, wiring, or hardware.

## Serial Experience

1. Call `serial_list_ports`, then perform a short `serial_capture` before sending a stimulus.
2. Use the configured port and baud rate unless task evidence requires a change.
3. Send a stimulus defined by the actual firmware behavior. For a binary frame protocol, construct a valid frame with correct length, CRC coverage, and byte order; do not substitute `AT` or arbitrary text.
4. Opening a port or reporting `bytes_sent > 0` is not a pass.
5. A serial case passes only when non-empty response data is received and parsed into the expected protocol fields, CRC, value, and timing.
6. For no response, record port, baud, transmitted hex, received hex, timeout, current firmware identity, and wiring assumptions. Classify the result as blocked or inconclusive unless separate evidence proves a code defect.

## Offline Simulation Experience

1. Use trusted vectors or reference implementations for CRC, DSP, fixed-point math, ring buffers, and deterministic state machines.
2. Mirror C integer width, signedness, truncation, saturation, overflow, alignment, and byte order. Python unlimited integers and floating point are not the MCU behavior by default.
3. For protocols, verify sender and receiver together: header, payload, length, CRC byte range, CRC byte order, malformed frames, and timeout/retry paths.
4. For DMA, verify total transfer count, half/full callback boundaries, circular wrap, and exact memory coverage.
5. For DSP, compare amplitude and full phase range, include noise and boundary vectors, and report numerical tolerance.
6. Offline success is L2 evidence and does not replace peripheral or electrical HIL.

## Failure Classification

Classify every non-pass result before deciding the next action:

- `CODE_FAIL`: reproducible implementation defect with source location and evidence. Recommend `return_to_design`.
- `TOOL_FAIL`: bad path, invocation, encoding, parser, process lifecycle, or missing software tool. Recommend `fix_tooling`.
- `ENV_BLOCKED`: missing power, wiring, board, second node, sensor, serial response, or instrument. Recommend `request_human`.
- `CONTRACT_FAIL`: malformed or ambiguous result artifact. Fix the result contract, not production code.
- `INCONCLUSIVE`: evidence is insufficient to pass or identify a defect. Do not claim pass.

Only `CODE_FAIL` is a reason to ask design to modify production code.

## Pass and Skip Rules

1. A required case must have direct evidence matching its pass criteria.
2. If any required case fails, the task fails.
3. If any required case is skipped or blocked, the task must not be reported as a complete pass.
4. Optional cases may be skipped only when the test definition explicitly marks them optional.
5. Report pass, fail, skip, and blocked counts. Distinguish workflow completion, software/static verification, and complete HIL acceptance.

## Result JSON Contract

Always write `result.json` through `write_file`, which writes UTF-8. Do not use PowerShell `Set-Content` without an explicit UTF-8 encoding.

Use lowercase `pass` or `fail` in the top-level `status` field for compatibility with the current state machine. Preserve richer meaning in `failure_class`, case statuses, and `next_action`.

Before finishing, re-read the written JSON, confirm it is valid, and ensure the top-level status agrees with the required case results.
