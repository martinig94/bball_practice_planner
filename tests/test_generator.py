"""Run with:  pytest"""

import itertools
from pathlib import Path

import pytest

from planner import (AGE_LEVELS, FOCUS_LABELS, SKILL_LEVELS, generate_practice, load_drills,
                     plan_to_markdown)
from planner.generator import AGE_FORMATS
from planner.generator import CATEGORIES, SPACES, SUPERVISION, level_plan, scale_minutes

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def drills():
    return load_drills(ROOT / "data" / "drills.csv")


# --- database sanity ----------------------------------------------------------

def test_database_size(drills):
    assert len(drills) >= 100


def test_database_fields(drills):
    for d in drills:
        assert d.min_players <= d.max_players, d.id
        assert d.duration_min > 0, d.id
        assert d.ages <= set(AGE_LEVELS), d.id
        assert d.levels <= set(SKILL_LEVELS), d.id
        assert d.category in CATEGORIES, d.id
        assert d.description, d.id
        assert d.source, d.id
        assert d.space in SPACES, d.id
        assert d.supervision in SUPERVISION, d.id
        if d.sideline_ok:
            assert not d.needs_basket and d.space != "full_court", d.id
        if d.space == "full_court":
            assert d.max_players >= 15, d.id  # full-court drills cannot be split, so they must hold a squad


@pytest.mark.parametrize("age", AGE_LEVELS)
def test_physical_prep_available_for_every_age(drills, age):
    assert sum(1 for d in drills if d.category == "warmup" and age in d.ages) >= 3
    assert sum(1 for d in drills if d.category == "coordination" and age in d.ages) >= 3


# --- generator over the full grid of inputs -----------------------------------------

AGE_SETS = [["U9"], ["U11"], ["U14"], ["U9", "U11"], ["U11", "U13"], list(AGE_LEVELS)]
FOCUS_SETS = [["ballhandling"], ["offense", "defense"],
              ["ballhandling", "passing_shooting", "offense"], list(FOCUS_LABELS)]
GRID = list(itertools.product((60, 90, 120), AGE_SETS, (5, 8, 12, 18, 25), FOCUS_SETS,
                              ((2, 1, True, True), (3, 1, False, False), (4, 2, True, True))))


@pytest.mark.parametrize("duration,ages,n,focus,court", GRID)
def test_plan_structure(drills, duration, ages, n, focus, court):
    baskets, coaches, strip, athletic = court
    third = n // 3
    levels = {"beginner": third, "intermediate": n - 2 * third, "advanced": third}
    plan = generate_practice(drills, n, ages, duration, levels, focus,
                             seed=hash((duration, n, tuple(focus), court)) % 10_000,
                             baskets=baskets, coaches=coaches, sideline_strip=strip, include_athletic=athletic)

    # block order: prep, [athletic], skills..., game, cool-down
    titles = [b.title for b in plan.blocks]
    assert titles[0].startswith("Physical preparation")
    assert ("Athletic development" in titles) == athletic
    if athletic:
        assert titles[1] == "Athletic development"
    assert titles[-2].startswith("Game (")
    assert titles[-1].startswith("Cool-down")

    # the game block ends with a scrimmage in an age-appropriate format
    game = plan.blocks[-2]
    last = game.drills[-1].drill
    allowed = frozenset.intersection(*(AGE_FORMATS[a] for a in ages)) or frozenset.union(*(AGE_FORMATS[a] for a in ages))
    if last.game_format & allowed:
        pass
    else:
        assert n == 25 or n < 8, "only a huge or tiny roster may fall back to another scrimmage format"
        assert any("scrimmage" in w for w in plan.warnings)

    # nobody waits: every drill fits the players on court once split into allowed parallel groups
    for b in plan.blocks:
        for pd in b.drills:
            assert pd.groups * pd.drill.max_players >= pd.court_players, pd.drill.id
            assert pd.groups <= pd.drill.max_groups(baskets), pd.drill.id
            if pd.drill.space == "full_court":
                assert pd.groups == 1, pd.drill.id
            assert (pd.setup_note != "") == (pd.groups > 1 or pd.sideline is not None)
            if pd.sideline is not None:
                assert strip
                assert pd.sideline.sideline_ok
                assert pd.sideline.supervision == "low" if coaches == 1 else pd.sideline.supervision != "high"
                assert pd.court_players + pd.sideline_players == n
                assert pd.court_players >= pd.drill.min_players

    ids = plan.drill_ids
    assert len(ids) == len(set(ids)), "a drill is repeated in the plan"
    assert plan.planned_minutes == duration
    assert not [w for w in plan.warnings if "Planned" in w]

    first = plan.blocks[0]
    assert first.title.startswith("Physical preparation")
    assert 5 <= first.minutes <= 15
    assert {pd.drill.category for pd in first.drills} <= {"warmup", "coordination"}
    assert any(pd.drill.category == "warmup" for pd in first.drills)

    assert all(pd.drill.min_players <= n for b in plan.blocks for pd in b.drills)
    n_skill_blocks = sum(1 for b in plan.blocks if b.title.startswith("Skill block"))
    if n_skill_blocks < len(focus):
        # only allowed when the database truly has nothing for that roster, and the coach is told
        assert n == 25
        assert any(w.startswith("No drill in the database fits") for w in plan.warnings)
    else:
        assert n_skill_blocks == len(focus)

    md = plan_to_markdown(plan)
    assert f"# Practice plan — {duration} min" in md
    for b in plan.blocks:
        assert b.title in md


# --- helpers --------------------------------------------------------------------------

def test_scale_minutes_sums_to_target():
    for target in range(4, 40):
        for durations in ([5], [6, 8], [5, 7, 9], [10, 10, 10]):
            assert sum(scale_minutes(durations, target)) == target


def test_level_plan():
    assert level_plan({"beginner": 0, "intermediate": 10, "advanced": 0}).mode == "single"
    mixed = level_plan({"beginner": 4, "intermediate": 4, "advanced": 2})
    assert mixed.mode == "split"
    assert "fewer than 3" in mixed.note


def test_same_seed_same_plan(drills):
    a = generate_practice(drills, 10, ["U13"], 90, seed=42)
    b = generate_practice(drills, 10, ["U13"], 90, seed=42)
    assert a.drill_ids == b.drill_ids


def test_level_mismatch_warning(drills):
    plan = generate_practice(drills, 12, ["U13"], 60, {"beginner": 5, "intermediate": 5, "advanced": 0})
    assert any("Players per level" in w for w in plan.warnings)


def test_big_roster_two_baskets_never_queues_at_a_hoop(drills):
    plan = generate_practice(drills, 25, ["U13", "U14"], 90, focus=["passing_shooting"], seed=3, baskets=2)
    for b in plan.blocks:
        for pd in b.drills:
            assert pd.groups * pd.drill.max_players >= pd.court_players, pd.drill.id
            if pd.drill.space == "full_court":
                assert pd.drill.max_players >= pd.court_players, pd.drill.id


def test_alone_with_two_baskets_uses_split_and_swap(drills):
    plan = generate_practice(drills, 25, ["U13", "U14"], 90, focus=["passing_shooting", "defense"],
                             seed=11, baskets=2, coaches=1, sideline_strip=True)
    swaps = [pd for b in plan.blocks for pd in b.drills if pd.sideline]
    assert swaps, "crowded basket drills should become split-and-swap blocks"
    assert all(pd.sideline.supervision == "low" for pd in swaps)
    assert all("Swap after" in pd.setup_note for pd in swaps)


def test_no_strip_means_no_split_and_swap(drills):
    plan = generate_practice(drills, 25, ["U13", "U14"], 90, focus=["passing_shooting", "defense"],
                             seed=11, baskets=2, coaches=1, sideline_strip=False)
    assert not any(pd.sideline for b in plan.blocks for pd in b.drills)


def test_side_baskets_open_more_half_court_drills(drills):
    from planner.generator import Pool
    two = Pool(drills, ["U13"], ["intermediate"], 25, baskets=2)
    four = Pool(drills, ["U13"], ["intermediate"], 25, baskets=4)
    assert len(four.strict) > len(two.strict)


def test_groups_for():
    d = next(iter(load_drills(ROOT / "data" / "drills.csv")))
    assert d.groups_for(d.max_players) == 1
    assert d.groups_for(d.max_players + 1) == 2


def test_young_groups_get_more_game_time(drills):
    assert generate_practice(drills, 10, ["U9"], 60, seed=1).budget["game"] == 17
    assert generate_practice(drills, 10, ["U13"], 60, seed=1).budget["game"] == 12


def test_athletic_optional_gives_minutes_back_to_skills(drills):
    with_ = generate_practice(drills, 12, ["U13"], 90, seed=1, include_athletic=True)
    without = generate_practice(drills, 12, ["U13"], 90, seed=1, include_athletic=False)
    assert without.budget["skills"] == with_.budget["skills"] + with_.budget["athletic"]
    assert without.planned_minutes == with_.planned_minutes == 90


@pytest.mark.parametrize("ages,expected", [(["U9"], {"2v2", "3v3"}), (["U11"], {"3v3", "4v4"}),
                                           (["U13"], {"3v3", "4v4", "5v5"}), (["U9", "U11"], {"3v3"})])
def test_scrimmage_format_by_age(drills, ages, expected):
    for seed in range(5):
        plan = generate_practice(drills, 12, ages, 90, seed=seed)
        last = plan.blocks[-2].drills[-1].drill
        assert last.game_format & expected, (ages, last.id)


def test_offense_focus_has_half_court_and_transition(drills):
    off = [d for d in drills if d.category == "offense"]
    assert len(off) >= 12
    assert any(d.space == "full_court" for d in off) and any(d.space == "half_court" for d in off)


def test_u9_advanced_is_capped(drills):
    plan = generate_practice(drills, 12, ["U9"], 90, {"beginner": 4, "intermediate": 4, "advanced": 4}, seed=1)
    assert plan.level_cap_note
    assert "Harder (advanced)" not in plan_to_markdown(plan)
    plan11 = generate_practice(drills, 12, ["U11"], 90, {"beginner": 4, "intermediate": 4, "advanced": 4}, seed=1)
    assert not plan11.level_cap_note


def test_single_age_groups_never_get_off_age_drills(drills):
    for age in AGE_LEVELS:
        for seed in range(8):
            plan = generate_practice(drills, 12, [age], 90, focus=list(FOCUS_LABELS), seed=seed)
            for b in plan.blocks:
                for pd in b.drills:
                    assert age in pd.drill.ages, (age, pd.drill.id)
                    assert pd.age_note == ""


def test_off_age_drills_are_flagged_in_mixed_groups(drills):
    flagged = 0
    for seed in range(20):
        plan = generate_practice(drills, 12, ["U9", "U11"], 90, focus=["offense", "team_concepts"], seed=seed)
        for b in plan.blocks:
            for pd in b.drills:
                if not {"U9", "U11"} <= pd.drill.ages:
                    assert pd.age_note.startswith("Written for"), pd.drill.id
                    flagged += 1
    assert flagged > 0  # the fallback is exercised, and every use is flagged


def test_age_specific_drills_are_preferred(drills):
    from planner.generator import age_specificity
    assert age_specificity(next(d for d in drills if len(d.ages) == 4)) == 0.25
    assert age_specificity(next(d for d in drills if len(d.ages) == 1)) == 1.0
    all_age_share = []
    for seed in range(30):
        plan = generate_practice(drills, 12, ["U14"], 90, focus=list(FOCUS_LABELS), seed=seed)
        picks = [pd.drill for b in plan.blocks for pd in b.drills]
        all_age_share.append(sum(len(d.ages) == 4 for d in picks) / len(picks))
    pool_share = sum(len(d.ages) == 4 for d in drills if "U14" in d.ages) / sum("U14" in d.ages for d in drills)
    assert sum(all_age_share) / len(all_age_share) < pool_share  # picked less often than their share of the pool
