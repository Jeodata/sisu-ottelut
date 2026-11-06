"""No-network regression tests for Sisu Hockey public match links."""
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sisu_ottelut import public_game_link, build_payload, parse_date
from render_html import render_html

BASE = "https://tulospalvelu.leijonat.fi"


def raw_game(game_id, level="U16 Suomi-sarja"):
    return {
        "GameID": game_id, "GameStatus": 0, "LevelName": level,
        "GameDate": "24.10.2026", "GameTime": "16:30",
        "HomeTeamName": "KPK / KeuPa HT", "AwayTeamName": "SiSu",
        "AwayAssociation": 11015646,
    }


class OfficialLinksTest(unittest.TestCase):
    def test_verified_u16_match(self):
        url, specific, source = public_game_link(raw_game(732527), 2027)
        self.assertEqual(url, BASE + "/game?season=2027&gameid=2721476&lang=fi")
        self.assertTrue(specific)
        self.assertEqual(source, "verified_override")

    def test_verified_u18_match(self):
        url, specific, source = public_game_link(raw_game(735159), 2027)
        self.assertEqual(url, BASE + "/game?season=2027&gameid=2727976&lang=fi")
        self.assertTrue(specific)
        self.assertEqual(source, "verified_override")

    def test_unverified_internal_id_never_links_to_wrong_match(self):
        url, specific, source = public_game_link(raw_game(752874), 2027)
        self.assertEqual(url, BASE + "/")
        self.assertFalse(specific)
        self.assertEqual(source, "unresolved")

    def test_no_cross_season_matching(self):
        url, specific, _ = public_game_link(raw_game(732527), 2026)
        self.assertEqual(url, BASE + "/")
        self.assertFalse(specific)

    def test_api_explicit_public_id(self):
        raw = raw_game(123456)
        raw["PublicGameID"] = 2711111
        url, specific, source = public_game_link(raw, 2027)
        self.assertEqual(url, BASE + "/game?season=2027&gameid=2711111&lang=fi")
        self.assertTrue(specific)
        self.assertEqual(source, "PublicGameID")

    def test_api_canonical_public_url(self):
        raw = raw_game(123456)
        raw["GameURL"] = BASE + "/game?season=2027&gameid=2711111&lang=fi"
        url, specific, source = public_game_link(raw, 2027)
        self.assertEqual(url, raw["GameURL"])
        self.assertTrue(specific)
        self.assertEqual(source, "GameURL")

    def test_no_third_party_url(self):
        raw = raw_game(123456)
        raw["GameURL"] = "https://malicious.invalid/game?season=2027&gameid=2711111"
        self.assertEqual(public_game_link(raw, 2027)[0], BASE + "/")

    def test_full_payload_and_render(self):
        day = parse_date('2026-10-24')
        payload = build_payload(day=day, season={'SeasonNumber':2027, 'SeasonName':'2026-2027', 'current':True}, club={'AssID':'11015646','AssName':'Sisu Hockey'}, teams=[], raw_games=[raw_game(732527),raw_game(752874)])
        self.assertEqual(len(payload['games']), 2)
        html = render_html(payload)
        self.assertIn('gameid=2721476',html)
        self.assertNotIn('gameid=732527',html)
        self.assertNotIn('gameid=752874',html)
        self.assertIn('href="https://tulospalvelu.leijonat.fi/"',html)

    def test_renderer_rejects_old_internal_and_wrong_season_links(self):
        from render_html import _game_card
        game = {'game_id': 732527, 'urls': {'gamecentre': BASE + '/game?gameid=732527'}}
        markup = _game_card(game, 2027)
        self.assertNotIn('gameid=732527', markup)
        self.assertIn('href="' + BASE + '/"', markup)
        game['link_is_specific'] = True
        for url in (BASE + '/game?season=2026&gameid=2721476&lang=fi',
                    'https://invalid.example/game?season=2027&gameid=2721476&lang=fi'):
            game['urls']['gamecentre'] = url
            self.assertNotIn('gameid=', _game_card(game, 2027))

    def test_prebuilt_pages_regression(self):
        from html import escape
        from urllib.parse import parse_qs, urlsplit
        docs = Path(__file__).resolve().parents[1] / 'docs'
        data = json.loads((docs / 'games.json').read_text(encoding='utf-8'))
        # Render the latest snapshot with the current code. Do not demand
        # that yesterday's checked-in output already uses a new template.
        # Actual HTML/JSON output equality is checked by validate_site.py.
        page = render_html(data)
        groups = [data.get('games') or []] + [d.get('games') or [] for d in data.get('coming_days') or []]
        for group in groups:
            for game in group:
                url = (game.get('urls') or {}).get('gamecentre') or BASE + '/'
                self.assertIn('href="' + escape(url, quote=True) + '"', page)
                if game.get('link_is_specific'):
                    parsed = urlsplit(url)
                    query = parse_qs(parsed.query)
                    self.assertEqual(parsed.netloc, 'tulospalvelu.leijonat.fi')
                    self.assertEqual(parsed.path, '/game')
                    self.assertEqual(query.get('season'), [str(data['season']['number'])])
                    self.assertEqual(query.get('lang'), ['fi'])
                    self.assertNotEqual(query.get('gameid'), [str(game['game_id'])])


if __name__ == '__main__':
    unittest.main()
