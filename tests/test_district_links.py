"""No-network regressions against official getgames records captured 6 Nov 2026."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from public_game_ids import _games, _match, enrich_public_links

FIXTURE = json.loads((Path(__file__).parent / 'fixtures/district_links.json').read_text())
HOME = 'https://tulospalvelu.leijonat.fi/'


class DistrictLinkTests(unittest.TestCase):
    def setUp(self):
        self.calls = []

    def source(self, endpoint, params, **kwargs):
        self.assertTrue(endpoint.endswith('/helpers/getgames'))
        self.assertEqual(params['season'], 2027)
        self.calls.append(dict(params))
        for row in FIXTURE['responses']:
            if (params['districtid'] == row['params']['districtid'] and
                    params['dog'] == row['params']['dog']):
                self.assertEqual(params['gamedays'], -1)
                return copy.deepcopy(row['data'])
        return []

    def resolve(self, games, source=None):
        with tempfile.TemporaryDirectory() as tmp:
            return enrich_public_links([games], season=2027, cache_file=Path(tmp)/'ids.json',
                                       get_json=source or self.source)

    def test_all_29_current_games_and_later_u16_u18(self):
        games = copy.deepcopy(FIXTURE['current'])
        summary = self.resolve(games)
        self.assertEqual(summary, {'resolved': 29, 'total': 29, 'unresolved': 0, 'queries': 8})
        expected = {r['legacy_id']:r['public_id'] for r in FIXTURE['expected_current']}
        for game in games:
            self.assertEqual(game['public_game_id'], expected[game['game_id']])
            self.assertEqual(game['urls']['gamecentre'],
                 HOME + 'game?season=2027&gameid=' + str(expected[game['game_id']]) + '&lang=fi')
        for legacy, public in ((735167,2727984),(735176,2727993),(771756,2758488)):
            self.assertEqual(next(g for g in games if g['game_id']==legacy)['public_game_id'], public)
        self.assertEqual({p['districtid'] for p in self.calls}, {2,6})

    def test_u9_four_games(self):
        games = copy.deepcopy(FIXTURE['u9'])
        summary = self.resolve(games)
        self.assertEqual(summary['resolved'], 4)
        self.assertEqual({g['public_game_id'] for g in games}, {2755414,2755415,2755416,2755417})

    def test_cache_second_run_needs_no_api(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp)/'ids.json'
            first = copy.deepcopy(FIXTURE['current'])
            enrich_public_links([first], season=2027, cache_file=file, get_json=self.source)
            def forbidden(*args, **kwargs): self.fail('Unexpected API call for a cached ID')
            second = copy.deepcopy(FIXTURE['current'])
            summary = enrich_public_links([second], season=2027, cache_file=file, get_json=forbidden)
            self.assertEqual(summary['queries'], 0)
            self.assertEqual(summary['resolved'], 29)

    def test_wrong_season_date_time_team_and_swapped_teams_rejected(self):
        game = next(g for g in FIXTURE['current'] if g['game_id']==771756)
        official = next(o for r in FIXTURE['responses'] for o in _games(r['data']) if o['GameID']==2758488)
        self.assertTrue(_match(game, official, 2027))
        for key, value in [('Season',2026),('GameDateDB','2026-11-15'),('GameTime','18:45:00'),
                           ('HomeTeam',123456),('AwayTeam',123456)]:
            bad = copy.deepcopy(official); bad[key]=value
            self.assertFalse(_match(game,bad,2027),key)
        swapped = copy.deepcopy(official)
        swapped['HomeTeam'],swapped['AwayTeam']=swapped['AwayTeam'],swapped['HomeTeam']
        self.assertFalse(_match(game,swapped,2027))

    def test_conflicting_ids_across_districts_not_assigned(self):
        game = copy.deepcopy(FIXTURE['current'][0])
        original = next(o for r in FIXTURE['responses'] for o in _games(r['data']) if _match(game,o,2027))
        def conflict(endpoint, params, **kwargs):
            data = copy.deepcopy(original)
            if params['districtid'] == 6: data['GameID'] += 100
            return [{'Games':[data]}]
        summary = self.resolve([game], conflict)
        self.assertEqual(summary['resolved'],0)
        self.assertEqual(game['urls']['gamecentre'],HOME)

    def test_total_request_cap_kept(self):
        games = copy.deepcopy(FIXTURE['current'])
        with patch('public_game_ids.MAX_LOOKUP_REQUESTS', 2):
            summary = self.resolve(games)
            self.assertEqual(summary['queries'],2)
            self.assertEqual(len(self.calls),2)

    def test_api_errors_keep_safe_fallback(self):
        games = copy.deepcopy(FIXTURE['current'])
        def blocked(*args, **kwargs): raise OSError('403 blocked')
        summary = self.resolve(games, blocked)
        self.assertEqual(summary['resolved'],0)
        self.assertTrue(all(g['urls']['gamecentre']==HOME for g in games))


if __name__ == '__main__':
    unittest.main()
