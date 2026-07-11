from __future__ import annotations

from embedded_agent.nodes import (
    algorithm_simulation_node,
    build_context_node,
    design_node,
    execute_tasks_node,
    material_summary_node,
    minimum_compilable_baseline_node,
    slice_node,
    subtask_feature_design_node,
    subtask_feature_test_node,
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


def build_node_map() -> dict:
    return {
        "build_context": human_guarded_node("build_context", build_context_node),
        "thinkingmap": human_guarded_node("thinkingmap", thinkingmap_node),
        "design": human_guarded_node("design", design_node),
        "algorithm_simulation": human_guarded_node("algorithm_simulation", algorithm_simulation_node),
        "subtask_feature_design": human_guarded_node("subtask_feature_design", subtask_feature_design_node),
        "subtask_feature_test": human_guarded_node("subtask_feature_test", subtask_feature_test_node),
        "slice": human_guarded_node("slice", slice_node),
        "minimum_compilable_baseline": human_guarded_node("minimum_compilable_baseline", minimum_compilable_baseline_node),
        "material_summary": human_guarded_node("material_summary", material_summary_node),
        "execute_tasks": human_guarded_node("execute_tasks", execute_tasks_node),
    }


MAX_GRAPH_STEPS = 50


class SequentialGraph:
    def __init__(self) -> None:
        self.node_map = build_node_map()

    def invoke(self, state: dict) -> dict:
        current = state
        current_state = current.get("current_state") or "build_context"
        for _ in range(MAX_GRAPH_STEPS):
            if current_state == "done":
                break
            node = self.node_map.get(current_state)
            if node is None:
                raise RuntimeError(f"no node registered for state: {current_state}")
            current = node(current)
            current_state = current.get("current_state")
            if current.get("failed_task_id"):
                break
        return current


def _route_after_algorithm_simulation(state: dict) -> str:
    if state.get("current_state") == "subtask_feature_design":
        return "subtask_feature_design"
    return "design"


def build_graph():
    try:
        from langgraph.graph import END, StateGraph
    except ImportError as exc:
        return SequentialGraph()

    graph = StateGraph(dict)
    graph.add_node("build_context", human_guarded_node("build_context", build_context_node))
    graph.add_node("thinkingmap", human_guarded_node("thinkingmap", thinkingmap_node))
    graph.add_node("design", human_guarded_node("design", design_node))
    graph.add_node("algorithm_simulation", human_guarded_node("algorithm_simulation", algorithm_simulation_node))
    graph.add_node("subtask_feature_design", human_guarded_node("subtask_feature_design", subtask_feature_design_node))
    graph.add_node("subtask_feature_test", human_guarded_node("subtask_feature_test", subtask_feature_test_node))
    graph.add_node("slice", human_guarded_node("slice", slice_node))
    graph.add_node("minimum_compilable_baseline", human_guarded_node("minimum_compilable_baseline", minimum_compilable_baseline_node))
    graph.add_node("material_summary", human_guarded_node("material_summary", material_summary_node))
    graph.add_node("execute_tasks", human_guarded_node("execute_tasks", execute_tasks_node))
    graph.set_entry_point("build_context")
    graph.add_edge("build_context", "thinkingmap")
    graph.add_edge("thinkingmap", "design")
    graph.add_edge("design", "algorithm_simulation")
    graph.add_conditional_edges(
        "algorithm_simulation",
        _route_after_algorithm_simulation,
        {
            "subtask_feature_design": "subtask_feature_design",
            "design": "design",
        },
    )
    graph.add_edge("subtask_feature_design", "subtask_feature_test")
    graph.add_edge("subtask_feature_test", "slice")
    graph.add_edge("slice", "minimum_compilable_baseline")
    graph.add_edge("minimum_compilable_baseline", "material_summary")
    graph.add_edge("material_summary", "execute_tasks")
    graph.add_edge("execute_tasks", END)
    try:
        from langgraph.checkpoint.memory import MemorySaver
    except ImportError:
        return graph.compile()
    return graph.compile(checkpointer=MemorySaver())
