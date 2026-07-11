import pytest

from embedded_agent.human import HumanInterventionRequired, request_human_intervention
from embedded_agent.state import AgentState


def test_request_human_intervention_defaults_to_structured_exception(tmp_path, monkeypatch):
    monkeypatch.delenv("EMBEDDED_AGENT_LANGGRAPH_INTERRUPT", raising=False)
    state = AgentState(project_root=tmp_path, run_dir=tmp_path / "run", goal="finish task")

    with pytest.raises(HumanInterventionRequired) as error:
        request_human_intervention(state, "build_context", "model failed", "provide context")

    assert error.value.payload["type"] == "human_intervention_required"
    assert error.value.payload["state"] == "build_context"
    assert error.value.payload["issue"] == "model failed"
