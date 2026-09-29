"""CSV export, step B1: value formatting and the stream itself. Written before the code.

The acceptance criterion from spec §9 — "eksport CSV otwiera się w Excelu z polskimi
znakami" — cannot be automated, so these tests pin the three things that decide it: the
BOM, the `;` separator and the decimal comma. Each of them is invisible when wrong: the
file still downloads, still looks like a CSV, and only fails on someone else's computer.

No database here. `format_value` and `stream_csv` are pure functions, like `trees/status.py`.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from factories import LocalityFactory, TreeFactory, UserFactory
from panel.export import (
    BOM,
    CSV_DELIMITER,
    TREES_HEADER,
    WATERINGS_HEADER,
    WEATHER_HEADER,
    csv_response,
    format_value,
    stream_csv,
    trees_rows,
    waterings_rows,
    weather_rows,
)
from trees.models import Tree
from trees.status_display import STATUS_DISPLAY
from trees.tests.factories import assign, water
from weather.models import WeatherDaily


def csv_text(header, rows):
    return "".join(stream_csv(header, rows))


def body(header, rows):
    """The stream without the BOM, split into lines — what a parser would see."""
    return csv_text(header, rows).removeprefix(BOM).splitlines()


@pytest.fixture
def full_history(db):
    """One of everything, so the width and end-to-end tests have all three datasets."""
    locality = LocalityFactory(name="Żółkiewka")
    volunteer = UserFactory(display_name="Anna Kowalska")
    tree = TreeFactory(locality=locality, species="Jabłoń – Ligol")
    assign(tree, volunteer)
    water(tree, volunteer, days_ago=2)
    WeatherDaily.objects.create(
        locality=locality,
        day=date(2026, 9, 27),
        precip_mm=Decimal("12.50"),
        temp_max_c=Decimal("18.3"),
    )
    return tree


class TestFormatValue:
    def test_none_becomes_an_empty_cell(self):
        assert format_value(None) == ""

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (Decimal("12.50"), "12,50"),
            (Decimal("0.00"), "0,00"),
            (Decimal("-3.2"), "-3,2"),
            (Decimal("7"), "7"),
            (52.8711, "52,8711"),
        ],
    )
    def test_numbers_use_a_decimal_comma(self, value, expected):
        """Excel with Polish settings reads "12.50" as text — and SUMA() over text is 0."""
        assert format_value(value) == expected

    def test_dates_are_iso(self):
        assert format_value(date(2026, 9, 28)) == "2026-09-28"

    def test_datetimes_are_local_and_minute_precise(self, settings):
        """Stored in UTC, read by a person in Warsaw: 14:30 UTC is 16:30 for them."""
        settings.TIME_ZONE = "Europe/Warsaw"
        moment = datetime(2026, 9, 28, 14, 30, tzinfo=UTC)

        assert format_value(moment) == "2026-09-28 16:30"

    def test_datetime_is_not_mistaken_for_a_date(self):
        """`datetime` subclasses `date`, so the order of the checks matters."""
        assert " " in format_value(datetime(2026, 9, 28, 14, 30, tzinfo=UTC))

    def test_text_passes_through_untouched(self):
        assert format_value("Jabłoń – Ligol") == "Jabłoń – Ligol"

    def test_integers_keep_no_separator(self):
        assert format_value(3) == "3"

    def test_empty_string_stays_empty(self):
        assert format_value("") == ""


class TestStreamCsv:
    def test_starts_with_a_bom(self):
        """Without it Excel decodes UTF-8 as Windows-1250 and „Żółkiewka" turns to mojibake."""
        assert csv_text(["miejscowość"], [["Żółkiewka"]]).startswith(BOM)

    def test_columns_are_separated_by_semicolons(self):
        assert body(["a", "b"], [["1", "2"]])[0] == "a;b"

    def test_rows_end_with_crlf(self):
        assert csv_text(["a"], [["1"]]).endswith("\r\n")
        assert "\r\n" in csv_text(["a"], [["1"]]).removesuffix("\r\n")

    def test_header_comes_first_then_the_rows(self):
        lines = body(["gatunek", "miejscowość"], [["Grusza – Konferencja", "Sierpc"]])

        assert lines == ["gatunek;miejscowość", "Grusza – Konferencja;Sierpc"]

    def test_every_cell_goes_through_format_value(self):
        """Note the decimal comma needs no quoting — the separator is a semicolon."""
        lines = body(["opad", "dzień", "temp"], [[Decimal("12.50"), date(2026, 9, 28), None]])

        assert lines[1] == "12,50;2026-09-28;"

    def test_a_value_containing_the_separator_is_quoted(self):
        """Otherwise one stray semicolon in a note shifts every later column by one."""
        lines = body(["notatka"], [["Sierpc; przy kasie"]])

        assert lines[1] == '"Sierpc; przy kasie"'

    def test_polish_characters_survive_a_utf8_sig_roundtrip(self):
        """`utf-8-sig` is what Excel and pandas use — it eats the BOM and keeps the letters."""
        raw = csv_text(["miejscowość"], [["Żółkiewka"]]).encode("utf-8")

        assert "Żółkiewka" in raw.decode("utf-8-sig")

    def test_rows_are_consumed_lazily(self):
        """Building the whole file in memory would defeat the point of streaming."""

        def rows():
            yield ["pierwszy"]
            raise AssertionError("Drugi wiersz nie powinien być pobrany z góry")

        stream = stream_csv(["kolumna"], rows())

        assert next(stream)

    def test_no_rows_still_produces_a_usable_file(self):
        """An empty export is a header, not an empty file — Excel needs the column names."""
        assert body(["gatunek"], []) == ["gatunek"]


# --- step B2: the three datasets -----------------------------------------------------


class TestRowWidths:
    """A row narrower or wider than its header shifts every later column, silently."""

    @pytest.mark.django_db
    @pytest.mark.parametrize(
        ("header", "rows"),
        [
            (TREES_HEADER, trees_rows),
            (WATERINGS_HEADER, waterings_rows),
            (WEATHER_HEADER, weather_rows),
        ],
        ids=["trees", "waterings", "weather"],
    )
    def test_every_row_is_as_wide_as_its_header(self, header, rows, full_history):
        produced = list(rows())

        assert produced, "Fixture powinna wyprodukować co najmniej jeden wiersz"
        for row in produced:
            assert len(row) == len(header)


@pytest.mark.django_db
class TestLaziness:
    """`stream_csv` streams, so the datasets must hand it an iterator, not a built list."""

    @pytest.mark.parametrize("rows", [trees_rows, waterings_rows, weather_rows])
    def test_returns_an_iterator(self, rows, full_history):
        produced = rows()

        assert iter(produced) is produced, "Zwróć iterator (.iterator()), nie listę"


@pytest.mark.django_db
class TestTreesRows:
    def test_columns_in_header_order(self, locality):
        volunteer = UserFactory(display_name="Anna Kowalska")
        tree = TreeFactory(
            locality=locality,
            species="Jabłoń – Ligol",
            planted_on=date(2026, 5, 10),
            status=Tree.Status.URGENT,
            gps_accuracy_m=Decimal("4.2"),
            created_by=volunteer,
        )
        assign(tree, volunteer)

        row = next(iter(trees_rows()))

        assert row[TREES_HEADER.index("id")] == tree.pk
        assert row[TREES_HEADER.index("miejscowość")] == locality.name
        assert row[TREES_HEADER.index("gatunek")] == "Jabłoń – Ligol"
        assert row[TREES_HEADER.index("data posadzenia")] == date(2026, 5, 10)
        assert row[TREES_HEADER.index("opiekun")] == "Anna Kowalska"
        assert row[TREES_HEADER.index("dodał")] == "Anna Kowalska"

    def test_status_is_the_polish_label_not_the_code(self):
        """The report is read by people; `trees/status_display.py` owns those words."""
        TreeFactory(status=Tree.Status.URGENT)

        row = next(iter(trees_rows()))

        assert row[TREES_HEADER.index("status")] == STATUS_DISPLAY[Tree.Status.URGENT]["label"]

    def test_lifecycle_is_a_label_too(self):
        TreeFactory(lifecycle=Tree.Lifecycle.ARCHIVED)

        row = next(iter(trees_rows()))

        assert row[TREES_HEADER.index("cykl życia")] == "Zarchiwizowane"

    def test_archived_trees_are_included(self, locality):
        """Trees are never deleted, only archived — the yearly report must show them."""
        TreeFactory(locality=locality, lifecycle=Tree.Lifecycle.ACTIVE)
        archived = TreeFactory(locality=locality, lifecycle=Tree.Lifecycle.ARCHIVED)

        exported = {row[TREES_HEADER.index("id")] for row in trees_rows()}

        assert archived.pk in exported
        assert len(exported) == 2

    def test_tree_without_a_caretaker_leaves_the_cell_empty(self):
        TreeFactory()

        row = next(iter(trees_rows()))

        assert row[TREES_HEADER.index("opiekun")] == ""

    def test_released_caretaker_is_no_longer_listed(self):
        tree = TreeFactory()
        assignment = assign(tree, UserFactory(display_name="Jan Zieliński"))
        assignment.ended_at = timezone.now()
        assignment.save()

        row = next(iter(trees_rows()))

        assert row[TREES_HEADER.index("opiekun")] == ""

    def test_order_is_stable(self, locality):
        late = TreeFactory(locality=locality, planted_on=date(2026, 6, 1))
        early = TreeFactory(locality=locality, planted_on=date(2026, 3, 1))

        ids = [row[TREES_HEADER.index("id")] for row in trees_rows()]

        assert ids == [early.pk, late.pk]

    def test_query_count_does_not_grow_with_trees(self, locality, django_assert_num_queries):
        for _ in range(3):
            assign(TreeFactory(locality=locality), UserFactory())
        with CaptureQueriesContext(connection) as captured:
            list(trees_rows())
        baseline = len(captured.captured_queries)

        for _ in range(9):
            assign(TreeFactory(locality=locality), UserFactory())
        with django_assert_num_queries(baseline):
            list(trees_rows())


@pytest.mark.django_db
class TestWateringsRows:
    def test_columns_in_header_order(self, locality):
        volunteer = UserFactory(display_name="Anna Kowalska")
        tree = TreeFactory(locality=locality, species="Grusza – Konferencja")
        water(tree, volunteer)

        row = next(iter(waterings_rows()))

        assert row[WATERINGS_HEADER.index("drzewo")] == tree.pk
        assert row[WATERINGS_HEADER.index("miejscowość")] == locality.name
        assert row[WATERINGS_HEADER.index("gatunek")] == "Grusza – Konferencja"
        assert row[WATERINGS_HEADER.index("wolontariusz")] == "Anna Kowalska"

    def test_newest_first(self):
        tree, volunteer = TreeFactory(), UserFactory()
        older = water(tree, volunteer, days_ago=5)
        newer = water(tree, volunteer, days_ago=1)

        dates = [row[WATERINGS_HEADER.index("data podlania")] for row in waterings_rows()]

        assert dates == [newer.watered_at, older.watered_at]

    def test_waterings_of_archived_trees_stay_in(self):
        """`waterings` is append-only audit data — archiving a tree does not undo the work."""
        tree = TreeFactory(lifecycle=Tree.Lifecycle.ARCHIVED)
        water(tree, UserFactory())

        assert len(list(waterings_rows())) == 1

    def test_query_count_does_not_grow_with_waterings(self, locality, django_assert_num_queries):
        volunteer = UserFactory()
        for _ in range(3):
            water(TreeFactory(locality=locality), volunteer)
        with CaptureQueriesContext(connection) as captured:
            list(waterings_rows())
        baseline = len(captured.captured_queries)

        for _ in range(9):
            water(TreeFactory(locality=locality), volunteer)
        with django_assert_num_queries(baseline):
            list(waterings_rows())


@pytest.mark.django_db
class TestWeatherRows:
    def test_columns_in_header_order(self, locality):
        WeatherDaily.objects.create(
            locality=locality,
            day=date(2026, 9, 27),
            precip_mm=Decimal("12.50"),
            temp_max_c=Decimal("18.3"),
        )

        row = next(iter(weather_rows()))

        assert row[WEATHER_HEADER.index("miejscowość")] == locality.name
        assert row[WEATHER_HEADER.index("dzień")] == date(2026, 9, 27)
        assert row[WEATHER_HEADER.index("opad [mm]")] == Decimal("12.50")
        assert row[WEATHER_HEADER.index("temp. max [°C]")] == Decimal("18.3")
        assert row[WEATHER_HEADER.index("źródło")] == "open-meteo"

    def test_missing_temperature_is_empty_not_zero(self, locality):
        """Spec §5.1: no reading is not a reading of zero."""
        WeatherDaily.objects.create(locality=locality, day=date(2026, 9, 27), temp_max_c=None)

        row = next(iter(weather_rows()))

        assert row[WEATHER_HEADER.index("temp. max [°C]")] is None

    def test_days_ascend(self, locality):
        WeatherDaily.objects.create(locality=locality, day=date(2026, 9, 27))
        WeatherDaily.objects.create(locality=locality, day=date(2026, 9, 25))

        days = [row[WEATHER_HEADER.index("dzień")] for row in weather_rows()]

        assert days == [date(2026, 9, 25), date(2026, 9, 27)]

    def test_query_count_does_not_grow_with_days(self, locality, django_assert_num_queries):
        for offset in range(3):
            WeatherDaily.objects.create(locality=locality, day=date(2026, 9, 1 + offset))
        with CaptureQueriesContext(connection) as captured:
            list(weather_rows())
        baseline = len(captured.captured_queries)

        for offset in range(3, 12):
            WeatherDaily.objects.create(locality=locality, day=date(2026, 9, 1 + offset))
        with django_assert_num_queries(baseline):
            list(weather_rows())


@pytest.mark.django_db
class TestDatasetsFeedTheStream:
    """The two halves of the export, joined: what a view in step B3 will actually do."""

    def test_trees_export_opens_as_a_csv_with_polish_text(self, full_history):
        text = "".join(stream_csv(TREES_HEADER, trees_rows()))

        assert text.startswith(BOM)
        lines = text.removeprefix(BOM).splitlines()
        assert lines[0] == CSV_DELIMITER.join(TREES_HEADER)
        assert "Jabłoń – Ligol" in lines[1]

    def test_weather_export_formats_rainfall_with_a_comma(self, full_history):
        text = "".join(stream_csv(WEATHER_HEADER, weather_rows()))

        assert "12,50" in text


# --- step B3: the HTTP layer ----------------------------------------------------------


@pytest.mark.django_db
class TestCsvResponse:
    @pytest.mark.parametrize(
        ("dataset", "stem"),
        [("trees", "drzewa"), ("waterings", "podlania"), ("weather", "pogoda")],
    )
    def test_filename_names_the_dataset_and_the_day(self, dataset, stem, full_history):
        response = csv_response(dataset)

        today = timezone.localdate().isoformat()
        assert response["Content-Disposition"] == f'attachment; filename="{stem}-{today}.csv"'

    def test_declares_csv_and_utf8(self, full_history):
        assert csv_response("trees")["Content-Type"] == "text/csv; charset=utf-8"

    def test_is_streamed_not_buffered(self, full_history):
        """A buffered response would put every tree in memory before the first byte leaves."""
        response = csv_response("trees")

        assert response.streaming is True

    def test_body_is_the_dataset(self, full_history):
        text = b"".join(csv_response("trees").streaming_content).decode("utf-8-sig")

        lines = text.splitlines()
        assert lines[0] == CSV_DELIMITER.join(TREES_HEADER)
        assert "Jabłoń – Ligol" in lines[1]


@pytest.mark.django_db
class TestExportEndpoints:
    """Spec §4: GET /api/admin/export/{trees|waterings|weather}.csv"""

    URLS = ["admin-api:export-trees", "admin-api:export-waterings", "admin-api:export-weather"]

    @pytest.fixture
    def as_admin(self, client):
        client.force_login(UserFactory(role="admin"))
        return client

    @pytest.mark.parametrize("name", URLS)
    def test_admin_downloads_a_csv(self, as_admin, name, full_history):
        response = as_admin.get(reverse(name))

        assert response.status_code == 200
        assert response["Content-Type"] == "text/csv; charset=utf-8"
        assert response["Content-Disposition"].startswith("attachment;")

    @pytest.mark.parametrize("name", URLS)
    def test_url_ends_with_csv_so_browsers_and_excel_recognise_it(self, name):
        assert reverse(name).endswith(".csv")

    @pytest.mark.parametrize("name", URLS)
    def test_volunteer_is_refused(self, client, name):
        client.force_login(UserFactory())

        assert client.get(reverse(name)).status_code == 403

    @pytest.mark.parametrize("name", URLS)
    def test_anonymous_is_refused(self, client, name):
        assert client.get(reverse(name)).status_code == 403

    def test_polish_characters_reach_the_browser(self, as_admin, full_history):
        response = as_admin.get(reverse("admin-api:export-trees"))

        body = b"".join(response.streaming_content)
        assert body.startswith(b"\xef\xbb\xbf"), "Brak BOM — Excel przeczyta to jako mojibake"
        assert "Żółkiewka" in body.decode("utf-8-sig")


@pytest.mark.django_db
class TestExportPage:
    def test_admin_sees_a_link_to_each_dataset(self, client):
        client.force_login(UserFactory(role="admin"))

        content = client.get(reverse("panel:export")).content.decode()

        for name in TestExportEndpoints.URLS:
            assert reverse(name) in content

    def test_page_is_part_of_the_panel_navigation(self, client):
        client.force_login(UserFactory(role="admin"))

        content = client.get(reverse("panel:dashboard")).content.decode()

        assert reverse("panel:export") in content, "Brak zakładki eksportu w nawigacji panelu"

    def test_volunteer_gets_403(self, client):
        client.force_login(UserFactory())

        assert client.get(reverse("panel:export")).status_code == 403

    def test_anonymous_is_sent_to_the_login_page(self, client):
        assert client.get(reverse("panel:export")).status_code == 302
