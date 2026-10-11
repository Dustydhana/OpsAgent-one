import agent
import chat_troubleshooting


def test_mutation_commands_are_blocked_but_diagnostic_questions_are_allowed():
    assert chat_troubleshooting.is_mutation_request("Start AWS-MS-OPSTESTVM")
    assert chat_troubleshooting.is_mutation_request("Please reboot the server")
    assert chat_troubleshooting.is_mutation_request("Take snapshot AWS-MS-OPSTESTVM")
    assert not chat_troubleshooting.is_mutation_request("Why did the server stop yesterday?")


def test_first_general_question_collects_read_only_summary():
    assert chat_troubleshooting.diagnostic_mode("Troubleshoot this VM") == "summary_query"
    assert chat_troubleshooting.diagnostic_mode("Check current CPU") == "cpu_query"
    assert chat_troubleshooting.diagnostic_mode("Is the server healthy?") == "summary_query"


def test_follow_up_reuses_context_until_target_or_mode_changes():
    result = {"host": "10.0.0.5", "request_mode": "cpu_query"}
    assert not chat_troubleshooting.needs_fresh_diagnostics(
        result, "10.0.0.5", "cpu_query", "What should we do?"
    )
    assert chat_troubleshooting.needs_fresh_diagnostics(
        result, "10.0.0.6", "cpu_query", "What should we do?"
    )
    assert chat_troubleshooting.needs_fresh_diagnostics(
        result, "10.0.0.5", "memory_query", "Check memory"
    )


def test_chat_prompt_contains_recent_conversation():
    result = {
        "host": "10.0.0.5", "os_type": "windows", "verdict": "healthy",
        "diagnostics_before": {}, "diagnostics_after": {}, "agent_result": {},
    }
    prompt = agent._investigation_chat_prompt(
        result, "What next?",
        conversation_history=[{"role": "user", "content": "Check CPU"}],
    )
    assert "Recent troubleshooting conversation" in prompt[1]["content"]
    assert "User: Check CPU" in prompt[1]["content"]
