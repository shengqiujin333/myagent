from embedded_agent.graph import build_graph
from embedded_agent.graph import human_guarded_node


def test_graph_exposes_expected_nodes():
    graph = build_graph()

    assert graph is not None


def test_human_guarded_node_can_resume_with_replacement_state(tmp_path, monkeypatch):
    state = {
        "project_root": tmp_path,
        "run_dir": tmp_path / "runs" / "run-1",
        "goal": "finish task",
        "hardware": {},
        "llm": {},
    }
    replacement = dict(state)
    replacement["current_state"] = "thinkingmap"

    def failing_node(_state):
        raise RuntimeError("model output invalid")

    def fake_human_intervention(*_args, **_kwargs):
        return {"state": replacement}

    monkeypatch.setattr("embedded_agent.graph.request_human_intervention", fake_human_intervention)

    result = human_guarded_node("plan", failing_node)(state)

    assert result["current_state"] == "thinkingmap"
