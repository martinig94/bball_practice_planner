"""Basketball Practice Planner — Streamlit UI.

Run with:  streamlit run app.py
"""

from __future__ import annotations

import random
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

from planner import AGE_LEVELS, FOCUS_LABELS, SKILL_LEVELS, generate_practice, load_drills, plan_to_markdown

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data" / "drills.csv"

st.set_page_config(page_title="Practice Planner", page_icon="🏀", layout="wide")


@st.cache_data
def drills_cached(mtime: float):
    """Reload the CSV whenever the file changes on disk."""
    return load_drills(DATA)


drills = drills_cached(DATA.stat().st_mtime)

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

    st.caption("Every plan opens with 5–15 min of physical preparation (warm-up + coordination) "
               "and closes with a small-sided game in the format that suits the age group.")

# ---------------------------------------------------------------------------- tabs

tab_plan, tab_library, tab_about = st.tabs(["Plan a practice", "Drill library", "About"])

with tab_plan:
    plan = generate_practice(
        drills, n_players=int(n_players), ages=ages, duration=int(duration),
        levels=levels, focus=focus, seed=st.session_state.seed, baskets=baskets,
        sideline_strip=sideline_strip, coaches=int(coaches), include_athletic=include_athletic,
    )
    present = {k: v for k, v in plan.levels.items() if v > 0}
    show_easier = plan.level_plan.mode == "split" or "beginner" in present
    show_harder = plan.level_plan.mode == "split" or "advanced" in present

    head, dl = st.columns([4, 1])
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
                st.caption(f"Source: {d.source}")
        t += b.minutes

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
        st.caption(f"Source: {pick.source}")

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

        Drill data lives in `data/drills.csv` — edit it freely, the app reloads it automatically.
        """
    )
