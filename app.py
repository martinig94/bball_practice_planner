"""Basketball Practice Planner — Streamlit UI.

Run with:  streamlit run app.py
"""

from __future__ import annotations

import random
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

from planner import (AGE_LEVELS, FOCUS_LABELS, SKILL_LEVELS, Drill, generate_practice, load_drills,
                     next_drill_id, plan_to_markdown, save_drills)
from planner.generator import CATEGORIES, FOCUS_TAGS, GAME_FORMATS, INTENSITIES, SPACES, SUPERVISION
from planner.log import LogEntry, drill_stats, load_log, log_plan, rating_weights, recent_drill_ids, save_log

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data" / "drills.csv"
LOG = ROOT / "data" / "practice_log.csv"

st.set_page_config(page_title="Practice Planner", page_icon="🏀", layout="wide")


@st.cache_data
def drills_cached(mtime: float):
    """Reload the CSV whenever the file changes on disk."""
    return load_drills(DATA)


drills = drills_cached(DATA.stat().st_mtime)
drill_by_id = {d.id: d for d in drills}
log_entries = load_log(LOG)
stats = drill_stats(log_entries)

if "seed" not in st.session_state:
    st.session_state.seed = random.randint(1, 999_999)

# ------------------------------------------------------------------- sidebar form

with st.sidebar:
    st.header("Group")
    n_players = st.number_input("Number of players", min_value=2, max_value=30, value=12, step=1)
    side_baskets = st.number_input("Side baskets in use", min_value=0, max_value=2, value=0, step=1,
                                   help="Full court with 2 main baskets, plus up to 2 side baskets on the same court. "
                                        "Half-court drills can run one group per basket; full-court drills always use the whole floor.")
    baskets = 2 + int(side_baskets)
    sideline_strip = st.checkbox("Sideline strip available", value=True,
                                 help="The narrow area along the long side of the court. Used for split-and-swap "
                                      "blocks: half the team does a self-managed drill there while the other half "
                                      "works at the baskets, then they swap.")
    coaches = st.number_input("Coaches on the floor", min_value=1, max_value=4, value=1, step=1,
                              help="Alone, the sideline drill must need little supervision.")
    st.caption(f"Court: full court, {baskets} baskets in use"
               f"{', sideline strip' if sideline_strip else ''} · {coaches} coach{'es' if coaches > 1 else ''}.")
    ages = st.multiselect("Age categories", AGE_LEVELS, default=["U13"])

    st.subheader("Players per level")
    st.caption("Split the group into three levels. Leave a level at 0 if not present.")
    c1, c2, c3 = st.columns(3)
    lv_beg = c1.number_input("Beginner", min_value=0, max_value=30, value=0, step=1)
    lv_int = c2.number_input("Intermed.", min_value=0, max_value=30, value=12, step=1)
    lv_adv = c3.number_input("Advanced", min_value=0, max_value=30, value=0, step=1)
    levels = dict(zip(SKILL_LEVELS, (lv_beg, lv_int, lv_adv)))
    if sum(levels.values()) != n_players:
        st.warning(f"Levels sum to {sum(levels.values())}, players = {n_players}.", icon="⚠️")

    st.header("Practice")
    duration = st.radio("Length (minutes)", (60, 90, 120), index=1, horizontal=True)
    include_athletic = st.checkbox("Athletic development block", value=True,
                                   help="Speed, jumps, change of direction — right after the warm-up. "
                                        "Off: those minutes go to the skill blocks.")
    focus = st.multiselect(
        "Focus areas", list(FOCUS_LABELS), default=["ballhandling", "passing_shooting"],
        format_func=FOCUS_LABELS.get,
    )

    if st.button("🔀 Reshuffle drills", use_container_width=True):
        st.session_state.seed = random.randint(1, 999_999)

    st.header("Memory")
    avoid_n = st.number_input("Avoid drills used in the last … practices", min_value=0, max_value=10, value=2, step=1,
                              help="Uses the practice log. 0 = no restriction.")
    use_ratings = st.checkbox("Prefer well-rated drills", value=True,
                              help="Drills you rated high are picked more often, low less often; 0 stars = never again.")
    st.caption("Every plan opens with 5–15 min of physical preparation (warm-up + coordination) "
               "and closes with a small-sided game in the format that suits the age group.")

# ---------------------------------------------------------------------------- tabs

tab_plan, tab_log, tab_library, tab_edit, tab_about = st.tabs(
    ["Plan a practice", "Practice log", "Drill library", "Edit drills", "About"])

with tab_plan:
    weights, banned = rating_weights(log_entries) if use_ratings else ({}, set())
    exclude = recent_drill_ids(log_entries, int(avoid_n)) | banned
    plan = generate_practice(
        drills, n_players=int(n_players), ages=ages, duration=int(duration),
        levels=levels, focus=focus, seed=st.session_state.seed, baskets=baskets,
        sideline_strip=sideline_strip, coaches=int(coaches), include_athletic=include_athletic,
        exclude_ids=exclude, weights=weights,
    )
    present = {k: v for k, v in plan.levels.items() if v > 0}
    show_easier = plan.level_plan.mode == "split" or "beginner" in present
    show_harder = (plan.level_plan.mode == "split" or "advanced" in present) and not plan.level_cap_note

    head, save, dl = st.columns([3, 1, 1])
    if save.button("💾 Save to practice log", use_container_width=True,
                   help="Records every drill of this plan with today's date so you can rate it afterwards."):
        pid = log_plan(plan, LOG)
        st.toast(f"Saved as practice {pid}. Rate it in the Practice log tab.", icon="💾")
        st.rerun()
    head.markdown(
        f"## {plan.duration}-minute practice &nbsp; "
        f"<span style='font-size:0.6em;color:gray'>{plan.n_players} players · {' · '.join(plan.ages)} · "
        f"{' · '.join(FOCUS_LABELS[f] for f in plan.focus)} · seed {plan.seed}</span>",
        unsafe_allow_html=True,
    )
    dl.download_button(
        "⬇️ Download plan (.md)", plan_to_markdown(plan),
        file_name=f"practice_{date.today():%Y%m%d}_{plan.duration}min.md", mime="text/markdown",
        use_container_width=True,
    )

    if plan.level_plan.note:
        st.info(plan.level_plan.note, icon="👥")
    if plan.level_cap_note:
        st.info(plan.level_cap_note, icon="🧒")
    for w in plan.warnings:
        st.warning(w, icon="⚠️")

    # timeline overview
    t = 0
    rows = []
    for b in plan.blocks:
        for pd_ in b.drills:
            rows.append({"Start": f"{t:02d}'", "Min": pd_.minutes, "Block": b.title, "Drill": pd_.drill.name,
                         "Sideline drill": pd_.sideline.name if pd_.sideline else "", "Groups": pd_.groups,
                         "Intensity": pd_.drill.intensity, "Equipment": pd_.drill.equipment})
            t += pd_.minutes
    with st.expander("Timeline overview", expanded=False):
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

    # blocks
    t = 0
    for b in plan.blocks:
        st.markdown(f"### {b.title} &nbsp; <span style='font-size:0.65em;color:gray'>{b.minutes} min · starts at {t:02d}'</span>",
                    unsafe_allow_html=True)
        if b.note:
            st.caption(b.note)
        for pd_ in b.drills:
            d = pd_.drill
            with st.expander(f"**{d.name}** — {pd_.minutes} min", expanded=True):
                st.caption(f"{d.id} · {d.min_players}–{d.max_players} players per group · intensity {d.intensity} · "
                           f"equipment: {d.equipment} · {d.space.replace('_', ' ')}{' · needs a basket' if d.needs_basket else ''}")
                if pd_.age_note:
                    st.markdown(f":blue[**Age**] {pd_.age_note}")
                if pd_.setup_note:
                    st.markdown(f":orange[**Organisation**] {pd_.setup_note}")
                st.write(d.description)
                st.markdown(f"**Coaching points:** {d.coaching_points}")
                if pd_.sideline:
                    sd = pd_.sideline
                    with st.container(border=True):
                        st.markdown(f":violet[**Sideline strip — {sd.name}**] &nbsp; "
                                    f"<span style='color:gray;font-size:0.85em'>{sd.id} · supervision {sd.supervision} · "
                                    f"equipment: {sd.equipment}</span>", unsafe_allow_html=True)
                        st.write(sd.description)
                        st.markdown(f"**Coaching points:** {sd.coaching_points}")
                if show_easier:
                    st.markdown(f":green[**Easier**] {d.easier}")
                if show_harder:
                    st.markdown(f":red[**Harder**] {d.harder}")
                for v in d.variants:
                    st.markdown(f":gray[**Variant**] {v}")
                s_ = stats.get(d.id)
                hist = (f" · used {s_.uses}× (last {s_.last_used})" + (f" · ★ {s_.avg_rating:.1f}" if s_.avg_rating is not None else "")) if s_ else ""
                st.caption(f"Source: {d.source}{hist}")
        t += b.minutes

with tab_log:
    if not log_entries:
        st.info("No practice saved yet. Build a plan and press **Save to practice log**; then come back here to rate each drill from 0 to 5 stars.", icon="📓")
    else:
        st.caption("Rate each drill 0–5 (0 = never again, 3 = fine, 5 = great) and add notes. Ratings feed the planner: "
                   "well-rated drills come up more often, 0-star drills are excluded, and recently used drills are avoided.")
        practices = sorted({e.practice_id for e in log_entries}, reverse=True)
        chosen = st.selectbox("Practice", practices, format_func=lambda p: f"{p}  ·  {next(e.ages for e in log_entries if e.practice_id == p)} · {next(e.n_players for e in log_entries if e.practice_id == p)} players")
        rows_ = [e for e in log_entries if e.practice_id == chosen]
        table = pd.DataFrame([{"drill_id": e.drill_id, "drill": e.drill_name, "block": e.block, "min": e.minutes,
                               "rating": e.rating, "notes": e.notes} for e in rows_])
        edited = st.data_editor(
            table, hide_index=True, use_container_width=True, key=f"editor_{chosen}",
            column_config={
                "drill_id": st.column_config.TextColumn(disabled=True),
                "drill": st.column_config.TextColumn(disabled=True),
                "block": st.column_config.TextColumn(disabled=True),
                "min": st.column_config.NumberColumn(disabled=True),
                "rating": st.column_config.NumberColumn("rating (0–5)", min_value=0, max_value=5, step=1, format="%d ★"),
                "notes": st.column_config.TextColumn("notes", width="large"),
            },
        )
        c1, c2 = st.columns([1, 1])
        if c1.button("💾 Save ratings", use_container_width=True):
            for e, (_, r) in zip(rows_, edited.iterrows()):
                e.rating = None if pd.isna(r["rating"]) else int(r["rating"])
                e.notes = "" if pd.isna(r["notes"]) else str(r["notes"])
            save_log(log_entries, LOG)
            st.toast("Ratings saved.", icon="⭐")
            st.rerun()
        if c2.button("🗑️ Delete this practice from the log", use_container_width=True):
            save_log([e for e in log_entries if e.practice_id != chosen], LOG)
            st.rerun()

        st.markdown("#### Drill history")
        hist_rows = []
        for did, s_ in sorted(stats.items(), key=lambda kv: (-kv[1].uses, kv[0])):
            d = drill_by_id.get(did)
            hist_rows.append({"id": did, "drill": d.name if d else "(deleted)", "uses": s_.uses, "last used": s_.last_used,
                              "avg ★": None if s_.avg_rating is None else round(s_.avg_rating, 1),
                              "ratings": len(s_.ratings)})
        st.dataframe(pd.DataFrame(hist_rows), hide_index=True, use_container_width=True, height=300)

with tab_library:
    st.caption(f"{len(drills)} drills. Filter below, then pick a drill to see the full description. "
               "To add your own, append rows to `data/drills.csv` (see README).")
    f1, f2, f3, f4 = st.columns(4)
    cat = f1.multiselect("Category", sorted({d.category for d in drills}))
    age_f = f2.multiselect("Age", AGE_LEVELS)
    lvl_f = f3.multiselect("Level", SKILL_LEVELS)
    text = f4.text_input("Search text")

    view = [
        d for d in drills
        if (not cat or d.category in cat)
        and (not age_f or set(age_f) <= d.ages)
        and (not lvl_f or set(lvl_f) <= d.levels)
        and (not text or text.lower() in f"{d.name} {d.description} {d.coaching_points} {d.equipment}".lower())
    ]
    table = pd.DataFrame([{
        "id": d.id, "name": d.name, "category": d.category, "focus": ", ".join(sorted(d.focus)),
        "ages": " ".join(a for a in AGE_LEVELS if a in d.ages),
        "levels": ", ".join(l for l in SKILL_LEVELS if l in d.levels),
        "players": f"{d.min_players}–{d.max_players}", "space": d.space.replace("_", " "),
        "basket": "yes" if d.needs_basket else "", "sideline": "yes" if d.sideline_ok else "",
        "supervision": d.supervision, "source": d.source.split(" (")[0].split(" —")[0],
        "uses": stats[d.id].uses if d.id in stats else 0,
        "avg ★": (round(stats[d.id].avg_rating, 1) if d.id in stats and stats[d.id].avg_rating is not None else None),
        "min": d.duration_min, "intensity": d.intensity, "equipment": d.equipment,
    } for d in view])
    st.dataframe(table, hide_index=True, use_container_width=True, height=420)

    if view:
        pick = st.selectbox("Drill details", view, format_func=lambda d: f"{d.id} — {d.name}")
        st.markdown(f"#### {pick.name}")
        st.write(pick.description)
        st.markdown(f"**Coaching points:** {pick.coaching_points}")
        st.markdown(f":green[**Easier**] {pick.easier}")
        st.markdown(f":red[**Harder**] {pick.harder}")
        for v in pick.variants:
            st.markdown(f":gray[**Variant**] {v}")
        st.caption(f"Source: {pick.source}")

with tab_edit:
    st.caption("Add a drill, modify one, or add variants. Changes are written to `data/drills.csv` and the "
               "planner reloads them immediately. Commit the file to keep them in git.")
    mode = st.radio("What do you want to do?", ("Edit an existing drill", "Add a new drill"), horizontal=True)
    base: Drill | None = None
    if mode == "Edit an existing drill":
        base = st.selectbox("Drill", drills, format_func=lambda d: f"{d.id} — {d.name}", key="edit_pick")
    new_cat = st.selectbox("Category", CATEGORIES, index=CATEGORIES.index(base.category) if base else 2,
                           help="Decides which block the drill can fill; also sets the id prefix for a new drill.")
    with st.form("drill_form", clear_on_submit=False):
        c1, c2 = st.columns([1, 3])
        drill_id = c1.text_input("Id", value=base.id if base else next_drill_id(drills, new_cat), disabled=base is not None)
        name = c2.text_input("Name", value=base.name if base else "")
        c1, c2, c3 = st.columns(3)
        focus_sel = c1.multiselect("Focus tags", FOCUS_TAGS, default=sorted(base.focus) if base else [new_cat] if new_cat in FOCUS_TAGS else [])
        ages_sel = c2.multiselect("Ages", AGE_LEVELS, default=[a for a in AGE_LEVELS if base and a in base.ages] or (list(AGE_LEVELS) if not base else []))
        levels_sel = c3.multiselect("Levels", SKILL_LEVELS, default=[l for l in SKILL_LEVELS if base and l in base.levels] or (list(SKILL_LEVELS) if not base else []))
        c1, c2, c3, c4 = st.columns(4)
        min_p = c1.number_input("Min players", 1, 30, base.min_players if base else 4)
        max_p = c2.number_input("Max players per group", 1, 30, base.max_players if base else 16)
        dur = c3.number_input("Typical minutes", 2, 30, base.duration_min if base else 8)
        intensity = c4.selectbox("Intensity", INTENSITIES, index=INTENSITIES.index(base.intensity) if base else 1)
        c1, c2, c3, c4 = st.columns(4)
        needs_basket = c1.checkbox("Needs a basket", value=base.needs_basket if base else True)
        space = c2.selectbox("Space", SPACES, index=SPACES.index(base.space) if base else 1)
        sideline_ok = c3.checkbox("Fits the sideline strip", value=base.sideline_ok if base else False)
        supervision = c4.selectbox("Supervision", SUPERVISION, index=SUPERVISION.index(base.supervision) if base else 1)
        game_format = st.multiselect("Scrimmage format (only for games that end a practice)", GAME_FORMATS,
                                     default=sorted(base.game_format) if base else [])
        equipment = st.text_input("Equipment", value=base.equipment if base else "balls")
        description = st.text_area("Description — how to run it", value=base.description if base else "", height=110)
        coaching_points = st.text_area("Coaching points", value=base.coaching_points if base else "", height=70)
        c1, c2 = st.columns(2)
        easier = c1.text_area("Easier (beginners)", value=base.easier if base else "", height=70)
        harder = c2.text_area("Harder (advanced)", value=base.harder if base else "", height=70)
        variants = st.text_area("Variants — one per line", value="\n".join(base.variants) if base else "", height=90,
                                help="Any further variations, constraints or progressions. Shown on the card and in the export.")
        source = st.text_input("Source", value=base.source if base else "original (written for this project)")
        submitted = st.form_submit_button("💾 Save drill", use_container_width=True)
    if submitted:
        problems = []
        if not name.strip(): problems.append("name is required")
        if not description.strip(): problems.append("description is required")
        if not ages_sel: problems.append("pick at least one age")
        if not levels_sel: problems.append("pick at least one level")
        if min_p > max_p: problems.append("min players must be ≤ max players")
        if base is None and drill_id in drill_by_id: problems.append(f"id {drill_id} already exists")
        if problems:
            st.error("; ".join(problems))
        else:
            new_drill = Drill(
                id=drill_id.strip(), name=name.strip(), category=new_cat, focus=frozenset(focus_sel) | {new_cat} if new_cat in FOCUS_TAGS else frozenset(focus_sel),
                ages=frozenset(ages_sel), levels=frozenset(levels_sel), min_players=int(min_p), max_players=int(max_p),
                duration_min=int(dur), intensity=intensity, equipment=equipment.strip(), description=description.strip(),
                coaching_points=coaching_points.strip(), easier=easier.strip(), harder=harder.strip(),
                needs_basket=needs_basket, space=space, sideline_ok=sideline_ok, supervision=supervision,
                game_format=frozenset(game_format), source=source.strip() or "original",
                variants=tuple(v.strip() for v in variants.splitlines() if v.strip()),
            )
            updated = [new_drill if d.id == new_drill.id else d for d in drills]
            if base is None:
                updated.append(new_drill)
            save_drills(updated, DATA)
            st.toast(f"Saved {new_drill.id} — {new_drill.name}.", icon="✅")
            st.rerun()
    if base is not None:
        with st.expander("Delete this drill"):
            st.warning("Deleting removes the drill from the database; log entries keep its id.", icon="⚠️")
            if st.button(f"🗑️ Delete {base.id}", type="primary"):
                save_drills([d for d in drills if d.id != base.id], DATA)
                st.rerun()

with tab_about:
    st.markdown(
        """
        #### How the planner builds a practice

        | Block | 60' | 90' | 120' |
        |---|---|---|---|
        | Physical preparation (warm-up + coordination) | 10 | 12 | 15 |
        | Athletic development (optional) | 6 | 8 | 10 |
        | Skill blocks (split across selected focus areas) | 27 | 47 | 65 |
        | Game — themed game + closing scrimmage | 12 | 18 | 25 |
        | Cool-down & reflection | 5 | 5 | 5 |

        If only U9/U11 are selected, 5 minutes move from skills to games. Turning the athletic block
        off gives its minutes to the skill blocks.

        **Closing scrimmage.** The game block always ends with a small-sided game in a format that
        suits the age group: 2v2 or 3v3 for U9, 3v3 or 4v4 for U11, 3v3 to 5v5 with variations for
        U13/U14 (with mixed ages, the formats they share). A shorter themed game comes before it
        when there is time.

        **Keeping everyone active.** Each drill has a maximum group size. When the roster is bigger,
        the drill is run in parallel groups according to the court: full-court drills occupy the
        whole floor and cannot be split; half-court drills run one group per basket (2 main + side
        baskets); small-area drills run as up to 4 stations. Drills that cannot fit the roster are
        excluded, and the planner prefers formats that keep the whole group in one drill.

        **Split and swap.** If a basket drill would still have more than 8 players per hoop, and the
        sideline strip is available, half the team goes to the strip for a self-managed drill
        (stationary ball handling, ladder, core…) while the other half works at the baskets; the two
        halves swap halfway. With a single coach the sideline drill must need low supervision.

        When the group mixes levels, each drill shows an easier and a harder variation so you can run stations.

        **Age coherence.** Drills are chosen among those tagged for every selected age; when a block has
        too few, drills tagged for some of the ages are allowed and flagged ("Written for U11/U13/U14,
        not U9"). Sampling prefers drills written specifically for the selected ages over all-ages
        fundamentals. Level is relative to age: for a U9-only group the standard version of a drill
        is the advanced version, so the *Harder* variation (written for U11+) is hidden.

        Drill data lives in `data/drills.csv` — edit it freely, the app reloads it automatically.
        """
    )
