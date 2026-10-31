# Guess the Ballplayer

A RefGuess-style game: you're shown a mystery player's career stat table (laid out like Baseball-Reference)
and guess who it is with a live-search box. Filter the player pool by years, career minimums, and teams
every time you start a new round.

## Run it

```bash
npm install
npm run dev          # http://localhost:5173
npm run build        # static site in dist/ (host anywhere: Netlify, Vercel, GitHub Pages)
```

`public/data/` already contains a generated dataset (players through the 2025 season), so the app runs as-is.

## Rebuild the data

```bash
git clone --depth 1 https://github.com/cdalzell/Lahman.git            # Lahman 14.0 (through 2025), as .RData
git clone --depth 1 https://github.com/chadwickbureau/register.git    # player IDs -> MLB headshots
pip install -r pipeline/requirements.txt
python pipeline/build_data.py --lahman ./Lahman --register ./register  # ~4 min
```

`pipeline/rdata.py` is a tiny built-in reader for R's `.RData` format, so you don't need R.

Optional inputs to `build_data.py`:

| Flag | What it does |
|---|---|
| `--extra-dir DIR` | Folder of Lahman-schema CSVs (`Batting.csv`, `Pitching.csv`, `Appearances.csv`, `AwardsPlayers.csv`, `AllstarFull.csv`) appended to the base data, e.g. a 2026 season |
| `--war-bat` / `--war-pit` | Baseball-Reference's published bulk files `war_daily_bat.txt` / `war_daily_pitch.txt`. Fills the WAR column (hidden until supplied) |
| `--active-file FILE` | bbref IDs (one per line) treated as "active" for the italic career-leader flags. Default: anyone who played in the latest season in the data |

## What's computed (and how it differs from Baseball-Reference)

- **Rows**: one row per season; traded players get a combined `N Tms` row (lg `MLB` if it spanned leagues) followed by one row per team, then a career row and per-team career rows.
- **Age**: on June 30. **Team** codes are BR's. **Pos** uses BR's numeric style (`*8/D`).
- **Derived stats**: PA, TB, BA/OBP/SLG/OPS, OPS+, ERA+, FIP, WHIP, rate stats. OPS+/ERA+/FIP use Lahman park factors and
  league environments, so they land within a few points of BR but won't match exactly (Trout 2019: 186 vs BR 185; Bonds 2001: 267 vs BR 259).
- **Awards**: All-Star, MVP/Cy Young/ROY finishes (`MVP-3`), Gold Glove, Silver Slugger.
- **Bold / italic / gold**: league leader, MLB leader, active career leader, all-time record. Rate stats require
  3.1 PA or 1 IP per team game (career: 3,000 PA / 1,000 IP). Players traded between leagues aren't eligible for the bold league-leader mark.
- **Left out**: rOBA and Rbat+ (not derivable from Lahman).
- **Two-way players** (Ohtani, Ruth, ...) get both a batting and a pitching table.
