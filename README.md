# Duck Dynasty Fantasy League Hub (ESPN League #52568337)

An interactive, self-updating league dashboard hosted on **GitHub Pages** featuring:
- **Current Standings & Playoff Picture** (ESPN seeds, live playoff odds, BYE/IN cutoff, projected bracket)
- **Matchups** for every week: live scores, projections and win probability, all-time series, and both starting lineups with player points
- **Lineup IQ**: points left on the bench, lineup efficiency, and losses a better lineup would have won (by season and all-time)
- **Draft & Keepers**: the auction draft board with prices and points per dollar, team spending, and next season's keeper prices
- **Trades & Waivers**: every trade with points each side has started since, FAAB spending, and all waiver claims
- **All-Time Standings & Records**, the **Rivalry Matrix**, and **Season-by-Season Archives**
- **Official Rulebook**: house rules plus league settings and scoring pulled straight from ESPN

## 3-Step Setup on GitHub Pages

1. **Create a Public GitHub Repository**
   - Go to [github.com/new](https://github.com/new) and create a **Public** repository (e.g., `duck-dynasty-league`).
2. **Upload These Files**
   - Upload all files and folders (`index.html`, `data/`, `scripts/`, `.github/`, `README.md`) to the `main` branch so `index.html` is at the root of the repo.
3. **Turn On GitHub Pages**
   - Open your repo's **Settings → Pages**.
   - Under **Build and deployment**, set **Source** to **Deploy from a branch**, select **`main`** and **`/ (root)`**, and click **Save**.
   - Within ~1 minute, your league link will be live at:
     `https://<your-github-username>.github.io/duck-dynasty-league/`

## How Automatic Updates Work
- **Automated GitHub Actions:** `.github/workflows/sync-espn.yml` runs `scripts/sync_espn.py` every 30 minutes during NFL game windows (Sunday, Monday and Thursday nights) and on Tuesday mornings. It only commits when something actually changed.
- **Manual Refresh Anytime:** **Actions** tab → **Sync ESPN Fantasy League Data** → **Run workflow**.
- **Sync Live button:** pulls the latest standings and scores straight from ESPN in your browser. Lineups, the draft and transactions update with the next automatic sync.

### What the sync writes (`data/`)
| File | Contents |
|---|---|
| `<season>.json` | Current-season standings, playoff odds and matchup scores |
| `<season>-lineups.json` | Every team's weekly lineup with player points, plus the best lineup they could have set |
| `<season>-league.json` | League settings and scoring rules, the auction draft, rosters, waiver claims, trades and player info |
| `history.json` | Past seasons' standings and schedules, managers and champions (edited by hand) |
| `manifest.json` | The current season and which seasons have lineup/league files |

Trades are worked out from week-to-week rosters, because ESPN doesn't publish accepted trades without a login.

## Backfilling a Past Season
2023 and 2024 are already backfilled. **2025 is private on ESPN**, so it needs your login cookies:
1. Log in at fantasy.espn.com, open your browser's developer tools → Application/Storage → Cookies, and copy the values of `espn_s2` and `SWID`.
2. In the repo, go to **Settings → Secrets and variables → Actions** and add them as secrets named `ESPN_S2` and `SWID`.
3. **Actions** → **Sync ESPN Fantasy League Data** → **Run workflow**, enter season `2025` and tick **backfill**.

## Rolling Over to 2027 Next Season
1. Copy the finished `data/2026.json` into `data/history.json` under `"seasons": { "2026": ... }` and add the 2026 Champion to `"champions"`.
2. Change `ESPN_SEASON_ID` to `"2027"` in `.github/workflows/sync-espn.yml`. The next sync writes `data/2027*.json` and updates `data/manifest.json`, and the site follows automatically.
3. Optional: update the default `ESPN_SEASON_ID` in `scripts/sync_espn.py` and the fallback `CURRENT_SEASON` in `index.html` (only used if `manifest.json` is missing).
