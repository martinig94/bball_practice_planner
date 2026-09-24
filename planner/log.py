"""Practice log: which drills were used when, and how they went (0–5 stars).

Stored as a plain CSV (data/practice_log.csv) so it lives in the repo and can be
edited by hand. One row per drill per practice.

Rating scale: blank = not rated yet; 0 = never again (excluded from future plans);
1–5 stars = weight in future sampling (3 = neutral).
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Iterable

LOG_COLUMNS = ("date", "practice_id", "drill_id", "drill_name", "block", "minutes", "ages", "n_players", "rating", "notes")


@dataclass
class LogEntry:
    date: str
    practice_id: str
    drill_id: str
    drill_name: str
    block: str
    minutes: int
    ages: str
    n_players: int
    rating: int | None = None  # None = unrated, 0..5
    notes: str = ""

    def to_row(self) -> dict[str, str]:
        return {
            "date": self.date, "practice_id": self.practice_id, "drill_id": self.drill_id,
            "drill_name": self.drill_name, "block": self.block, "minutes": str(self.minutes),
            "ages": self.ages, "n_players": str(self.n_players),
            "rating": "" if self.rating is None else str(self.rating), "notes": self.notes,
        }

    @classmethod
    def from_row(cls, r: dict[str, str]) -> "LogEntry":
        rating = (r.get("rating") or "").strip()
        return cls(
            date=r["date"], practice_id=r["practice_id"], drill_id=r["drill_id"],
            drill_name=r.get("drill_name", ""), block=r.get("block", ""),
            minutes=int(r.get("minutes") or 0), ages=r.get("ages", ""),
            n_players=int(r.get("n_players") or 0),
            rating=int(float(rating)) if rating else None, notes=r.get("notes", ""),
        )


@dataclass
class DrillStats:
    uses: int = 0
    ratings: list[int] = field(default_factory=list)
    last_used: str = ""

    @property
    def avg_rating(self) -> float | None:
        return sum(self.ratings) / len(self.ratings) if self.ratings else None


def load_log(path: str | Path = "data/practice_log.csv") -> list[LogEntry]:
    p = Path(path)
    if not p.exists():
        return []
    with open(p, newline="", encoding="utf-8") as fh:
        return [LogEntry.from_row(r) for r in csv.DictReader(fh)]


def save_log(entries: Iterable[LogEntry], path: str | Path = "data/practice_log.csv") -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=LOG_COLUMNS)
        w.writeheader()
        for e in entries:
            w.writerow(e.to_row())


def log_plan(plan, path: str | Path = "data/practice_log.csv", on: date | None = None) -> str:
    """Append every drill of a plan (incl. sideline drills) to the log. Returns the practice id."""
    on = on or date.today()
    entries = load_log(path)
    same_day = {e.practice_id for e in entries if e.date == on.isoformat()}
    practice_id = f"{on.isoformat()}-{len(same_day) + 1}"
    ages = "/".join(plan.ages)
    for b in plan.blocks:
        for pd in b.drills:
            entries.append(LogEntry(on.isoformat(), practice_id, pd.drill.id, pd.drill.name, b.title,
                                    pd.minutes, ages, plan.n_players))
            if pd.sideline:
                entries.append(LogEntry(on.isoformat(), practice_id, pd.sideline.id, pd.sideline.name,
                                        b.title + " (sideline)", pd.minutes, ages, plan.n_players))
    save_log(entries, path)
    return practice_id


def drill_stats(entries: Iterable[LogEntry]) -> dict[str, DrillStats]:
    stats: dict[str, DrillStats] = {}
    for e in entries:
        s = stats.setdefault(e.drill_id, DrillStats())
        s.uses += 1
        if e.rating is not None:
            s.ratings.append(e.rating)
        if e.date > s.last_used:
            s.last_used = e.date
    return stats


def recent_drill_ids(entries: Iterable[LogEntry], last_n_practices: int) -> set[str]:
    """Drill ids used in the most recent `last_n_practices` practices."""
    if last_n_practices <= 0:
        return set()
    practices = sorted({e.practice_id for e in entries}, reverse=True)[:last_n_practices]
    return {e.drill_id for e in entries if e.practice_id in practices}


def rating_weights(entries: Iterable[LogEntry]) -> tuple[dict[str, float], set[str]]:
    """Sampling weight per drill from its average rating, and the set of 0-star (banned) drills.

    3 stars = neutral (1.0); 5 stars = 1.67; 1 star = 0.33. Unrated drills keep weight 1.0.
    A drill whose average rounds to 0 is excluded from future plans.
    """
    weights: dict[str, float] = {}
    banned: set[str] = set()
    for drill_id, s in drill_stats(entries).items():
        avg = s.avg_rating
        if avg is None:
            continue
        if avg < 0.5:
            banned.add(drill_id)
        else:
            weights[drill_id] = avg / 3.0
    return weights, banned
