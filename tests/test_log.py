"""Practice log and drill editor round-trip tests."""

from datetime import date
from pathlib import Path

import pytest

from planner import Drill, generate_practice, load_drills, next_drill_id, save_drills
from planner.log import (LogEntry, drill_stats, load_log, log_plan, rating_weights, recent_drill_ids,
                         save_log)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def drills():
    return load_drills(ROOT / "data" / "drills.csv")


def test_log_plan_and_reload(drills, tmp_path):
    log = tmp_path / "log.csv"
    plan = generate_practice(drills, 12, ["U13"], 90, seed=1)
    pid = log_plan(plan, log, on=date(2026, 9, 24))
    assert pid == "2026-09-24-1"
    entries = load_log(log)
    assert {e.drill_id for e in entries} >= set(plan.drill_ids)
    assert all(e.rating is None for e in entries)
    # a second practice the same day gets a new id
    assert log_plan(plan, log, on=date(2026, 9, 24)) == "2026-09-24-2"


def test_ratings_round_trip(tmp_path):
    log = tmp_path / "log.csv"
    entries = [LogEntry("2026-09-01", "2026-09-01-1", "BH01", "x", "b", 5, "U13", 12, rating=4, notes="good"),
               LogEntry("2026-09-01", "2026-09-01-1", "BH02", "y", "b", 5, "U13", 12)]
    save_log(entries, log)
    back = load_log(log)
    assert back[0].rating == 4 and back[0].notes == "good" and back[1].rating is None


def test_stats_weights_and_bans():
    entries = [
        LogEntry("2026-09-01", "p1", "A", "", "", 5, "U13", 12, rating=5),
        LogEntry("2026-09-08", "p2", "A", "", "", 5, "U13", 12, rating=4),
        LogEntry("2026-09-08", "p2", "B", "", "", 5, "U13", 12, rating=0),
        LogEntry("2026-09-15", "p3", "C", "", "", 5, "U13", 12),
    ]
    s = drill_stats(entries)
    assert s["A"].uses == 2 and s["A"].avg_rating == 4.5 and s["A"].last_used == "2026-09-08"
    assert s["C"].avg_rating is None
    weights, banned = rating_weights(entries)
    assert banned == {"B"}
    assert weights["A"] == pytest.approx(1.5) and "C" not in weights
    assert recent_drill_ids(entries, 1) == {"C"}
    assert recent_drill_ids(entries, 2) == {"A", "B", "C"}
    assert recent_drill_ids(entries, 0) == set()


def test_planner_respects_exclusions_and_bans(drills):
    plan0 = generate_practice(drills, 12, ["U13"], 90, seed=3)
    used = set(plan0.drill_ids)
    plan1 = generate_practice(drills, 12, ["U13"], 90, seed=3, exclude_ids=used)
    assert not used & set(plan1.drill_ids)
    assert plan1.planned_minutes == 90


def test_weights_change_selection_frequency(drills):
    target = "BH01"  # all-ages stationary ball handling, eligible for U13
    base = sum(target in generate_practice(drills, 12, ["U13"], 90, focus=["ballhandling"], seed=s).drill_ids for s in range(60))
    boosted = sum(target in generate_practice(drills, 12, ["U13"], 90, focus=["ballhandling"], seed=s,
                                              weights={target: 5.0}).drill_ids for s in range(60))
    assert boosted > base


def test_save_drills_round_trip_and_editor_fields(drills, tmp_path):
    out = tmp_path / "drills.csv"
    new = Drill(id=next_drill_id(drills, "ballhandling"), name="Editor test", category="ballhandling",
                focus=frozenset({"ballhandling"}), ages=frozenset({"U9"}), levels=frozenset({"beginner"}),
                min_players=2, max_players=30, duration_min=5, intensity="low", equipment="balls",
                description="desc", coaching_points="cp", easier="", harder="",
                needs_basket=False, space="small_area", sideline_ok=True, supervision="low",
                game_format=frozenset(), source="original", variants=("Weak hand only", "Add a defender"))
    assert new.id not in {d.id for d in drills}
    save_drills(list(drills) + [new], out)
    back = load_drills(out)
    assert len(back) == len(drills) + 1
    got = next(d for d in back if d.id == new.id)
    assert got.variants == ("Weak hand only", "Add a defender") and got.sideline_ok and not got.needs_basket
    for a, b in zip(drills, back):  # existing rows survive unchanged (as sets)
        assert (a.id, a.name, a.ages, a.levels, a.focus, a.description) == (b.id, b.name, b.ages, b.levels, b.focus, b.description)


def test_save_drills_rejects_duplicate_ids(drills, tmp_path):
    with pytest.raises(ValueError):
        save_drills(list(drills) + [drills[0]], tmp_path / "x.csv")
