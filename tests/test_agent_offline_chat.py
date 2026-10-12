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


def test_chat_uses_organization_model_configuration(monkeypatch):
    captured = {}

    class Completions:
        def create(self, **values):
            captured.update(values)
            message = type("Message", (), {"content": "Configured model response"})()
            choice = type("Choice", (), {"message": message})()
            return type("Response", (), {"choices": [choice], "usage": None})()

    class Client:
        def __init__(self, **values):
            captured.update(values)
            self.chat = type("Chat", (), {"completions": Completions()})()

    monkeypatch.setattr(agent, "OpenAI", Client)
    monkeypatch.setattr(agent.ai_usage, "record", lambda *args, **kwargs: None)

    answer = agent.answer_infrastructure_question(
        "hello model",
        model_configuration={
            "api_key": "organization-key",
            "endpoint": "https://models.example.test/v1",
            "model": "organization-model",
        },
    )

    assert answer == "Configured model response"
    assert captured["api_key"] == "organization-key"
    assert captured["base_url"] == "https://models.example.test/v1"
    assert captured["model"] == "organization-model"
