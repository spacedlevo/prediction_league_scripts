# Cup Competition

A single-elimination knockout cup that runs at the end of each Premier League season, using the same prediction scoring as the main league.

---

## Format

- **Structure**: Single-elimination bracket (standard knockout)
- **Timing**: Final `num_rounds` gameweeks of the season, always finishing on GW38 (the Final)
- **Rounds**: Determined automatically by player count — `ceil(log2(n))` rounds, bracket size rounded up to the next power of 2

| Active Players | Rounds | Bracket Size | Cup Starts |
| :-: | :-: | :-: | :-: |
| 2 | 1 | 2 | GW38 |
| 3–4 | 2 | 4 | GW37 |
| 5–8 | 3 | 8 | GW36 |
| 9–16 | 4 | 16 | GW35 |

---

## Seeding

Players are seeded by their **current season points at the time the bracket is generated** (seed 1 = top of the table). This means seedings reflect wherever players stand in the league when you run the script — typically after the last gameweek before the cup starts.

League position is determined by:

1. Total points (correct results + correct scores across the season)
2. Tiebreaker 1: correct results count
3. Tiebreaker 2: correct scores count

Only **active** players are entered.

---

## Byes

When the number of players is not a power of 2, the **bottom seeds** (worst performers) receive first-round byes and advance automatically to round 2.

- Number of byes = bracket size − number of players
- Bottom seeds get byes so that the best performers must play from round 1

---

## Round 1 Pairings

Within the active (non-bye) group, the bracket uses top-vs-bottom seeding:

- Seed 1 vs Seed N
- Seed 2 vs Seed N−1
- Seed 3 vs Seed N−2
- etc.

---

## Match Scoring

Each cup match covers **one gameweek**. The player who scores more points across that gameweek's fixtures wins the match and advances.

Scoring is identical to the main league:

- **1 point** — correct result (H/D/A)
- **1 point** — correct exact scoreline

---

## Generating the Bracket

### When to run

Run the script **after the last gameweek before the cup starts**, once all results are in. This ensures seedings reflect the most up-to-date standings.

To find out which gameweek the cup starts: run the script once (it prints the bracket summary without writing anything if a bracket already exists), or pre-calculate: count active players → `ceil(log2(n))` rounds → `38 - rounds + 1 = start GW`.

### Commands

```bash
source venv/bin/activate

# Check who would be seeded and which GW the cup starts (safe to run anytime)
python scripts/cup/generate_cup_bracket.py --season 2025/2026

# Generate the bracket (only writes if none exists for this season)
python scripts/cup/generate_cup_bracket.py --season 2025/2026

# Regenerate if needed
python scripts/cup/generate_cup_bracket.py --season 2025/2026 --force
```

After generating, sync to PythonAnywhere:

```bash
python scripts/database/mysql_sync.py --full-sync
```

---

## Database Tables

| Table | Purpose |
| --- | --- |
| `cup_config` | One row per season — records rounds, start GW, generated timestamp |
| `cup_matches` | One row per bracket slot — stores player IDs, seeds, gameweek, and `next_match_id` link to the next round |

The `next_match_id` / `next_match_slot` columns form a linked bracket: winners are written into the referenced slot in the next round.

> **Note**: Match advancement logic (writing winners into the next round slot after each gameweek) is not yet implemented.
