# Duck Dynasty Fantasy League Hub (ESPN League #52568337)

An interactive, self-updating league dashboard hosted on **GitHub Pages** featuring:
- **Current Standings & Playoff Picture** (ESPN seeds, live playoff odds, BYE/IN cutoff, projected bracket) plus a **Playoff Race** that checks every remaining outcome to show who has clinched, who is out, and how many wins each team needs
- **Matchups** for every week: live scores, projections and win probability, all-time series, both starting lineups with player points, and previews of upcoming games (form, key players, last meeting)
- **Playoffs**: the bracket for every season, projected from the current seeds until Week 15, then filled in with real games and live scores, plus all consolation games
- **Weekly Recap**: awards for every completed week (top score, luckiest win, bench blunder, waiver pickup of the week…) with a copy-for-group-chat button
- **Power Rankings**: all-play records, recent form, expected wins and luck, by season and career
- **Lineup IQ**: points left on the bench, lineup efficiency, and losses a better lineup would have won (by season and all-time)
- **Draft & Keepers**: the auction draft board with prices and points per dollar, team spending, and next season's keeper prices
- **Trades & Waivers**: every trade with points each side has started since, FAAB spending, and all waiver claims
- **Manager profiles**: career record, finishes, rivalries, draft hits and misses, every trade and waiver spending (click any manager's name)
- **Player Records**: top single-week scores, best weeks and seasons by position, and the most-drafted players
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

### Keeper rules
Keeper Watch starts from ESPN's listed keeper price. To apply house rules, edit `KEEPER_RULES` near the bottom of `index.html`:
```js
const KEEPER_RULES = {
  priceIncrease: 0,    // dollars added to ESPN's price when a player is kept again
  maxYearsKept: null   // e.g. 2 = no player can be kept more than 2 seasons in a row
};
```
"K1/K2/K3" tags show how many seasons in a row a team has already kept a player (from the draft history).

Note: ESPN has no auction prices for the 2024 draft (every pick is recorded at $0), so price-based stats skip 2024.

## Tests
`tests/test_sync_espn.py` covers the best-lineup math, trade detection, the skip-unchanged-file logic and settings parsing. They run automatically on every push and pull request (`.github/workflows/tests.yml`), along with a check that the page's JavaScript and every data file parse. To run them locally:
```bash
python -m unittest discover tests
```

## Backfilling a Past Season
2023, 2024 and 2025 are already backfilled. **2025 is private on ESPN**, so syncing it needs your login cookies (already saved as secrets):
1. Log in at fantasy.espn.com, open your browser's developer tools → Application/Storage → Cookies, and copy the values of `espn_s2` and `SWID`.
2. In the repo, go to **Settings → Secrets and variables → Actions** and add them as secrets named `ESPN_S2` and `SWID`.
3. **Actions** → **Sync ESPN Fantasy League Data** → **Run workflow**, enter season `2025` and tick **backfill**.

## End of Season & Rollover (automatic)
- **After the championship:** once the final and the 3rd-place game are over, the sync adds the season to `data/history.json` (standings, schedule, champion, runner-up and 3rd place) on its own.
- **New season:** every Tuesday run then checks whether ESPN has opened next season's league (this happens when the league is renewed). As soon as it has, the sync switches `data/manifest.json` to the new season and the site follows. Nothing needs editing.
- **Manual override:** to sync a specific season, run the workflow with a season entered, or set `ESPN_SEASON_ID` in the workflow's `env`.
