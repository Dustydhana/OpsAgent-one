from datetime import datetime, timedelta, timezone

import config
import sccm_operations


def _times():
    available = datetime.now(timezone.utc) + timedelta(days=1)
    return available.isoformat(), (available + timedelta(hours=2)).isoformat()


def _create(client, **overrides):
    available, deadline = _times()
    values = {
        "name": "September Test Day 1",
        "collection": "OPSAGENT-TEST-D1",
        "software_update_group": "2026-09 Security Updates",
        "batch": "test-day-1",
        "available_at": available,
        "deadline_at": deadline,
        "approved": True,
        "client": client,
    }
    values.update(overrides)
    return sccm_operations.create_patch_deployment(**values)


def setup_function():
    config.SCCM_MODE = "simulation"
    config.SCCM_ALLOWED_ACTIONS = {"create_patch_deployment"}
    config.SCCM_ALLOW_REBOOT = False
    config.SCCM_SIMULATED_COLLECTIONS = ("OPSAGENT-TEST-D1",)


def test_deployment_requires_approval():
    result = _create(sccm_operations.SimulatedSCCMClient(), approved=False)
    assert not result["success"]
    assert "approval" in result["error"].lower()


def test_collection_must_be_allowlisted():
    result = _create(sccm_operations.SimulatedSCCMClient(), collection="PRODUCTION-ALL")
    assert not result["success"]
    assert "allowlisted" in result["error"]


def test_reboot_is_suppressed_by_default():
    result = _create(sccm_operations.SimulatedSCCMClient(), allow_reboot=True)
    assert not result["success"]
    assert "SCCM_ALLOW_REBOOT" in result["error"]


def test_create_and_monitor_deployment():
    client = sccm_operations.SimulatedSCCMClient()
    result = _create(client)
    assert result["success"]
    deployment_id = result["deployment"]["deployment_id"]
    assert result["deployment"]["allow_reboot"] is False

    client.set_compliance(deployment_id, compliant=4, pending_reboot=1)
    compliance = sccm_operations.get_compliance(deployment_id, client=client)
    assert compliance["deployment"]["status"] == "patched_reboot_deferred"
    assert compliance["deployment"]["compliant"] == 4


def test_deadline_must_follow_available_time():
    available, deadline = _times()
    result = _create(
        sccm_operations.SimulatedSCCMClient(),
        available_at=deadline,
        deadline_at=available,
    )
    assert not result["success"]
    assert "deadline" in result["error"].lower()
