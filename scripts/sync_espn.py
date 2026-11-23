#!/usr/bin/env python3
"""
Syncs Duck Dynasty league data from ESPN's Fantasy Football API.

Writes, per season:
  data/<season>.json          standings, playoff odds and matchup scores
                              (current season only; past seasons live in history.json)
  data/<season>-lineups.json  every team's weekly lineup with player points,
                              plus the best lineup they could have set
  data/<season>-league.json   league settings and scoring rules, the auction
                              draft, waiver claims, trades and player info
  data/manifest.json          the current season and which seasons have which files

After the championship game is final, the season is archived into
data/history.json (standings, schedule and champion / runner-up / third).
From then on, each run checks whether ESPN has opened next season's league
and, once it has, switches data/manifest.json over to it automatically.

Zero dependencies. Works without login for seasons where the league is
public. For private seasons, set ESPN_S2 and SWID (cookie values from a
logged-in browser) as environment variables / GitHub secrets.

Usage:
  python scripts/sync_espn.py                         # current season (manifest, or ESPN_SEASON_ID)
  python scripts/sync_espn.py --season 2024 --backfill
      --backfill  refetch every week and skip data/<season>.json
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

LEAGUE_ID = int(os.environ.get("ESPN_LEAGUE_ID", "52568337"))
DATA_DIR = os.environ.get("DATA_DIR", "data")
FALLBACK_SEASON = 2026
API = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons"

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

POSITIONS = {1: "QB", 2: "RB", 3: "WR", 4: "TE", 5: "K", 16: "D/ST"}
BENCH, IR = 20, 21
DST_SLOT = "16"

# ESPN scoring stat ids -> (category, label). Covers every stat this league
# scores; anything else falls back to "ESPN stat #<id>".
SCORING_STATS = {
    1: ("Passing", "Each Pass Completed"),
    3: ("Passing", "Passing Yards"),
    4: ("Passing", "TD Pass"),
    15: ("Passing", "40+ Yard TD Pass Bonus"),
    16: ("Passing", "50+ Yard TD Pass Bonus"),
    17: ("Passing", "300–399 Yard Passing Game"),
    18: ("Passing", "400+ Yard Passing Game"),
    19: ("Passing", "2-Pt Passing Conversion"),
    20: ("Passing", "Interception Thrown"),
    24: ("Rushing", "Rushing Yards"),
    25: ("Rushing", "TD Rush"),
    26: ("Rushing", "2-Pt Rushing Conversion"),
    35: ("Rushing", "40+ Yard TD Rush Bonus"),
    36: ("Rushing", "50+ Yard TD Rush Bonus"),
    37: ("Rushing", "100–199 Yard Rushing Game"),
    38: ("Rushing", "200+ Yard Rushing Game"),
    42: ("Receiving", "Receiving Yards"),
    43: ("Receiving", "TD Reception"),
    44: ("Receiving", "2-Pt Receiving Conversion"),
    45: ("Receiving", "40+ Yard TD Reception Bonus"),
    46: ("Receiving", "50+ Yard TD Reception Bonus"),
    53: ("Receiving", "Each Reception"),
    56: ("Receiving", "100–199 Yard Receiving Game"),
    57: ("Receiving", "200+ Yard Receiving Game"),
    63: ("Misc", "Fumble Recovered for TD"),
    72: ("Misc", "Fumble Lost"),
    79: ("Kicking", "FG Missed (40–49 yds)"),
    82: ("Kicking", "FG Missed (0–39 yds)"),
    83: ("Kicking", "FG Made"),
    85: ("Kicking", "FG Missed"),
    86: ("Kicking", "PAT Made"),
    88: ("Kicking", "PAT Missed"),
    198: ("Kicking", "FG Made (50–59 yds) Bonus"),
    201: ("Kicking", "FG Made (60+ yds) Bonus"),
    89: ("D/ST", "0 Points Allowed"),
    90: ("D/ST", "1–6 Points Allowed"),
    91: ("D/ST", "7–13 Points Allowed"),
    92: ("D/ST", "14–17 Points Allowed"),
    123: ("D/ST", "28–34 Points Allowed"),
    124: ("D/ST", "35–45 Points Allowed"),
    125: ("D/ST", "46+ Points Allowed"),
    128: ("D/ST", "Under 100 Yards Allowed"),
    129: ("D/ST", "100–199 Yards Allowed"),
    130: ("D/ST", "200–299 Yards Allowed"),
    132: ("D/ST", "350–399 Yards Allowed"),
    133: ("D/ST", "400–449 Yards Allowed"),
    134: ("D/ST", "450–499 Yards Allowed"),
    135: ("D/ST", "500–549 Yards Allowed"),
    136: ("D/ST", "550+ Yards Allowed"),
    93: ("D/ST", "Blocked Punt/FG Return TD"),
    95: ("D/ST", "Interception"),
    96: ("D/ST", "Fumble Recovered"),
    97: ("D/ST", "Blocked Punt, PAT or FG"),
    98: ("D/ST", "Safety"),
    99: ("D/ST", "Sack"),
    101: ("D/ST", "Kickoff Return TD"),
    102: ("D/ST", "Punt Return TD"),
    103: ("D/ST", "Interception Return TD"),
    104: ("D/ST", "Fumble Return TD"),
    206: ("D/ST", "2-Pt Return"),
    209: ("D/ST", "1-Pt Safety"),
}
CATEGORY_ORDER = ["Passing", "Rushing", "Receiving", "Misc", "Kicking", "D/ST", "Other"]


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #
class PrivateSeasonError(Exception):
    """ESPN refused the request (401): the season is private."""


def espn_get(season, params, fantasy_filter=None, path="", league=True):
    base = f"{API}/{season}/segments/0/leagues/{LEAGUE_ID}{path}" if league else f"{API}/{season}"
    url = f"{base}?{urllib.parse.urlencode(params, doseq=True)}"
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; DuckDynastyLeagueHub/1.0)",
        "Accept": "application/json",
    }
    if fantasy_filter is not None:
        headers["X-Fantasy-Filter"] = json.dumps(fantasy_filter)
    espn_s2 = os.environ.get("ESPN_S2", "").strip()
    swid = os.environ.get("SWID", "").strip()
    if espn_s2 and swid:
        headers["Cookie"] = f"espn_s2={espn_s2}; SWID={swid}"

    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                raise PrivateSeasonError(
                    f"ESPN says season {season} is private (401). "
                    "Set ESPN_S2 and SWID to sync it."
                )
            if exc.code < 500 or attempt == 3:
                raise
        except urllib.error.URLError:
            if attempt == 3:
                raise
        time.sleep(2 ** attempt)


# --------------------------------------------------------------------------- #
# Files
# --------------------------------------------------------------------------- #
def path_for(name):
    return os.path.join(DATA_DIR, name)


def read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def write_if_changed(path, payload):
    """Write payload unless only `syncedAt` differs, so the scheduled
    workflow doesn't commit on every run. Returns True when written."""
    existing = read_json(path)
    strip = lambda d: {k: v for k, v in d.items() if k != "syncedAt"}
    if isinstance(existing, dict) and strip(existing) == strip(payload):
        print(f"  unchanged: {path}")
        return False
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=1, ensure_ascii=False)
        f.write("\n")
    print(f"  wrote:     {path}")
    return True


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------- #
# Standings (data/<season>.json)
# --------------------------------------------------------------------------- #
def transform_standings(data):
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
        h, a = m["home"], m["away"]
        h_pts = round(h.get("totalPoints", 0.0), 2)
        a_pts = round(a.get("totalPoints", 0.0), 2)
        matchups.append({
            "season": season,
            "week": m["matchupPeriodId"],
            "playoffTier": m.get("playoffTierType", "NONE"),
            "winner": m.get("winner", "UNDECIDED"),
            "homeId": h["teamId"],
            "awayId": a["teamId"],
            "homePts": h_pts,
            "awayPts": a_pts,
            "homeLive": round(h.get("totalPointsLive", h_pts), 2),
            "awayLive": round(a.get("totalPointsLive", a_pts), 2),
            "homeProj": round(h.get("totalProjectedPointsLive", h.get("totalProjectedPoints", 0.0)), 2),
            "awayProj": round(a.get("totalProjectedPointsLive", a.get("totalProjectedPoints", 0.0)), 2),
            "homeWinProb": round(h["winProbability"] * 100, 1) if "winProbability" in h else None,
            "awayWinProb": round(a["winProbability"] * 100, 1) if "winProbability" in a else None,
        })

    return {
        "seasonId": season,
        "scoringPeriodId": data.get("scoringPeriodId", 1),
        "currentMatchupPeriod": data.get("status", {}).get("currentMatchupPeriod", data.get("scoringPeriodId", 1)),
        "syncedAt": now_iso(),
        "teams": teams,
        "schedule": matchups,
    }


# --------------------------------------------------------------------------- #
# Lineups (data/<season>-lineups.json)
# --------------------------------------------------------------------------- #
def stat_total(player, season, period, source):
    """Points from a player's stats entry. source 0 = actual, 1 = projected."""
    for s in player.get("stats", []):
        if (s.get("seasonId", season) == season and s.get("scoringPeriodId") == period
                and s.get("statSourceId") == source and s.get("statSplitTypeId") in (0, 1)):
            return s.get("appliedTotal", 0.0)
    return 0.0


def starter_slots(slot_counts):
    return [int(s) for s, n in slot_counts.items() for _ in range(n) if int(s) not in (BENCH, IR)]


def best_lineup(players, slot_counts):
    """Highest score the team could have started this week, and who.

    Fills the most restrictive slots first (K, D/ST, QB, TE, then RB/WR),
    leaving FLEX for last, which is optimal when FLEX accepts every position
    of the slots it overlaps (true for ESPN's RB/WR/TE flex). IR is excluded.
    """
    pool = sorted((p for p in players if p["slot"] != IR), key=lambda p: -p["pts"])
    slots = starter_slots(slot_counts)
    slots.sort(key=lambda s: sum(1 for p in pool if s in p["elig"]))
    used, total = set(), 0.0
    for slot in slots:
        for p in pool:
            if p["id"] not in used and slot in p["elig"]:
                used.add(p["id"])
                total += p["pts"]
                break
    return round(total, 2), used


def week_lineups(box, season, period, slot_counts):
    teams = {}
    for m in box.get("schedule", []):
        for side in ("home", "away"):
            s = m.get(side) or {}
            roster = s.get("rosterForCurrentScoringPeriod")
            if not roster:
                continue
            players = []
            for e in roster.get("entries", []):
                pe = e.get("playerPoolEntry", {})
                pl = pe.get("player", {})
                players.append({
                    "id": pl.get("id", e.get("playerId")),
                    "name": pl.get("fullName", "Unknown"),
                    "pos": POSITIONS.get(pl.get("defaultPositionId"), "?"),
                    "slot": e.get("lineupSlotId"),
                    "pts": round(pe.get("appliedStatTotal", 0.0), 2),
                    "proj": round(stat_total(pl, season, period, 1), 2),
                    "elig": pl.get("eligibleSlots", []),
                })
            actual = round(sum(p["pts"] for p in players if p["slot"] not in (BENCH, IR)), 2)
            best, best_ids = best_lineup(players, slot_counts)
            for p in players:
                del p["elig"]
                if p["id"] in best_ids:
                    p["opt"] = 1   # in the best possible lineup
            players.sort(key=lambda p: (p["slot"] in (BENCH, IR), p["slot"], -p["pts"]))
            team = {"actual": actual, "best": max(best, actual), "players": players}
            # Commissioner score adjustments (e.g. penalties) aren't player points.
            adj = round(s.get("adjustment", 0.0) or 0.0, 2)
            if adj:
                team["adj"] = adj
            teams[str(s["teamId"])] = team
    return teams


def sync_lineups(season, status, slot_counts, backfill):
    path = path_for(f"{season}-lineups.json")
    existing = (read_json(path) or {}) if not backfill else {}
    weeks = dict(existing.get("weeks", {}))
    latest = status.get("latestScoringPeriod") or status.get("currentMatchupPeriod") or 1
    final = status.get("finalScoringPeriod") or latest
    last = min(latest, final)
    for period in range(1, last + 1):
        # Finished weeks never change (bar stat corrections, covered by
        # refetching the previous week too).
        if str(period) in weeks and period < latest - 1:
            continue
        box = espn_get(season, [("view", "mMatchupScore"), ("view", "mBoxscore"), ("scoringPeriodId", period)])
        wk = week_lineups(box, season, period, slot_counts)
        if wk:
            weeks[str(period)] = wk
        print(f"  lineups week {period}: {len(wk)} teams")
    payload = {
        "seasonId": season,
        "syncedAt": now_iso(),
        "slots": {"QB": 0, "RB": 2, "WR": 4, "TE": 6, "FLEX": 23, "D/ST": 16, "K": 17, "Bench": 20, "IR": 21},
        "weeks": dict(sorted(weeks.items(), key=lambda kv: int(kv[0]))),
    }
    write_if_changed(path, payload)
    return payload


def trades_from_lineups(weeks, transactions):
    """ESPN's public API hides completed trade proposals, so trades are
    reconstructed from rosters: a player on team A one week and team B the
    next moved by trade, unless team B claimed him off waivers after A
    dropped him (those claims are in `transactions` and are skipped)."""
    claimed = {(t["teamId"], i["playerId"], t["week"])
               for t in transactions for i in t["items"] if i["type"] == "ADD"}
    order = sorted(weeks, key=int)
    trades = {}
    for prev, cur in zip(order, order[1:]):
        owner_prev = {p["id"]: int(t) for t, d in weeks[prev].items() for p in d["players"]}
        for t, d in weeks[cur].items():
            for p in d["players"]:
                old = owner_prev.get(p["id"])
                if old is not None and old != int(t) and not any(
                        (int(t), p["id"], w) in claimed for w in range(int(prev), int(cur) + 1)):
                    a, b = sorted((old, int(t)))
                    key = (int(cur), a, b)
                    trades.setdefault(key, []).append({"playerId": p["id"], "name": p["name"], "pos": p["pos"], "from": old, "to": int(t)})
    return [
        {"week": wk, "teams": [a, b], "moves": moves}
        for (wk, a, b), moves in sorted(trades.items())
    ]


# --------------------------------------------------------------------------- #
# League file (data/<season>-league.json)
# --------------------------------------------------------------------------- #
def settings_summary(settings):
    acq = settings.get("acquisitionSettings", {})
    draft = settings.get("draftSettings", {})
    trade = settings.get("tradeSettings", {})
    sched = settings.get("scheduleSettings", {})
    roster = settings.get("rosterSettings", {})
    scoring = settings.get("scoringSettings", {})

    rules = []
    for item in scoring.get("scoringItems", []):
        sid = item.get("statId")
        cat, label = SCORING_STATS.get(sid, ("Other", f"ESPN stat #{sid}"))
        overrides = item.get("pointsOverrides") or {}
        pts = overrides.get(DST_SLOT, item.get("points", 0)) if cat == "D/ST" else item.get("points", 0)
        if pts == 0:
            continue
        rules.append({"statId": sid, "cat": cat, "label": label, "pts": round(pts, 3)})
    rules.sort(key=lambda r: (CATEGORY_ORDER.index(r["cat"]), r["statId"]))

    slot_names = {0: "QB", 2: "RB", 4: "WR", 6: "TE", 23: "FLEX", 16: "D/ST", 17: "K", 20: "Bench", 21: "IR"}
    lineup = [{"slot": slot_names.get(int(s), f"Slot {s}"), "count": n}
              for s, n in roster.get("lineupSlotCounts", {}).items() if n]
    caps = {POSITIONS[int(p)]: n for p, n in roster.get("positionLimits", {}).items()
            if n > 0 and int(p) in POSITIONS}
    return {
        "teams": settings.get("size"),
        "draftType": draft.get("type"),
        "auctionBudget": draft.get("auctionBudget"),
        "keeperCount": draft.get("keeperCount"),
        "draftDate": draft.get("date"),
        "faabBudget": acq.get("acquisitionBudget") if acq.get("isUsingAcquisitionBudget") else None,
        "minBid": acq.get("minimumBid"),
        "waiverHours": acq.get("waiverHours"),
        "tradeDeadline": trade.get("deadlineDate"),
        "tradeReviewHours": trade.get("revisionHours"),
        "vetoVotesRequired": trade.get("vetoVotesRequired"),
        "regularSeasonWeeks": sched.get("matchupPeriodCount"),
        "playoffTeams": sched.get("playoffTeamCount"),
        "seedingTiebreak": sched.get("playoffSeedingRule"),
        "lineup": lineup,
        "positionCaps": caps,
        "scoring": rules,
    }


def sync_transactions(season, latest, existing, backfill):
    """Waiver claims (with FAAB bids) and drops, cached by scoring period."""
    fetched = set() if backfill else set(existing.get("txPeriodsFetched", []))
    txs = {} if backfill else {t["id"]: t for t in existing.get("transactions", [])}
    for period in range(0, latest + 1):
        if period in fetched and period < latest - 1:
            continue
        data = espn_get(season, [("view", "mTransactions2"), ("scoringPeriodId", period)])
        for x in data.get("transactions", []):
            if x.get("status") != "EXECUTED":
                continue
            items = x.get("items", [])
            kinds = {i.get("type") for i in items}
            if x.get("type") == "WAIVER" or (x.get("type") in ("ROSTER", "FREEAGENT") and kinds & {"ADD", "DROP"}):
                txs[x["id"]] = {
                    "id": x["id"],
                    "week": x.get("scoringPeriodId", period),
                    "date": x.get("processDate") or x.get("proposedDate"),
                    "type": "WAIVER" if x.get("type") == "WAIVER" else ("ADD" if "ADD" in kinds else "DROP"),
                    "teamId": x.get("teamId"),
                    "bid": x.get("bidAmount", 0),
                    "items": [{"type": i.get("type"), "playerId": i.get("playerId")}
                              for i in items if i.get("type") in ("ADD", "DROP")],
                }
        fetched.add(period)
    return sorted(txs.values(), key=lambda t: t["date"] or 0, reverse=True), sorted(fetched)


HEALTHY = (None, "", "ACTIVE", "NORMAL")


def player_info(entry, season):
    """One player's entry in the league file from a kona_player_info row."""
    pl = entry.get("player", {})
    info = {
        "name": pl.get("fullName", "Unknown"),
        "pos": POSITIONS.get(pl.get("defaultPositionId"), "?"),
        "pts": round(stat_total(pl, season, 0, 0), 2),
        "team": entry.get("onTeamId", 0),
        "keeperCost": entry.get("keeperValueFuture"),
        "nfl": pl.get("proTeamId"),
    }
    # Current injury designation (QUESTIONABLE, DOUBTFUL, OUT, INJURY_RESERVE,
    # SUSPENSION, ...). ESPN only gives today's status, not past weeks'.
    if pl.get("injuryStatus") not in HEALTHY:
        info["injury"] = pl["injuryStatus"]
    return info


def pro_team_byes(data):
    """{proTeamId: {"abbrev", "bye"}} from the proTeamSchedules view."""
    teams = data.get("settings", {}).get("proTeams", [])
    return {str(t["id"]): {"abbrev": t.get("abbrev", ""), "bye": t.get("byeWeek", 0)}
            for t in teams if t.get("id")}


def fetch_players(season, ids):
    """Name, position, season points, keeper cost, NFL team and injury
    status for the given players."""
    players = {}
    ids = sorted(set(i for i in ids if i))
    for start in range(0, len(ids), 100):
        chunk = ids[start:start + 100]
        flt = {"players": {
            "filterIds": {"value": chunk},
            "filterStatsForTopScoringPeriodIds": {"value": 2, "additionalValue": [f"00{season}"]},
        }}
        data = espn_get(season, [("view", "kona_player_info")], flt)
        for entry in data.get("players", []):
            pl = entry.get("player", {})
            players[str(pl.get("id", entry.get("id")))] = player_info(entry, season)
    return players


def sync_league(season, main, lineups, backfill):
    path = path_for(f"{season}-league.json")
    existing = (read_json(path) or {}) if not backfill else {}
    status = main.get("status", {})
    latest = status.get("latestScoringPeriod") or status.get("currentMatchupPeriod") or 1

    picks = [{
        "pick": p.get("overallPickNumber"),
        "teamId": p.get("teamId"),
        "playerId": p.get("playerId"),
        "bid": p.get("bidAmount", 0),
        "keeper": bool(p.get("keeper")),
    } for p in main.get("draftDetail", {}).get("picks", [])]

    transactions, fetched = sync_transactions(season, latest, existing, backfill)
    trades = trades_from_lineups(lineups["weeks"], transactions)

    weeks = lineups["weeks"]
    last_week = weeks[max(weeks, key=int)] if weeks else {}
    rosters = {t: [p["id"] for p in d["players"]] for t, d in last_week.items()}

    ids = {p["playerId"] for p in picks}
    ids |= {i["playerId"] for t in transactions for i in t["items"]}
    ids |= {pid for r in rosters.values() for pid in r}
    players = fetch_players(season, ids)

    payload = {
        "seasonId": season,
        "syncedAt": now_iso(),
        "settings": settings_summary(main.get("settings", {})),
        "draft": sorted(picks, key=lambda p: p["pick"] or 0),
        "rosters": rosters,
        "transactions": transactions,
        "txPeriodsFetched": fetched,
        "trades": trades,
        "players": dict(sorted(players.items(), key=lambda kv: int(kv[0]))),
        "proTeams": pro_team_byes(espn_get(season, [("view", "proTeamSchedules_wl")], league=False)),
    }
    write_if_changed(path, payload)


# --------------------------------------------------------------------------- #
# Season wrap-up (history.json) and rollover
# --------------------------------------------------------------------------- #
HISTORY_KEYS = ("seasonId", "scoringPeriodId", "currentMatchupPeriod", "teams", "schedule")


def _decided(m):
    return m["winner"] in ("HOME", "AWAY")


def _winner_loser(m):
    return (m["homeId"], m["awayId"]) if m["winner"] == "HOME" else (m["awayId"], m["homeId"])


def champion_entry(standings):
    """The champions-list entry for a finished season, or None while the
    championship (or the 3rd-place game) is still to be played."""
    sched = standings.get("schedule", [])
    bracket = [m for m in sched if m.get("playoffTier") == "WINNERS_BRACKET"]
    if not bracket:
        return None
    last = max(m["week"] for m in bracket)
    finals = [m for m in bracket if m["week"] == last]
    if len(finals) != 1 or not _decided(finals[0]):
        return None
    if any(m["winner"] == "UNDECIDED" for m in sched if m["week"] == last):
        return None  # wait for the rest of the final week, incl. 3rd place
    final = finals[0]
    champ, runner = _winner_loser(final)
    pts = {final["homeId"]: final["homePts"], final["awayId"]: final["awayPts"]}

    semi_losers = {_winner_loser(m)[1] for m in bracket if m["week"] == last - 1 and _decided(m)}
    third = None
    for m in sched:
        if m["week"] == last and {m["homeId"], m["awayId"]} == semi_losers and _decided(m):
            third = _winner_loser(m)[0]
    if third is None:
        third = next((t["id"] for t in standings.get("teams", []) if t.get("rankCalculatedFinal") == 3), None)

    names = {t["id"]: t["name"] for t in standings.get("teams", [])}
    return {
        "year": standings["seasonId"],
        "champId": champ,
        "champTeam": names.get(champ, f"Team {champ}"),
        "runnerUpId": runner,
        "runnerUpTeam": names.get(runner, f"Team {runner}"),
        "score": f"{pts[champ]:.2f} \u2013 {pts[runner]:.2f}",
        "thirdId": third,
    }


def archive_season(history, standings):
    """Add a finished season and its champion to history (in place).
    Returns True if anything changed."""
    champ = champion_entry(standings)
    if champ is None:
        return False
    season = standings["seasonId"]
    changed = False
    seasons = history.setdefault("seasons", {})
    if str(season) not in seasons:
        seasons[str(season)] = {k: standings[k] for k in HISTORY_KEYS if k in standings}
        history["seasons"] = dict(sorted(seasons.items(), key=lambda kv: int(kv[0])))
        changed = True
    champions = history.setdefault("champions", [])
    if not any(c.get("year") == season for c in champions):
        champions.append(champ)
        champions.sort(key=lambda c: c["year"])
        changed = True
    return changed


def wrap_up_season(season, standings):
    """Archive a finished season into history.json. Returns True once the
    season is complete (whether archived now or earlier)."""
    if champion_entry(standings) is None:
        return False
    path = path_for("history.json")
    history = read_json(path)
    if history is None:
        print("  history.json missing; can't archive the season")
        return False
    if archive_season(history, standings):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2)
        print(f"  archived season {season} into {path} (champion: {MANAGERS.get(champion_entry(standings)['champId'])})")
    return True


def next_season_ready(season):
    """True once ESPN has opened the league for `season` (it does this when
    the league is renewed for the new year)."""
    try:
        data = espn_get(season, [("view", "mTeam")])
    except (PrivateSeasonError, urllib.error.HTTPError, urllib.error.URLError) as exc:
        print(f"  season {season} not available yet ({exc})")
        return False
    return bool(data.get("teams"))


def current_season():
    env = os.environ.get("ESPN_SEASON_ID", "").strip()
    if env:
        return int(env)
    manifest = read_json(path_for("manifest.json")) or {}
    return int(manifest.get("currentSeason") or FALLBACK_SEASON)


def update_manifest(season, current):
    path = path_for("manifest.json")
    manifest = read_json(path) or {}
    manifest["leagueId"] = LEAGUE_ID
    if current:
        manifest["currentSeason"] = season
    extras = set(manifest.get("extras", []))
    extras.add(season)
    manifest["extras"] = sorted(extras)
    write_if_changed(path, manifest)


# --------------------------------------------------------------------------- #
def sync_season(season, backfill):
    print(f"Syncing season {season} (league {LEAGUE_ID})")
    main_data = espn_get(season, [("view", v) for v in
                                  ("mTeam", "mStandings", "mMatchupScore", "mSettings", "mDraftDetail")])
    standings = transform_standings(main_data)
    if not backfill:
        write_if_changed(path_for(f"{season}.json"), standings)

    slot_counts = main_data.get("settings", {}).get("rosterSettings", {}).get("lineupSlotCounts", {})
    lineups = sync_lineups(season, main_data.get("status", {}), slot_counts, backfill)
    sync_league(season, main_data, lineups, backfill)
    update_manifest(season, current=not backfill)
    return standings


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--season", type=int, default=None,
                    help="season to sync (default: the current season from data/manifest.json)")
    ap.add_argument("--backfill", action="store_true",
                    help="past season: refetch everything and don't write data/<season>.json")
    args = ap.parse_args()
    season = args.season or current_season()
    standings = sync_season(season, args.backfill)

    if not args.backfill and wrap_up_season(season, standings):
        print(f"Season {season} is complete; checking whether ESPN has opened {season + 1}...")
        if next_season_ready(season + 1):
            print(f"Rolling over to {season + 1}.")
            sync_season(season + 1, backfill=False)
    print("Done.")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except PrivateSeasonError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"Sync failed: {exc}", file=sys.stderr)
        sys.exit(1)
