"""CSV export for the admin panel (spec §4: `GET /api/admin/export/{…}.csv`).

Three things decide whether the file opens in a Polish Excel, and only the first is the one
people remember: a UTF-8 BOM, `;` as the column separator, and a **comma** as the decimal
separator — with a dot, `12.50` lands in the cell as text and `SUMA()` returns 0.

Rows are streamed, not built in memory. `panel/tests/test_export.py` pins every column.
"""

import csv
from datetime import date, datetime
from decimal import Decimal

from django.db.models import OuterRef, Subquery
from django.http import StreamingHttpResponse
from django.utils import timezone

from trees.models import Assignment, Tree, Watering
from trees.status_display import STATUS_DISPLAY
from weather.models import WeatherDaily

CSV_DELIMITER = ";"
CSV_LINE_TERMINATOR = "\r\n"
BOM = "﻿"

TREES_HEADER = [
    "id",
    "miejscowość",
    "gatunek",
    "data posadzenia",
    "status",
    "cykl życia",
    "lat",
    "lng",
    "dokładność GPS [m]",
    "opiekun",
    "dodał",
    "utworzono",
]
WATERINGS_HEADER = ["drzewo", "miejscowość", "gatunek", "data podlania", "wolontariusz"]
WEATHER_HEADER = ["miejscowość", "dzień", "opad [mm]", "temp. max [°C]", "źródło"]


def format_value(value):
    """One cell as text, in the form a Polish Excel understands."""
    if value is None:
        return ""
    elif isinstance(value, (Decimal, float)):
        return str(value).replace(".", ",")
    # Before `date`, which `datetime` subclasses — the other order would drop the time.
    elif isinstance(value, datetime):
        return value.astimezone().strftime("%Y-%m-%d %H:%M")
    elif isinstance(value, date):
        return value.isoformat()
    else:
        return str(value)


class Echo:
    """A stand-in file whose `write()` returns the line, so `csv` can format without a file."""

    def write(self, value):
        return value


def stream_csv(header, rows):
    """Yield the CSV: BOM and header first, then one chunk per row."""
    writer = csv.writer(Echo(), delimiter=CSV_DELIMITER, lineterminator=CSV_LINE_TERMINATOR)

    yield BOM + writer.writerow(header)
    for row in rows:
        yield writer.writerow([format_value(cell) for cell in row])


def trees_rows():
    """Every tree, archived ones included — a yearly report covers what was removed."""
    # A Subquery, not a lookup per tree: the caretaker must not cost one query per row.
    caretaker = Subquery(
        Assignment.objects.filter(tree=OuterRef("pk"), ended_at__isnull=True).values(
            "user__display_name"
        )[:1]
    )
    trees = (
        Tree.objects.select_related("locality", "created_by")
        .annotate(caretaker=caretaker)
        .order_by("locality__name", "planted_on", "id")
    )
    return (
        [
            tree.pk,
            tree.locality.name,
            tree.species,
            tree.planted_on,
            STATUS_DISPLAY[tree.status]["label"],
            tree.get_lifecycle_display(),
            tree.lat,
            tree.lng,
            tree.gps_accuracy_m,
            tree.caretaker or "",
            tree.created_by.display_name,
            tree.created_at,
        ]
        for tree in trees.iterator()
    )


def waterings_rows():
    """The whole watering history, newest first — audit data, so archived trees stay in."""
    waterings = Watering.objects.select_related("tree__locality", "user").order_by("-watered_at")
    return (
        [
            watering.tree_id,
            watering.tree.locality.name,
            watering.tree.species,
            watering.watered_at,
            watering.user.display_name,
        ]
        for watering in waterings.iterator()
    )


def weather_rows():
    """Rainfall per locality and day — the evidence behind the statuses in the trees export."""
    # Ascending by day, the opposite of WeatherDaily.Meta.ordering: a chart reads left to right.
    days = WeatherDaily.objects.select_related("locality").order_by("locality__name", "day")
    return (
        [day.locality.name, day.day, day.precip_mm, day.temp_max_c, day.source]
        for day in days.iterator()
    )


# URL segment → (filename stem, header, rows). Keeping the three together is what stops a
# header drifting away from the generator that fills it, or a filename from the dataset.
DATASETS = {
    "trees": ("drzewa", TREES_HEADER, trees_rows),
    "waterings": ("podlania", WATERINGS_HEADER, waterings_rows),
    "weather": ("pogoda", WEATHER_HEADER, weather_rows),
}


def csv_response(dataset):
    """A downloadable CSV for one key of `DATASETS`.

    Contract (`panel/tests/test_export.py::TestCsvResponse` pins it):
      * a `StreamingHttpResponse` — the rows must stay lazy all the way to the socket;
      * `content_type="text/csv; charset=utf-8"`;
      * `Content-Disposition: attachment; filename="drzewa-2026-09-29.csv"`, the date from
        `timezone.localdate()`, so a folder of exports sorts by day;
      * body = `stream_csv(header, rows())`.
    """

    if dataset not in DATASETS:
        raise ValueError(f"Unknown dataset: {dataset!r}")
    filename_stem, header, rows = DATASETS[dataset]
    filename = f"{filename_stem}-{timezone.localdate().isoformat()}.csv"
    response = StreamingHttpResponse(
        stream_csv(header, rows()), content_type="text/csv; charset=utf-8"
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
