import agent


def test_offline_chat_greeting_does_not_expose_sdk_error(monkeypatch):
    monkeypatch.setattr(agent.config, "OPENAI_API_KEY", None)
    answer = agent.answer_infrastructure_question("hi")
    assert answer.startswith("Hi!")
    assert "api_key" not in answer


def test_offline_chat_summarizes_inventory(monkeypatch):
    monkeypatch.setattr(agent.config, "OPENAI_API_KEY", None)
    answer = agent.answer_infrastructure_question(
        "summarize server inventory",
        [{"status": "running", "vm_type": "aws"}, {"status": "stopped", "vm_type": "vmware"}],
    )
    assert "2 assets" in answer
    assert "1 report" in answer


def test_offline_hardware_answer_reports_missing_connector(monkeypatch):
    monkeypatch.setattr(agent.config, "OPENAI_API_KEY", None)
    monkeypatch.setattr(agent.hardware_monitoring, "dashboard", lambda: {
        "summary": {"chassis": 0, "blades": 0, "healthy_blades": 0, "active_alerts": 0},
        "connector": {"configured": False},
    })
    answer = agent.answer_infrastructure_question("summarize chassis and blade health")
    assert "No live hardware connector" in answer
