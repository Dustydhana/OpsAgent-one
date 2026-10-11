import aws_operations
import config


def setup_function():
    # Persistence is covered by database integration tests; unit tests avoid PostgreSQL.
    aws_operations._audit = lambda *args, **kwargs: None
    aws_operations.ops_log.write = lambda *args, **kwargs: None


def test_customer_credentials_create_isolated_boto_session(monkeypatch):
    captured = {}

    class Session:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(aws_operations, "boto3", type("Boto", (), {"Session": Session}))
    session = aws_operations._session({
        "aws_access_key_id": "AKIA-CUSTOMER",
        "aws_secret_access_key": "customer-secret",
        "region": "ap-south-1",
    })

    assert isinstance(session, Session)
    assert captured == {
        "aws_access_key_id": "AKIA-CUSTOMER",
        "aws_secret_access_key": "customer-secret",
        "aws_session_token": None,
        "region_name": "ap-south-1",
    }


class FakeEC2:
    def __init__(self, state="running"):
        self.instance = {
            "InstanceId": "i-test", "State": {"Name": state}, "InstanceType": "t3.small",
            "BlockDeviceMappings": [{"Ebs": {"VolumeId": "vol-test"}}],
            "NetworkInterfaces": [
                {"NetworkInterfaceId": "eni-primary", "Attachment": {"DeviceIndex": 0, "AttachmentId": "attach-0"}},
                {"NetworkInterfaceId": "eni-secondary", "Attachment": {"DeviceIndex": 1, "AttachmentId": "attach-1"}},
            ],
        }
        self.called = None
        self.volume_state = "available"
        self.volume_tags = [{"Key": "OpsAgentDeletable", "Value": "true"}]
        self.volume_attachments = []

    def describe_instances(self, **_kwargs):
        return {"Reservations": [{"Instances": [self.instance]}]}

    def reboot_instances(self, **kwargs):
        self.called = ("reboot", kwargs)
        return {"ok": True}

    def modify_instance_attribute(self, **kwargs):
        self.called = ("resize", kwargs)
        return {"ok": True}

    def detach_network_interface(self, **kwargs):
        self.called = ("detach", kwargs)
        return {"ok": True}

    def describe_volumes(self, **kwargs):
        return {"Volumes": [{"VolumeId": kwargs["VolumeIds"][0], "State": self.volume_state,
                             "Size": 30, "AvailabilityZone": "us-east-1a",
                             "Tags": self.volume_tags, "Attachments": self.volume_attachments}]}

    def create_snapshot(self, **kwargs):
        self.called = ("create_snapshot", kwargs)
        return {"SnapshotId": "snap-0123456789abcdef0", "State": "pending"}

    def describe_snapshots(self, **kwargs):
        return {"Snapshots": [{"SnapshotId": kwargs["SnapshotIds"][0], "State": "completed",
                               "VolumeId": "vol-test", "VolumeSize": 30, "Progress": "100%"}]}

    def delete_snapshot(self, **kwargs):
        self.called = ("delete_snapshot", kwargs)
        return {"ok": True}

    def delete_volume(self, **kwargs):
        self.called = ("delete_volume", kwargs)
        return {"ok": True}


def _configure(monkeypatch, tmp_path, actions):
    monkeypatch.setattr(config, "AWS_ALLOWED_ACTIONS", set(actions))
    monkeypatch.setattr(config, "AWS_DRY_RUN", False)
    monkeypatch.setattr(config, "AWS_DELETE_VOLUME_REQUIRED_TAG_KEY", "OpsAgentDeletable")
    monkeypatch.setattr(config, "AWS_DELETE_VOLUME_REQUIRED_TAG_VALUE", "true")


def test_mutation_requires_human_approval(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path, {"reboot_instance"})
    result = aws_operations.execute("reboot_instance", "i-test", client=FakeEC2())
    assert not result["success"]
    assert "approval" in result["error"].lower()


def test_mutation_requires_allowlist(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path, set())
    result = aws_operations.execute("reboot_instance", "i-test", approved=True, client=FakeEC2())
    assert not result["success"]
    assert "execution policy" in result["error"]


def test_reboot_executes(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path, {"reboot_instance"})
    client = FakeEC2()
    result = aws_operations.execute("reboot_instance", "i-test", approved=True, actor="tester", client=client)
    assert result["success"] and client.called[0] == "reboot"


def test_operation_passes_channel_context_to_audit(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path, {"reboot_instance"})
    captured = {}
    events = []

    def capture(*_args, **kwargs):
        captured.update(kwargs)

    aws_operations._audit = capture
    aws_operations.ops_log.write = lambda _component, _level, event, *_args: events.append(event)
    result = aws_operations.execute(
        "reboot_instance", "i-test", approved=True, actor="slack:approver",
        request_id="SLK-TEST", source="slack", requester="requester",
        approver="approver", client=FakeEC2(),
    )

    assert result["request_id"] == "SLK-TEST"
    assert captured["request_id"] == "SLK-TEST"
    assert captured["source"] == "slack"
    assert captured["requester"] == "requester"
    assert captured["approver"] == "approver"
    assert events == ["operation_started", "operation_completed"]


def test_primary_nic_can_never_be_detached(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path, {"detach_secondary_nic"})
    result = aws_operations.execute(
        "detach_secondary_nic", "i-test", approved=True,
        network_interface_id="eni-primary", client=FakeEC2(),
    )
    assert not result["success"]
    assert "primary" in result["error"].lower()


def test_resize_requires_stopped_instance(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path, {"resize_instance"})
    result = aws_operations.execute(
        "resize_instance", "i-test", approved=True,
        instance_type="t3.large", client=FakeEC2(state="running"),
    )
    assert not result["success"]
    assert "stopped" in result["error"].lower()


def test_create_snapshot_uses_only_attached_volume(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path, {"create_snapshot"})
    client = FakeEC2()
    result = aws_operations.execute(
        "create_snapshot", "i-test", approved=True, client=client,
        volume_id="vol-test", description="approved backup",
    )
    assert result["success"]
    assert result["snapshot_id"] == "snap-0123456789abcdef0"
    assert client.called[0] == "create_snapshot"


def test_create_snapshot_rejects_unattached_volume(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path, {"create_snapshot"})
    result = aws_operations.execute(
        "create_snapshot", "i-test", approved=True, client=FakeEC2(),
        volume_id="vol-not-attached",
    )
    assert not result["success"]
    assert "not attached" in result["error"]


def test_delete_snapshot_requires_exact_id_and_approval(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path, {"delete_snapshot"})
    client = FakeEC2()
    denied = aws_operations.execute(
        "delete_snapshot", "snap-0123456789abcdef0", client=client
    )
    assert not denied["success"]
    result = aws_operations.execute(
        "delete_snapshot", "snap-0123456789abcdef0", approved=True, client=client
    )
    assert result["success"] and client.called[0] == "delete_snapshot"


def test_delete_volume_requires_available_tagged_volume(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path, {"delete_volume"})
    client = FakeEC2()
    result = aws_operations.execute(
        "delete_volume", "vol-0123456789abcdef0", approved=True,
        volume_id="vol-0123456789abcdef0", client=client,
    )
    assert result["success"]
    assert result["volume_id"] == "vol-0123456789abcdef0"
    assert client.called[0] == "delete_volume"


def test_delete_volume_rejects_attached_or_untagged_volume(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path, {"delete_volume"})
    attached = FakeEC2()
    attached.volume_state = "in-use"
    attached.volume_attachments = [{"InstanceId": "i-test", "Device": "/dev/sda1"}]
    result = aws_operations.execute(
        "delete_volume", "vol-0123456789abcdef0", approved=True, client=attached,
    )
    assert not result["success"] and "detached" in result["error"]

    untagged = FakeEC2()
    untagged.volume_tags = []
    result = aws_operations.execute(
        "delete_volume", "vol-0123456789abcdef0", approved=True, client=untagged,
    )
    assert not result["success"] and "OpsAgentDeletable=true" in result["error"]
