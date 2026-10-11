"""Demo data (spec §10.2): 2 localities, 14 trees, watering and weather history.

Ported from the PoC (poc/assets/data.js). Dates are relative to "today" so the demo always
looks current. Idempotent: trees have stable UUIDs (uuid5) and waterings (append-only) are
created only for trees that did not exist yet. Weather rows are overwritten.
"""

import uuid
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import User
from trees.models import Assignment, Locality, Tree, TreeSpecies, Watering
from trees.services import recompute_tree_status
from weather.models import WeatherDaily

SEED_NAMESPACE = uuid.UUID("7d3c2f1e-5b8a-4c6d-9e0f-1a2b3c4d5e6f")

# Real places: the demo trees stand by the open-air museum, which is inside Sierpc, and the
# second group in Studzieniec 1.3 km north. The earlier coordinates were ~2 km out and
# reverse-geocoded to other villages entirely, so the demo map named the wrong town.
#
# Every tree below was checked through `reverse_locality()` on 2026-09-30 and resolves to the
# locality it is filed under. No test can hold that — §9 forbids calling Nominatim — so if you
# move a tree, re-run the check by hand: village limits here are tight enough that 200 m in
# the wrong direction lands in the next one.
LOCALITIES = {
    1: ("Sierpc", "52.852905", "19.667543"),
    2: ("Studzieniec", "52.876720", "19.641300"),
}

# precipitation in mm, index 0 = 13 days ago … index 13 = today
WEATHER = {
    1: [0, 2.4, 11.2, 4.0, 0, 0, 0, 0, 0.8, 0, 0, 0, 0, 0],
    2: [0, 3.1, 14.6, 6.2, 0.4, 0, 0, 1.2, 0, 0, 0, 0, 0, 0],
}

# key: (email, display_name, role, is_active)
USERS = {
    "u1": ("anna.k@przyklad.pl", "Anna Kowalska", User.Role.VOLUNTEER, True),
    "u2": ("piotr.n@przyklad.pl", "Piotr Nowak", User.Role.VOLUNTEER, True),
    "u3": ("marta.w@przyklad.pl", "Marta Wiśniewska", User.Role.VOLUNTEER, True),
    "u4": ("jan.z@przyklad.pl", "Jan Zieliński", User.Role.VOLUNTEER, False),
    "u5": ("admin@przyklad.pl", "Katarzyna Malinowska", User.Role.ADMIN, True),
}

SKANSEN = "Muzeum Wsi Mazowieckiej w Sierpcu"
SP2 = "SP nr 2 w Sierpcu (klasa 5b)"

# (key, species, locality, lat, lng, accuracy, planted days ago, planted by, notes,
#  status, caretaker, [(days ago, watered by), …])
TREES = [
    ("t01", "Lipa drobnolistna", 1, "52.864860", "19.634778", "4.2", 92, SP2,
     "Skansen — przy wejściu głównym, obok kasy.", "URGENT", "u1",
     [(9, "u1"), (16, "u1"), (23, "u2")]),
    ("t02", "Dąb szypułkowy", 1, "52.864815", "19.637163", "3.1", 145, SKANSEN,
     "Przy alei prowadzącej do dworu.", "OK", "u1",
     [(1, "u1"), (6, "u1"), (12, "u1"), (19, "u3")]),
    ("t03", "Klon zwyczajny", 1, "52.866435", "19.637973", "5.8", 60,
     "Wolontariusze GREENowacje", "Obok wiatraka koźlaka. Podpora wymaga poprawy.",
     "SOON", "u2", [(4, "u2"), (11, "u2")]),
    ("t04", "Brzoza brodawkowata", 1, "52.863960", "19.634193", "6.5", 210, "GREENowacje",
     "Przy zagrodzie z Rzeszotar.", "URGENT", None, [(12, "u3"), (21, "u3")]),
    ("t05", "Jarząb pospolity", 1, "52.866120", "19.632213", "4.0", 33, SKANSEN,
     "Młode nasadzenie przy karczmie — pierwszy sezon.", "SOON", "u1",
     [(4, "u1"), (8, "u1"), (14, "u1")]),
    ("t06", "Lipa drobnolistna", 1, "52.864545", "19.639368", "3.7", 92, SP2,
     "Aleja przy kościele z Drążdżewa.", "OK", "u3", [(2, "u3"), (9, "u3")]),
    ("t07", "Jabłoń – Ligol", 1, "52.863735", "19.635543", "8.9", 120, SKANSEN,
     "Sad przy chałupie — pierwsze drzewo nowego sadu.", "OK", None, [(2, "u2")]),
    ("t08", "Dąb szypułkowy", 1, "52.864365", "19.636308", "4.4", 145, SKANSEN,
     "Bliźniak dębu przy alei do dworu.", "SOON", None, [(5, "u1"), (13, "u2")]),
    ("t09", "Wiśnia – Łutówka", 1, "52.865535", "19.638378", "5.1", 75, "Koło Gospodyń Wiejskich",
     "Przy zagrodzie z młynem.", "OK", "u1", [(1, "u1"), (7, "u1"), (15, "u1")]),
    ("t10", "Grusza – Konferencja", 1, "52.865040", "19.633383", "3.9", 180, SKANSEN,
     "Na miedzy przy polu pokazowym.", "OK", "u2", [(3, "u2"), (10, "u2")]),
    ("t11", "Grab pospolity", 2, "52.876360", "19.642245", "4.6", 55,
     "Koło Gospodyń Wiejskich w Studzieńcu", "Przy świetlicy wiejskiej.", "URGENT", None,
     [(11, "u3")]),
    ("t12", "Dąb bezszypułkowy", 2, "52.877665", "19.640310", "5.5", 260, "GREENowacje",
     "", "OK", "u3", [(2, "u3"), (8, "u3"), (17, "u3")]),
    ("t13", "Klon zwyczajny", 2, "52.875955", "19.639320", "7.2", 40, "OSP Studzieniec",
     "Nasadzenie przy remizie.", "SOON", "u2", [(4, "u2"), (12, "u2")]),
    ("t14", "Jarząb pospolity", 2, "52.877305", "19.643055", "4.8", 40, "OSP Studzieniec",
     "", "OK", None, [(2, "u1")]),
]  # fmt: skip


def seed_tree_id(key):
    return uuid.uuid5(SEED_NAMESPACE, key)


class Command(BaseCommand):
    help = "Wgrywa dane demonstracyjne (tylko DEBUG, chyba że --force)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            default="podlewamy-drzewa",
            help="Hasło dla wszystkich kont demo (domyślnie: podlewamy-drzewa).",
        )
        parser.add_argument(
            "--force", action="store_true", help="Pozwól uruchomić przy DEBUG=false."
        )

    @transaction.atomic
    def handle(self, *args, password, force, **options):
        if not settings.DEBUG and not force:
            raise CommandError(
                "DEBUG=false — to nie wygląda na środowisko deweloperskie. Użyj --force."
            )

        now = timezone.localtime()
        today = now.date()

        localities = {}
        for key, (name, lat, lng) in LOCALITIES.items():
            localities[key], _ = Locality.objects.get_or_create(
                name=name, defaults={"lat": Decimal(lat), "lng": Decimal(lng)}
            )

        users = {}
        for key, (email, name, role, active) in USERS.items():
            user = User.objects.filter(email=email).first()
            if user is None:
                is_admin = role == User.Role.ADMIN
                user = User.objects.create_user(
                    email, password, name, role=role, is_active=active,
                    is_staff=is_admin, is_superuser=is_admin,
                )  # fmt: skip
            users[key] = user

        created = 0
        for (key, species, loc, lat, lng, acc, planted_ago, planted_by, notes, status,
             caretaker, waterings) in TREES:  # fmt: skip
            tree_id = seed_tree_id(key)
            # Keep the catalogue in step with the demo data; the tree itself stores the
            # name as text, so the return value is not needed here.
            TreeSpecies.objects.get_or_create(name=species)
            if Tree.objects.filter(pk=tree_id).exists():
                continue
            planted_at = now - timedelta(days=planted_ago)
            tree = Tree.objects.create(
                id=tree_id, species=species, locality=localities[loc],
                lat=Decimal(lat), lng=Decimal(lng), gps_accuracy_m=Decimal(acc),
                planted_on=planted_at.date(), planted_by=planted_by, notes=notes,
                status=status, created_by=users["u5"], created_at=planted_at,
            )  # fmt: skip
            Watering.objects.bulk_create(
                Watering(tree=tree, user=users[u], watered_at=self._evening(today, days_ago))
                for days_ago, u in waterings
            )
            if caretaker:
                Assignment.objects.create(
                    tree=tree, user=users[caretaker], started_at=planted_at + timedelta(days=1)
                )
            created += 1

        weather_rows = [
            WeatherDaily(
                locality=localities[loc],
                day=today - timedelta(days=len(mm) - 1 - i),
                precip_mm=Decimal(str(v)),
                source="seed",
            )
            for loc, mm in WEATHER.items()
            for i, v in enumerate(mm)
        ]
        WeatherDaily.objects.bulk_create(
            weather_rows,
            update_conflicts=True,
            unique_fields=["locality", "day"],
            update_fields=["precip_mm", "source"],
        )

        # Statuses in the table above come from the PoC; recompute them so the demo
        # shows what the real algorithm says about the seeded history (spec §6.2).
        for tree in Tree.objects.all():
            recompute_tree_status(tree, today=today)

        self.stdout.write(
            self.style.SUCCESS(
                f"Gotowe: {created} nowych drzew (razem {Tree.objects.count()}), "
                f"pogoda za {len(weather_rows)} dni-miejscowości.\n"
                f"Konta demo (hasło: {password}): "
                + ", ".join(email for email, *_ in USERS.values())
            )
        )

    @staticmethod
    def _evening(today, days_ago):
        day = today - timedelta(days=days_ago)
        return timezone.make_aware(datetime.combine(day, time(18, 0)))
