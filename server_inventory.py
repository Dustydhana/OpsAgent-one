"""PostgreSQL-backed server inventory for incident enrichment.

Exact IP/hostname lookup is deliberately preferred over semantic retrieval: an
operations agent must not connect to a merely similar server. Ranked text
search is provided for operator discovery and alert messages without an IP.
"""

import ipaddress
import json
import re
import threading
import time
import os
import database
import config

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:
    psycopg = None
    dict_row = None


_LOCK = threading.RLock()
_DB_CACHE = {}
_STATUS = {"source": "not_loaded", "database_error": None}
DATABASE_CACHE_SECONDS = int(os.getenv("SERVER_INVENTORY_CACHE_SECONDS", "30"))


def _normalize(record):
    item = dict(record or {})
    item["server_name"] = str(item.get("server_name") or "").strip()
    item["ip_address"] = str(item.get("ip_address") or "").strip()
    item["public_ip_address"] = str(item.get("public_ip_address") or "").strip()
    item["private_ip_address"] = str(item.get("private_ip_address") or "").strip()
    item["status"] = str(item.get("status") or "unknown").strip().lower()
    item["vm_type"] = str(item.get("vm_type") or "unknown").strip().lower()
    item["os_type"] = str(item.get("os_type") or "auto").strip().lower()
    item["os_version"] = str(item.get("os_version") or "Unknown").strip()
    item["environment"] = str(item.get("environment") or "unknown").strip().lower()
    item["application"] = str(item.get("application") or item.get("application_name") or "Unknown").strip()
    item["application_team"] = str(item.get("application_team") or "Unknown").strip()
    item["application_team_email"] = str(item.get("application_team_email") or "").strip()
    item["server_team"] = str(item.get("server_team") or "Unknown").strip()
    item["monitoring_service"] = str(item.get("monitoring_service") or "").strip()
    item["important_services"] = [
        str(value).strip() for value in item.get("important_services", []) if str(value).strip()
    ]
    item["tags"] = [str(value).strip().lower() for value in item.get("tags", []) if str(value).strip()]
    item["aliases"] = [str(value).strip().lower() for value in item.get("aliases", []) if str(value).strip()]
    item["enabled"] = bool(item.get("enabled", True))
    connection = dict(item.get("connection") or {})
    connection.setdefault("username", item.get("remote_username"))
    connection.setdefault("port", item.get("remote_port"))
    connection.setdefault("key_path", item.get("remote_key_path") or "")
    connection["username"] = str(connection.get("username") or "").strip()
    connection["key_path"] = str(connection.get("key_path") or "").strip()
    connection["port"] = int(connection.get("port") or 22)
    item["connection"] = connection
    item["gateway_ip"] = str(item.get("gateway_ip") or "").strip()
    item["aws_instance_id"] = str(item.get("aws_instance_id") or "").strip()
    item["aws_region"] = str(item.get("aws_region") or "").strip()
    for field in ("private_dns_name", "public_dns_name", "host_name", "instance_type", "architecture",
                  "availability_zone", "vpc_id", "subnet_id"):
        item[field] = str(item.get(field) or "").strip()
    item["storage_volumes"] = list(item.get("storage_volumes") or [])
    item["notes"] = str(item.get("notes") or "").strip()
    return item


def _validate(records):
    errors = []
    server_names = set()
    ssh_addresses = set()
    for index, item in enumerate(records, start=1):
        label = item.get("server_name") or f"record {index}"
        if not item.get("server_name"):
            errors.append(f"{label}: server_name is required")
        if not item.get("ip_address"):
            errors.append(f"{label}: ip_address is required")
        else:
            try:
                ipaddress.ip_address(item["ip_address"])
            except ValueError:
                errors.append(f"{label}: invalid IP address {item['ip_address']!r}")
        for field in ("public_ip_address", "private_ip_address"):
            if item.get(field):
                try:
                    ipaddress.ip_address(item[field])
                except ValueError:
                    errors.append(f"{label}: invalid {field} {item[field]!r}")
        normalized_name = item.get("server_name", "").lower()
        ssh_address = item.get("ip_address", "").lower()
        if normalized_name in server_names:
            errors.append(f"{label}: duplicate server name {normalized_name!r}")
        if ssh_address in ssh_addresses:
            errors.append(f"{label}: duplicate SSH address {ssh_address!r}")
        server_names.add(normalized_name)
        ssh_addresses.add(ssh_address)
        if item.get("vm_type") not in {"aws", "azure", "onprem", "on-prem", "vmware", "physical", "unknown"}:
            errors.append(f"{label}: vm_type must be aws, azure, onprem, vmware, physical, or unknown")
        if item.get("os_type") not in {"linux", "windows", "unix", "aix", "solaris", "auto"}:
            errors.append(f"{label}: os_type must be linux, windows, unix, aix, solaris, or auto")
    if errors:
        raise ValueError("Invalid server inventory:\n- " + "\n- ".join(errors))


def _organization_id(value=None):
    organization_id = str(value or config.DEFAULT_ORGANIZATION_ID or "").strip()
    if not organization_id:
        raise PermissionError("An organization is required for server inventory access")
    return organization_id


def _load_postgresql(force=False, organization_id=None):
    organization_id = _organization_id(organization_id)
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL is not configured")
    if psycopg is None:
        raise RuntimeError("psycopg is not installed")
    now = time.monotonic()
    database.initialize()
    with _LOCK:
        cached = _DB_CACHE.get(organization_id, {"loaded_at": 0.0, "records": []})
        if not force and cached["records"] and now - cached["loaded_at"] < DATABASE_CACHE_SECONDS:
            return [dict(record) for record in cached["records"]]
    # A short timeout prevents an inventory outage from blocking alert acknowledgement.
    with psycopg.connect(database_url, connect_timeout=5, row_factory=dict_row) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM ops_agent.server_inventory WHERE organization_id=%s ORDER BY server_name", (organization_id,))
            records = [_normalize(row) for row in cursor.fetchall()]
    _validate(records)
    with _LOCK:
        _DB_CACHE[organization_id] = {"loaded_at": now, "records": records}
    return [dict(record) for record in records]


def load(force=False, include_disabled=False, organization_id=None):
    """Load inventory exclusively from PostgreSQL; database failures are explicit."""
    try:
        # Preserve compatibility with callers/tests that replace the legacy loader.
        records = (_load_postgresql(force=force, organization_id=organization_id)
                   if organization_id is not None else _load_postgresql(force=force))
        _STATUS.update(source="postgresql", database_error=None)
    except Exception as exc:
        _STATUS.update(source="postgresql_unavailable", database_error=f"{type(exc).__name__}: {exc}")
        raise RuntimeError("PostgreSQL inventory is unavailable; no local fallback is configured") from exc
    return records if include_disabled else [record for record in records if record["enabled"]]


def source_status():
    """Return non-secret inventory backend health for dashboards and diagnostics."""
    return dict(_STATUS)


def invalidate_cache(organization_id=None):
    """Force the next inventory read to return current PostgreSQL state."""
    with _LOCK:
        if organization_id:
            _DB_CACHE.pop(_organization_id(organization_id), None)
        else:
            _DB_CACHE.clear()


def add(record, organization_id=None):
    """Insert one validated inventory record using relational columns only."""
    organization_id = _organization_id(organization_id)
    item = _normalize(record)
    _validate([item])
    database.initialize()
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""INSERT INTO ops_agent.server_inventory (
                organization_id,server_name,ip_address,public_ip_address,private_ip_address,status,enabled,vm_type,
                environment,os_type,os_version,application,application_team,application_team_email,
                server_team,monitoring_service,important_services,tags,aliases,gateway_ip,
                remote_username,remote_port,remote_key_path,aws_instance_id,aws_region,notes)
                VALUES (%s,%s,%s,NULLIF(%s,''),NULLIF(%s,''),%s,%s,%s,%s,%s,%s,%s,%s,NULLIF(%s,''),
                %s,NULLIF(%s,''),%s,%s,%s,NULLIF(%s,''),NULLIF(%s,''),%s,NULLIF(%s,''),
                NULLIF(%s,''),NULLIF(%s,''),%s)""", (
                organization_id,item["server_name"],item["ip_address"],item["public_ip_address"],item["private_ip_address"],
                item["status"],item["enabled"],item["vm_type"],item["environment"],item["os_type"],
                item["os_version"],item["application"],item["application_team"],item["application_team_email"],
                item["server_team"],item["monitoring_service"],item["important_services"],item["tags"],
                item.get("aliases",[]),item["gateway_ip"],item["connection"]["username"],
                item["connection"]["port"],item["connection"]["key_path"],item["aws_instance_id"],
                item["aws_region"],item["notes"],
            ))
        connection.commit()
    with _LOCK:
        _DB_CACHE.pop(organization_id, None)
    return get(item["server_name"], include_disabled=True, organization_id=organization_id)


def update_cloud_addresses(server_name, *, ssh_address, public_ip_address="",
                           private_ip_address="", aws_instance_id="", aws_region=""):
    """Update one exact PostgreSQL inventory record after strict address validation."""
    if not os.getenv("DATABASE_URL", "").strip():
        raise RuntimeError("DATABASE_URL is not configured; PostgreSQL inventory editing is unavailable")
    if psycopg is None:
        raise RuntimeError("psycopg is not installed")
    name = str(server_name or "").strip()
    if not name:
        raise ValueError("server_name is required")
    values = {
        "ip_address": str(ssh_address or "").strip(),
        "public_ip_address": str(public_ip_address or "").strip(),
        "private_ip_address": str(private_ip_address or "").strip(),
    }
    if not values["ip_address"]:
        raise ValueError("SSH address is required")
    for label, value in values.items():
        if value:
            try:
                ipaddress.ip_address(value)
            except ValueError as exc:
                raise ValueError(f"Invalid {label}: {value!r}") from exc
    instance_id = str(aws_instance_id or "").strip()
    if instance_id and not re.fullmatch(r"i-[0-9a-f]{8,17}", instance_id):
        raise ValueError("AWS instance ID must look like i-0123456789abcdef0")
    region = str(aws_region or "").strip()
    if region and not re.fullmatch(r"[a-z]{2}(?:-gov)?-[a-z]+-\d", region):
        raise ValueError("Invalid AWS region")
    with psycopg.connect(os.getenv("DATABASE_URL"), connect_timeout=5) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE ops_agent.server_inventory
                   SET ip_address = %s,
                       public_ip_address = NULLIF(%s, ''),
                       private_ip_address = NULLIF(%s, ''),
                       aws_instance_id = NULLIF(%s, ''),
                       aws_region = NULLIF(%s, '')
                 WHERE lower(server_name) = lower(%s)
                RETURNING server_name
                """,
                (values["ip_address"], values["public_ip_address"],
                 values["private_ip_address"], instance_id, region, name),
            )
            updated = cursor.fetchone()
            if not updated:
                raise ValueError(f"No PostgreSQL inventory record found for {name!r}")
        connection.commit()
    with _LOCK:
        _DB_CACHE.update(loaded_at=0.0, records=[])
    return get(name)


def update(server_name, changes):
    """Update all editable operational fields for one canonical inventory record."""
    current = get(server_name, include_disabled=True)
    if not current:
        raise ValueError(f"No PostgreSQL inventory record found for {server_name!r}")
    merged = dict(current)
    merged.update(dict(changes or {}))
    connection_changes = dict(current.get("connection") or {})
    connection_changes.update(dict((changes or {}).get("connection") or {}))
    merged["connection"] = connection_changes
    item = _normalize(merged)
    _validate([item])
    if item["server_name"].lower() != str(server_name).strip().lower():
        raise ValueError("Renaming a server is not supported; create a new record instead")
    database.initialize()
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""UPDATE ops_agent.server_inventory SET
                ip_address=%s,public_ip_address=NULLIF(%s,''),private_ip_address=NULLIF(%s,''),
                status=%s,enabled=%s,vm_type=%s,environment=%s,os_type=%s,os_version=%s,
                application=%s,application_team=%s,application_team_email=NULLIF(%s,''),
                server_team=%s,monitoring_service=NULLIF(%s,''),important_services=%s,tags=%s,
                aliases=%s,gateway_ip=NULLIF(%s,''),remote_username=NULLIF(%s,''),remote_port=%s,
                remote_key_path=NULLIF(%s,''),aws_instance_id=NULLIF(%s,''),aws_region=NULLIF(%s,''),notes=%s
                WHERE lower(server_name)=lower(%s) RETURNING server_name""", (
                item["ip_address"], item["public_ip_address"], item["private_ip_address"], item["status"],
                item["enabled"], item["vm_type"], item["environment"], item["os_type"], item["os_version"],
                item["application"], item["application_team"], item["application_team_email"], item["server_team"],
                item["monitoring_service"], item["important_services"], item["tags"], item["aliases"],
                item["gateway_ip"], item["connection"]["username"], item["connection"]["port"],
                item["connection"]["key_path"], item["aws_instance_id"], item["aws_region"], item["notes"],
                server_name,
            ))
            if not cursor.fetchone():
                raise ValueError(f"No PostgreSQL inventory record found for {server_name!r}")
        connection.commit()
    with _LOCK:
        _DB_CACHE.update(loaded_at=0.0, records=[])
    return get(server_name, include_disabled=True)


def get(identifier, include_disabled=False, organization_id=None):
    needle = str(identifier or "").strip().lower().rstrip(".")
    if not needle:
        return None
    matches = []
    for record in load(include_disabled=include_disabled, organization_id=organization_id):
        aliases = [str(value).strip().lower() for value in record.get("aliases", [])]
        if needle in {
            record["server_name"].lower(), record["ip_address"].lower(),
            record.get("public_ip_address", "").lower(), record.get("private_ip_address", "").lower(),
            record.get("aws_instance_id", "").lower(),
            *aliases,
        }:
            matches.append(record)
    # Never guess when secondary address metadata maps to multiple records.
    return matches[0] if len(matches) == 1 else None


def _tokens(text):
    return set(re.findall(r"[a-z0-9][a-z0-9_.-]+", str(text or "").lower()))


def search(query, limit=10, include_disabled=False, organization_id=None):
    """Rank inventory records for operator discovery; never selects a target by itself."""
    query_text = str(query or "").strip().lower()
    query_tokens = _tokens(query_text)
    ranked = []
    for record in load(include_disabled=include_disabled, organization_id=organization_id):
        fields = [
            record["server_name"], record["ip_address"], record.get("public_ip_address", ""),
            record.get("private_ip_address", ""), record.get("aws_instance_id", ""),
            record["vm_type"], record["os_type"],
            record["os_version"], record["environment"], record["application"],
            record["application_team"], record["server_team"], record["monitoring_service"],
            *record["important_services"], *record["tags"], *record.get("aliases", []),
        ]
        haystack = " ".join(str(value).lower() for value in fields)
        score = sum(2 for token in query_tokens if token in _tokens(haystack))
        if record["ip_address"].lower() in query_text:
            score += 100
        if record["server_name"].lower() in query_text:
            score += 80
        if query_text and query_text in haystack:
            score += 10
        if score:
            ranked.append((score, record))
    ranked.sort(key=lambda pair: (-pair[0], pair[1]["server_name"]))
    return [record for _score, record in ranked[: max(1, int(limit))]]


def retrieve_for_alert(alert_text, extracted_host=None):
    """Return one safe incident record, using exact identity before ranked search."""
    if extracted_host:
        exact = get(extracted_host)
        if exact:
            return exact
    for candidate in re.findall(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])", alert_text or ""):
        exact = get(candidate)
        if exact:
            return exact
    matches = search(alert_text, limit=2)
    # A ranked result is safe only when it is unique; otherwise require an IP/name.
    return matches[0] if len(matches) == 1 else None


def incident_context(record):
    if not record:
        return "No matching server inventory record was found."
    return json.dumps({
        "server_name": record["server_name"],
        "ip_address": record["ip_address"],
        "public_ip_address": record.get("public_ip_address", ""),
        "private_ip_address": record.get("private_ip_address", ""),
        "status": record["status"],
        "vm_type": record["vm_type"],
        "environment": record["environment"],
        "os_type": record["os_type"],
        "os_version_expected": record["os_version"],
        "application": record["application"],
        "application_team": record["application_team"],
        "server_team": record["server_team"],
        "monitoring_service": record["monitoring_service"],
        "important_services": record["important_services"],
        "aws_instance_id": record.get("aws_instance_id", ""),
        "aws_region": record.get("aws_region", ""),
        "notes": record["notes"],
    }, indent=2)
