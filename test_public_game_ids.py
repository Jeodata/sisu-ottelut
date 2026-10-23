"""Deterministic fixtures from the real /helpers/getgames JSON captured 23 Oct 2026."""
from __future__ import annotations
import copy
import sys
import tempfile
from pathlib import Path
from unittest import TestCase

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from public_game_ids import enrich_public_links
from sisu_ottelut import build_payload, parse_date

PUBLIC_U16 = {
    "GameID": 2721476, "GameDateDB": "2026-10-24", "GameTime": "16:30:00",
    "HomeTeam": 73529035, "AwayTeam": 1305184724,
    "HomeTeamAbbrv": "KPK / KeuPa HT", "AwayTeamAbbrv": "SiSu",
    "LevelID": 90, "SubSerieID": 4135, "Season": 2027,
}
PUBLIC_OTHER = {
    "GameID": 2721489, "GameDateDB": "2026-10-24", "GameTime": "14:40:00",
    "HomeTeam": 1368623392, "AwayTeam": 1368625918,
    "HomeTeamAbbrv": "Pelicans Team", "AwayTeamAbbrv": "Pingviinit",
    "LevelID": 90, "SubSerieID": 4135, "Season": 2027,
}


def legacy_game(game_id=732527, home=73529035, away=1305184724):
    return {
        "GameID": game_id, "GameDate": "24.10.2026", "GameTime": "16:30:00",
        "HomeTeam": home, "AwayTeam": away, "HomeTeamAbbrv": "KPK / KeuPa HT",
        "AwayTeamAbbrv": "SiSu", "AwayAssociation": 11015646,
        "LevelID": 90, "LevelName": "U16 Suomi-sarja", "GameStatus": 0,
    }


def payload(games):
    return build_payload(day=parse_date("2026-10-24"),
                         season={"SeasonNumber":2027, "SeasonName":"2026–2027"},
                         club={"AssID":"11015646", "AssName":"Sisu"},
                         teams=[], raw_games=games)


class PublicGameTest(TestCase):
    def get_games(self, endpoint, params, **kwargs):
        self.assertTrue(endpoint.endswith("/helpers/getgames"))
        self.assertEqual(params["season"], 2027)
        self.assertEqual(params["dog"], "2026-10-24")
        if params["subSerieId"] == 4135:
            return [{"Games": [copy.deepcopy(PUBLIC_OTHER), copy.deepcopy(PUBLIC_U16)]}]
        return []

    def test_verified_legacy_to_public_id(self):
        with tempfile.TemporaryDirectory() as d:
            p = payload([legacy_game()])
            game = p["games"][0]
            game["link_is_specific"] = False  # Ignore previously confirmed override in this test.
            summary = enrich_public_links([p["games"]], season=2027,
                          cache_file=Path(d) / "ids.json", get_json=self.get_games)
            self.assertEqual(summary["resolved"], 1)
            self.assertEqual(game["public_game_id"], 2721476)
            self.assertEqual(game["link_source"], "getgames")
            self.assertEqual(game["urls"]["gamecentre"],
                 "https://tulospalvelu.leijonat.fi/game?season=2027&gameid=2721476&lang=fi")

    def test_do_not_match_wrong_team(self):
        with tempfile.TemporaryDirectory() as d:
            p = payload([legacy_game(game_id=777777, home=444444)])
            game = p["games"][0]
            enrich_public_links([p["games"]], season=2027,
                          cache_file=Path(d) / "ids.json", get_json=self.get_games)
            self.assertFalse(game["link_is_specific"])
            self.assertEqual(game["urls"]["gamecentre"], "https://tulospalvelu.leijonat.fi/")

    def test_cache_avoids_fetch_next_run(self):
        with tempfile.TemporaryDirectory() as d:
            cache = Path(d) / "ids.json"
            for iteration in range(2):
                p = payload([legacy_game(game_id=777777)])
                def fail(*args, **kwargs):
                    if iteration:
                        raise AssertionError("Unnecessary API request for cached match")
                    return self.get_games(*args, **kwargs)
                summary = enrich_public_links([p["games"]], season=2027,
                               cache_file=cache, get_json=fail)
                self.assertEqual(summary["resolved"], 1)
                self.assertEqual(p["games"][0]["public_game_id"], 2721476)

    def test_later_u16_u18_games_match_despite_different_level_ids(self):
        """Regression: legacy LevelID 1138/1136 differs from getgames LevelID."""
        future = [
            {"GameID": 732524, "GameDate": "31.10.2026", "GameTime": "17:30:00",
             "HomeTeam": 1305184724, "AwayTeam": 1368625918,
             "HomeTeamAbbrv": "SiSu", "AwayTeamAbbrv": "Pingviinit",
             "HomeAssociation": 11015646, "LevelID": 1138,
             "LevelName": "U16 Suomi-sarja", "GameStatus": 0},
            {"GameID": 735165, "GameDate": "31.10.2026", "GameTime": "16:00:00",
             "HomeTeam": 182488615, "AwayTeam": 1368629034,
             "HomeTeamAbbrv": "KPK", "AwayTeamAbbrv": "SiSu",
             "AwayAssociation": 11015646, "LevelID": 1136,
             "LevelName": "U18 II-divisioona", "GameStatus": 0},
        ]
        # IDs below are synthetic test fixtures, not claimed actual official IDs.
        official = [
            {"GameID": 9000011, "Season": 2027, "GameDateDB": "2026-10-31",
             "GameTime": "17:30:00", "HomeTeam": 1305184724,
             "AwayTeam": 1368625918, "LevelID": 90},
            {"GameID": 9000012, "Season": 2027, "GameDateDB": "2026-10-31",
             "GameTime": "16:00:00", "HomeTeam": 182488615,
             "AwayTeam": 1368629034, "LevelID": 42},
        ]
        seen = []
        def get_games(endpoint, params, **kwargs):
            seen.append(dict(params))
            self.assertEqual(params["dog"], "2026-10-31")
            if params["teamid"] == 1305184724:
                return [{"Games": [official[0]]}]
            if params["teamid"] == 1368629034:
                return [{"Games": [official[1]]}]
            return []
        with tempfile.TemporaryDirectory() as folder:
            p = build_payload(day=parse_date("2026-10-31"),
                  season={"SeasonNumber": 2027, "SeasonName": "2026-2027"},
                  club={"AssID": "11015646", "AssName": "SiSu"},
                  teams=[], raw_games=future)
            result = enrich_public_links([p["games"]], season=2027,
                            cache_file=Path(folder) / "ids.json", get_json=get_games)
            self.assertEqual(result["resolved"], 2)
            self.assertEqual(result["unresolved"], 0)
            self.assertEqual(result["queries"], 2)
            self.assertEqual({g["game_id"]:g["public_game_id"] for g in p["games"]},
                             {732524: 9000011, 735165: 9000012})
            self.assertEqual({r["teamid"] for r in seen}, {1305184724,1368629034})

    def test_future_days_not_starved_by_unnecessary_queries(self):
        """One team/day request should reach dates beyond the first games."""
        from datetime import timedelta
        base = parse_date("2026-10-26")
        raw_days = []
        for n in range(10):
            day = (base + timedelta(days=n)).strftime("%d.%m.%Y")
            raw_days.append({"GameID": 800000+n, "GameDate": day,
                 "GameTime": "17:00:00", "HomeTeam": 1305184724,
                 "AwayTeam": 1368625918, "HomeTeamAbbrv": "SiSu",
                 "AwayTeamAbbrv": "Pingviinit", "HomeAssociation": 11015646,
                 "LevelID": 1138, "LevelName": "U16 Suomi-sarja", "GameStatus": 0})
        calls = []
        def get_games(endpoint, params, **kwargs):
            calls.append(dict(params))
            if params["teamid"] != 1305184724:
                return []
            n = (parse_date(params["dog"]) - base).days
            return [{"Games": [{"GameID": 9000100+n, "Season": 2027,
                "GameDateDB": params["dog"], "GameTime": "17:00:00",
                "HomeTeam": 1305184724, "AwayTeam": 1368625918,
                "LevelID": 90}]}]
        with tempfile.TemporaryDirectory() as folder:
            games = build_payload(day=base,
                season={"SeasonNumber": 2027, "SeasonName": "2026-2027"},
                club={"AssID":"11015646", "AssName":"SiSu"},
                teams=[], raw_games=raw_days)["games"]
            summary = enrich_public_links([games], season=2027,
                    cache_file=Path(folder)/"ids.json", get_json=get_games)
            self.assertEqual(summary["resolved"], 10)
            self.assertEqual(summary["queries"], 10)
            self.assertEqual(games[-1]["public_game_id"], 9000109)
            self.assertEqual(len(calls), 10)
