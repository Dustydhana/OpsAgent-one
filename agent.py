"""
agent.py
---------
The OpenAI reasoning loop. Given diagnostic data from the server, the model
decides on a root cause and, if needed, calls one or more "tools" (mapped
1:1 onto functions in remediation.py) to fix the problem. This is a classic
agentic tool-use loop:

    1. Send system prompt + diagnostics to the model.
    2. If the model requests a tool call, execute the corresponding
       remediation function against the live SSH session and feed the
       result back to the model.
    3. Repeat until the model responds with a final plain-text summary
       (no more tool calls), or MAX_AGENT_ITERATIONS is reached.

The model can only ever call the tools defined below - it cannot run
arbitrary shell commands. This keeps the blast radius of "the LLM made a
bad call" limited to a small, reviewed, validated set of actions.
"""

import json
import ipaddress
import re
from openai import OpenAI

import config
import ai_usage
import remediation

_IGNORED_HOST_TOKENS = {
    "server", "host", "down", "alert", "critical", "disk", "full", "not", "responding",
    "is", "are", "any", "hey", "hi", "hello", "check", "status", "issue", "error",
    "fail", "outage", "unreachable", "crash", "please", "ops", "agent",
}

SYSTEM_PROMPT = """You are an autonomous Site Reliability Engineer (SRE) agent responsible for \
diagnosing and remediating issues on a Linux or Windows server.

You will be given the original Slack alert text and a snapshot of diagnostic data \
(disk usage, memory, CPU, failed services, recent logs, and monitoring-service state).

Your job:
1. Identify the most likely root cause of the issue (e.g. disk full, memory exhaustion, \
a crashed/failed service, a runaway process).
2. If - and only if - the evidence supports it, call the appropriate tool to remediate it. \
Prefer the least invasive fix that addresses the evidence. Do not guess randomly.
3. If the diagnostics show the server is actually healthy, call `no_action_needed` and explain why.
   If the monitoring service is not installed, treat that as a monitoring/configuration gap rather
   than a server outage and explain that installation/configuration is needed.
   Only call `restart_monitoring_service` when the service exists but is stopped; this is a false
   alert when the underlying server remains healthy and the restart succeeds.
4. You may call multiple tools across multiple turns if the first action doesn't fully resolve \
the issue, but avoid taking redundant or unnecessary actions.
5. When you are finished, reply with a final plain-text summary (no further tool calls) covering: \
the root cause you identified, the actions you took (or chose not to take), and whether you \
believe the issue is now resolved. Keep it concise and factual - this will be posted directly \
to a Slack incident channel.

You can ONLY affect the server through the provided tools. Never claim to have run a command \
that isn't backed by a tool call.
"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "restart_monitoring_service",
            "description": (
                "Start the configured monitoring/telemetry service if it is stopped, then verify it is running. This handles false "
                "alerts caused by monitoring agent failure."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "restart_service",
            "description": (
                "Restart a specific Windows or systemd service. "
                "Use this when diagnostics show a failed/crashed service that should be running."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "service_name": {
                        "type": "string",
                        "description": "Exact service name, e.g. 'Alloy', 'nginx', or 'mysql.service'.",
                    }
                },
                "required": ["service_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "restart_all_failed_services",
            "description": (
                "Look up every systemd unit currently reported as 'failed' and restart all of them. "
                "Use this when there are multiple failed services rather than one specific one."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "clear_disk_space",
            "description": (
                "Free up disk space by vacuuming old systemd journal entries, deleting stale "
                "/tmp files, and removing rotated/compressed log files. "
                "Use this when `df -h` shows a filesystem is critically full."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "restart_heavy_process",
            "description": (
                "Forcefully stop a single runaway process that is consuming excessive memory or "
                "CPU, identified from the top memory/CPU process lists. Provide either pid or "
                "process_name (not both required, pid is more precise if known)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pid": {
                        "type": "integer",
                        "description": "Process ID to kill, taken directly from the process list output.",
                    },
                    "process_name": {
                        "type": "string",
                        "description": "Process/command name to match and kill if PID is not known.",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Why this process was selected, e.g. 'using 91% of memory'.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "no_action_needed",
            "description": (
                "Call this when diagnostics show the server is healthy and no remediation is "
                "required, instead of calling any other tool."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "Brief explanation of why no action is needed.",
                    }
                },
                "required": ["reason"],
            },
        },
    },
]


def _dispatch_tool_call(ssh, name, args, monitoring_service=None):
    """Map a tool call requested by the model onto the real remediation.py functions."""
    try:
        if name == "restart_monitoring_service":
            return remediation.restart_monitoring_service(ssh, service_name=monitoring_service)
        elif name == "restart_service":
            return remediation.restart_service(ssh, args.get("service_name"))
        elif name == "restart_all_failed_services":
            return remediation.restart_all_failed_services(ssh)
        elif name == "clear_disk_space":
            return remediation.clear_disk_space(ssh)
        elif name == "restart_heavy_process":
            return remediation.restart_heavy_process(
                ssh,
                process_name=args.get("process_name"),
                pid=args.get("pid"),
                reason=args.get("reason"),
            )
        elif name == "no_action_needed":
            return {"action": "no_action_needed", "reason": args.get("reason"), "success": True}
        else:
            return {"success": False, "error": f"Unknown tool requested by model: {name}"}
    except Exception as e:
        return {"success": False, "error": f"Tool execution raised an exception: {e}"}


def extract_server_address(alert_text, fallback=None):
    """Extract the first valid IPv4 address, or a hostname after server/host."""
    # Slack markup such as <@U012ABCDEF> is a user ID, never a server name.
    text = re.sub(r"<[@#!][^>]+>", " ", alert_text or "")

    for candidate in re.findall(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])", text):
        try:
            return str(ipaddress.ip_address(candidate))
        except ValueError:
            continue

    labeled_match = re.search(
        r"\b(?:server|host|hostname|instance|node)\s*[:=#-]?\s*([a-z0-9][a-z0-9.-]*[a-z0-9])\b",
        text,
        re.I,
    )
    if labeled_match:
        candidate = labeled_match.group(1)
        lowered = candidate.lower()
        if lowered not in _IGNORED_HOST_TOKENS:
            return candidate

    for candidate in re.findall(r"\b[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9-]+)*\b", text, re.I):
        lowered = candidate.lower()
        if lowered in _IGNORED_HOST_TOKENS or candidate.replace(".", "").isdigit():
            continue
        if "." in candidate or "-" in candidate or any(char.isdigit() for char in candidate):
            return candidate

    return fallback


def _investigation_chat_prompt(result, question, alert_text="Manual dashboard investigation",
                               conversation_history=None):
    before = result.get("diagnostics_before") or {}
    after = result.get("diagnostics_after") or {}
    disk_scan = result.get("disk_scan") or []
    actions = result.get("agent_result", {}).get("actions_taken", [])
    context_lines = [
        f"Target: {result.get('host', 'unknown')} ({result.get('os_type', 'unknown')})",
        f"Verdict: {result.get('verdict', 'unknown')}",
        f"Alert: {alert_text}",
        f"Server inventory: {result.get('server_inventory') or 'not found'}",
        f"Issues: {result.get('issues', [])}",
        f"Monitoring state: {result.get('monitoring_service_state', 'unknown')}",
        f"Agent diagnosis: {result.get('agent_result', {}).get('diagnosis', 'N/A')}",
        f"Actions taken: {actions}",
        f"Disk scan: {disk_scan}",
        "",
        "Diagnostics before remediation:",
        before and json.dumps(before, default=str)[:8000] or "{}",
        "",
        "Diagnostics after remediation:",
        after and json.dumps(after, default=str)[:8000] or "{}",
    ]
    prior_messages = []
    for message in (conversation_history or [])[-6:]:
        role = str(message.get("role") or "user").capitalize()
        content = str(message.get("content") or "").strip()
        if content:
            prior_messages.append(f"{role}: {content[:1000]}")
    if prior_messages:
        context_lines.extend(["", "Recent troubleshooting conversation:", *prior_messages])
    return [
        {
            "role": "system",
            "content": (
                "You are OpsAgent AI inside a Streamlit VM troubleshooting dashboard. Answer using only "
                "the provided inventory and freshly collected diagnostic evidence. Be concise, practical, "
                "and explicit when data is unavailable. Never claim to execute start, stop, reboot, resize, "
                "or other infrastructure mutations; those require the separate approval workflow."
            ),
        },
        {
            "role": "user",
            "content": "\n".join(context_lines) + f"\n\nUser question: {question}",
        },
    ]


def answer_investigation_question(result, question, alert_text="Manual dashboard investigation",
                                  conversation_history=None, requester="unknown"):
    """Answer a follow-up dashboard question using the existing investigation context."""
    if not question or not question.strip():
        return "Please ask a question about the current investigation."

    try:
        client = OpenAI(api_key=config.OPENAI_API_KEY)
        response = client.chat.completions.create(
            model=config.OPENAI_MODEL,
            messages=_investigation_chat_prompt(
                result, question, alert_text=alert_text,
                conversation_history=conversation_history,
            ),
            temperature=0.2,
        )
        ai_usage.record(response,requester=requester,activity="investigation_chat",request_text=question)
        return (response.choices[0].message.content or "").strip() or "I couldn't generate an answer."
    except Exception as exc:
        ai_usage.record(requester=requester,activity="investigation_chat",request_text=question,error=exc)
        return f"I couldn't answer that question right now: {exc}"


def answer_infrastructure_question(question, inventory_records=None, conversation_history=None, requester="unknown", persona="Senior Infrastructure Architect"):
    """Answer general infrastructure questions as a senior cross-platform architect."""
    if not question or not question.strip():
        return "How can I help with your infrastructure?"
    inventory = []
    for record in (inventory_records or [])[:200]:
        inventory.append({
            "server": record.get("server_name"), "platform": record.get("vm_type"),
            "status": record.get("status"), "environment": record.get("environment"),
            "os": record.get("os_type"), "application": record.get("application"),
            "application_team": record.get("application_team"),
            "important_services": record.get("important_services", []),
            "aws_instance_id": record.get("aws_instance_id"), "aws_region": record.get("aws_region"),
        })
    messages = [{
        "role": "system",
        "content": (
            f"You are OpsAgent. Your selected expert speaker is: {persona}. "
            "Behave as a senior enterprise infrastructure architect and operations engineer. "
            "You are deeply knowledgeable about AWS, Azure, VMware/vCenter/ESXi, Cisco UCS, Dell and HPE "
            "hardware, Windows Server/Active Directory, Linux, networking, storage, databases, SCCM/MECM, "
            "patching, monitoring, security, availability, capacity, disaster recovery, automation, ITIL, "
            "and change management. Understand informal English, shorthand, and spelling mistakes by intent. "
            "Respond conversationally like ChatGPT: lead with the answer, then give practical steps or tradeoffs. "
            "Use the supplied inventory when relevant and clearly distinguish observed inventory facts from advice. "
            "Never invent live results or claim an action ran. Infrastructure changes require an implemented tool, "
            "authorization, and explicit confirmation. If a request is materially ambiguous, ask one concise question."
        ),
    }]
    for message in (conversation_history or [])[-10:]:
        role = message.get("role")
        content = str(message.get("content") or "").strip()
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content[:3000]})
    messages.append({
        "role": "user",
        "content": f"Current canonical server inventory (no credentials):\n{json.dumps(inventory, default=str)[:16000]}\n\nQuestion: {question}",
    })
    try:
        client = OpenAI(api_key=config.OPENAI_API_KEY)
        response = client.chat.completions.create(
            model=config.OPENAI_MODEL, messages=messages, temperature=0.25,
        )
        ai_usage.record(response,requester=requester,activity="infrastructure_chat",request_text=question)
        return (response.choices[0].message.content or "").strip() or "I couldn't generate an answer."
    except Exception as exc:
        ai_usage.record(requester=requester,activity="infrastructure_chat",request_text=question,error=exc)
        return f"I couldn't answer that infrastructure question right now: {exc}"


def run_agent(ssh, diagnostics_text, alert_text, inventory_context=None, monitoring_service=None):
    """
    Run the full reasoning loop for one incident.

    Returns a dict:
        {
            "diagnosis": str,            final summary text from the model
            "actions_taken": [ {tool, arguments, result}, ... ],
            "resolved": bool,             True if at least one action reported success
            "error": str | None,
        }
    """
    client = OpenAI(api_key=config.OPENAI_API_KEY)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Slack alert message:\n{alert_text}\n\n"
                f"Retrieved server inventory context:\n{inventory_context or 'No inventory record found.'}\n\n"
                f"Server diagnostics snapshot:\n{diagnostics_text}\n\n"
                "Analyze the root cause and remediate it using the available tools, then give "
                "your final summary."
            ),
        },
    ]

    actions_taken = []
    final_text = None

    try:
        for _ in range(config.MAX_AGENT_ITERATIONS):
            response = client.chat.completions.create(
                model=config.OPENAI_MODEL,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                temperature=0.2,
            )
            ai_usage.record(response,requester="automation",activity="incident_agent",request_text=alert_text)
            message = response.choices[0].message

            assistant_msg = {"role": "assistant", "content": message.content or ""}
            if message.tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in message.tool_calls
                ]
            messages.append(assistant_msg)

            if not message.tool_calls:
                final_text = message.content
                break

            for tool_call in message.tool_calls:
                try:
                    args = json.loads(tool_call.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}

                result = _dispatch_tool_call(ssh, tool_call.function.name, args, monitoring_service=monitoring_service)
                actions_taken.append(
                    {"tool": tool_call.function.name, "arguments": args, "result": result}
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(result, default=str),
                    }
                )
        else:
            final_text = (
                "Agent reached the maximum number of reasoning steps "
                f"({config.MAX_AGENT_ITERATIONS}) without producing a final summary."
            )

    except Exception as e:
        return {
            "diagnosis": f"Agent error: {e}",
            "actions_taken": actions_taken,
            "resolved": False,
            "error": str(e),
        }

    resolved = any(a["result"].get("success") for a in actions_taken) if actions_taken else False
    return {
        "diagnosis": final_text or "No summary returned by the agent.",
        "actions_taken": actions_taken,
        "resolved": resolved,
        "error": None,
    }
