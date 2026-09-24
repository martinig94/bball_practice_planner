# Basketball Practice Planner

A small Python / Streamlit app that helps plan youth basketball practices (girls U9–U14).
Fill in a form — number of players, age categories, practice length, players per
level, focus areas — and get a structured practice built from a curated drill
database, always opening with 5–15 minutes of physical preparation and including
coordination / athletic development work.

## Run it

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

The app opens in your browser at http://localhost:8501. To put it online for free,
push the repo to GitHub and deploy it on [Streamlit Community Cloud](https://streamlit.io/cloud)
(pick `app.py` as the entry point).

## What the form does

| Input | Effect |
|---|---|
| Number of players | Drills whose `min_players` exceeds the group are excluded. Bigger rosters are split into parallel groups (see *Keeping everyone active*). |
| Side baskets in use (0–2) | The court is a full court with 2 main baskets; side baskets on the same court add hoops for half-court work. |
| Sideline strip available | The narrow area along the long side of the court, used for split-and-swap blocks (below). |
| Coaches on the floor | Alone, sideline drills must need low supervision; with help, medium is fine. |
| Age categories (U9, U11, U13, U14; multiple allowed) | Drills must suit **all** selected ages (falls back to *any* if the pool gets too small). If only U9/U11 are selected, 5 minutes move from skill work to games. |
| Players per level (beginner / intermediate / advanced) | Drills must suit every level present. With a mixed group each drill shows an **Easier** and **Harder** variation so you can run stations; groups under 3 players get a merge hint. |
| Length (60 / 90 / 120) | Sets the time budget below. |
| Athletic development block | Optional; sits right after the warm-up. Off: its minutes go to the skill blocks. |
| Focus areas | One skill block per selected area, equal time each: ball handling, passing & shooting, offense (half court & transition), defense / 1v1, team concepts. |

The plan updates as you change the form. **Reshuffle drills** draws a new random
selection with the same inputs; the seed is shown so a plan can be reproduced.
**Download plan (.md)** exports the practice as Markdown to print or share.

### Age coherence

Drills are drawn from those tagged for **every** selected age; only when a block would
otherwise run dry are drills tagged for some of the ages allowed, and each such drill is
flagged in the plan ("Written for U11/U13/U14, not U9: simplify for the younger players").
Sampling prefers drills written specifically for the selected ages over all-ages
fundamentals. Level is relative to age: for a U9-only group the standard version of each
drill *is* the advanced version, so the `harder` variation (written with U11+ in mind) is
hidden and the plan says so.

### Time budget (minutes)

| Block | 60' | 90' | 120' |
|---|---|---|---|
| Physical preparation (1 warm-up drill + coordination) | 10 | 12 | 15 |
| Athletic development (optional: speed, jumps, change of direction) | 6 | 8 | 10 |
| Skill blocks (split across focus areas) | 27 | 47 | 65 |
| Game (themed game + closing scrimmage) | 12 | 18 | 25 |
| Cool-down & reflection | 5 | 5 | 5 |

Drill durations are rescaled so each block — and the whole practice — sums exactly
to the requested time.

### Closing scrimmage

Every practice ends playing. The game block closes with a small-sided game whose format
suits the age group (drills tagged with `game_format`):

| Age | Formats |
|---|---|
| U9 | 2v2, 3v3 |
| U11 | 3v3, 4v4 |
| U13 / U14 | 3v3, 4v4, 5v5 — with rules and variations (no dribble, shot clock, screens mandatory…) |

With mixed ages the formats they share are used (U9+U11 → 3v3). The scrimmage gets at
least 60 % of the game block; a shorter themed game (knockout, dribble tag, transition
numbers game…) comes before it when there is time.

### Keeping everyone active (no long lines)

Every drill has a `max_players` group size. When the roster is bigger, the planner runs
the drill in parallel groups and says so in the plan ("Run in 4 parallel groups of ~7
players, one per basket"). How many groups a drill can have depends on its `space`:

| `space` | Parallel groups allowed |
|---|---|
| `full_court` | 1 — the drill occupies the whole floor (its `max_players` already assumes waves/lanes) |
| `half_court` | one per basket if it `needs_basket` (2 main + side baskets), otherwise 2 |
| `small_area` | up to 4 stations anywhere on the floor |

Basket drills spread over spare hoops until each hoop has about 8 players. Drills that
still cannot fit the roster are excluded, and sampling is weighted towards formats that
keep the whole group in one drill.

**Split and swap.** If a basket drill would still have more than 8 players per hoop and
the sideline strip is available, the block becomes a split-and-swap: half the team works
at the baskets while the other half does a self-managed drill on the strip (stationary
ball handling, agility ladder, core, balance…), and the halves swap halfway through. The
sideline drill is drawn from drills tagged `sideline_ok`; with one coach only `supervision
= low` drills qualify, with two or more `medium` is allowed too. With a very large group a focus area can run out of
usable drills — the planner then moves those minutes to the game block and tells you.

## The drill database — `data/drills.csv`

235 drills in English. Most were written for this project; others are adapted — in our
own words, with attribution in the `source` column — from
[hoopsaddict.com — Basketball Drills for 9-Year-Olds](https://www.hoopsaddict.com/basketball-drills-for-9-year-olds/),
[hoopdrills.org](https://hoopdrills.org/drills) (which credits Breakthrough Basketball) and the
[Transforming Basketball Small-Sided Games Book](https://www.transformingbball.com) (a
purchased coaching resource: only a youth-suitable selection is summarised here, the full
book with diagrams and the many advanced games is theirs).
One row per drill; list fields are `;`-separated. Offense has its own category with half-court
(motion, drive-and-kick, give-and-go, screens, post entry) and transition (outlet, lanes,
2v1/3v2 continuous, advantage games, early offense) drills.

| Column | Values |
|---|---|
| `id` | Unique code: `WU` warm-up, `CO` coordination/athletic, `BH` ball handling, `PS` passing & shooting, `OF` offense, `DF` defense, `TC` team concepts, `GM` games, `CD` cool-down |
| `name` | Short title |
| `category` | `warmup`, `coordination`, `ballhandling`, `passing_shooting`, `offense`, `defense`, `team_concepts`, `game`, `cooldown` — decides which block the drill can fill |
| `focus` | Tags: `physical`, `coordination`, `ballhandling`, `passing_shooting`, `offense`, `defense`, `team_concepts`, `game` |
| `ages` | Subset of `U9;U11;U13;U14` |
| `levels` | Subset of `beginner;intermediate;advanced` |
| `min_players`, `max_players` | Integers; `max_players` is the size of **one group** — bigger rosters are split |
| `duration_min` | Typical length; the planner rescales it |
| `intensity` | `low`, `medium`, `high` |
| `equipment` | Free text |
| `description` | How to run it |
| `coaching_points` | What to say |
| `easier`, `harder` | Regression / progression used for level-split groups |
| `needs_basket` | `yes` / `no` — whether the drill needs a hoop (limits how many parallel groups can run) |
| `space` | `full_court`, `half_court` or `small_area` — how much floor one group uses |
| `sideline_ok` | `yes` / `no` — can run in the narrow strip along the long side of the court |
| `supervision` | `low`, `medium`, `high` — how much coaching the drill needs to run properly |
| `game_format` | For scrimmage-type games: `2v2;3v3`, `4v4`, `5v5`… — used to pick the closing scrimmage by age |
| `source` | Where the drill comes from: `original (written for this project)`, optionally followed by "see also …" when a public source describes the same drill, or the site it was adapted from |
| `variants` | Extra variations, separated by ` \| ` (the app edits these one per line) |

### Adding your own drills

Append a row to `data/drills.csv` with a new unique `id` and keep the tag vocabulary
above; the app reloads the file automatically. Run `pytest` to make sure the file
still parses and every combination of inputs still produces a full practice.

## Practice log and ratings

**Save to practice log** on the plan tab records every drill of the plan (sideline drills
included) in `data/practice_log.csv` with today's date. In the **Practice log** tab you rate
each drill from 0 to 5 stars and add notes:

| Stars | Effect on future plans |
|---|---|
| blank | none (not rated yet) |
| 0 | never proposed again |
| 1–2 | picked less often |
| 3 | neutral |
| 4–5 | picked more often (5 stars ≈ 1.7× the chance of a neutral drill) |

The sidebar's **Memory** section also lets you avoid drills used in the last *N* practices
(default 2) and switch the rating preference off. Each plan card shows how often a drill
has been used, when, and its average rating; the drill history table lists everything.
The log is a plain CSV committed with the repo, so it follows you across machines with `git`.

## Editing drills in the app

The **Edit drills** tab adds a new drill (id assigned automatically from the category),
modifies an existing one, or deletes it. Besides the *Easier* / *Harder* variations each drill
can carry any number of free-text **variants** (one per line), shown on the plan card and in
the export. Changes are written straight to `data/drills.csv`; run `pytest` and commit to keep
them.

## Using the planner from Python

```python
from planner import load_drills, generate_practice, plan_to_markdown

drills = load_drills("data/drills.csv")
plan = generate_practice(drills, n_players=12, ages=["U11", "U13"], duration=90,
                         levels={"beginner": 4, "intermediate": 5, "advanced": 3},
                         focus=["ballhandling", "defense"], seed=1)
print(plan_to_markdown(plan))
```

## Repo layout

```
app.py                   Streamlit UI
planner/generator.py     Pure planning logic — filtering, time budget, export, save_drills
planner/log.py           Practice log: save plans, ratings, stats, weights for the planner
data/practice_log.csv    Your practices and ratings (created on first save)
data/drills.csv          Drill database
tests/test_generator.py  pytest suite: database checks + 1,080 input combinations (rosters to 25, 2–4 baskets, court set-ups)
tests/test_log.py        Practice log, ratings, exclusions and editor round trip
requirements.txt
```

## Ideas for later

- Italian translation of the drill text (add `name_it`, `description_it` columns).
- Season view: log the practices you ran and avoid repeating drills week to week.
- Per-drill "lock" so you can reshuffle everything except the drills you want to keep.
- Diagrams per drill (link a PNG/SVG in a `diagram` column).
