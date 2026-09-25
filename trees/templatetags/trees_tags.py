from django import template

from trees.status_display import STATUS_DISPLAY

register = template.Library()


@register.inclusion_tag("includes/status_badge.html")
def status_badge(status, big=False):
    return {"status": status, "big": big, **STATUS_DISPLAY[status]}


@register.inclusion_tag("includes/weather_chart.html")
def weather_chart(series):
    """Rainfall bars as SVG geometry (heights are attributes, not inline styles)."""
    bar_width, gap, chart_height = 16, 4, 70
    known = [day["precip_mm"] for day in series if day["precip_mm"] is not None]
    scale_max = max([4] + [float(value) for value in known])
    bars = []
    for index, day in enumerate(series):
        value = day["precip_mm"]
        missing = value is None
        height = 0 if missing else round(float(value) / scale_max * chart_height)
        bars.append(
            {
                "x": index * (bar_width + gap),
                "y": chart_height - max(height, 2),
                "height": max(height, 2),
                "width": bar_width,
                # The rotation centre goes into the SVG transform attribute, so the
                # label position must be known here rather than left to CSS.
                "label_x": index * (bar_width + gap) + bar_width,
                "label": day["day"],
                "value": value,
                "missing": missing,
                "dry": not missing and not float(value),
            }
        )
    return {
        "bars": bars,
        "chart_height": chart_height,
        "width": len(series) * (bar_width + gap),
        "label_y": chart_height + 14,
    }
