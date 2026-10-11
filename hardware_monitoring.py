"""Hardware monitoring domain service with connector-safe demo state.

Real Cisco CIMC/Intersight credentials belong in the server-side connector layer;
this module deliberately returns no credentials or session material to the UI.
"""
from datetime import datetime, timezone
import uuid

import ops_log

_LAST_SCAN = datetime.now(timezone.utc)
_TICKETS = []

_ASSETS = []
_COMPONENTS = []

def dashboard():
    total_blades = sum(item["blades"] for item in _ASSETS)
    healthy_blades = sum(item["healthy_blades"] for item in _ASSETS)
    connected = bool(_ASSETS)
    vendor_counts = {vendor:sum(str(item.get("vendor", "")).lower() == vendor.lower() for item in _ASSETS) for vendor in ("Cisco", "Dell", "HPE")}
    type_counts = {kind:sum(str(item.get("asset_type", "chassis")).lower() == kind.lower() for item in _ASSETS) for kind in ("Chassis", "Blade", "Rack server", "Storage", "Network")}
    return {"summary":{"assets":len(_ASSETS),"chassis":type_counts["Chassis"],"blades":total_blades,"healthy_blades":healthy_blades,"active_alerts":len(_COMPONENTS),"coverage":100 if connected else 0,"vendors":vendor_counts,"types":type_counts},"assets":_ASSETS,"alerts":_COMPONENTS,"tickets":_TICKETS,"last_scan":_LAST_SCAN.isoformat() if connected else None,"connector":{"configured":connected,"status":"Connected" if connected else "Not configured"},"report":{"schedule":"Not configured","recipients":"No recipients configured","last_status":"Waiting for hardware connector","next_report":"Configure after connecting hardware"}}

def scan(requester="OpsAgent"):
    global _LAST_SCAN
    _LAST_SCAN = datetime.now(timezone.utc)
    ops_log.write("hardware_monitoring", "INFO", "hardware_scan_completed", f"Daily Cisco inspection requested by {requester}")
    return dashboard()

def request_ticket(alert_index, requester):
    if alert_index < 0 or alert_index >= len(_COMPONENTS):
        raise ValueError("Hardware alert was not found")
    alert = _COMPONENTS[alert_index]
    ticket = {"request_id":f"HWR-{uuid.uuid4().hex[:8].upper()}","status":"Pending approval","asset":alert["asset"],"component":alert["component"],"summary":alert["error"],"requester":requester,"created_at":datetime.now(timezone.utc).isoformat()}
    _TICKETS.insert(0, ticket)
    alert["ticket_status"] = "Pending approval"
    ops_log.write("hardware_monitoring", "INFO", "ticket_approval_requested", ticket["summary"], ticket["request_id"])
    return ticket

def approve_ticket(request_id, approver):
    ticket = next((item for item in _TICKETS if item["request_id"] == request_id), None)
    if not ticket:
        raise ValueError("Ticket request was not found")
    ticket["status"] = "Approved · queued for ITSM"
    ticket["approver"] = approver
    ops_log.write("hardware_monitoring", "INFO", "ticket_approved", ticket["summary"], request_id)
    return ticket

def send_daily_report(requester):
    ops_log.write("hardware_monitoring", "INFO", "daily_report_queued", f"Hardware health report queued by {requester}")
    result = dashboard()["report"].copy()
    result.update({"last_status":"Queued for email delivery","requested_by":requester,"queued_at":datetime.now(timezone.utc).isoformat()})
    return result
