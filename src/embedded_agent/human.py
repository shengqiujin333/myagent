from __future__ import annotations

import os
from typing import Any

from embedded_agent.state import AgentState


class HumanInterventionRequired(RuntimeError):
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        super().__init__(f"human intervention required in {payload.get('state')}: {payload.get('issue')}")


def request_human_intervention(
    agent: AgentState,
    state_name: str,
    issue: str,
    request: str,
    payload: dict[str, Any] | None = None,
) -> Any:
    interrupt_payload = {
        "type": "human_intervention_required",
        "state": state_name,
        "issue": issue,
        "request": request,
        "run_dir": str(agent.run_dir),
        "goal": agent.goal,
        "payload": payload or {},
    }
    if os.getenv("EMBEDDED_AGENT_LANGGRAPH_INTERRUPT") != "1":
        raise HumanInterventionRequired(interrupt_payload)
    try:
        from langgraph.types import interrupt
    except ImportError as exc:
        raise HumanInterventionRequired(interrupt_payload) from exc
    return interrupt(interrupt_payload)
