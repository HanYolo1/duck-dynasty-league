"""Tests for the parts of scripts/sync_espn.py that would silently produce
wrong numbers if ESPN's data or our logic changed.

Run:  python -m unittest discover tests
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import sync_espn as s  # noqa: E402

QB, RB, WR, TE, FLEX, DST, K, BENCH, IR = 0, 2, 4, 6, 23, 16, 17, 20, 21
SLOT_COUNTS = {"0": 1, "2": 2, "4": 2, "6": 1, "23": 1, "16": 1, "17": 1, "20": 6, "21": 1}
ELIG = {"QB": [QB], "RB": [RB, FLEX], "WR": [WR, FLEX], "TE": [TE, FLEX], "D/ST": [DST], "K": [K]}


def player(pid, pos, pts, slot=BENCH):
    return {"id": pid, "pos": pos, "pts": pts, "slot": slot, "elig": ELIG[pos]}


class BestLineupTests(unittest.TestCase):
    def full_roster(self):
        return [
            player(1, "QB", 20, QB), player(2, "QB", 25),          # benched QB is better
            player(3, "RB", 15, RB), player(4, "RB", 10, RB), player(5, "RB", 12),
            player(6, "WR", 9, WR), player(7, "WR", 8, WR), player(8, "WR", 30),
            player(9, "TE", 5, TE), player(10, "TE", 4),
            player(11, "D/ST", 6, DST), player(12, "K", 7, K),
            player(13, "RB", 3, FLEX),
        ]

    def test_picks_best_legal_lineup(self):
        total, used = s.best_lineup(self.full_roster(), SLOT_COUNTS)
        # QB 25, RB 15+12, WR 30+9, TE 5, FLEX best leftover RB/WR/TE = RB 10, D/ST 6, K 7
        self.assertEqual(total, 25 + 15 + 12 + 30 + 9 + 5 + 10 + 6 + 7)
        self.assertEqual(used, {2, 3, 5, 8, 6, 9, 4, 11, 12})

    def test_flex_does_not_steal_from_position_slots(self):
        # Three great RBs and weak WRs: the third RB must land in FLEX,
        # not push a WR slot empty.
        roster = [player(1, "QB", 10), player(2, "RB", 30), player(3, "RB", 29), player(4, "RB", 28),
                  player(5, "WR", 1), player(6, "WR", 1), player(7, "TE", 1), player(8, "D/ST", 1), player(9, "K", 1)]
        total, used = s.best_lineup(roster, SLOT_COUNTS)
        self.assertEqual(total, 10 + 30 + 29 + 28 + 1 + 1 + 1 + 1 + 1)
        self.assertEqual(len(used), 9)

    def test_ir_players_are_excluded(self):
        roster = self.full_roster() + [player(99, "WR", 50, IR)]
        _, used = s.best_lineup(roster, SLOT_COUNTS)
        self.assertNotIn(99, used)

    def test_qb_cannot_fill_flex(self):
        roster = [player(1, "QB", 40), player(2, "QB", 35)]
        total, used = s.best_lineup(roster, SLOT_COUNTS)
        self.assertEqual(total, 40)
        self.assertEqual(used, {1})


class TradeDetectionTests(unittest.TestCase):
    def weeks(self):
        def team(*ids):
            return {"actual": 0, "best": 0, "players": [{"id": i, "name": f"P{i}", "pos": "RB", "slot": 2, "pts": 0} for i in ids]}
        return {
            "1": {"1": team(10, 11), "2": team(20, 21)},
            "2": {"1": team(10, 20), "2": team(11, 21)},   # 11 <-> 20 swapped: a trade
            "3": {"1": team(10, 20, 21), "2": team(11)},   # 21 moved 2 -> 1 via waiver claim
        }

    def test_swap_between_weeks_is_a_trade(self):
        trades = s.trades_from_lineups(self.weeks(), [])
        first = trades[0]
        self.assertEqual(first["week"], 2)
        self.assertEqual(first["teams"], [1, 2])
        self.assertEqual({(m["playerId"], m["from"], m["to"]) for m in first["moves"]}, {(11, 1, 2), (20, 2, 1)})

    def test_waiver_claim_of_dropped_player_is_not_a_trade(self):
        claims = [{"teamId": 1, "week": 3, "items": [{"type": "ADD", "playerId": 21}]}]
        trades = s.trades_from_lineups(self.weeks(), claims)
        self.assertEqual(len(trades), 1)
        self.assertNotIn(21, [m["playerId"] for t in trades for m in t["moves"]])


class FileWriteTests(unittest.TestCase):
    def test_only_timestamp_changed_means_no_write(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "x.json")
            self.assertTrue(s.write_if_changed(path, {"a": 1, "syncedAt": "t1"}))
            self.assertFalse(s.write_if_changed(path, {"a": 1, "syncedAt": "t2"}))
            with open(path) as f:
                self.assertEqual(json.load(f)["syncedAt"], "t1")
            self.assertTrue(s.write_if_changed(path, {"a": 2, "syncedAt": "t3"}))


class SettingsTests(unittest.TestCase):
    def settings(self):
        return {
            "name": "someone@example.com",   # ESPN puts personal info here
            "size": 10,
            "draftSettings": {"type": "AUCTION", "auctionBudget": 200, "keeperCount": 3},
            "acquisitionSettings": {"isUsingAcquisitionBudget": True, "acquisitionBudget": 100, "minimumBid": 1},
            "rosterSettings": {"lineupSlotCounts": {"0": 1, "20": 6, "3": 0}, "positionLimits": {"1": 4, "7": -1}},
            "scoringSettings": {"scoringItems": [
                {"statId": 3, "points": 0.04},
                {"statId": 99, "points": 0, "pointsOverrides": {"16": 1.0}},
                {"statId": 12345, "points": 2},
                {"statId": 53, "points": 0},
            ]},
        }

    def test_league_name_is_never_stored(self):
        summary = s.settings_summary(self.settings())
        self.assertNotIn("name", summary)
        self.assertNotIn("example.com", json.dumps(summary))

    def test_scoring_rules(self):
        rules = {r["statId"]: r for r in s.settings_summary(self.settings())["scoring"]}
        self.assertEqual(rules[3]["label"], "Passing Yards")
        self.assertEqual(rules[99]["pts"], 1.0)                 # D/ST uses its override
        self.assertEqual(rules[12345]["label"], "ESPN stat #12345")
        self.assertNotIn(53, rules)                             # zero-point rules dropped

    def test_caps_and_lineup_skip_unused(self):
        summary = s.settings_summary(self.settings())
        self.assertEqual(summary["positionCaps"], {"QB": 4})
        self.assertEqual([x["slot"] for x in summary["lineup"]], ["QB", "Bench"])


class SeasonWrapUpTests(unittest.TestCase):
    HISTORY = os.path.join(os.path.dirname(__file__), "..", "data", "history.json")

    def history(self):
        with open(self.HISTORY, encoding="utf-8") as f:
            return json.load(f)

    def test_champion_matches_every_recorded_season(self):
        h = self.history()
        for year, season in h["seasons"].items():
            want = next(c for c in h["champions"] if c["year"] == int(year))
            self.assertEqual(s.champion_entry(season), want, year)

    def test_unfinished_season_has_no_champion(self):
        season = self.history()["seasons"]["2023"]
        final_week = max(m["week"] for m in season["schedule"])
        for target in ("WINNERS_BRACKET", "WINNERS_CONSOLATION_LADDER"):
            sched = json.loads(json.dumps(season["schedule"]))
            for m in sched:
                if m["week"] == final_week and m["playoffTier"] == target:
                    m["winner"] = "UNDECIDED"
            self.assertIsNone(s.champion_entry({**season, "schedule": sched}), target)

    def test_archive_adds_season_once(self):
        h = self.history()
        season = h["seasons"].pop("2025")
        h["champions"] = [c for c in h["champions"] if c["year"] != 2025]
        self.assertTrue(s.archive_season(h, {**season, "syncedAt": "x"}))
        self.assertIn("2025", h["seasons"])
        self.assertNotIn("syncedAt", h["seasons"]["2025"])
        self.assertEqual([c["year"] for c in h["champions"]], [2023, 2024, 2025])
        self.assertFalse(s.archive_season(h, season))           # second run: no change
        self.assertEqual(len(h["champions"]), 3)

    def test_current_season_prefers_env_then_manifest(self):
        with tempfile.TemporaryDirectory() as d:
            old_dir, old_env = s.DATA_DIR, os.environ.pop("ESPN_SEASON_ID", None)
            try:
                s.DATA_DIR = d
                self.assertEqual(s.current_season(), s.FALLBACK_SEASON)
                with open(os.path.join(d, "manifest.json"), "w") as f:
                    json.dump({"currentSeason": 2031}, f)
                self.assertEqual(s.current_season(), 2031)
                os.environ["ESPN_SEASON_ID"] = "2032"
                self.assertEqual(s.current_season(), 2032)
            finally:
                s.DATA_DIR = old_dir
                os.environ.pop("ESPN_SEASON_ID", None)
                if old_env is not None:
                    os.environ["ESPN_SEASON_ID"] = old_env


if __name__ == "__main__":
    unittest.main()
