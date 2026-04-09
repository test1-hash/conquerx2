from __future__ import annotations

from html import escape
from typing import Iterable

from markupsafe import Markup


# Adapted from the earlier Flask version for static rendering.
def sparkline_svg(
    values: Iterable[int],
    *,
    width: int = 720,
    height: int = 180,
    invert: bool = False,
    title: str = "",
) -> Markup:
    points = list(values)
    if not points:
        return Markup('<div class="empty-chart">データなし</div>')
    if len(points) == 1:
        points = [points[0], points[0]]

    min_value = min(points)
    max_value = max(points)
    value_span = max(max_value - min_value, 1)
    padding = 18
    plot_width = width - (padding * 2)
    plot_height = height - (padding * 2)

    svg_points: list[str] = []
    for index, value in enumerate(points):
        x = padding + (plot_width * index / max(len(points) - 1, 1))
        y_ratio = (value - min_value) / value_span
        if invert:
            y = padding + (plot_height * y_ratio)
        else:
            y = padding + plot_height - (plot_height * y_ratio)
        svg_points.append(f"{x:.2f},{y:.2f}")

    polyline = " ".join(svg_points)
    title_text = f"<title>{escape(title)}</title>" if title else ""
    top_label_y = padding - 2
    bottom_label_y = height - 4
    top_label = min_value if invert else max_value
    bottom_label = max_value if invert else min_value

    svg = f"""
    <svg class="sparkline" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">
      {title_text}
      <rect x="0" y="0" width="{width}" height="{height}" rx="10" ry="10" class="sparkline-bg"></rect>
      <line x1="{padding}" y1="{padding}" x2="{padding}" y2="{height - padding}" class="sparkline-axis"></line>
      <line x1="{padding}" y1="{height - padding}" x2="{width - padding}" y2="{height - padding}" class="sparkline-axis"></line>
      <polyline fill="none" points="{polyline}" class="sparkline-line"></polyline>
      <text x="{padding}" y="{top_label_y}" class="sparkline-label">{top_label:,}</text>
      <text x="{padding}" y="{bottom_label_y}" class="sparkline-label">{bottom_label:,}</text>
    </svg>
    """
    return Markup(svg)
