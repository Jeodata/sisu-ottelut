import copy
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from logo_assets import MAX_IMAGE_BYTES, REFRESH_SECONDS, _valid_png, download_png, localize_logos
from publish import main, write_site
from render_html import _logo, render_html
from sisu_ottelut import ApiError, BASE_URL, TEAM_LOGO_BASE, logo_url, team_side

ROOT = Path(__file__).resolve().parents[1]
PNG = (ROOT / 'assets/logo.png').read_bytes()
TEAM = TEAM_LOGO_BASE + '2027/teams/123.png?associationId=456'


def payload():
    game = {'game_id': 1, 'status': 'upcoming', 'home': {'logo': TEAM,
            'name': 'HPK Oranssi', 'association_id': 456},
            'away': {'name': 'SiSu', 'logo': TEAM, 'association_id': 11015646}}
    return {'date': '2026-11-07', 'games': [game], 'upcoming': [game], 'live': [],
            'finished': [], 'counts': {'total': 1}, 'coming_days': []}


class LogoTests(unittest.TestCase):
    def test_current_img_path_and_query(self):
        side = team_side({'HomeImg': '2027/teams/123.png?associationId=456'}, 'Home', False)
        self.assertEqual(side['logo'], TEAM)

    def test_legacy_filename_absolute_and_slash(self):
        self.assertEqual(logo_url('11015646.png'), TEAM_LOGO_BASE + '11015646.png')
        self.assertEqual(logo_url('/2027/teams/123.png?associationId=456'), TEAM)
        self.assertEqual(logo_url(BASE_URL + '/images/associations/weblogos/200x200/2027/teams/123.png?associationId=456'), TEAM)
        self.assertEqual(logo_url(TEAM), TEAM)

    def test_reject_invalid_urls(self):
        for value in (None, '', '//evil.example/logo.png', 'https://evil.example/logo.png',
                      '../logo.png', '%2e%2e/logo.png', 'javascript:alert(1)', 'photo.html'):
            self.assertIsNone(logo_url(value), repr(value))

    def test_all_groups_localized_one_fetch_and_no_state_change(self):
        data = payload()
        data['coming_days'] = [{'date': '2026-11-08', 'games': [copy.deepcopy(data['games'][0])]}]
        calls = []
        with tempfile.TemporaryDirectory() as tmp:
            stats = localize_logos(data, Path(tmp), downloader=lambda u: calls.append(u) or PNG, now=100)
            self.assertEqual(calls, [TEAM])
            self.assertEqual(stats['downloaded'], 1)
            for group in [data['games'], data['upcoming'], data['coming_days'][0]['games']]:
                for game in group:
                    self.assertEqual(game['status'], 'upcoming')
                    self.assertEqual(game['game_id'], 1)
                    for key in ('home', 'away'):
                        self.assertTrue((Path(tmp) / game[key]['logo']).is_file())
                        self.assertEqual(game[key]['logo_external'], TEAM)
            self.assertEqual(data['counts'], {'total': 1})

    def test_fresh_cache_needs_no_requests(self):
        with tempfile.TemporaryDirectory() as tmp:
            localize_logos(payload(), Path(tmp), downloader=lambda u: PNG, now=100)
            with patch('logo_assets.download_png', side_effect=AssertionError('network forbidden')):
                stats = localize_logos(payload(), Path(tmp), downloader=lambda u: self.fail(u), now=101)
                self.assertEqual(stats['requests'], 0)

    def test_failed_refresh_keeps_good_file_and_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = payload()
            localize_logos(data, Path(tmp), downloader=lambda u: PNG, now=100)
            prior = (Path(tmp) / 'assets/team-logos/index.json').read_bytes()
            def blocked(u):
                raise urllib.error.HTTPError(u, 403, 'Blocked', {}, None)
            new = payload()
            localize_logos(new, Path(tmp), downloader=blocked, now=100 + REFRESH_SECONDS + 1)
            self.assertEqual(new['games'][0]['home']['logo'], data['games'][0]['home']['logo'])
            self.assertEqual((Path(tmp) / 'assets/team-logos/index.json').read_bytes(), prior)

    def test_failed_team_uses_own_association_not_sisu(self):
        data = payload()
        calls = []
        def own_club(u):
            calls.append(u)
            if u == TEAM_LOGO_BASE + '456.png':
                return PNG
            raise OSError('404')
        with tempfile.TemporaryDirectory() as tmp:
            localize_logos(data, Path(tmp), downloader=own_club, now=100)
            home = data['games'][0]['home']
            self.assertEqual(home['logo_source'], 'association')
            self.assertEqual(home['association_id'], 456)
            self.assertTrue((Path(tmp) / home['logo']).is_file())

    def test_all_remote_errors_leave_initials_fallback(self):
        def unavailable(u):
            raise OSError('404')
        with tempfile.TemporaryDirectory() as tmp:
            data = payload()
            localize_logos(data, Path(tmp), downloader=unavailable)
            markup = _logo(data['games'][0]['home'])
            self.assertIn('>HP</span>', markup)
            self.assertIn('onerror="this.remove()"', markup)
            self.assertNotIn('assets/logo.png', markup)
            self.assertIn('aria-label="HPK Oranssi"', markup)

    def test_no_url_and_escaped_name(self):
        self.assertNotIn('<img', _logo({'name': 'Fortuna'}))
        self.assertIn('>FO</span>', _logo({'name': 'Fortuna'}))
        self.assertNotIn('aria-label="<script>', _logo({'name': '<script>'}))

    def test_png_validation_rejects_html_truncated_and_oversized(self):
        self.assertTrue(_valid_png(PNG))
        for body in (b'<html>403</html>', PNG[:24], PNG[:-5], PNG + b'x' * MAX_IMAGE_BYTES):
            self.assertFalse(_valid_png(body))

    def test_api_failure_does_not_replace_previous_html_or_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            originals = {'index.html': b'previous published page', 'games.json': b'{"previous":true}',
                         'latest.json': b'{"previous":true}'}
            for name, body in originals.items():
                (out / name).write_bytes(body)
            with patch('publish.build_site_payload', side_effect=ApiError('HTTP 403 blocked')):
                self.assertEqual(main(['--out', tmp]), 1)
            for name, body in originals.items():
                self.assertEqual((out / name).read_bytes(), body)

    def test_download_rejects_html_200(self):
        class FakeResponse:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def geturl(self): return TEAM
            headers = type('Headers', (), {'get_content_type': lambda self: 'text/html'})()
        with patch('urllib.request.urlopen', return_value=FakeResponse()):
            with self.assertRaises(ValueError): download_png(TEAM)

    def test_content_hash_changes_when_logo_changes(self):
        other = (ROOT / 'icons/icon-192.png').read_bytes()
        with tempfile.TemporaryDirectory() as tmp:
            data = payload()
            localize_logos(data, Path(tmp), downloader=lambda u: PNG, now=100)
            updated = payload()
            localize_logos(updated, Path(tmp), downloader=lambda u: other, now=100 + REFRESH_SECONDS + 1)
            self.assertNotEqual(updated['games'][0]['home']['logo'], data['games'][0]['home']['logo'])

    def test_publish_fresh_directory_writes_local_images_and_pwa(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = payload()
            with patch('publish.localize_logos', side_effect=lambda p, o: localize_logos(p, o, downloader=lambda u: PNG)):
                write_site(data, Path(tmp))
            result = json.loads((Path(tmp) / 'games.json').read_text())
            self.assertEqual(result, json.loads((Path(tmp) / 'latest.json').read_text()))
            self.assertIn(result['games'][0]['home']['logo'], (Path(tmp) / 'index.html').read_text())
            for name in ('manifest.webmanifest', 'service-worker.js', 'icons/icon-192.png', 'icons/icon-512.png',
                         'icons/apple-touch-icon.png', 'assets/logo.png', 'archive/2026-11-07.json'):
                self.assertTrue((Path(tmp) / name).is_file(), name)


if __name__ == '__main__':
    unittest.main()
