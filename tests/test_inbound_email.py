import inbound_email


def test_parse_basic_aws_request():
    result = inbound_email.parse_request("AWS REQUEST stop_instance i-0b803014af102ad61")
    assert result == {"action": "stop_instance", "identifier": "i-0b803014af102ad61", "params": {}}


def test_parse_resize_parameters():
    result = inbound_email.parse_request(
        "AWS REQUEST resize_instance i-0b803014af102ad61 instance_type=t3.large"
    )
    assert result["params"]["instance_type"] == "t3.large"


def test_reject_unknown_action():
    assert inbound_email.parse_request("AWS REQUEST delete_everything i-0b803014af102ad61") is None


def test_natural_start_resolves_inventory(monkeypatch):
    record = {"server_name": "win-demo", "ip_address": "10.0.0.5", "public_ip_address": "",
              "private_ip_address": "10.0.0.5", "vm_type": "aws", "aws_instance_id": "i-0123456789abcdef0"}
    monkeypatch.setattr(inbound_email.server_inventory, "load", lambda: [record])
    result, candidates = inbound_email.parse_natural_request("Please start win-demo")
    assert not candidates
    assert result["action"] == "start_instance"
    assert result["identifier"] == "i-0123456789abcdef0"


def test_question_does_not_become_stop_request():
    result, _ = inbound_email.parse_natural_request("Why did the server stop yesterday?")
    assert result is None


def test_parse_snapshot_requests():
    create = inbound_email.parse_request(
        "AWS REQUEST create_snapshot i-0b803014af102ad61 volume_id=vol-0123456789abcdef0"
    )
    assert create["action"] == "create_snapshot"
    assert create["params"]["volume_id"] == "vol-0123456789abcdef0"
    delete = inbound_email.parse_request(
        "AWS REQUEST delete_snapshot snap-0123456789abcdef0"
    )
    assert delete["params"]["snapshot_id"] == "snap-0123456789abcdef0"


def test_parse_delete_ebs_volume_requests():
    structured = inbound_email.parse_request(
        "AWS REQUEST delete_volume vol-0123456789abcdef0"
    )
    assert structured == {
        "action": "delete_volume",
        "identifier": "vol-0123456789abcdef0",
        "params": {"volume_id": "vol-0123456789abcdef0"},
    }
    natural, candidates = inbound_email.parse_natural_request(
        "Please delete EBS volume vol-0123456789abcdef0"
    )
    assert not candidates
    assert natural["action"] == "delete_volume"
    assert natural["identifier"] == "vol-0123456789abcdef0"
