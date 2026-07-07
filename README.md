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

## Configure Hardware

Copy `configs/agent_config.example.yaml` and edit:

- `project_root`
- `llm.model` if your DeepSeek account uses a different model id
- `hardware.build_command`
- `hardware.flash_command`
- `hardware.serial_port`
- expected serial or host-test behavior in the generated plan/task acceptance checks

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

The execution adapter runs real local commands, including CMSIS-DAP flashing through tools such as `pyocd` or OpenOCD.

## Run

```bash
embedded-agent --config configs/agent_config.example.yaml --goal "implement UART echo and verify it on serial"
```

Artifacts are written under `runs/<run_id>/`:

- `context/context.md`
- `thinkingmap/keywords.md`
- `plan/plan.json`
- `slices/<task_id>.md`
- `execution/<task_id>/attempts.jsonl`
- `execution/<task_id>/latest_failure.md`
- `execution/<task_id>/result.json`

## Safety Rules

The context state reads the configured `project_root`, passes the user goal to the model unchanged, and asks the model to summarize task files, directories, and hardware connection notes from the gathered materials.

If a model-backed state cannot produce usable output, the CLI prints `human_intervention_required` with the state, issue, and request instead of writing a fallback artifact. Set `EMBEDDED_AGENT_LANGGRAPH_INTERRUPT=1` to use LangGraph interrupt support directly.
