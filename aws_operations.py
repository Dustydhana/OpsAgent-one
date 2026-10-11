"""Guarded AWS EC2 control-plane operations for OpsAgent.

The module deliberately keeps AWS mutations outside the LLM tool loop. Every
change requires an explicit approval from the caller and an environment
allowlist entry, and every attempt is appended to an audit log.
"""

import os
import time
from datetime import datetime, timezone
from uuid import uuid4

import config
import database
import ops_log

try:
    import boto3
    from botocore.exceptions import ClientError
except ImportError:  # Allows the rest of OpsAgent to run without AWS extras.
    boto3 = None
    ClientError = Exception


MUTATING_ACTIONS = {
    "start_instance", "stop_instance", "reboot_instance", "resize_instance",
    "extend_volume", "detach_secondary_nic", "terminate_instance",
    "create_snapshot", "delete_snapshot", "delete_volume", "provision_instance",
}

AMI_FILTERS = {
    "Windows Server 2022": "Windows_Server-2022-English-Full-Base-*",
    "Windows Server 2025": "Windows_Server-2025-English-Full-Base-*",
    "Amazon Linux 2023": "al2023-ami-2023.*-x86_64",
    "Ubuntu Server 24.04 LTS": "ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*",
    "Red Hat Enterprise Linux 9": "RHEL-9.*_HVM-*-x86_64-*-Hourly2-GP3",
}
AMI_OWNERS = {"Ubuntu Server 24.04 LTS": "099720109477", "Red Hat Enterprise Linux 9": "309956199498"}


def _session():
    if boto3 is None:
        raise RuntimeError("boto3 is not installed; run pip install -r requirements.txt")
    profile = str(config.AWS_PROFILE or "").strip()
    if profile in {"", "()"}:
        # An empty AWS_PROFILE environment variable makes botocore search for
        # a profile literally named "()" instead of using the EC2 IAM role.
        os.environ.pop("AWS_PROFILE", None)
        if not os.environ.get("AWS_DEFAULT_PROFILE", "").strip():
            os.environ.pop("AWS_DEFAULT_PROFILE", None)
        session = boto3.Session()
    else:
        session = boto3.Session(profile_name=profile)
    if not config.AWS_ROLE_ARN:
        return session
    assume = {
        "RoleArn": config.AWS_ROLE_ARN,
        "RoleSessionName": config.AWS_ROLE_SESSION_NAME or "opsagent-connector",
    }
    if config.AWS_EXTERNAL_ID:
        assume["ExternalId"] = config.AWS_EXTERNAL_ID
    credentials = session.client("sts", region_name=config.AWS_REGION).assume_role(**assume)["Credentials"]
    return boto3.Session(
        aws_access_key_id=credentials["AccessKeyId"],
        aws_secret_access_key=credentials["SecretAccessKey"],
        aws_session_token=credentials["SessionToken"],
        region_name=config.AWS_REGION,
    )


def _client(region=None):
    return _session().client("ec2", region_name=region or config.AWS_REGION)


def connection_status():
    """Validate the configured credential chain without returning secrets."""
    session = _session()
    identity = session.client("sts", region_name=config.AWS_REGION).get_caller_identity()
    _client(config.AWS_REGION).describe_instances(MaxResults=5)
    return {
        "connected": True,
        "account_id": identity.get("Account"),
        "principal_arn": identity.get("Arn"),
        "region": config.AWS_REGION,
        "regions": list(config.AWS_INVENTORY_REGIONS),
        "authentication": "cross_account_role" if config.AWS_ROLE_ARN else ("profile" if config.AWS_PROFILE else "default_credential_chain"),
        "role_arn": config.AWS_ROLE_ARN or None,
    }


def instance_status(instance_id, region=None):
    """Return the current EC2 state so the UI can verify lifecycle operations."""
    response = _client(region).describe_instances(InstanceIds=[instance_id])
    reservations = response.get("Reservations", [])
    instances = reservations[0].get("Instances", []) if reservations else []
    status = instances[0].get("State", {}).get("Name", "unknown") if instances else "not-found"
    return {"instance_id": instance_id, "status": status}


def _safe_error(value, limit=800):
    text = str(value or "").strip()
    if "Encoded authorization failure message:" in text:
        text = text.split("Encoded authorization failure message:", 1)[0].strip()
    return text[:limit]


def _aws_request_id(response):
    return str((response or {}).get("ResponseMetadata", {}).get("RequestId") or "") or None


def _audit(action, target, approved, result, actor="unknown", *, request_id=None,
           source="unknown", requester=None, approver=None, started_at=None):
    completed_at = datetime.now(timezone.utc)
    started_at = started_at or completed_at
    duration_ms = max(0, int((completed_at - started_at).total_seconds() * 1000))
    database.initialize()
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""INSERT INTO ops_agent.cloud_operation_audit
                (provider,actor,action,target,approved,dry_run,success,instance_id,
                 volume_id,snapshot_id,message,error_message,request_id,source,requester,
                 approver,started_at,completed_at,duration_ms,before_status,after_status,
                 aws_request_id)
                VALUES ('aws',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (actor, action, target, bool(approved), config.AWS_DRY_RUN,
                 result.get("success"), result.get("instance_id"), result.get("volume_id"),
                 result.get("snapshot_id"), result.get("message"), _safe_error(result.get("error")),
                 request_id, source or "unknown", requester, approver, started_at, completed_at,
                 duration_ms, result.get("before_status"), result.get("after_status"),
                 result.get("aws_request_id")))
        connection.commit()


def _record(action, target, approved, result, actor, context, started_at):
    result["request_id"] = context["request_id"]
    _audit(action, target, approved, result, actor, started_at=started_at, **context)
    succeeded = bool(result.get("success"))
    event = "operation_completed" if succeeded else "operation_failed"
    level = "INFO" if succeeded else "ERROR"
    details = (
        f"action={action}; target={target}; source={context['source']}; "
        f"requester={context['requester'] or 'unknown'}; approver={context['approver'] or 'none'}"
    )
    if result.get("snapshot_id"):
        details += f"; snapshot={result['snapshot_id']}"
    if result.get("volume_id"):
        details += f"; volume={result['volume_id']}"
    if result.get("error"):
        details += f"; error={_safe_error(result['error'], 300)}"
    ops_log.write("aws", level, event, details, context["request_id"])


def audit_summary(hours=24, organization_id=None):
    organization_id = str(organization_id or config.DEFAULT_ORGANIZATION_ID or "").strip()
    database.initialize()
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""SELECT COUNT(*),
                COUNT(*) FILTER (WHERE success IS TRUE),
                COUNT(*) FILTER (WHERE success IS FALSE),
                COUNT(*) FILTER (WHERE success IS NULL)
                FROM ops_agent.cloud_operation_audit
                WHERE organization_id=%s AND occurred_at >= NOW() - (%s * INTERVAL '1 hour')""", (organization_id,max(1, int(hours))))
            total, succeeded, failed, unknown = cursor.fetchone()
    return {"total": total, "succeeded": succeeded, "failed": failed, "unknown": unknown}


def audit_recent(hours=24, limit=100, organization_id=None):
    organization_id = str(organization_id or config.DEFAULT_ORGANIZATION_ID or "").strip()
    database.initialize()
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""SELECT occurred_at,request_id,source,requester,approver,actor,
                action,target,approved,dry_run,success,before_status,after_status,instance_id,
                volume_id,snapshot_id,duration_ms,aws_request_id,error_message
                FROM ops_agent.cloud_operation_audit
                WHERE organization_id=%s AND occurred_at >= NOW() - (%s * INTERVAL '1 hour')
                ORDER BY occurred_at DESC LIMIT %s""",
                (organization_id,max(1, int(hours)), max(1, min(int(limit), 1000))))
            rows = cursor.fetchall()
    output = []
    for row in rows:
        success = row[10]
        output.append({
            "Time": row[0].astimezone().strftime("%Y-%m-%d %H:%M:%S"),
            "Request ID": row[1] or "", "Source": row[2] or "unknown",
            "Requester": row[3] or row[5] or "unknown", "Approver": row[4] or "",
            "Action": row[6], "Target": row[7], "Approved": row[8], "Mode": "Dry run" if row[9] else "Live",
            "Status": "Succeeded" if success is True else "Failed" if success is False else "Unknown",
            "Before": row[11] or "", "After": row[12] or "", "Instance ID": row[13] or "",
            "Volume ID": row[14] or "", "Snapshot ID": row[15] or "",
            "Duration ms": row[16], "AWS Request ID": row[17] or "", "Error": row[18] or "",
        })
    return output


def _guard(action, approved):
    if action not in MUTATING_ACTIONS:
        raise ValueError(f"Unknown AWS action: {action}")
    if not approved:
        raise PermissionError("Explicit human approval is required")
    if action not in config.AWS_ALLOWED_ACTIONS:
        raise PermissionError(f"{action} is not present in AWS_ALLOWED_ACTIONS")


def resolve_instance(identifier, region=None, client=None):
    """Resolve an exact instance ID, private/public IP, DNS name, or Name tag."""
    ec2 = client or _client(region)
    value = str(identifier or "").strip()
    if not value:
        raise ValueError("AWS instance identifier is required")
    if value.startswith("i-"):
        response = ec2.describe_instances(InstanceIds=[value])
    else:
        filters = [{"Name": "instance-state-name", "Values": ["pending", "running", "stopping", "stopped"]}]
        candidates = [
            ("private-ip-address", value), ("ip-address", value),
            ("private-dns-name", value), ("dns-name", value), ("tag:Name", value),
        ]
        matches = []
        for name, candidate in candidates:
            response = ec2.describe_instances(Filters=filters + [{"Name": name, "Values": [candidate]}])
            matches.extend(i for r in response.get("Reservations", []) for i in r.get("Instances", []))
        unique = {item["InstanceId"]: item for item in matches}
        if len(unique) != 1:
            raise ValueError(f"Expected exactly one AWS instance for {value!r}; found {len(unique)}")
        return next(iter(unique.values()))
    instances = [i for r in response.get("Reservations", []) for i in r.get("Instances", [])]
    if len(instances) != 1:
        raise ValueError(f"AWS instance {value!r} was not found")
    return instances[0]


def describe_instance(identifier, region=None, client=None):
    instance = resolve_instance(identifier, region, client)
    return {
        "instance_id": instance["InstanceId"],
        "state": instance.get("State", {}).get("Name"),
        "instance_type": instance.get("InstanceType"),
        "private_ip": instance.get("PrivateIpAddress"),
        "public_ip": instance.get("PublicIpAddress"),
        "availability_zone": instance.get("Placement", {}).get("AvailabilityZone"),
        "volumes": [item.get("Ebs", {}).get("VolumeId") for item in instance.get("BlockDeviceMappings", [])],
        "network_interfaces": [
            {"network_interface_id": nic.get("NetworkInterfaceId"),
             "device_index": nic.get("Attachment", {}).get("DeviceIndex"),
             "attachment_id": nic.get("Attachment", {}).get("AttachmentId")}
            for nic in instance.get("NetworkInterfaces", [])
        ],
    }


def termination_protection(identifier, region=None, client=None):
    ec2 = client or _client(region)
    instance = resolve_instance(identifier, region, ec2)
    response = ec2.describe_instance_attribute(InstanceId=instance["InstanceId"], Attribute="disableApiTermination")
    return bool(response.get("DisableApiTermination", {}).get("Value", False))


def describe_volume(volume_id, region=None, client=None):
    ec2 = client or _client(region)
    response = ec2.describe_volumes(VolumeIds=[str(volume_id or "").strip()])
    volumes = response.get("Volumes", [])
    if len(volumes) != 1:
        raise ValueError(f"EBS volume {volume_id!r} was not found")
    volume = volumes[0]
    return {
        "volume_id": volume.get("VolumeId"), "state": volume.get("State"),
        "size_gib": volume.get("Size"), "availability_zone": volume.get("AvailabilityZone"),
        "attachments": [
            {"instance_id": item.get("InstanceId"), "device": item.get("Device"),
             "state": item.get("State"), "delete_on_termination": item.get("DeleteOnTermination")}
            for item in volume.get("Attachments", [])
        ],
        "tags": {item.get("Key"): item.get("Value") for item in volume.get("Tags", []) if item.get("Key")},
    }


def describe_snapshot(snapshot_id, region=None, client=None):
    ec2 = client or _client(region)
    value = str(snapshot_id or "").strip()
    if not value.startswith("snap-"):
        raise ValueError("An exact EBS snapshot ID beginning with snap- is required")
    response = ec2.describe_snapshots(SnapshotIds=[value])
    snapshots = response.get("Snapshots", [])
    if len(snapshots) != 1:
        raise ValueError(f"EBS snapshot {value!r} was not found")
    snapshot = snapshots[0]
    return {
        "snapshot_id": snapshot.get("SnapshotId"), "state": snapshot.get("State"),
        "volume_id": snapshot.get("VolumeId"), "volume_size_gib": snapshot.get("VolumeSize"),
        "progress": snapshot.get("Progress"), "description": snapshot.get("Description"),
    }


def _resolve_provisioning(spec, region=None, client=None):
    """Resolve friendly form values into exact AWS resource identifiers."""
    ec2 = client or _client(region)
    os_name = str(spec.get("os") or "").strip()
    if os_name not in AMI_FILTERS:
        raise ValueError(f"Unsupported operating system: {os_name}")
    images = ec2.describe_images(
        Owners=[AMI_OWNERS.get(os_name, "amazon")],
        Filters=[
            {"Name": "name", "Values": [AMI_FILTERS[os_name]]},
            {"Name": "state", "Values": ["available"]},
            {"Name": "architecture", "Values": ["x86_64"]},
            {"Name": "root-device-type", "Values": ["ebs"]},
        ],
    ).get("Images", [])
    if not images:
        raise ValueError(f"No approved AMI found for {os_name} in {region or config.AWS_REGION}")
    image = max(images, key=lambda item: item.get("CreationDate", ""))
    existing = ec2.describe_instances(Filters=[
        {"Name": "tag:Name", "Values": [str(spec.get("name") or "").strip()]},
        {"Name": "instance-state-name", "Values": ["pending", "running", "stopping", "stopped"]},
    ]).get("Reservations", [])
    if any(reservation.get("Instances") for reservation in existing):
        raise ValueError(f"An active instance named {spec.get('name')!r} already exists")
    vpc_value = str(spec.get("vpc") or "Default VPC").strip()
    vpc_filters = [{"Name": "is-default", "Values": ["true"]}] if vpc_value == "Default VPC" else ([{"Name": "vpc-id", "Values": [vpc_value]}] if vpc_value.startswith("vpc-") else [{"Name": "tag:Name", "Values": [vpc_value]}])
    vpcs = ec2.describe_vpcs(Filters=vpc_filters).get("Vpcs", [])
    if len(vpcs) != 1:
        raise ValueError(f"Expected one VPC for {vpc_value!r}; found {len(vpcs)}")
    vpc_id = vpcs[0]["VpcId"]
    subnet_value = str(spec.get("subnet") or "Auto-select private subnet").strip()
    subnet_filters = [{"Name": "vpc-id", "Values": [vpc_id]}, {"Name": "state", "Values": ["available"]}]
    if subnet_value.startswith("subnet-"):
        subnet_filters.append({"Name": "subnet-id", "Values": [subnet_value]})
    subnets = ec2.describe_subnets(Filters=subnet_filters).get("Subnets", [])
    if not subnets:
        raise ValueError(f"No available subnet found in {vpc_id}")
    if subnet_value.startswith("Auto-select private"):
        private = [item for item in subnets if not item.get("MapPublicIpOnLaunch", False)]
        subnets = private or subnets
    subnet = sorted(subnets, key=lambda item: (-int(item.get("AvailableIpAddressCount", 0)), item["SubnetId"]))[0]
    security_value = str(spec.get("security_group") or "").strip()
    sg_filters = [{"Name": "vpc-id", "Values": [vpc_id]}]
    if security_value.startswith("sg-"):
        sg_filters.append({"Name": "group-id", "Values": [security_value]})
    else:
        group_name = "OpsAgentManaged" if security_value == "OpsAgent managed security group" else security_value
        sg_filters.append({"Name": "group-name", "Values": [group_name or "default"]})
    groups = ec2.describe_security_groups(Filters=sg_filters).get("SecurityGroups", [])
    if len(groups) != 1:
        raise ValueError(f"Expected one security group for {security_value!r}; found {len(groups)}. Select an existing group ID.")
    return {"ami_id": image["ImageId"], "ami_name": image.get("Name"), "root_device_name": image.get("RootDeviceName") or "/dev/sda1", "vpc_id": vpc_id, "subnet_id": subnet["SubnetId"], "security_group_id": groups[0]["GroupId"]}


def preview_provision(spec, region=None, client=None):
    resolved = _resolve_provisioning(spec, region, client)
    name = str(spec.get("name") or "").strip()
    if not name or len(name) > 128:
        raise ValueError("Instance name is required and must be at most 128 characters")
    instance_type = str(spec.get("instance_type") or "t3.medium")
    if instance_type not in {"t3.small", "t3.medium", "t3.large", "m6i.large", "m6i.xlarge"}:
        raise ValueError("Instance type is not in the OpsAgent allowlist")
    size = int(spec.get("storage_gib") or 80)
    if size < 30 or size > 2048:
        raise ValueError("Root storage must be between 30 and 2048 GiB")
    key_name = str(spec.get("key_name") or "").strip() or None
    if key_name:
        keys = (client or _client(region)).describe_key_pairs(KeyNames=[key_name]).get("KeyPairs", [])
        if len(keys) != 1:
            raise ValueError(f"AWS key pair {key_name!r} was not found")
    return {**resolved, "name": name, "region": region or config.AWS_REGION, "os": spec.get("os"), "instance_type": instance_type, "storage_gib": size, "environment": str(spec.get("environment") or "Development"), "instance_profile": str(spec.get("instance_profile") or "OpsAgentManagedInstanceProfile"), "key_name": key_name, "approval_phrase": f"APPROVE PROVISION {name}"}


def provisioning_options(region=None, client=None):
    """Return selectable network resources from the connected customer account."""
    ec2 = client or _client(region)
    vpcs = ec2.describe_vpcs().get("Vpcs", [])
    subnets = ec2.describe_subnets(Filters=[{"Name": "state", "Values": ["available"]}]).get("Subnets", [])
    groups = ec2.describe_security_groups().get("SecurityGroups", [])
    keys = ec2.describe_key_pairs().get("KeyPairs", [])
    name = lambda item: next((tag.get("Value") for tag in item.get("Tags", []) if tag.get("Key") == "Name"), "")
    return {
        "region": region or config.AWS_REGION,
        "vpcs": [{"id": item["VpcId"], "name": name(item) or ("Default VPC" if item.get("IsDefault") else item["VpcId"]), "cidr": item.get("CidrBlock")} for item in vpcs],
        "subnets": [{"id": item["SubnetId"], "name": name(item) or item["SubnetId"], "vpc_id": item["VpcId"], "zone": item.get("AvailabilityZone"), "public": bool(item.get("MapPublicIpOnLaunch"))} for item in subnets],
        "security_groups": [{"id": item["GroupId"], "name": item.get("GroupName") or item["GroupId"], "vpc_id": item.get("VpcId")} for item in groups],
        "key_pairs": [{"name": item["KeyName"], "id": item.get("KeyPairId")} for item in keys],
    }


def provision_instance(spec, approved=False, actor="unknown", requester=None, approver=None, source="enterprise_api", region=None, client=None):
    """Provision one tagged EC2 instance after deterministic validation and approval."""
    _guard("provision_instance", approved)
    started_at = datetime.now(timezone.utc)
    context = {"request_id": str(uuid4()), "source": source, "requester": requester, "approver": approver}
    target = str(spec.get("name") or "new-instance")
    try:
        preview = preview_provision(spec, region, client)
        ec2 = client or _client(preview["region"])
        tags = [
            {"Key": "Name", "Value": preview["name"]},
            {"Key": "Environment", "Value": preview["environment"]},
            {"Key": "OpsAgentManaged", "Value": "true"},
            {"Key": "ManagedBy", "Value": "OpsAgent"},
        ]
        response = ec2.run_instances(ImageId=preview["ami_id"], MinCount=1, MaxCount=1,
            InstanceType=preview["instance_type"], SubnetId=preview["subnet_id"],
            SecurityGroupIds=[preview["security_group_id"]],
            IamInstanceProfile={"Name": preview["instance_profile"]},
            BlockDeviceMappings=[{"DeviceName": preview["root_device_name"], "Ebs": {"VolumeSize": preview["storage_gib"], "VolumeType": "gp3", "Encrypted": True, "DeleteOnTermination": True}}],
            TagSpecifications=[{"ResourceType": "instance", "Tags": tags}, {"ResourceType": "volume", "Tags": tags}],
            MetadataOptions={"HttpTokens": "required", "HttpEndpoint": "enabled"},
            **({"KeyName": preview["key_name"]} if preview.get("key_name") else {}),
            DryRun=config.AWS_DRY_RUN)
        instance_id = response["Instances"][0]["InstanceId"]
        if not config.AWS_DRY_RUN:
            ec2.get_waiter("instance_running").wait(InstanceIds=[instance_id], WaiterConfig={"Delay": 10, "MaxAttempts": 30})
        result = {"success": True, "instance_id": instance_id, "before_status": "absent", "after_status": "running" if not config.AWS_DRY_RUN else "dry-run", "message": "EC2 instance provisioned and tagged for OpsAgent management", "aws_request_id": _aws_request_id(response), "resolved": preview}
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "") if hasattr(exc, "response") else ""
        if config.AWS_DRY_RUN and code == "DryRunOperation":
            result = {"success": True, "dry_run": True, "before_status": "absent", "after_status": "dry_run_validated", "message": "AWS authorization and provisioning request validation succeeded"}
        else:
            result = {"success": False, "error": _safe_error(exc), "before_status": "absent", "after_status": "failed"}
    except Exception as exc:
        result = {"success": False, "error": _safe_error(exc), "before_status": "absent", "after_status": "failed"}
    _record("provision_instance", target, approved, result, actor, context, started_at)
    return result


def wait_for_snapshot_deleted(snapshot_id, region=None, timeout=120, poll_seconds=5):
    deadline = time.monotonic() + max(1, int(timeout))
    while time.monotonic() < deadline:
        try:
            last = describe_snapshot(snapshot_id, region)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "") if hasattr(exc, "response") else ""
            if code in {"InvalidSnapshot.NotFound", "InvalidSnapshotID.NotFound"}:
                return {"verified": True, "snapshot": None, "state": "deleted"}
            raise
        time.sleep(max(1, int(poll_seconds)))
    return {"verified": False, "snapshot": last, "state": last.get("state"),
            "error": f"Timed out after {timeout}s waiting for snapshot deletion"}


def wait_for_volume_deleted(volume_id, region=None, timeout=120, poll_seconds=5):
    deadline = time.monotonic() + max(1, int(timeout))
    last = None
    while time.monotonic() < deadline:
        try:
            last = describe_volume(volume_id, region)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "") if hasattr(exc, "response") else ""
            if code in {"InvalidVolume.NotFound", "InvalidVolumeID.NotFound"}:
                return {"verified": True, "volume": None, "state": "deleted"}
            raise
        time.sleep(max(1, int(poll_seconds)))
    return {"verified": False, "volume": last, "state": (last or {}).get("state"),
            "error": f"Timed out after {timeout}s waiting for volume deletion"}


def wait_for_instance_state(identifier, expected_state, region=None, timeout=120, poll_seconds=5):
    """Poll EC2 until a start/stop action reaches its expected terminal state."""
    deadline = time.monotonic() + max(1, int(timeout))
    last = None
    while time.monotonic() < deadline:
        last = describe_instance(identifier, region)
        if last.get("state") == expected_state:
            return {"verified": True, "expected_state": expected_state, "instance": last}
        time.sleep(max(1, int(poll_seconds)))
    return {"verified": False, "expected_state": expected_state, "instance": last,
            "error": f"Timed out after {timeout}s waiting for {expected_state}"}


def execute(action, identifier, *, approved=False, actor="unknown", region=None,
            instance_type=None, volume_id=None, size_gib=None,
            network_interface_id=None, snapshot_id=None, description=None, client=None,
            request_id=None, source=None, requester=None, approver=None):
    """Execute one approved, allowlisted EC2 action and return an auditable result."""
    target = str(identifier or "")
    started_at = datetime.now(timezone.utc)
    request_id = str(request_id or f"AWS-{uuid4().hex[:10].upper()}")
    inferred_source = str(source or (str(actor).split(":", 1)[0] if ":" in str(actor) else "api"))
    context = {
        "request_id": request_id,
        "source": inferred_source,
        "requester": str(requester or actor or "unknown"),
        "approver": str(approver or actor or "") if approved else None,
    }
    ops_log.write(
        "aws", "INFO", "operation_started",
        f"action={action}; target={target}; source={inferred_source}; requester={context['requester']}",
        request_id,
    )
    try:
        _guard(action, approved)
        ec2 = client or _client(region)
        if action == "delete_volume":
            selected_volume = str(volume_id or identifier or "").strip()
            target = selected_volume
            if not selected_volume.startswith("vol-"):
                raise ValueError("An exact volume_id beginning with vol- is required")
            before = describe_volume(selected_volume, region, ec2)
            if before.get("state") != "available" or before.get("attachments"):
                raise ValueError("EBS volume must be detached and in the available state before deletion")
            required_key = config.AWS_DELETE_VOLUME_REQUIRED_TAG_KEY
            required_value = config.AWS_DELETE_VOLUME_REQUIRED_TAG_VALUE
            actual_value = (before.get("tags") or {}).get(required_key)
            if required_key and str(actual_value or "").casefold() != required_value.casefold():
                raise ValueError(
                    f"EBS volume must have tag {required_key}={required_value} before deletion"
                )
            response = ec2.delete_volume(VolumeId=selected_volume, DryRun=config.AWS_DRY_RUN)
            result = {"success": True, "action": action, "volume_id": selected_volume,
                      "dry_run": config.AWS_DRY_RUN, "before_status": before.get("state"),
                      "after_status": "delete_requested", "aws_request_id": _aws_request_id(response),
                      "response": response}
            _record(action, target, approved, result, actor, context, started_at)
            return result

        if action == "delete_snapshot":
            selected_snapshot = str(snapshot_id or identifier or "").strip()
            target = selected_snapshot
            if not selected_snapshot.startswith("snap-"):
                raise ValueError("An exact snapshot_id beginning with snap- is required")
            before = describe_snapshot(selected_snapshot, region, ec2)
            response = ec2.delete_snapshot(SnapshotId=selected_snapshot, DryRun=config.AWS_DRY_RUN)
            result = {"success": True, "action": action, "snapshot_id": selected_snapshot,
                      "volume_id": before.get("volume_id"), "dry_run": config.AWS_DRY_RUN,
                      "before_status": before.get("state"), "after_status": "delete_requested",
                      "aws_request_id": _aws_request_id(response), "response": response}
            _record(action, target, approved, result, actor, context, started_at)
            return result

        instance = resolve_instance(identifier, region, ec2)
        instance_id = instance["InstanceId"]
        before_status = instance.get("State", {}).get("Name")
        after_status = None
        kwargs = {"DryRun": config.AWS_DRY_RUN}
        if action == "create_snapshot":
            attached = [x.get("Ebs", {}).get("VolumeId") for x in instance.get("BlockDeviceMappings", [])]
            attached = [value for value in attached if value]
            selected_volume = str(volume_id or "").strip()
            if selected_volume and selected_volume not in attached:
                raise ValueError("The requested EBS volume is not attached to the selected instance")
            if not selected_volume:
                if len(attached) != 1:
                    raise ValueError("volume_id is required when the instance has zero or multiple EBS volumes")
                selected_volume = attached[0]
            describe_volume(selected_volume, region, ec2)
            snapshot_description = (description or f"OpsAgent snapshot for {instance_id}").strip()[:255]
            response = ec2.create_snapshot(
                VolumeId=selected_volume, Description=snapshot_description,
                TagSpecifications=[{"ResourceType": "snapshot", "Tags": [
                    {"Key": "CreatedBy", "Value": "OpsAgent"},
                    {"Key": "SourceInstance", "Value": instance_id},
                ]}], **kwargs,
            )
            after_status = response.get("State") or "snapshot_requested"
            result = {"success": True, "action": action, "instance_id": instance_id,
                      "volume_id": selected_volume, "snapshot_id": response.get("SnapshotId"),
                      "dry_run": config.AWS_DRY_RUN, "response": response}
        elif action == "start_instance":
            response = ec2.start_instances(InstanceIds=[instance_id], **kwargs)
            changes = response.get("StartingInstances", [])
            after_status = (changes[0].get("CurrentState", {}).get("Name") if changes else None) or "start_requested"
        elif action == "stop_instance":
            response = ec2.stop_instances(InstanceIds=[instance_id], **kwargs)
            changes = response.get("StoppingInstances", [])
            after_status = (changes[0].get("CurrentState", {}).get("Name") if changes else None) or "stop_requested"
        elif action == "reboot_instance":
            response = ec2.reboot_instances(InstanceIds=[instance_id], **kwargs)
            after_status = "reboot_requested"
        elif action == "resize_instance":
            if instance.get("State", {}).get("Name") != "stopped":
                raise ValueError("Instance must be stopped before changing its CPU/RAM instance type")
            if not instance_type:
                raise ValueError("instance_type is required")
            response = ec2.modify_instance_attribute(
                InstanceId=instance_id, InstanceType={"Value": instance_type}, **kwargs
            )
            after_status = "resize_requested"
        elif action == "extend_volume":
            if not volume_id or not size_gib or int(size_gib) <= 0:
                raise ValueError("volume_id and a positive size_gib are required")
            attached = {x.get("Ebs", {}).get("VolumeId") for x in instance.get("BlockDeviceMappings", [])}
            if volume_id not in attached:
                raise ValueError("The requested EBS volume is not attached to the selected instance")
            response = ec2.modify_volume(VolumeId=volume_id, Size=int(size_gib), **kwargs)
            after_status = "volume_modification_requested"
        elif action == "detach_secondary_nic":
            nic = next((n for n in instance.get("NetworkInterfaces", []) if n.get("NetworkInterfaceId") == network_interface_id), None)
            if not nic:
                raise ValueError("Network interface is not attached to the selected instance")
            if nic.get("Attachment", {}).get("DeviceIndex") == 0:
                raise ValueError("Refusing to detach the primary network interface")
            response = ec2.detach_network_interface(
                AttachmentId=nic["Attachment"]["AttachmentId"], Force=False, **kwargs
            )
            after_status = "detach_requested"
        elif action == "terminate_instance":
            response = ec2.terminate_instances(InstanceIds=[instance_id], **kwargs)
            changes = response.get("TerminatingInstances", [])
            after_status = (changes[0].get("CurrentState", {}).get("Name") if changes else None) or "termination_requested"
        result = {"success": True, "action": action, "instance_id": instance_id,
                  "volume_id": result.get("volume_id") if action == "create_snapshot" else None,
                  "snapshot_id": result.get("snapshot_id") if action == "create_snapshot" else None,
                  "dry_run": config.AWS_DRY_RUN, "before_status": before_status,
                  "after_status": after_status, "aws_request_id": _aws_request_id(response),
                  "response": response}
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "") if hasattr(exc, "response") else ""
        if config.AWS_DRY_RUN and code == "DryRunOperation":
            result = {"success": True, "action": action, "instance_id": target,
                      "dry_run": True, "message": "AWS authorization and request validation succeeded",
                      "after_status": "dry_run_validated"}
        else:
            result = {"success": False, "action": action, "error": _safe_error(exc)}
    except Exception as exc:
        result = {"success": False, "action": action, "error": _safe_error(exc)}
    _record(action, target, approved, result, actor, context, started_at)
    return result
