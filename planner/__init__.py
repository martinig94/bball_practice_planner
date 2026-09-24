"""Basketball practice planner — pure planning logic (no UI dependency)."""

from .generator import (
    AGE_LEVELS,
    FOCUS_LABELS,
    SKILL_LEVELS,
    Drill,
    Plan,
    generate_practice,
    load_drills,
    next_drill_id,
    plan_to_markdown,
    save_drills,
)

__all__ = [
    "AGE_LEVELS",
    "FOCUS_LABELS",
    "SKILL_LEVELS",
    "Drill",
    "Plan",
    "generate_practice",
    "load_drills",
    "next_drill_id",
    "plan_to_markdown",
    "save_drills",
]
