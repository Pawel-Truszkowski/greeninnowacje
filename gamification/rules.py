"""Points, levels and badges — pure functions, no database (like `trees/status.py`).

Everything here works on `Stats`, which `gamification/selectors.user_stats()` reads from the
domain tables (waterings, trees, assignments, photos). Not from `activity_events`: those are
pruned after a year, and a level must not drop because the log was cleaned.

A watering counts once per tree per day ("tree-day"). The button can be pressed again and
again (only a rate limit stops it), and points per press would reward exactly that.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class Stats:
    tree_days: int = 0  # distinct (tree, local day) waterings
    watering_days: tuple[date, ...] = ()  # distinct local days with any watering
    registered: int = 0  # trees this person registered (created_by)
    trees_cared: int = 0  # distinct trees ever in their care
    longest_care_days: int = 0  # the longest single assignment, ongoing ones up to today
    photos: int = 0
    # Tree-days on a tree the person neither registered nor had in their care at the time.
    neighbour_tree_days: int = 0
    species: int = 0  # distinct species among the trees they watered
    localities: int = 0  # distinct localities among the trees they watered
    morning_tree_days: int = 0  # tree-days with a watering in MORNING_HOURS (local time)
    evening_tree_days: int = 0  # tree-days with a watering in EVENING_HOURS (local time)
    # Tree-days the tree was URGENT when watered; known only since `waterings.tree_status`.
    rescue_tree_days: int = 0


# Product decision, tuned with Greenowacje — tests read these constants, not the numbers.
# Calibrated so a typical volunteer (2 trees, twice a week, ~20-week season) reaches the top
# level after about three seasons — the years a young tree needs watering to take root.
POINTS_PER_TREE_DAY = 10
POINTS_PER_REGISTERED = 25
POINTS_PER_TREE_CARED = 15
POINTS_PER_PHOTO = 5

# (points needed, icon, name), ascending; the first one must start at 0.
LEVELS = (
    (0, "🌰", "Nasiono"),
    (50, "🌱", "Siewka"),
    (150, "🌿", "Sadzonka"),
    (400, "🪴", "Młode drzewo"),
    (1000, "🌳", "Drzewo"),
    (2500, "🌲", "Dąb"),
)


def points_for(stats: Stats) -> int:
    return (
        stats.tree_days * POINTS_PER_TREE_DAY
        + stats.registered * POINTS_PER_REGISTERED
        + stats.trees_cared * POINTS_PER_TREE_CARED
        + stats.photos * POINTS_PER_PHOTO
    )


@dataclass(frozen=True)
class Level:
    number: int  # 1-based, for "Poziom 3"
    icon: str
    name: str
    threshold: int
    next_threshold: int | None  # None on the top level
    next_name: str | None
    points: int

    @property
    def progress(self) -> int:
        """Points gathered inside this level — `<progress value>`."""
        return self.points - self.threshold

    @property
    def span(self) -> int:
        """Points this level spans — `<progress max>`; 0 on the top level."""
        return (self.next_threshold - self.threshold) if self.next_threshold else 0

    @property
    def to_next(self) -> int:
        return (self.next_threshold - self.points) if self.next_threshold else 0


def level_for(points: int) -> Level:
    index = max(i for i, (threshold, _, _) in enumerate(LEVELS) if points >= threshold)
    threshold, icon, name = LEVELS[index]
    upcoming = LEVELS[index + 1] if index + 1 < len(LEVELS) else None
    return Level(
        number=index + 1,
        icon=icon,
        name=name,
        threshold=threshold,
        next_threshold=upcoming[0] if upcoming else None,
        next_name=upcoming[2] if upcoming else None,
        points=points,
    )


# Cool hours, when less water evaporates — the advice in the knowledge base. Local time.
MORNING_HOURS = range(5, 9)  # 5:00–8:59
EVENING_HOURS = range(19, 24)  # 19:00–23:59
# The watering season for young trees: May to September.
SEASON_MONTHS = range(5, 10)


def _longest_run(points: Iterable[date], step: timedelta) -> int:
    best = run = 0
    previous = None
    for point in sorted(set(points)):
        run = run + 1 if previous and point - previous == step else 1
        best = max(best, run)
        previous = point
    return best


def _week_of(day: date) -> date:
    """The Monday of the day's week — a key for a calendar week."""
    return day - timedelta(days=day.weekday())


def longest_streak(days: Iterable[date]) -> int:
    """The longest run of consecutive calendar days; repeats and order do not matter."""
    return _longest_run(days, timedelta(days=1))


def longest_week_streak(days: Iterable[date]) -> int:
    """The longest run of consecutive calendar weeks (Mon–Sun) with at least one watering.

    Weeks, not days: a young tree wants a deep watering once or twice a week, not a daily
    splash — this is the regularity worth rewarding.
    """
    return _longest_run((_week_of(day) for day in days), timedelta(weeks=1))


def best_season_weeks(days: Iterable[date]) -> int:
    """The most calendar weeks with a watering inside one season (May–September of a year)."""
    weeks_by_year: dict[int, set[date]] = {}
    for day in days:
        if day.month in SEASON_MONTHS:
            weeks_by_year.setdefault(day.year, set()).add(_week_of(day))
    return max((len(weeks) for weeks in weeks_by_year.values()), default=0)


@dataclass(frozen=True)
class Badge:
    code: str  # stored in `user_badges.code` — never rename one that was awarded
    icon: str
    name: str
    how: str  # "how to earn it", shown on a locked badge too
    earned: Callable[[Stats], bool]
    group: str  # heading on the achievements page; BADGES keeps each group together


# "Tree-day" is the unit in code only. On the page a watering is a watering, and this line,
# shown under the "Podlewanie" heading, says once that each tree counts once a day.
WATERING_NOTE = "Każde drzewo liczy się raz dziennie — podlewaj z głową, nie na wyścigi."


WATERING = "Podlewanie"
REGULARITY = "Regularność"
CARE = "Opieka"
PLANTING = "Sadzenie"
EXPLORING = "Odkrywanie"
PHOTOS = "Zdjęcia"

# Tiers are spread over time, so that after the first day (when the "first time" badges
# come at once) something new is in reach every week or two of a season.
BADGES = (
    Badge("first_drop", "💧", "Pierwsza kropla", "Podlej pierwsze drzewo.",
          lambda s: s.tree_days >= 1, WATERING),
    Badge("three_drops", "💦", "Trzy krople", "Podlej drzewa 3 razy.",
          lambda s: s.tree_days >= 3, WATERING),
    Badge("watering_can", "🪣", "Konewka", "Podlej drzewa 10 razy.",
          lambda s: s.tree_days >= 10, WATERING),
    Badge("garden_hose", "🚿", "Wąż ogrodowy", "Podlej drzewa 25 razy.",
          lambda s: s.tree_days >= 25, WATERING),
    Badge("sprinkler", "🌧️", "Deszczownik", "Podlej drzewa 50 razy.",
          lambda s: s.tree_days >= 50, WATERING),
    Badge("rain_cloud", "⛈️", "Chmura deszczowa", "Podlej drzewa 100 razy.",
          lambda s: s.tree_days >= 100, WATERING),
    Badge("downpour", "🌊", "Ulewa", "Podlej drzewa 250 razy.",
          lambda s: s.tree_days >= 250, WATERING),
    Badge("rescuer", "🚑", "Ratownik", "Podlej drzewo, które pilnie potrzebowało wody.",
          lambda s: s.rescue_tree_days >= 1, WATERING),
    Badge("guardian_angel", "😇", "Anioł stróż",
          "Podlej 10 razy drzewo, które pilnie potrzebowało wody.",
          lambda s: s.rescue_tree_days >= 10, WATERING),
    Badge("week_streak", "🔥", "Tydzień z konewką", "Podlewaj 7 dni z rzędu.",
          lambda s: longest_streak(s.watering_days) >= 7, REGULARITY),
    Badge("steady_rhythm", "🎵", "Stały rytm", "Podlewaj w 4 kolejnych tygodniach.",
          lambda s: longest_week_streak(s.watering_days) >= 4, REGULARITY),
    Badge("whole_season", "☀️", "Cały sezon",
          "Podlewaj w 12 różnych tygodniach jednego sezonu (maj–wrzesień).",
          lambda s: best_season_weeks(s.watering_days) >= 12, REGULARITY),
    Badge("early_bird", "🐦", "Ranny ptaszek",
          "Podlej drzewa 3 razy między 5:00 a 9:00 — rano mniej wody paruje.",
          lambda s: s.morning_tree_days >= 3, REGULARITY),
    Badge("evening_waterer", "🌙", "Wieczorny podlewacz",
          "Podlej drzewa 3 razy po 19:00 — wieczorem woda zostaje w ziemi.",
          lambda s: s.evening_tree_days >= 3, REGULARITY),
    Badge("caretaker", "💚", "Opiekun", "Zaopiekuj się pierwszym drzewem.",
          lambda s: s.trees_cared >= 1, CARE),
    Badge("grove_keeper", "🛡️", "Strażnik zagajnika", "Opiekuj się trzema różnymi drzewami.",
          lambda s: s.trees_cared >= 3, CARE),
    Badge("avenue_keeper", "🛤️", "Opiekun alei", "Opiekuj się pięcioma różnymi drzewami.",
          lambda s: s.trees_cared >= 5, CARE),
    Badge("forest_guardian", "🦉", "Strażnik lasu", "Opiekuj się dziesięcioma różnymi drzewami.",
          lambda s: s.trees_cared >= 10, CARE),
    Badge("first_week", "🗓️", "Pierwszy tydzień", "Opiekuj się jednym drzewem przez 7 dni.",
          lambda s: s.longest_care_days >= 7, CARE),
    Badge("faithful", "🤝", "Wierny opiekun", "Opiekuj się jednym drzewem przez 30 dni.",
          lambda s: s.longest_care_days >= 30, CARE),
    Badge("season_friend", "🍂", "Przyjaciel na sezon", "Opiekuj się jednym drzewem przez 90 dni.",
          lambda s: s.longest_care_days >= 90, CARE),
    Badge("year_together", "🎂", "Rok z drzewem", "Opiekuj się jednym drzewem przez rok.",
          lambda s: s.longest_care_days >= 365, CARE),
    Badge("good_neighbour", "🤗", "Dobry sąsiad",
          "Podlej drzewo, którym nie opiekujesz się Ty — sąsiedzka pomoc się liczy.",
          lambda s: s.neighbour_tree_days >= 1, CARE),
    Badge("neighbourhood_help", "🏘️", "Sąsiedzka pomoc",
          "Podlej 10 razy drzewa, którymi nie opiekujesz się Ty.",
          lambda s: s.neighbour_tree_days >= 10, CARE),
    Badge("planter", "🌳", "Sadownik", "Zarejestruj pierwsze drzewo.",
          lambda s: s.registered >= 1, PLANTING),
    Badge("three_saplings", "🌿", "Trzy sadzonki", "Zarejestruj trzy drzewa.",
          lambda s: s.registered >= 3, PLANTING),
    Badge("forester", "🌲", "Leśnik", "Zarejestruj pięć drzew.",
          lambda s: s.registered >= 5, PLANTING),
    Badge("grove_founder", "🏞️", "Założyciel zagajnika", "Zarejestruj piętnaście drzew.",
          lambda s: s.registered >= 15, PLANTING),
    Badge("botanist", "🔬", "Botanik", "Podlej drzewa trzech różnych gatunków.",
          lambda s: s.species >= 3, EXPLORING),
    Badge("dendrologist", "🍃", "Dendrolog", "Podlej drzewa pięciu różnych gatunków.",
          lambda s: s.species >= 5, EXPLORING),
    Badge("wanderer", "🧭", "Wędrowiec", "Podlej drzewa w dwóch różnych miejscowościach.",
          lambda s: s.localities >= 2, EXPLORING),
    Badge("chronicler", "📷", "Kronikarz", "Dodaj pierwsze zdjęcie drzewa.",
          lambda s: s.photos >= 1, PHOTOS),
    Badge("photo_reporter", "🎞️", "Fotoreporter", "Dodaj pięć zdjęć drzew.",
          lambda s: s.photos >= 5, PHOTOS),
    Badge("photo_chronicle", "🖼️", "Fotokronika", "Dodaj dwadzieścia zdjęć drzew.",
          lambda s: s.photos >= 20, PHOTOS),
)  # fmt: skip

BADGES_BY_CODE = {badge.code: badge for badge in BADGES}


def earned_codes(stats: Stats) -> set[str]:
    return {badge.code for badge in BADGES if badge.earned(stats)}
