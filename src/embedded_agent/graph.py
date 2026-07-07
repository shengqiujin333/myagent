from __future__ import annotations

from embedded_agent.nodes import (
    build_context_node,
    execute_tasks_node,
    plan_node,
    slice_node,
    thinkingmap_node,
)
from embedded_agent.human import HumanInterventionRequired, request_human_intervention
from embedded_agent.state import AgentState


def _coerce_human_state(response: object) -> dict:
    if isinstance(response, dict):
        candidate = response.get("state", response)
        if isinstance(candidate, dict):
            AgentState.model_validate(candidate)
            return candidate
    raise RuntimeError("human intervention did not provide a valid replacement AgentState dict")


def human_guarded_node(name, node):
    def guarded(state: dict) -> dict:
        try:
            return node(state)
        except HumanInterventionRequired:
            raise
        except Exception as exc:
            agent = AgentState.model_validate(state)
            response = request_human_intervention(
                agent,
                name,
                f"State failed: {exc}",
                "Provide a complete replacement AgentState dict as `state`, or fix the issue and resume this state.",
                {"state": state},
            )
            return _coerce_human_state(response)

    guarded.__name__ = f"{name}_human_guarded"
    return guarded


class SequentialGraph:
    def __init__(self) -> None:
        self.nodes = [
            human_guarded_node("build_context", build_context_node),
            human_guarded_node("thinkingmap", thinkingmap_node),
            human_guarded_node("plan", plan_node),
            human_guarded_node("slice", slice_node),
            human_guarded_node("execute_tasks", execute_tasks_node),
        ]

    def invoke(self, state: dict) -> dict:
        current = state
        for node in self.nodes:
            current = node(current)
            if current.get("failed_task_id"):
                break
        return current


def build_graph():
    try:
        from langgraph.graph import END, StateGraph
    except ImportError as exc:
        return SequentialGraph()

    graph = StateGraph(dict)
    graph.add_node("build_context", human_guarded_node("build_context", build_context_node))
    graph.add_node("thinkingmap", human_guarded_node("thinkingmap", thinkingmap_node))
    graph.add_node("plan", human_guarded_node("plan", plan_node))
    graph.add_node("slice", human_guarded_node("slice", slice_node))
    graph.add_node("execute_tasks", human_guarded_node("execute_tasks", execute_tasks_node))
    graph.set_entry_point("build_context")
    graph.add_edge("build_context", "thinkingmap")
    graph.add_edge("thinkingmap", "plan")
    graph.add_edge("plan", "slice")
    graph.add_edge("slice", "execute_tasks")
    graph.add_edge("execute_tasks", END)
    try:
        from langgraph.checkpoint.memory import MemorySaver
    except ImportError:
        return graph.compile()
    return graph.compile(checkpointer=MemorySaver())
