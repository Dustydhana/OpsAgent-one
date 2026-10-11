import slack_actions
import slack_handler


def _aws_record():
    return {
        "server_name": "AWS-MS-OPSTESTVM",
        "vm_type": "aws",
        "aws_instance_id": "i-0b803014af102ad61",
        "aws_region": "us-east-1",
    }


def test_parse_start_request_resolves_postgresql_inventory(monkeypatch):
    monkeypatch.setattr(
        slack_actions.server_inventory, "retrieve_for_alert", lambda _text: _aws_record()
    )
    result = slack_actions.parse_action_request(
        "<@U123BOT> start AWS-MS-OPSTESTVM"
    )
    assert result == {
        "action": "start_instance",
        "server_name": "AWS-MS-OPSTESTVM",
        "provider": "aws",
        "resource_id": "i-0b803014af102ad61",
        "region": "us-east-1",
    }


def test_question_about_stopped_server_is_not_an_action():
    assert slack_actions.parse_action_request("Why did AWS-MS-OPSTESTVM stop?") is None


def test_parse_snapshot_create_and_delete(monkeypatch):
    monkeypatch.setattr(
        slack_actions.server_inventory, "retrieve_for_alert", lambda _text: _aws_record()
    )
    create = slack_actions.parse_action_request(
        "<@U123BOT> take snapshot AWS-MS-OPSTESTVM"
    )
    assert create["action"] == "create_snapshot"
    assert create["resource_id"] == "i-0b803014af102ad61"
    delete = slack_actions.parse_action_request(
        "<@U123BOT> delete snapshot snap-0123456789abcdef0 region=us-east-1"
    )
    assert delete["action"] == "delete_snapshot"
    assert delete["snapshot_id"] == "snap-0123456789abcdef0"


def test_parse_delete_ebs_volume_request():
    result = slack_actions.parse_action_request(
        "<@U123BOT> delete EBS volume vol-0123456789abcdef0 region=us-east-1"
    )
    assert result == {
        "action": "delete_volume",
        "server_name": "EBS Volume",
        "provider": "aws",
        "resource_id": "vol-0123456789abcdef0",
        "volume_id": "vol-0123456789abcdef0",
        "region": "us-east-1",
    }


def test_parse_approval_requires_exact_command():
    assert slack_actions.parse_approval("APPROVE SLK-12AB34CD") == "SLK-12AB34CD"
    assert slack_actions.parse_approval("<@U123BOT> APPROVE SLK-12AB34CD") == "SLK-12AB34CD"
    assert slack_actions.parse_approval("`APPROVE SLK-12AB34CD`") == "SLK-12AB34CD"
    assert slack_actions.parse_approval("please approve SLK-12AB34CD") is None


def test_unmentioned_action_is_not_handled(monkeypatch):
    monkeypatch.setattr(
        slack_actions, "parse_action_request", lambda _text: {"action": "start_instance"}
    )
    assert not slack_actions.handle_message(
        "start AWS-MS-OPSTESTVM", "C123", "1.2", "U123", mentioned=False
    )


def test_guarded_action_routing_happens_before_alert_keywords():
    calls = []

    class Logger:
        def exception(self, message):
            raise AssertionError(message)

    slack_handler._handle_incoming_text(
        "<@U123BOT> start server AWS-MS-OPSTESTVM",
        "C123", "1.2", Logger(),
        lambda *_args, **_kwargs: calls.append("alert"),
        on_action=lambda *_args, **_kwargs: calls.append("action") or True,
        force_mention=True, requester="U123",
    )
    assert calls == ["action"]
