from django import template

from trees.status_display import STATUS_DISPLAY

register = template.Library()


@register.inclusion_tag("includes/status_badge.html")
def status_badge(status, big=False):
    return {"status": status, "big": big, **STATUS_DISPLAY[status]}


SLOT, BAR_WIDTH, CHART_HEIGHT, CORNER = 40, 24, 70, 5


def _bar_path(x, top, height):
    """A bar rounded at the top only, like the PoC's `border-radius: 4px 4px 0 0`.

    A plain `rect rx=` rounds all four corners, which lifts the bars off the baseline.
    """
    radius = min(CORNER, height, BAR_WIDTH / 2)
    right = x + BAR_WIDTH
    bottom = CHART_HEIGHT
    return (
        f"M{x},{bottom} V{top + radius} "
        f"Q{x},{top} {x + radius},{top} "
        f"H{right - radius} Q{right},{top} {right},{top + radius} "
        f"V{bottom} Z"
    )


@register.inclusion_tag("includes/weather_chart.html")
def weather_chart(series):
    """Rainfall bars as SVG geometry — heights are attributes, never inline styles (CSP).

    The dates are HTML below the chart rather than `<text>` inside it. SVG text scales with
    the viewBox, so on a phone it would shrink to a few pixels; HTML labels keep their size
    at every width, which is why the PoC could afford them horizontal instead of tilted.
    """
    known = [day["precip_mm"] for day in series if day["precip_mm"] is not None]
    scale_max = max([4] + [float(value) for value in known])
    bars = []
    for index, day in enumerate(series):
        value = day["precip_mm"]
        missing = value is None
        height = 2 if missing else max(round(float(value) / scale_max * CHART_HEIGHT), 2)
        x = index * SLOT + (SLOT - BAR_WIDTH) / 2
        bars.append(
            {
                "path": _bar_path(x, CHART_HEIGHT - height, height),
                "label": day["day"],
                "value": value,
                "missing": missing,
                "dry": not missing and not float(value),
            }
        )
    return {"bars": bars, "chart_height": CHART_HEIGHT, "width": len(series) * SLOT}
