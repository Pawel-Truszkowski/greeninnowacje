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


def longest_streak(days: Iterable[date]) -> int:
    """The longest run of consecutive calendar days; repeats and order do not matter."""
    best = run = 0
    previous = None
    for day in sorted(set(days)):
        run = run + 1 if previous and day - previous == timedelta(days=1) else 1
        best = max(best, run)
        previous = day
    return best


@dataclass(frozen=True)
class Badge:
    code: str  # stored in `user_badges.code` — never rename one that was awarded
    icon: str
    name: str
    how: str  # "how to earn it", shown on a locked badge too
    earned: Callable[[Stats], bool]


BADGES = (
    Badge("first_drop", "💧", "Pierwsza kropla", "Podlej pierwsze drzewo.",
          lambda s: s.tree_days >= 1),
    Badge("watering_can", "🪣", "Konewka", "Podlewaj drzewa przez 10 drzewo-dni.",
          lambda s: s.tree_days >= 10),
    Badge("sprinkler", "🌧️", "Deszczownik", "Podlewaj drzewa przez 50 drzewo-dni.",
          lambda s: s.tree_days >= 50),
    Badge("week_streak", "🔥", "Tydzień z konewką", "Podlewaj 7 dni z rzędu.",
          lambda s: longest_streak(s.watering_days) >= 7),
    Badge("caretaker", "💚", "Opiekun", "Zaopiekuj się pierwszym drzewem.",
          lambda s: s.trees_cared >= 1),
    Badge("grove_keeper", "🛡️", "Strażnik zagajnika", "Opiekuj się trzema różnymi drzewami.",
          lambda s: s.trees_cared >= 3),
    Badge("faithful", "🤝", "Wierny opiekun", "Opiekuj się jednym drzewem przez 30 dni.",
          lambda s: s.longest_care_days >= 30),
    Badge("planter", "🌳", "Sadownik", "Zarejestruj pierwsze drzewo.",
          lambda s: s.registered >= 1),
    Badge("forester", "🌲", "Leśnik", "Zarejestruj pięć drzew.",
          lambda s: s.registered >= 5),
    Badge("chronicler", "📷", "Kronikarz", "Dodaj pierwsze zdjęcie drzewa.",
          lambda s: s.photos >= 1),
)  # fmt: skip

BADGES_BY_CODE = {badge.code: badge for badge in BADGES}


def earned_codes(stats: Stats) -> set[str]:
    return {badge.code for badge in BADGES if badge.earned(stats)}
