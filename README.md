# Duck Dynasty Fantasy League Hub (ESPN League #52568337)

An interactive, self-updating league dashboard hosted on **GitHub Pages** featuring:
- **Current Standings & Playoff Picture** (live playoff odds, BYE/IN cutoff, projected bracket, and live weekly matchups)
- **All-Time Standings & Records** (2023–2026 dynamically combined)
- **Interactive 10×10 Rivalry Matrix** (Regular Season vs. All Games incl. Playoffs + Spotlight Card)
- **Season-by-Season Archives** (2023–2026)
- **2026 Official Rulebook** (House Rules, $20 Draft Party fine, ESPN settings, and searchable scoring)

## 3-Step Setup on GitHub Pages

1. **Create a Public GitHub Repository**
   - Go to [github.com/new](https://github.com/new) and create a **Public** repository (e.g., `duck-dynasty-league`).
2. **Upload These Files**
   - Upload all files and folders from this zip (`index.html`, `data/`, `scripts/`, `.github/`, `README.md`) to the `main` branch.
   - *(Tip: On GitHub's web uploader, drag the contents inside `duck-dynasty-league/` directly into the upload box so `index.html` is at the root of the repo.)*
3. **Turn On GitHub Pages**
   - Open your repo's **Settings → Pages**.
   - Under **Build and deployment**, set **Source** to **Deploy from a branch**, select **`main`** and **`/ (root)`**, and click **Save**.
   - Within ~1 minute, your permanent league link will be live at:
     `https://<your-github-username>.github.io/duck-dynasty-league/`

## How Automatic Updates Work
- **Live Browser Sync:** Because your league is **Public**, the **Sync Live** button in the top bar pulls directly from ESPN's API on demand.
- **Automated GitHub Actions:** `.github/workflows/sync-espn.yml` automatically updates `data/2026.json` every 30 minutes during NFL game windows and every Tuesday morning at 7:00 AM ET.
- **Manual Refresh Anytime:** Go to the **Actions** tab in GitHub → **Sync ESPN Fantasy League Data** → **Run workflow**.

## Rolling Over to 2027 Next Season
1. Copy the finished `data/2026.json` entry into `data/history.json` under `"seasons": { "2026": ... }` and add the 2026 Champion to `"champions"`.
2. Update `ESPN_SEASON_ID` to `"2027"` in `.github/workflows/sync-espn.yml`, `scripts/sync_espn.py`, and `index.html`.
