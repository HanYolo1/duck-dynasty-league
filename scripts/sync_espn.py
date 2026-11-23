#!/usr/bin/env python3
"""
Syncs the current season standings, playoff odds, and matchup scores
from ESPN's Fantasy Football API for League 52568337 into data/2026.json.

Works with zero dependencies for a Public league.
If you ever switch the league to Private, set ESPN_S2 and SWID as GitHub Secrets.
"""
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

LEAGUE_ID = int(os.environ.get("ESPN_LEAGUE_ID", "52568337"))
SEASON_ID = int(os.environ.get("ESPN_SEASON_ID", "2026"))
OUTPUT_PATH = os.environ.get("OUTPUT_PATH", f"data/{SEASON_ID}.json")

MANAGERS = {
    1: "Cody",
    2: "Nick",
    3: "Patrick",
    4: "Jaret",
    5: "Erik",
    6: "Jon",
    7: "Adam",
    8: "Rory",
    9: "Kiana",
    10: "Zachary",
}

def fetch_espn_data():
    url = (
        f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/"
        f"seasons/{SEASON_ID}/segments/0/leagues/{LEAGUE_ID}"
        f"?view=mTeam&view=mStandings&view=mMatchupScore"
    )
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; DuckDynastyLeagueHub/1.0)",
        "Accept": "application/json",
    }
    espn_s2 = os.environ.get("ESPN_S2", "").strip()
    swid = os.environ.get("SWID", "").strip()
    if espn_s2 and swid:
        headers["Cookie"] = f"espn_s2={espn_s2}; SWID={swid}"

    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))

def transform(data):
    season = data["seasonId"]
    teams = []
    for t in data.get("teams", []):
        tid = t["id"]
        rec = t.get("record", {}).get("overall", {})
        sim = t.get("currentSimulationResults", {})
        teams.append({
            "id": tid,
            "manager": MANAGERS.get(tid, f"Team {tid}"),
            "name": t.get("name", f"Team {tid}").strip(),
            "abbrev": t.get("abbrev", ""),
            "wins": rec.get("wins", 0),
            "losses": rec.get("losses", 0),
            "ties": rec.get("ties", 0),
            "pf": round(rec.get("pointsFor", 0.0), 2),
            "pa": round(rec.get("pointsAgainst", 0.0), 2),
            "streakType": rec.get("streakType", "NONE"),
            "streakLength": rec.get("streakLength", 0),
            "playoffSeed": t.get("playoffSeed", 0),
            "rankCalculatedFinal": t.get("rankCalculatedFinal", 0),
            "playoffPct": round(sim.get("playoffPct", 0.0) * 100, 1),
        })

    matchups = []
    for m in data.get("schedule", []):
        if "home" not in m or "away" not in m:
            continue
        h = m["home"]
        a = m["away"]
        h_pts = round(h.get("totalPoints", 0.0), 2)
        a_pts = round(a.get("totalPoints", 0.0), 2)
        h_live = round(h.get("totalPointsLive", h_pts), 2)
        a_live = round(a.get("totalPointsLive", a_pts), 2)
        h_proj = round(h.get("totalProjectedPointsLive", h.get("totalProjectedPoints", 0.0)), 2)
        a_proj = round(a.get("totalProjectedPointsLive", a.get("totalProjectedPoints", 0.0)), 2)
        matchups.append({
            "season": season,
            "week": m["matchupPeriodId"],
            "playoffTier": m.get("playoffTierType", "NONE"),
            "winner": m.get("winner", "UNDECIDED"),
            "homeId": h["teamId"],
            "awayId": a["teamId"],
            "homePts": h_pts,
            "awayPts": a_pts,
            "homeLive": h_live,
            "awayLive": a_live,
            "homeProj": h_proj,
            "awayProj": a_proj,
            "homeWinProb": round(h.get("winProbability", 0.5) * 100, 1) if "winProbability" in h else None,
            "awayWinProb": round(a.get("winProbability", 0.5) * 100, 1) if "winProbability" in a else None,
        })

    return {
        "seasonId": season,
        "scoringPeriodId": data.get("scoringPeriodId", 1),
        "currentMatchupPeriod": data.get("status", {}).get("currentMatchupPeriod", data.get("scoringPeriodId", 1)),
        "syncedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "teams": teams,
        "schedule": matchups,
    }

def main():
    raw = fetch_espn_data()
    payload = transform(raw)

    # Skip the write when nothing but the timestamp would change, so the
    # workflow doesn't commit on every scheduled run.
    try:
        with open(OUTPUT_PATH, encoding="utf-8") as f:
            existing = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        existing = None
    if existing is not None:
        strip = lambda d: {k: v for k, v in d.items() if k != "syncedAt"}
        if strip(existing) == strip(payload):
            print(f"No changes for Season {payload['seasonId']} (Week {payload['currentMatchupPeriod']}); leaving {OUTPUT_PATH} untouched.")
            return

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"Successfully synced Season {payload['seasonId']} (Week {payload['currentMatchupPeriod']}) -> {OUTPUT_PATH}")

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Sync failed: {exc}", file=sys.stderr)
        sys.exit(1)
