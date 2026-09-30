"""The rainfall chart on the tree card (UI doc §8.3).

Two constraints shape it and neither is visible from the picture. Heights are SVG geometry,
never inline `style=`, so a strict CSP stays possible (M4). And the dates are HTML rather
than SVG `<text>`, because SVG text scales with the viewBox and would shrink to a few pixels
on a phone.
"""

import re
from decimal import Decimal

import pytest
from django.template import Context, Template

TEMPLATE = Template("{% load trees_tags %}{% weather_chart series %}")


def render(values):
    from datetime import date, timedelta

    start = date(2026, 9, 17)
    series = [
        {"day": start + timedelta(days=index), "precip_mm": value}
        for index, value in enumerate(values)
    ]
    return TEMPLATE.render(Context({"series": series}))


def test_one_bar_and_one_label_per_day():
    html = render([Decimal("0"), Decimal("4.2"), None])

    assert html.count("<path") == 3
    assert html.count("<li>") == 3


def test_no_inline_styles_anywhere():
    """The whole reason the chart is SVG geometry instead of the PoC's divs."""
    html = render([Decimal("1.5"), Decimal("12")])

    assert "style=" not in html


def test_dates_are_html_not_svg_text():
    html = render([Decimal("1.5"), Decimal("12")])

    assert "<text" not in html
    assert "17.09" in html and "18.09" in html


def test_dry_and_missing_days_are_marked_apart():
    """Spec §5.1: no reading is not a reading of zero, and they must not look alike."""
    html = render([Decimal("0"), None, Decimal("8")])

    assert "bar-dry" in html
    assert "bar-missing" in html


def test_tooltip_distinguishes_no_data_from_no_rain():
    html = render([Decimal("0"), None])

    assert "brak danych" in html
    assert "0,00 mm" in html or "0 mm" in html


def test_bars_are_rounded_on_top_only():
    """A `rect rx=` would round the bottom too and lift the bars off the baseline."""
    html = render([Decimal("10")])

    path = re.search(r'(?<![a-z])d="([^"]+)"', html)[1]
    assert path.startswith("M"), path
    assert path.count("Q") == 2, "Dwa zaokrąglenia: lewy i prawy górny róg"


def test_tallest_bar_fills_the_chart():
    html = render([Decimal("20"), Decimal("10"), Decimal("0")])

    tops = [float(m) for m in re.findall(r"Q[\d.]+,([\d.]+) ", html)]
    assert min(tops) == 0.0, "Najwyższy słupek dotyka górnej krawędzi"


def test_a_day_without_rain_still_draws_something():
    """A flat line of nothing reads as a broken chart, not as a dry fortnight."""
    html = render([Decimal("0")])

    assert "<path" in html
    assert re.search(r'(?<![a-z])d="M', html)


@pytest.mark.parametrize("values", [[], [None], [Decimal("0")] * 14])
def test_edge_cases_render(values):
    assert render(values).strip().startswith("<div")
