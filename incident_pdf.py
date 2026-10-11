"""Generate a polished downloadable incident PDF from an investigation result."""

from io import BytesIO
from xml.sax.saxutils import escape

import matplotlib.pyplot as plt
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak


def _text(value):
    return escape(str(value if value not in (None, "") else "N/A"))


def _format_time(value):
    try:
        return value.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    except (AttributeError, ValueError):
        return "N/A"


def _utilization_chart(metrics):
    labels = ["Disk", "Memory", "CPU"]
    values = [float(metrics.get(f"{name.lower()}_percent") or 0) for name in labels]
    figure, axis = plt.subplots(figsize=(7.2, 3.2), dpi=130)
    bars = axis.bar(labels, values, color=["#2563eb", "#7c3aed", "#f59e0b"])
    axis.set_ylim(0, 100)
    axis.set_ylabel("Utilization (%)")
    axis.set_title("Resource utilization at investigation time")
    axis.axhline(75, color="#dc2626", linestyle="--", linewidth=1, label="75% threshold")
    axis.legend(loc="upper right")
    for bar, value in zip(bars, values):
        axis.text(bar.get_x() + bar.get_width() / 2, value + 2, f"{value:.1f}%", ha="center")
    figure.tight_layout()
    output = BytesIO()
    figure.savefig(output, format="png", bbox_inches="tight")
    plt.close(figure)
    output.seek(0)
    return output


def build_incident_pdf(result, alert_text):
    output = BytesIO()
    doc = SimpleDocTemplate(output, pagesize=A4, rightMargin=16*mm, leftMargin=16*mm,
                            topMargin=16*mm, bottomMargin=16*mm,
                            title=f"A2Z OpsAgent Incident - {result.get('host', 'unknown')}")
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="TitleCenter", parent=styles["Title"], alignment=TA_CENTER,
                              textColor=colors.HexColor("#1f2937"), spaceAfter=10))
    styles.add(ParagraphStyle(name="Section", parent=styles["Heading2"], textColor=colors.HexColor("#1d4ed8"),
                              spaceBefore=10, spaceAfter=6))
    styles.add(ParagraphStyle(name="BodySmall", parent=styles["BodyText"], fontSize=8.5, leading=11))
    story = [Paragraph("A2Z Ops_Agent - Incident Investigation Report", styles["TitleCenter"])]
    start, end = result.get("start_time"), result.get("end_time")
    duration = (end - start).total_seconds() if start and end else None
    overview = [
        ["Target", _text(result.get("host")), "Operating system", _text(result.get("os_type"))],
        ["Verdict", _text(result.get("verdict")), "Request type", _text(result.get("request_mode"))],
        ["Started", _format_time(start), "Completed", _format_time(end)],
        ["Duration", f"{duration:.1f} seconds" if duration is not None else "N/A", "Alert", Paragraph(_text(alert_text), styles["BodySmall"])],
    ]
    table = Table(overview, colWidths=[25*mm, 55*mm, 30*mm, 52*mm])
    table.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), colors.HexColor("#eff6ff")),
                               ("GRID", (0,0), (-1,-1), .35, colors.HexColor("#cbd5e1")),
                               ("VALIGN", (0,0), (-1,-1), "TOP"), ("FONTSIZE", (0,0), (-1,-1), 8),
                               ("FONTNAME", (0,0), (0,-1), "Helvetica-Bold"),
                               ("FONTNAME", (2,0), (2,-1), "Helvetica-Bold"), ("PADDING", (0,0), (-1,-1), 5)]))
    story += [table, Spacer(1, 8), Paragraph("Resource utilization", styles["Section"])]
    metrics = (result.get("diagnostics_after") or {}).get("metrics", {})
    story += [Image(_utilization_chart(metrics), width=165*mm, height=73*mm)]
    story += [Paragraph("Timeline", styles["Section"])]
    timeline = [["Time", "Event"], [_format_time(start), "Investigation started"], [_format_time(end), "Investigation completed"]]
    t = Table(timeline, colWidths=[55*mm, 110*mm], repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), colors.HexColor("#1d4ed8")),
                           ("TEXTCOLOR", (0,0), (-1,0), colors.white), ("GRID", (0,0), (-1,-1), .35, colors.grey),
                           ("FONTSIZE", (0,0), (-1,-1), 8), ("PADDING", (0,0), (-1,-1), 5)]))
    story += [t]
    story += [Paragraph("Diagnosis", styles["Section"]),
              Paragraph(_text((result.get("agent_result") or {}).get("diagnosis", "No diagnosis returned")).replace("\n", "<br/>"), styles["BodySmall"])]
    issues = result.get("issues") or []
    story += [Paragraph("Findings", styles["Section"])]
    story += [Paragraph("<br/>".join(f"- {_text(item)}" for item in issues) or "No unresolved findings.", styles["BodySmall"])]
    actions = (result.get("agent_result") or {}).get("actions_taken") or []
    action_rows = [["Action", "Success", "Result"]]
    for action in actions:
        response = action.get("result") or {}
        action_rows.append([_text(action.get("tool")), "Yes" if response.get("success") else "No",
                            Paragraph(_text(response.get("status_after") or response.get("error") or "Completed"), styles["BodySmall"])])
    if len(action_rows) == 1:
        action_rows.append(["No automated action", "N/A", "Read-only investigation"])
    story += [Paragraph("Automated actions", styles["Section"])]
    a = Table(action_rows, colWidths=[52*mm, 22*mm, 91*mm], repeatRows=1)
    a.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), colors.HexColor("#1d4ed8")),
                           ("TEXTCOLOR", (0,0), (-1,0), colors.white), ("GRID", (0,0), (-1,-1), .35, colors.grey),
                           ("VALIGN", (0,0), (-1,-1), "TOP"), ("FONTSIZE", (0,0), (-1,-1), 8),
                           ("PADDING", (0,0), (-1,-1), 5)]))
    story += [a, PageBreak(), Paragraph("Diagnostic evidence", styles["Section"])]
    diagnostics = result.get("diagnostics_after") or {}
    for key, title in (("os_version", "Operating system"), ("uptime", "Uptime"),
                       ("monitoring_service", "Monitoring service"), ("monitoring_service_history", "Alloy history"),
                       ("failed_services", "Failed services"), ("recent_logs", "Recent errors"),
                       ("reboot_history", "Reboot history")):
        value = (diagnostics.get(key) or {}).get("stdout") or (diagnostics.get(key) or {}).get("stderr")
        if value:
            story += [Paragraph(title, styles["Heading3"]),
                      Paragraph(_text(value[:3500]).replace("\n", "<br/>"), styles["BodySmall"]), Spacer(1, 5)]
    network = result.get("network_diagnostics") or {}
    if network:
        story += [Paragraph("Network evidence", styles["Section"])]
        for key in ("target_ping", "traceroute", "gateway_ping"):
            item = network.get(key) or {}
            story += [Paragraph(key.replace("_", " ").title(), styles["Heading3"]),
                      Paragraph(_text(item.get("stdout", "No output")).replace("\n", "<br/>"), styles["BodySmall"])]

    def footer(canvas, document):
        canvas.saveState(); canvas.setFont("Helvetica", 8); canvas.setFillColor(colors.grey)
        canvas.drawString(16*mm, 9*mm, "Generated by A2Z Ops_Agent")
        canvas.drawRightString(A4[0]-16*mm, 9*mm, f"Page {document.page}"); canvas.restoreState()
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()
