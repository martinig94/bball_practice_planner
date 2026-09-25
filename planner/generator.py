"""Turn the drill database + coach inputs into a practice plan.

Pure Python (stdlib only) so the logic can be tested and reused without the UI.
"""

from __future__ import annotations

import csv
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

FOCUS_LABELS: dict[str, str] = {
    "ballhandling": "Ball handling / dribbling",
    "passing_shooting": "Passing & shooting",
    "offense": "Offense (half court & transition)",
    "defense": "Defense / 1v1 & small-sided games",
    "team_concepts": "Team concepts (spacing, screens, zone, press)",
}
# Small-sided game formats that suit each age group for the closing scrimmage.
AGE_FORMATS: dict[str, frozenset[str]] = {
    "U9": frozenset({"2v2", "3v3"}),
    "U11": frozenset({"3v3", "4v4"}),
    "U13": frozenset({"3v3", "4v4", "5v5"}),
    "U14": frozenset({"3v3", "4v4", "5v5"}),
}
AGE_LEVELS: tuple[str, ...] = ("U9", "U11", "U13", "U14")
SKILL_LEVELS: tuple[str, ...] = ("beginner", "intermediate", "advanced")
CATEGORIES: tuple[str, ...] = (
    "warmup", "coordination", "ballhandling", "passing_shooting", "offense",
    "defense", "team_concepts", "game", "cooldown",
)
SKILL_CATEGORIES = ("ballhandling", "passing_shooting", "offense", "defense", "team_concepts", "game")
REQUIRED_COLUMNS = (
    "id", "name", "category", "focus", "ages", "levels", "min_players", "max_players",
    "duration_min", "intensity", "equipment", "description", "coaching_points", "easier", "harder",
)
OPTIONAL_COLUMNS = ("needs_basket", "space", "sideline_ok", "supervision", "game_format", "source", "variants", "game_like", "concepts", "themes")  # have defaults when absent
THEMES = {"rebounding": "Rebounding / box-out", "closeouts": "Closeouts", "finishing": "Finishing at the rim", "1v1": "1v1",
          "contact": "Contact / physicality", "passing": "Passing", "shooting": "Shooting", "transition": "Transition",
          "footwork": "Footwork", "spacing": "Spacing & cutting", "reaction": "Reaction", "conditioning": "Conditioning"}
EMPHASIS_WEIGHT = 6.0
PREREQ_CONCEPTS = {"screens": "Screens (on and off the ball)", "zone": "Zone defence / attacking a zone", "press": "Full-court press and traps"}
STYLE_CONCEPTS = {"dribble_drive": "Dribble-drive (drive, kick, cut — no screens)"}
GAMES_ONLY_AGES = frozenset({"U9"})  # 6-8 year olds: everything except the cool-down must be a game
ALL_COLUMNS = REQUIRED_COLUMNS + OPTIONAL_COLUMNS
FOCUS_TAGS = ("physical", "coordination", "ballhandling", "passing_shooting", "offense", "defense", "team_concepts", "game")
INTENSITIES = ("low", "medium", "high")
GAME_FORMATS = ("2v2", "3v3", "4v4", "5v5")
SPACES = ("full_court", "half_court", "small_area")
SUPERVISION = ("low", "medium", "high")
TARGET_PER_BASKET = 8  # above this many players per hoop, waiting starts to hurt


# --------------------------------------------------------------------------- data


@dataclass(frozen=True)
class Drill:
    id: str
    name: str
    category: str
    focus: frozenset[str]
    ages: frozenset[str]
    levels: frozenset[str]
    min_players: int
    max_players: int
    duration_min: int
    intensity: str
    equipment: str
    description: str
    coaching_points: str
    easier: str
    harder: str
    needs_basket: bool = False
    space: str = "small_area"  # full_court | half_court | small_area
    sideline_ok: bool = False  # fits the narrow strip along the long side of the court
    supervision: str = "medium"  # low | medium | high — how much coaching it needs to run
    game_format: frozenset[str] = frozenset()  # e.g. {"3v3", "4v4"} for scrimmage-type games
    source: str = "original"  # where the drill comes from (attribution shown in the UI/export)
    variants: tuple[str, ...] = ()  # extra variations beyond easier/harder, free text
    game_like: bool = False  # framed as a game (tag, race, points, story) — required for U9
    concepts: frozenset[str] = frozenset()  # screens | zone | press (prerequisites) | dribble_drive (style)
    themes: frozenset[str] = frozenset()  # what the drill emphasises: rebounding, closeouts, finishing, 1v1, contact...

    def max_groups(self, baskets: int, max_stations: int = 4) -> int:
        """How many parallel groups this drill can run on one court.

        full_court: the drill occupies the whole floor, so one group only (its
        max_players already assumes waves / lanes). half_court: one group per
        basket if it needs a hoop, otherwise one per half. small_area: up to
        `max_stations` stations anywhere on the floor.
        """
        if self.space == "full_court":
            return 1
        if self.space == "half_court":
            return baskets if self.needs_basket else 2
        return baskets if self.needs_basket else max_stations

    def groups_for(self, n_players: int) -> int:
        """Minimum number of parallel groups needed to run this drill with n players."""
        return max(1, -(-n_players // self.max_players))

    def groups_plan(self, n_players: int, baskets: int, max_stations: int = 4,
                    target_per_basket: int = 8) -> int:
        """Groups to actually run: the minimum, but basket drills spread over spare
        hoops until each hoop has ~`target_per_basket` players (fewer people waiting)."""
        groups = self.groups_for(n_players)
        allowed = self.max_groups(baskets, max_stations)
        if self.needs_basket and self.space != "full_court":
            wanted = -(-n_players // target_per_basket)
            groups = max(groups, min(allowed, wanted))
        # spare-hoop spreading must not push a group below the drill's minimum
        floor = self.groups_for(n_players)
        while groups > floor and n_players // groups < self.min_players:
            groups -= 1
        return groups

    @classmethod
    def from_row(cls, row: dict[str, str]) -> "Drill":
        split = lambda s: frozenset(x.strip() for x in s.split(";") if x.strip())  # noqa: E731
        return cls(
            id=row["id"].strip(),
            name=row["name"].strip(),
            category=row["category"].strip(),
            focus=split(row["focus"]),
            ages=split(row["ages"]),
            levels=split(row["levels"]),
            min_players=int(row["min_players"]),
            max_players=int(row["max_players"]),
            duration_min=int(row["duration_min"]),
            intensity=row["intensity"].strip(),
            equipment=row["equipment"].strip(),
            description=row["description"].strip(),
            coaching_points=row["coaching_points"].strip(),
            easier=row["easier"].strip(),
            harder=row["harder"].strip(),
            needs_basket=row.get("needs_basket", "no").strip().lower() in ("yes", "y", "true", "1"),
            space=(row.get("space") or "small_area").strip().lower(),
            sideline_ok=(row.get("sideline_ok") or "no").strip().lower() in ("yes", "y", "true", "1"),
            supervision=(row.get("supervision") or "medium").strip().lower(),
            game_format=split(row.get("game_format") or ""),
            source=(row.get("source") or "original").strip(),
            variants=tuple(v.strip() for v in (row.get("variants") or "").split(" | ") if v.strip()),
            game_like=(row.get("game_like") or "no").strip().lower() in ("yes", "y", "true", "1"),
            concepts=split(row.get("concepts") or ""),
            themes=split(row.get("themes") or ""),
        )

    def to_row(self) -> dict[str, str]:
        """Inverse of from_row: the CSV representation of this drill."""
        order = lambda vals, ref: ";".join(v for v in ref if v in vals) or ";".join(sorted(vals))  # noqa: E731
        return {
            "id": self.id, "name": self.name, "category": self.category,
            "focus": order(self.focus, FOCUS_TAGS), "ages": order(self.ages, AGE_LEVELS),
            "levels": order(self.levels, SKILL_LEVELS),
            "min_players": str(self.min_players), "max_players": str(self.max_players),
            "duration_min": str(self.duration_min), "intensity": self.intensity, "equipment": self.equipment,
            "description": self.description, "coaching_points": self.coaching_points,
            "easier": self.easier, "harder": self.harder,
            "needs_basket": "yes" if self.needs_basket else "no", "space": self.space,
            "sideline_ok": "yes" if self.sideline_ok else "no", "supervision": self.supervision,
            "game_format": ";".join(sorted(self.game_format)), "source": self.source,
            "variants": " | ".join(self.variants),
            "game_like": "yes" if self.game_like else "no",
            "concepts": ";".join(sorted(self.concepts)),
            "themes": ";".join(sorted(self.themes)),
        }


@dataclass
class PlannedDrill:
    drill: Drill
    minutes: int
    groups: int = 1
    n_players: int = 0
    sideline: "Drill | None" = None  # split-and-swap: the other half works on the sideline strip
    ages_selected: frozenset[str] = frozenset()  # ages of the group, to flag drills not written for all of them

    @property
    def age_note(self) -> str:
        """Warn when the drill is not tagged for every selected age (loose fallback was used)."""
        missing = [a for a in AGE_LEVELS if a in self.ages_selected and a not in self.drill.ages]
        if not missing:
            return ""
        tagged = "/".join(a for a in AGE_LEVELS if a in self.drill.ages)
        return f"Written for {tagged}, not {'/'.join(missing)}: simplify for the younger players."

    @property
    def group_size(self) -> int:
        return -(-self.court_players // self.groups) if self.groups else self.court_players

    @property
    def court_players(self) -> int:
        """Players on the court at any moment (half the roster in a split-and-swap block)."""
        return -(-self.n_players // 2) if self.sideline else self.n_players

    @property
    def sideline_players(self) -> int:
        return self.n_players - self.court_players if self.sideline else 0

    @property
    def setup_note(self) -> str:
        """How to organise the roster for this drill (empty when the whole group runs it together)."""
        if self.sideline:
            half = self.minutes // 2
            court = (f"group A ({self.court_players}) on the court"
                     + (f" in {self.groups} groups of ~{self.group_size}, one per basket" if self.groups > 1 else ""))
            return (f"Split and swap: {court}; group B ({self.sideline_players}) on the sideline strip doing "
                    f"'{self.sideline.name}' (self-managed). Swap after {half} min.")
        if self.groups <= 1:
            return ""
        if self.drill.needs_basket:
            where = "one per basket"
        elif self.drill.space == "half_court":
            where = "one per half court"
        else:
            where = "as stations in separate areas of the floor"
        return f"Run in {self.groups} parallel groups of ~{self.group_size} players, {where}."


@dataclass
class Block:
    title: str
    minutes: int
    drills: list[PlannedDrill]
    note: str = ""


@dataclass
class LevelPlan:
    mode: str  # "single" | "split"
    groups: list[str]
    note: str


@dataclass
class Plan:
    n_players: int
    ages: list[str]
    duration: int
    levels: dict[str, int]
    focus: list[str]
    seed: int | None
    baskets: int
    sideline_strip: bool
    coaches: int
    include_athletic: bool
    budget: dict[str, int]
    level_plan: LevelPlan
    blocks: list[Block]
    warnings: list[str] = field(default_factory=list)
    level_cap_note: str = ""  # e.g. U9: 'advanced' capped at the standard version

    @property
    def planned_minutes(self) -> int:
        return sum(pd.minutes for b in self.blocks for pd in b.drills)

    @property
    def drill_ids(self) -> list[str]:
        ids = []
        for b in self.blocks:
            for pd in b.drills:
                ids.append(pd.drill.id)
                if pd.sideline:
                    ids.append(pd.sideline.id)
        return ids


def load_drills(path: str | Path = "data/drills.csv") -> list[Drill]:
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        missing = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"drills.csv is missing columns: {', '.join(missing)}")
        drills = [Drill.from_row(r) for r in reader]
    ids = [d.id for d in drills]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        raise ValueError(f"drills.csv has duplicated ids: {', '.join(dupes)}")
    return drills


def save_drills(drills: Sequence[Drill], path: str | Path = "data/drills.csv") -> None:
    """Write the whole database back to CSV (used by the in-app editor)."""
    ids = [d.id for d in drills]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        raise ValueError(f"duplicated ids: {', '.join(dupes)}")
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=ALL_COLUMNS)
        w.writeheader()
        for d in drills:
            w.writerow(d.to_row())


def next_drill_id(drills: Sequence[Drill], category: str) -> str:
    """Next free id for a category, following the WU/CO/BH/PS/OF/DF/TC/GM/CD convention."""
    prefix = {"warmup": "WU", "coordination": "CO", "ballhandling": "BH", "passing_shooting": "PS",
              "offense": "OF", "defense": "DF", "team_concepts": "TC", "game": "GM", "cooldown": "CD"}[category]
    nums = [int(d.id[len(prefix):]) for d in drills if d.id.startswith(prefix) and d.id[len(prefix):].isdigit()]
    return f"{prefix}{(max(nums) + 1) if nums else 1:02d}"


# ------------------------------------------------------------------------ helpers


def fits_roster(d: Drill, n_players: int, baskets: int, max_groups: int) -> bool:
    """Can the whole roster be kept active in this drill?

    A drill written for `max_players` can be run in parallel groups, limited by
    the court geometry (see Drill.max_groups): full-court drills cannot be split,
    basket drills are capped by the baskets available, stations by `max_groups`.
    """
    if d.min_players > n_players:
        return False
    groups = d.groups_for(n_players)
    if n_players // groups < d.min_players:  # splitting would leave groups too small
        return False
    return groups <= d.max_groups(baskets, max_groups)


class Pool:
    """Drills that suit the group, with a strict and a loose view.

    Strict: the drill suits ALL selected ages and ALL levels present.
    Loose: it suits ANY of them. `select` uses the strict view per block and falls
    back to the loose one when strict leaves fewer than `min_pool` candidates.
    """

    def __init__(self, drills: Iterable[Drill], ages: Sequence[str], levels_present: Sequence[str],
                 n_players: int, baskets: int = 2, max_groups: int = 4, min_pool: int = 2):
        fit = [d for d in drills if fits_roster(d, n_players, baskets, max_groups)]
        self.strict = [d for d in fit if set(ages) <= d.ages and set(levels_present) <= d.levels]
        self.loose = [d for d in fit if d.ages & set(ages) and d.levels & set(levels_present)]
        self.min_pool = min_pool

    def select(self, pred, exclude: set[str] = frozenset()) -> list[Drill]:
        strict = [d for d in self.strict if pred(d) and d.id not in exclude]
        if len(strict) >= self.min_pool:
            return strict
        return [d for d in self.loose if pred(d) and d.id not in exclude]


def filter_pool(drills: Iterable[Drill], ages: Sequence[str], levels_present: Sequence[str],
                n_players: int, baskets: int = 2, max_groups: int = 4, min_pool: int = 3) -> list[Drill]:
    """Flat list of suitable drills (strict, falling back to loose). Kept for convenience."""
    pool = Pool(drills, ages, levels_present, n_players, baskets, max_groups, min_pool)
    return pool.strict if len(pool.strict) >= min_pool else pool.loose


def scale_minutes(durations: Sequence[int], target: int) -> list[int]:
    """Rescale durations so they sum exactly to `target` (largest-remainder rounding)."""
    if not durations:
        return []
    total = sum(durations)
    raw = [d / total * target for d in durations]
    mins = [int(r) for r in raw]
    remainder = target - sum(mins)
    for idx in sorted(range(len(raw)), key=lambda i: raw[i] - mins[i], reverse=True)[:remainder]:
        mins[idx] += 1
    return mins


def age_specificity(d: Drill) -> float:
    """1.0 for a drill written for a single age group, down to 0.25 for an all-ages drill.

    Used as a sampling weight so that, for a U9 group, a drill written for U9/U11 is
    preferred over an all-ages fundamental, and for U14 a teen drill over a generic one.
    """
    return 1.0 / max(1, len(d.ages & set(AGE_LEVELS)))


def pick_block(pool: Sequence[Drill], minutes: int, used: set[str], rng: random.Random,
               max_drills: int = 3, min_drill: int = 4, n_players: int = 0,
               baskets: int = 2, max_groups: int = 4, ages: Sequence[str] = (),
               weights: dict[str, float] | None = None) -> list[PlannedDrill]:
    """Draw drills from `pool` until `minutes` are covered, then rescale to fit exactly.

    Drills that keep the whole roster in one group are preferred over ones that
    must be split into several groups (weighted sampling, weight = 1 / groups).
    """
    candidates = [d for d in pool if d.id not in used]
    if not candidates or minutes <= 0:
        return []
    # Efraimidis-Spirakis weighted sampling without replacement
    # weight = age specificity * rating weight / groups needed  ->  key = u ** (1 / weight)
    weights = weights or {}
    candidates.sort(
        key=lambda d: rng.random() ** (d.groups_for(n_players) / (age_specificity(d) * weights.get(d.id, 1.0))),
        reverse=True)
    chosen: list[Drill] = []
    total = 0
    for d in candidates:
        if total >= minutes or len(chosen) >= max_drills:
            break
        if chosen and (minutes - total) < min_drill:
            break
        chosen.append(d)
        total += d.duration_min
    return [PlannedDrill(d, m, d.groups_plan(n_players, baskets, max_groups), n_players, ages_selected=frozenset(ages))
            for d, m in zip(chosen, scale_minutes([d.duration_min for d in chosen], minutes))]


def time_budget(duration: int, ages: Sequence[str], include_athletic: bool = True) -> dict[str, int]:
    table = {
        60: dict(prep=10, athletic=6, game=12, cooldown=5),
        90: dict(prep=12, athletic=8, game=18, cooldown=5),
        120: dict(prep=15, athletic=10, game=25, cooldown=5),
    }
    if duration not in table:
        raise ValueError("duration must be 60, 90 or 120")
    b = dict(table[duration])
    if not include_athletic:
        b["athletic"] = 0
    if all(a in ("U9", "U11") for a in ages):  # younger kids: more game time
        b["game"] += 5
    b["skills"] = duration - b["prep"] - b["athletic"] - b["game"] - b["cooldown"]
    b["total"] = duration
    return b


def level_plan(levels: dict[str, int]) -> LevelPlan:
    present = {k: v for k, v in levels.items() if v > 0}
    if not present:
        return LevelPlan("single", [], "")
    if len(present) == 1:
        (name,) = present
        return LevelPlan("single", [name], f"Whole group works at {name} level.")
    desc = ", ".join(f"{v} {k}" for k, v in present.items())
    note = (f"Mixed group: {desc}. Run skill blocks as stations or split lines: beginners use the "
            f"'Easier' variation, advanced players the 'Harder' one.")
    small = [k for k, v in present.items() if v < 3]
    if small:
        note += f" Groups with fewer than 3 players ({', '.join(small)}) should merge with the nearest level."
    return LevelPlan("split", list(present), note)


# ------------------------------------------------------------------------- main


def generate_practice(
    drills: Sequence[Drill],
    n_players: int,
    ages: Sequence[str],
    duration: int,
    levels: dict[str, int] | None = None,
    focus: Sequence[str] | None = None,
    seed: int | None = None,
    baskets: int = 2,
    max_groups: int = 4,
    sideline_strip: bool = True,
    coaches: int = 1,
    include_athletic: bool = True,
    exclude_ids: Iterable[str] = (),
    weights: dict[str, float] | None = None,
    concepts_used: Iterable[str] = (),
    style: Iterable[str] = ("dribble_drive",),
    emphasis: Iterable[str] = (),
) -> Plan:
    """Build a practice plan.

    baskets: hoops available — drills that need a basket are split into at most
    this many parallel groups. max_groups: cap on parallel groups for drills
    that need no basket. sideline_strip: a narrow strip along the long side of
    the court is free, so crowded basket drills can be run as split-and-swap
    blocks with half the team doing a self-managed drill there. coaches: with a
    single coach the sideline drill must need low supervision. exclude_ids: drills to
    leave out (recently used, or rated 0 stars). weights: per-drill sampling multipliers
    from ratings (1.0 = neutral). concepts_used: prerequisites the team has (screens,
    zone, press) — drills requiring others are excluded. style: concept tags to
    favour (weight ×1.5), e.g. dribble_drive. emphasis: theme tags (rebounding,
    closeouts...) whose drills get a strong preference (×4) in every block.
    """
    rng = random.Random(seed)
    plan_warnings_extra: list[str] = []
    ages = [a for a in AGE_LEVELS if a in (ages or [])] or list(AGE_LEVELS)
    focus = [f for f in FOCUS_LABELS if f in (focus or [])] or list(FOCUS_LABELS)
    levels = {lv: int((levels or {}).get(lv, 0) or 0) for lv in SKILL_LEVELS}
    if sum(levels.values()) == 0:
        levels["intermediate"] = n_players
    levels_present = [lv for lv, n in levels.items() if n > 0]

    # Age ceiling on level: 'advanced' is relative to the age group. For a U9-only group the
    # standard version of a drill IS the advanced version; the 'Harder' variation (written
    # with older players in mind) is reserved for U11+.
    level_cap_note = ""
    if set(ages) & GAMES_ONLY_AGES:
        level_cap_note = "U9 (6–8 year olds): every drill is a game; technical drills and the core circuit are left out. "
    if set(ages) == {"U9"} and levels.get("advanced", 0) > 0:
        levels_present = [lv for lv in levels_present if lv != "advanced"] or ["intermediate"]
        if "intermediate" not in levels_present:
            levels_present.append("intermediate")
        level_cap_note += (f"The {levels['advanced']} 'advanced' players work the standard version of each "
                           "drill (the 'Harder' variation is written for U11+ and is hidden).")

    budget = time_budget(duration, ages, include_athletic)
    exclude = set(exclude_ids)
    known = set(concepts_used)
    drills = [d for d in drills if not (d.concepts & set(PREREQ_CONCEPTS)) - known]
    style_tags = set(style)
    weights = dict(weights or {})
    emph = set(emphasis)
    for d in drills:
        if d.concepts & style_tags:
            weights[d.id] = weights.get(d.id, 1.0) * 1.5
        if d.themes & emph:
            weights[d.id] = weights.get(d.id, 1.0) * EMPHASIS_WEIGHT
    games_only = bool(set(ages) & GAMES_ONLY_AGES)
    if games_only:  # U9: only game-like drills, cool-down excepted
        drills = [d for d in drills if d.game_like or d.category == "cooldown"]
    pool = Pool([d for d in drills if d.id not in exclude], ages, levels_present, n_players, baskets, max_groups)
    if not pool.loose:  # everything excluded (tiny database or huge exclusion) — fall back to all drills
        pool = Pool(drills, ages, levels_present, n_players, baskets, max_groups)
    used: set[str] = set()
    blocks: list[Block] = []

    def add_block(title: str, minutes: int, chosen: list[PlannedDrill], note: str = "") -> None:
        if not chosen:
            return
        used.update(pd.drill.id for pd in chosen)
        blocks.append(Block(title, minutes, chosen, note))

    def attach_sideline(chosen: list[PlannedDrill]) -> None:
        """Turn crowded basket drills into split-and-swap blocks.

        If, even using every hoop, a basket drill would have more than
        TARGET_PER_BASKET players per basket, half the team goes to the sideline
        strip for a self-managed drill (low supervision when the coach is alone)
        and the two halves swap halfway through.
        """
        max_sup = "low" if coaches <= 1 else "medium"
        for pd in chosen:
            d = pd.drill
            if not d.needs_basket or d.space == "full_court" or pd.minutes < 8 or pd.sideline:
                continue
            if n_players / d.max_groups(baskets, max_groups) <= TARGET_PER_BASKET:
                continue
            side_pool = pool.select(
                lambda x: x.sideline_ok and SUPERVISION.index(x.supervision) <= SUPERVISION.index(max_sup)
                and x.category != "cooldown", used | {p.drill.id for p in chosen})
            if not side_pool:
                continue
            side = side_pool[rng.randrange(len(side_pool))]
            half = -(-n_players // 2)
            if half < d.min_players:
                continue
            pd.sideline = side
            pd.groups = d.groups_plan(half, baskets, max_groups)
            used.add(side.id)

    # 1. Physical preparation: one warm-up drill + coordination / athletic work.
    warm = pick_block(pool.select(lambda d: d.category == "warmup"), min(6, budget["prep"] - 4), used, rng, max_drills=1, n_players=n_players, baskets=baskets, max_groups=max_groups, ages=ages, weights=weights)
    used.update(pd.drill.id for pd in warm)
    coord_pool = pool.select(lambda d: d.category == "coordination" and d.intensity != "high", used)
    if len(coord_pool) < 2:
        coord_pool = pool.select(lambda d: d.category == "coordination", used)
    coord = pick_block(coord_pool, budget["prep"] - sum(pd.minutes for pd in warm), used, rng, max_drills=2, n_players=n_players, baskets=baskets, max_groups=max_groups, ages=ages, weights=weights)
    prep = warm + coord
    for pd, m in zip(prep, scale_minutes([pd.drill.duration_min for pd in prep], budget["prep"])):
        pd.minutes = m
    add_block("Physical preparation (warm-up + coordination)", budget["prep"], prep,
              "Start every practice here: raise heart rate, mobilise, then coordination and "
              "landing mechanics before any skill work.")

    # 2. Athletic development (optional), right after the warm-up while legs are fresh.
    if budget["athletic"] > 0:
        ath = pick_block(pool.select(lambda d: d.category == "coordination", used), budget["athletic"], used, rng,
                         max_drills=2, n_players=n_players, baskets=baskets, max_groups=max_groups, ages=ages, weights=weights)
        add_block("Athletic development", budget["athletic"], ath,
                  "Speed, jumping and change of direction while the players are warm but not tired.")

    # 3. One skill block per focus area; ball handling first (fresh legs), team concepts last.
    per_focus = scale_minutes([1] * len(focus), budget["skills"])
    unfilled: list[str] = []
    for f, minutes in zip(focus, per_focus):
        fpool = pool.select(lambda d: d.category in SKILL_CATEGORIES and f in d.focus, used)
        primary = pool.select(lambda d: (d.category == f or (games_only and d.category == "game" and not d.game_format))
                              and f in d.focus, used)
        chosen = pick_block(primary, minutes, used, rng, max_drills=3, n_players=n_players, baskets=baskets, max_groups=max_groups, ages=ages, weights=weights)
        got = sum(pd.minutes for pd in chosen)
        if got < minutes and len(chosen) < 3:
            extra = pick_block(fpool, minutes - got, used | {pd.drill.id for pd in chosen}, rng,
                               max_drills=3 - len(chosen), n_players=n_players, baskets=baskets, max_groups=max_groups, ages=ages, weights=weights)
            chosen += extra
            for pd, m in zip(chosen, scale_minutes([pd.drill.duration_min for pd in chosen], minutes)):
                pd.minutes = m
        if not chosen:
            unfilled.append(FOCUS_LABELS[f])
        if sideline_strip:
            attach_sideline(chosen)
        add_block(f"Skill block: {FOCUS_LABELS[f]}", minutes, chosen)

    # Minutes a skill block could not fill go to the game block (games scale to any roster).
    shortfall = budget["skills"] - sum(b.minutes for b in blocks if b.title.startswith("Skill block"))

    # 4. Game: always close with an age-appropriate scrimmage, plus a themed game if time allows.
    game_minutes = budget["game"] + shortfall
    allowed = frozenset.intersection(*(AGE_FORMATS[a] for a in ages)) or frozenset.union(*(AGE_FORMATS[a] for a in ages))
    scrim_pool = pool.select(lambda d: bool(d.game_format & allowed), used)
    if not scrim_pool:  # nothing for this exact roster — accept any scrimmage format
        scrim_pool = pool.select(lambda d: bool(d.game_format), used)
        if scrim_pool:
            plan_warnings_extra = [f"No {'/'.join(sorted(allowed))} scrimmage fits this roster; using another format."]
    scrim_minutes = game_minutes if game_minutes <= 14 else max(10, round(game_minutes * 0.6))
    scrim = pick_block(scrim_pool, scrim_minutes, used, rng, max_drills=1, n_players=n_players,
                       baskets=baskets, max_groups=max_groups, ages=ages, weights=weights)
    rest = game_minutes - sum(pd.minutes for pd in scrim)
    fun_pool = pool.select(lambda d: (d.category == "game" or "game" in d.focus) and not d.game_format, used | {pd.drill.id for pd in scrim})
    themed = [d for d in fun_pool if d.focus & set(focus)]
    fun = pick_block(themed if len(themed) >= 2 else fun_pool, rest, used | {pd.drill.id for pd in scrim}, rng,
                     max_drills=2 if shortfall else 1, n_players=n_players, baskets=baskets, max_groups=max_groups, ages=ages, weights=weights) if rest >= 5 else []
    game = fun + scrim  # scrimmage last
    if rest < 5 and scrim:
        scrim[0].minutes = game_minutes
    if sideline_strip:
        attach_sideline(game)
    add_block("Game (" + "/".join(sorted(allowed)) + " scrimmage)", game_minutes, game,
              "Always finish playing: a small-sided game in the format that suits the age group, "
              "with a rule or variation that reinforces the theme of the day.")

    # Anything still unplanned (very small drill pool) becomes extra coordination work.
    remaining = duration - budget["cooldown"] - sum(b.minutes for b in blocks)
    if remaining > 0:
        extra = pick_block(pool.select(lambda d: d.category == "coordination", used), remaining, used, rng,
                           max_drills=2, n_players=n_players, baskets=baskets, max_groups=max_groups, ages=ages, weights=weights)
        add_block("Extra coordination", remaining, extra)

    # 5. Cool-down.
    cool = pick_block(pool.select(lambda d: d.category == "cooldown", used), budget["cooldown"], used, rng, max_drills=1, n_players=n_players, baskets=baskets, max_groups=max_groups, ages=ages, weights=weights)
    add_block("Cool-down & reflection", budget["cooldown"], cool)

    plan = Plan(n_players, ages, duration, levels, focus, seed, baskets, sideline_strip, coaches,
                include_athletic, budget, level_plan(levels), blocks, level_cap_note=level_cap_note)
    plan.warnings.extend(plan_warnings_extra)
    if not scrim:
        plan.warnings.append("No scrimmage drill fits this roster — the game block has no small-sided game.")
    if plan.planned_minutes != duration:
        plan.warnings.append(
            f"Planned {plan.planned_minutes} min vs requested {duration} min (drill pool too small for some block).")
    if sum(levels.values()) != n_players:
        plan.warnings.append(f"Players per level sum to {sum(levels.values())} but you entered {n_players} players.")
    thin = [b.title.replace("Skill block: ", "") for b in blocks
            if b.title.startswith("Skill block") and b.minutes >= 15 and len(b.drills) < 2]
    if unfilled:
        plan.warnings.append(
            f"No drill in the database fits this roster for: {'; '.join(unfilled)} — those minutes went to the game block. "
            "More baskets (or a tighter age/level selection) widens the choice.")
    elif thin:
        plan.warnings.append(
            "Few drills fit this roster for: " + "; ".join(thin)
            + ". With a big group, more baskets (or a tighter age/level selection) widens the choice.")
    return plan


# ------------------------------------------------------------------------ export


def plan_to_markdown(plan: Plan) -> str:
    present = {k: v for k, v in plan.levels.items() if v > 0}
    show_easier = plan.level_plan.mode == "split" or "beginner" in present
    show_harder = (plan.level_plan.mode == "split" or "advanced" in present) and "hidden" not in plan.level_cap_note
    lines = [
        f"# Practice plan — {plan.duration} min",
        "",
        f"- Players: {plan.n_players} ({', '.join(f'{v} {k}' for k, v in present.items())})",
        f"- Age groups: {', '.join(plan.ages)}",
        f"- Focus: {'; '.join(FOCUS_LABELS[f] for f in plan.focus)}",
        f"- Baskets available: {plan.baskets} · sideline strip: {'yes' if plan.sideline_strip else 'no'} · coaches: {plan.coaches}",
    ]
    if plan.level_plan.note:
        lines.append(f"- Groups: {plan.level_plan.note}")
    if plan.level_cap_note:
        lines.append(f"- Level: {plan.level_cap_note}")
    lines.append("")
    t = 0
    for b in plan.blocks:
        lines.append(f"## {b.title} ({b.minutes} min, from {t:02d}')")
        if b.note:
            lines += ["", f"_{b.note}_"]
        lines.append("")
        for pd in b.drills:
            d = pd.drill
            lines += [
                f"### {d.name} — {pd.minutes} min  ({d.id})",
                f"- Players: {d.min_players}–{d.max_players} · Intensity: {d.intensity} · Equipment: {d.equipment}",
                f"- How: {d.description}",
                f"- Coaching points: {d.coaching_points}",
                f"- Source: {d.source}",
            ]
            if pd.age_note:
                lines.append(f"- Age: {pd.age_note}")
            if pd.setup_note:
                lines.append(f"- Organisation: {pd.setup_note}")
            if pd.sideline:
                sd = pd.sideline
                lines.append(f"- Sideline drill — {sd.name} ({sd.id}): {sd.description} Coaching points: {sd.coaching_points}")
            if show_easier:
                lines.append(f"- Easier (beginners): {d.easier}")
            if show_harder:
                lines.append(f"- Harder (advanced): {d.harder}")
            for v in d.variants:
                lines.append(f"- Variant: {v}")
            lines.append("")
            t += pd.minutes
    for w in plan.warnings:
        lines.append(f"> Note: {w}")
    return "\n".join(lines)
