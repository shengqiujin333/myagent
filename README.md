# Embedded LangGraph Agent

This project scaffolds a LangGraph embedded coding agent with five states:

1. `build_context`
2. `thinkingmap`
3. `plan`
4. `slice`
5. `execute_tasks`

The agent is disk-first. Model messages should stay small and point at run artifacts instead of carrying long context. The `plan` state validates that every child task is directly completable and does not ask the executor to split work again.

## Install

```bash
pip install -e .
```

## Configure

Copy `configs/agent_config.example.yaml` and edit:

- `project_root`
- `llm.model` if your DeepSeek account uses a different model id
- `verification_env_file`, which points to the separate verification environment YAML

Put hardware and software verification capabilities in the verification environment file, not in `agent_config`.
That file describes serial port negotiation, CMSIS-DAP/OpenOCD usage, build tools, Python runtime, package install policy, and host-side test examples.

The default LLM provider is DeepSeek through an OpenAI-compatible chat client:

```yaml
llm:
  provider: "deepseek"
  model: "deepseek-v4-flash"
  base_url: "https://api.deepseek.com"
  api_key_env: "DEEPSEEK_API_KEY"
```

Set the API key before running:

```powershell
$env:DEEPSEEK_API_KEY="sk-..."
```

The `plan` state receives two separate inputs: the generated build context and the verification environment YAML. Build context is for project design; verification environment is for HIL, build, flash, serial, Python, and host-side test planning.

## Run From The Beginning

```bash
embedded-agent --config configs/agent_config.example.yaml --goal "implement UART echo and verify it on serial"
```

For your local config and a task directory goal:

```powershell
embedded-agent --config configs\agent_config.myagent.yaml --goal "完成C:\Users\123\Desktop\neizu\tasknew里面的任务要求"
```

Artifacts are written under `runs/<run_id>/`:

- `context/context.md`
- `thinkingmap/thinkingmap.json` or `thinkingmap/thinkingmap.md`
- `plan/plan.json`
- `slices/<task_id>.md`
- `execution/<task_id>/attempts.jsonl`
- `execution/<task_id>/latest_failure.md`
- `execution/<task_id>/result.json`

## Resume From A State

Use `--resume-run` with an existing `runs/<run_id>` directory and choose where to restart with `--from-state`.

Supported states:

- `build_context`
- `thinkingmap`
- `plan`
- `slice`
- `execute_tasks`

Examples:

```powershell
# Re-run thinkingmap, then continue through plan, slice, and execute_tasks.
embedded-agent --config configs\agent_config.myagent.yaml --goal "完成C:\Users\123\Desktop\neizu\tasknew里面的任务要求" --resume-run runs\20260709-090019 --from-state thinkingmap

# Re-run only from plan onward. Useful after editing src\embedded_agent\prompts\plan.md.
embedded-agent --config configs\agent_config.myagent.yaml --goal "完成C:\Users\123\Desktop\neizu\tasknew里面的任务要求" --resume-run runs\20260709-090019 --from-state plan

# Continue from slice. Requires runs\<run_id>\plan\plan.json to exist.
embedded-agent --config configs\agent_config.myagent.yaml --goal "完成C:\Users\123\Desktop\neizu\tasknew里面的任务要求" --resume-run runs\20260709-090019 --from-state slice
```

Resume requirements:

- `thinkingmap`, `plan`, `slice`, and `execute_tasks` require `context/context.md`.
- `slice` and `execute_tasks` require `plan/plan.json`.
- `thinkingmap/thinkingmap.json` or `.md` is restored when present, but `plan` does not use thinkingmap as input.

## Safety Rules

The context state reads the configured `project_root`, passes the user goal to the model unchanged, and asks the model to summarize task files, directories, and hardware connection notes from the gathered materials.

If a model-backed state cannot produce usable output, the CLI prints `human_intervention_required` with the state, issue, and request instead of writing a fallback artifact. Set `EMBEDDED_AGENT_LANGGRAPH_INTERRUPT=1` to use LangGraph interrupt support directly.
