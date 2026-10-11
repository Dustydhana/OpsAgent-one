"""Utilities for rendering disk usage charts for Slack and Streamlit."""

import os
import re
import tempfile
from io import BytesIO

import matplotlib.pyplot as plt


def _safe_host(host):
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", host or "unknown-host")


def _bar_color(size_gb):
    if size_gb > 20:
        return "#d9534f"
    if size_gb > 10:
        return "#f0ad4e"
    return "#5cb85c"


def build_disk_chart_figure(disk_data, host, os_type):
    """Build a matplotlib figure for the provided disk usage rows."""
    figure, axis = plt.subplots(figsize=(12, 8), dpi=100)
    background = "#1e1e1e"
    accent = "#0066CC"
    figure.patch.set_facecolor(background)
    axis.set_facecolor(background)

    if not disk_data:
        axis.text(0.5, 0.5, "No disk scan data available", color="white", ha="center", va="center", fontsize=16)
        axis.set_xticks([])
        axis.set_yticks([])
        axis.set_title(f"Disk Space Usage — {host}", color="white", fontsize=18, pad=16)
        return figure

    folders = [row.get("folder", "unknown") for row in disk_data]
    sizes = [float(row.get("size_gb", 0) or 0) for row in disk_data]
    colors = [_bar_color(size) for size in sizes]
    positions = list(range(len(folders)))

    bars = axis.barh(positions, sizes, color=colors, edgecolor=accent, linewidth=1.2)
    axis.set_yticks(positions)
    axis.set_yticklabels(folders, color="white")
    axis.invert_yaxis()
    axis.set_xlabel("Size in GB", color="white", labelpad=10)
    axis.set_title(f"Disk Space Usage — {host}", color="white", fontsize=18, pad=16)
    axis.grid(axis="x", color="#555555", linestyle="--", linewidth=0.8, alpha=0.5)
    axis.tick_params(axis="x", colors="white")
    axis.tick_params(axis="y", colors="white")

    for spine in axis.spines.values():
        spine.set_color(accent)

    for bar, size in zip(bars, sizes):
        axis.text(
            bar.get_width() + max(max(sizes) * 0.01, 0.1),
            bar.get_y() + bar.get_height() / 2,
            f"{size:.2f} GB",
            va="center",
            ha="left",
            color="white",
            fontsize=10,
        )

    axis.text(
        0.99,
        0.02,
        f"OS: {os_type}",
        transform=axis.transAxes,
        ha="right",
        va="bottom",
        color=accent,
        fontsize=10,
    )
    figure.tight_layout()
    return figure


def generate_disk_chart(disk_data, host, os_type):
    """Render a disk chart to a temp PNG file and return its path."""
    figure = build_disk_chart_figure(disk_data, host, os_type)
    filename = f"disk_chart_{_safe_host(host)}.png"
    image_path = os.path.join(tempfile.gettempdir(), filename)
    figure.savefig(image_path, facecolor=figure.get_facecolor(), bbox_inches="tight")
    plt.close(figure)
    return image_path


def build_ranked_chart_png(rows, host, title, value_label, color="#7c3aed"):
    """Return a PNG bar chart for ranked process/folder utilization rows."""
    figure, axis = plt.subplots(figsize=(10, 5.5), dpi=120)
    labels = [str(row[0])[:45] for row in rows]
    values = [float(row[1]) for row in rows]
    positions = list(range(len(rows)))
    bars = axis.barh(positions, values, color=color)
    axis.set_yticks(positions, labels=labels)
    axis.invert_yaxis()
    axis.set_xlabel(value_label)
    axis.set_title(f"{title} — {host}")
    axis.grid(axis="x", linestyle="--", alpha=0.3)
    maximum = max(values, default=0)
    for bar, value in zip(bars, values):
        axis.text(bar.get_width() + max(maximum * 0.01, 0.05), bar.get_y() + bar.get_height() / 2,
                  f"{value:.2f}", va="center", fontsize=9)
    figure.tight_layout()
    output = BytesIO()
    figure.savefig(output, format="png", bbox_inches="tight")
    plt.close(figure)
    return output.getvalue()


def generate_ranked_chart(rows, host, resource, value_label, color):
    """Write a ranked resource chart to a temporary PNG for Slack upload."""
    data = build_ranked_chart_png(rows, host, f"Top {resource}-consuming Processes", value_label, color)
    image_path = os.path.join(tempfile.gettempdir(), f"{resource.lower()}_chart_{_safe_host(host)}.png")
    with open(image_path, "wb") as output:
        output.write(data)
    return image_path
