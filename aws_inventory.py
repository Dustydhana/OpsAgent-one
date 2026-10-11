"""Automatic, read-only AWS EC2 discovery and PostgreSQL inventory sync."""

import json
import threading
from datetime import timezone

import config
import database
import ops_log
import server_inventory
from aws_operations import _client, _session

try:
    from psycopg.rows import dict_row
except ImportError:
    dict_row = None

_START_LOCK = threading.Lock()
_STARTED = False
_STATUS = {"running": False, "last_sync": None, "last_error": None, "instances": 0}

def _org(value):
    value = str(value or config.DEFAULT_ORGANIZATION_ID or "").strip()
    if not value: raise ValueError("organization_id is required")
    return value


def _tags(values):
    return {str(x.get("Key")): str(x.get("Value", "")) for x in (values or []) if x.get("Key")}


def _optional_map(client, method, result_key, id_key, ids):
    if not ids:
        return {}
    try:
        response = getattr(client, method)(**{id_key: sorted(ids)})
        return {row.get(id_key[:-1] if id_key.endswith("s") else id_key): row
                for row in response.get(result_key, [])}
    except Exception:
        return {}


def _ssm_nodes(region):
    """Return managed-node OS details; missing SSM permission is non-fatal."""
    try:
        ssm = _session().client("ssm", region_name=region)
        pages = ssm.get_paginator("describe_instance_information").paginate()
        return {row["InstanceId"]: row for page in pages
                for row in page.get("InstanceInformationList", []) if row.get("InstanceId")}
    except Exception:
        return {}


def discover_region(region, client=None):
    """Return every non-terminated EC2 instance, including stopped instances."""
    ec2 = client or _client(region)
    try:
        pages = ec2.get_paginator("describe_instances").paginate(Filters=[{
            "Name": "instance-state-name", "Values": ["pending", "running", "stopping", "stopped"]
        }])
    except Exception:
        pages = [ec2.describe_instances(Filters=[{
            "Name": "instance-state-name", "Values": ["pending", "running", "stopping", "stopped"]
        }])]
    raw = [item for page in pages for reservation in page.get("Reservations", [])
           for item in reservation.get("Instances", [])]
    vpc_ids = {x.get("VpcId") for x in raw if x.get("VpcId")}
    subnet_ids = {x.get("SubnetId") for x in raw if x.get("SubnetId")}
    key_names = {x.get("KeyName") for x in raw if x.get("KeyName")}
    volume_ids = {mapping.get("Ebs", {}).get("VolumeId") for item in raw
                  for mapping in item.get("BlockDeviceMappings", []) if mapping.get("Ebs", {}).get("VolumeId")}
    vpcs = _optional_map(ec2, "describe_vpcs", "Vpcs", "VpcIds", vpc_ids)
    subnets = _optional_map(ec2, "describe_subnets", "Subnets", "SubnetIds", subnet_ids)
    try:
        keys = {x.get("KeyName"): x for x in ec2.describe_key_pairs(KeyNames=sorted(key_names)).get("KeyPairs", [])} if key_names else {}
    except Exception:
        keys = {}
    volumes = _optional_map(ec2, "describe_volumes", "Volumes", "VolumeIds", volume_ids)
    ssm_nodes = _ssm_nodes(region) if client is None else {}
    output = []
    for item in raw:
        tags = _tags(item.get("Tags"))
        vpc, subnet = vpcs.get(item.get("VpcId"), {}), subnets.get(item.get("SubnetId"), {})
        groups = item.get("SecurityGroups") or []
        block_devices = item.get("BlockDeviceMappings") or []
        profile = item.get("IamInstanceProfile") or {}
        ssm = ssm_nodes.get(item["InstanceId"], {})
        volume_details = []
        for mapping in block_devices:
            ebs = mapping.get("Ebs") or {}
            volume = volumes.get(ebs.get("VolumeId"), {})
            if not ebs.get("VolumeId"):
                continue
            volume_details.append({
                "volume_id": ebs.get("VolumeId"), "device": mapping.get("DeviceName"),
                "size_gib": volume.get("Size"), "volume_type": volume.get("VolumeType"),
                "iops": volume.get("Iops"), "throughput_mibps": volume.get("Throughput"),
                "encrypted": volume.get("Encrypted"), "state": volume.get("State"),
                "delete_on_termination": ebs.get("DeleteOnTermination"),
            })
        output.append({
            "region": region, "instance_id": item["InstanceId"], "name": tags.get("Name") or item["InstanceId"],
            "state": (item.get("State") or {}).get("Name", "unknown"), "instance_type": item.get("InstanceType"),
            "platform_details": item.get("PlatformDetails") or item.get("Platform") or "Linux/UNIX",
            "architecture": item.get("Architecture"), "image_id": item.get("ImageId"),
            "launch_time": item.get("LaunchTime"), "availability_zone": (item.get("Placement") or {}).get("AvailabilityZone"),
            "vpc_id": item.get("VpcId"), "vpc_name": _tags(vpc.get("Tags")).get("Name"), "vpc_cidr": vpc.get("CidrBlock"),
            "subnet_id": item.get("SubnetId"), "subnet_name": _tags(subnet.get("Tags")).get("Name"), "subnet_cidr": subnet.get("CidrBlock"),
            "private_ip": item.get("PrivateIpAddress"), "public_ip": item.get("PublicIpAddress"),
            "private_dns": item.get("PrivateDnsName"), "public_dns": item.get("PublicDnsName"),
            "ssm_computer_name": ssm.get("ComputerName"), "ssm_platform_name": ssm.get("PlatformName"),
            "ssm_platform_version": ssm.get("PlatformVersion"), "ssm_ping_status": ssm.get("PingStatus"),
            "ssm_agent_version": ssm.get("AgentVersion"),
            "key_name": item.get("KeyName"), "key_fingerprint": (keys.get(item.get("KeyName")) or {}).get("KeyFingerprint"),
            "iam_instance_profile_arn": profile.get("Arn"),
            "security_group_ids": [x.get("GroupId") for x in groups if x.get("GroupId")],
            "security_group_names": [x.get("GroupName") for x in groups if x.get("GroupName")],
            "volume_ids": [x.get("Ebs", {}).get("VolumeId") for x in block_devices if x.get("Ebs", {}).get("VolumeId")],
            "volume_details": volume_details,
            "network_interface_ids": [x.get("NetworkInterfaceId") for x in item.get("NetworkInterfaces", []) if x.get("NetworkInterfaceId")],
            "tags": [f"{key}={value}" for key, value in sorted(tags.items())], "environment": tags.get("Environment", "unknown"),
        })
    return output


_COLUMNS = ("region", "instance_id", "name", "state", "instance_type", "platform_details", "architecture",
            "image_id", "launch_time", "availability_zone", "vpc_id", "vpc_name", "vpc_cidr", "subnet_id",
            "subnet_name", "subnet_cidr", "private_ip", "public_ip", "private_dns", "public_dns", "key_name",
            "key_fingerprint", "iam_instance_profile_arn", "security_group_ids", "security_group_names", "volume_ids",
            "volume_details", "network_interface_ids", "tags", "ssm_computer_name", "ssm_platform_name",
            "ssm_platform_version", "ssm_ping_status", "ssm_agent_version")


def _persist(records, regions, organization_id=None):
    organization_id = _org(organization_id)
    database.initialize()
    with database.connect() as connection:
        with connection.cursor() as cursor:
            for row in records:
                values = [json.dumps(row.get(column) or []) if column == "volume_details" else row.get(column)
                          for column in _COLUMNS]
                placeholders = ["%s::jsonb" if column == "volume_details" else "%s" for column in _COLUMNS]
                cursor.execute(f"""INSERT INTO ops_agent.aws_ec2_inventory (organization_id,{','.join(_COLUMNS)})
                    VALUES (%s,{','.join(placeholders)}) ON CONFLICT (region,instance_id) DO UPDATE SET
                    {','.join(f'{c}=EXCLUDED.{c}' for c in _COLUMNS if c not in ('region','instance_id'))},last_seen_at=NOW()""", [organization_id, *values])
                # organization_id is immutable ownership for a globally unique EC2 instance ID.
                address = row.get("public_ip") or row.get("private_ip")
                if not address:
                    continue
                cursor.execute("SELECT server_name FROM ops_agent.server_inventory WHERE organization_id=%s AND aws_instance_id=%s AND aws_region=%s LIMIT 1",
                               (organization_id,row["instance_id"], row["region"]))
                existing = cursor.fetchone()
                if existing:
                    os_type = "windows" if "windows" in row["platform_details"].lower() else "linux"
                    os_version = " ".join(filter(None, [row.get("ssm_platform_name"), row.get("ssm_platform_version")])) or "Unavailable — enable AWS Systems Manager inventory"
                    cursor.execute("""UPDATE ops_agent.server_inventory SET ip_address=%s,public_ip_address=%s,
                        private_ip_address=%s,status=%s,enabled=TRUE,tags=%s,os_type=%s,os_version=%s,
                        private_dns_name=%s,public_dns_name=%s,host_name=%s,instance_type=%s,architecture=%s,
                        availability_zone=%s,vpc_id=%s,subnet_id=%s,storage_volumes=%s::jsonb WHERE organization_id=%s AND server_name=%s""",
                        (address, row.get("public_ip"), row.get("private_ip"), row["state"], row["tags"], os_type,
                         os_version, row.get("private_dns"), row.get("public_dns"), row.get("ssm_computer_name"),
                         row.get("instance_type"), row.get("architecture"), row.get("availability_zone"),
                         row.get("vpc_id"), row.get("subnet_id"), json.dumps(row.get("volume_details") or []),organization_id, existing[0]))
                else:
                    os_type = "windows" if "windows" in row["platform_details"].lower() else "linux"
                    os_version = " ".join(filter(None, [row.get("ssm_platform_name"), row.get("ssm_platform_version")])) or "Unavailable — enable AWS Systems Manager inventory"
                    cursor.execute("""INSERT INTO ops_agent.server_inventory
                        (organization_id,server_name,ip_address,public_ip_address,private_ip_address,status,enabled,vm_type,environment,
                         os_type,os_version,tags,aws_instance_id,aws_region,private_dns_name,public_dns_name,host_name,
                         instance_type,architecture,availability_zone,vpc_id,subnet_id,storage_volumes,notes)
                        VALUES (%s,%s,%s,%s,%s,%s,TRUE,'aws',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,'Automatically discovered from AWS EC2')
                        ON CONFLICT DO NOTHING""", (organization_id,row["name"], address, row.get("public_ip"), row.get("private_ip"),
                        row["state"], row["environment"].lower(), os_type, os_version, row["tags"],
                        row["instance_id"], row["region"], row.get("private_dns"), row.get("public_dns"),
                        row.get("ssm_computer_name"), row.get("instance_type"), row.get("architecture"),
                        row.get("availability_zone"), row.get("vpc_id"), row.get("subnet_id"),
                        json.dumps(row.get("volume_details") or [])))
            # Anything previously discovered in a successfully scanned region but
            # absent now is no longer active EC2 inventory. Preserve its lifecycle
            # evidence in the audit table, while removing it from active views.
            for region in regions:
                seen_ids = [row["instance_id"] for row in records if row["region"] == region]
                cursor.execute(
                    "SELECT instance_id FROM ops_agent.aws_ec2_inventory WHERE organization_id=%s AND region=%s AND NOT (instance_id=ANY(%s))",
                    (organization_id,region, seen_ids),
                )
                retired_ids = [row[0] for row in cursor.fetchall()]
                if not retired_ids:
                    continue
                cursor.execute(
                    "UPDATE ops_agent.server_inventory SET status='terminated',enabled=FALSE "
                    "WHERE organization_id=%s AND vm_type='aws' AND aws_region=%s AND aws_instance_id=ANY(%s)",
                    (organization_id,region, retired_ids),
                )
                cursor.execute(
                    "UPDATE ops_agent.cloud_operation_audit SET after_status='terminated' "
                    "WHERE organization_id=%s AND provider='aws' AND action='terminate_instance' AND success=TRUE "
                    "AND instance_id=ANY(%s) AND after_status<>'terminated'",
                    (organization_id,retired_ids,),
                )
                cursor.execute(
                    "DELETE FROM ops_agent.aws_ec2_inventory WHERE organization_id=%s AND region=%s AND instance_id=ANY(%s)",
                    (organization_id,region, retired_ids),
                )
        connection.commit()
    server_inventory.invalidate_cache(organization_id)


def sync(regions=None, organization_id=None):
    selected = tuple(regions or config.AWS_INVENTORY_REGIONS)
    records = []
    for region in selected:
        records.extend(discover_region(region))
    _persist(records, selected, organization_id)
    _STATUS.update(last_sync=__import__("datetime").datetime.now(timezone.utc), last_error=None, instances=len(records))
    return records


def list_inventory(organization_id=None):
    organization_id = _org(organization_id)
    database.initialize()
    with database.connect(row_factory=dict_row) as connection:
        with connection.cursor() as cursor:
            cursor.execute("""SELECT aws.*,
                COALESCE(servers.application, 'Unknown') AS application_name,
                COALESCE(servers.application_team, 'Unknown') AS application_team,
                COALESCE(servers.important_services, '{}') AS important_services,
                COALESCE(servers.server_team, 'Unknown') AS server_team,
                COALESCE(servers.environment, 'unknown') AS environment
                FROM ops_agent.aws_ec2_inventory aws
                LEFT JOIN ops_agent.server_inventory servers
                  ON servers.aws_instance_id = aws.instance_id
                 AND servers.aws_region = aws.region AND servers.organization_id=aws.organization_id
                WHERE aws.organization_id=%s
                ORDER BY aws.region,aws.name,aws.instance_id""", (organization_id,))
            return [dict(row) for row in cursor.fetchall()]


def status():
    return dict(_STATUS)


def _worker():
    _STATUS["running"] = True
    while True:
        try:
            sync()
        except Exception as exc:
            _STATUS["last_error"] = f"{type(exc).__name__}: {exc}"
            ops_log.write("aws_inventory", "ERROR", "sync_failed", _STATUS["last_error"])
        threading.Event().wait(config.AWS_INVENTORY_SYNC_INTERVAL_SECONDS)


def start():
    global _STARTED
    if not config.AWS_INVENTORY_SYNC_ENABLED:
        return False
    with _START_LOCK:
        if _STARTED:
            return True
        threading.Thread(target=_worker, name="aws-inventory-sync", daemon=True).start()
        _STARTED = True
    return True
