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
    max_label_y = padding - 2
    min_label_y = height - 4

    svg = f"""
    <svg class="sparkline" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">
      {title_text}
      <rect x="0" y="0" width="{width}" height="{height}" rx="10" ry="10" class="sparkline-bg"></rect>
      <line x1="{padding}" y1="{padding}" x2="{padding}" y2="{height - padding}" class="sparkline-axis"></line>
      <line x1="{padding}" y1="{height - padding}" x2="{width - padding}" y2="{height - padding}" class="sparkline-axis"></line>
      <polyline fill="none" points="{polyline}" class="sparkline-line"></polyline>
      <text x="{padding}" y="{max_label_y}" class="sparkline-label">{max_value:,}</text>
      <text x="{padding}" y="{min_label_y}" class="sparkline-label">{min_value:,}</text>
    </svg>
    """
    return Markup(svg)
