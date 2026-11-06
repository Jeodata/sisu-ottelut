"""Validate release products without an API, Git push or deployment."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from publish import write_site
from render_html import render_html
from sisu_ottelut import build_payload, parse_date
from validate_site import validate_site

ROOT = Path(__file__).resolve().parents[1]


class ReleaseValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.out = Path(self.temp.name)
        raw = {'GameID': 732527, 'GameStatus': 0, 'LevelName': 'U16 Suomi-sarja',
               'GameDate': '24.10.2026', 'GameTime': '16:30',
               'HomeTeamName': 'KPK / KeuPa HT', 'AwayTeamName': 'SiSu',
               'AwayAssociation': 11015646}
        self.data = build_payload(day=parse_date('2026-10-24'),
                   season={'SeasonNumber': 2027, 'SeasonName': '2026-2027', 'current': True},
                   club={'AssID': '11015646', 'AssName': 'Sisu Hockey'}, teams=[], raw_games=[raw])
        self.data['coming_days'] = []
        self.data['public_link_resolution'] = {'total': 1, 'resolved': 1, 'unresolved': 0, 'queries': 0}
        with patch('publish.localize_logos'):
            write_site(self.data, self.out)

    def sync(self):
        body = json.dumps(self.data)
        for name in ('games.json', 'latest.json', 'archive/2026-10-24.json'):
            (self.out / name).write_text(body)
        (self.out / 'index.html').write_text(render_html(self.data))

    def test_valid_product_allows_initials_fallback(self):
        summary = validate_site(self.out)
        self.assertEqual(summary['status'], 'PASS')
        self.assertEqual(summary['resolved_links'], 1)
        self.assertEqual(summary['fallback_logo_displays'], 2)

    def test_stale_html_rejected(self):
        (self.out / 'index.html').write_text('old published HTML')
        with self.assertRaisesRegex(ValueError, 'HTML'):
            validate_site(self.out)

    def test_json_mismatch_rejected(self):
        (self.out / 'latest.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'disagree'):
            validate_site(self.out)

    def test_wrong_season_link_rejected(self):
        self.data['games'][0]['urls']['gamecentre'] = 'https://tulospalvelu.leijonat.fi/game?season=2026&gameid=2721476&lang=fi'
        self.sync()
        with self.assertRaisesRegex(ValueError, 'Unsafe public game link'):
            validate_site(self.out)

    def test_missing_local_logo_rejected(self):
        self.data['games'][0]['home']['logo'] = 'assets/team-logos/' + 'a' * 64 + '.png'
        self.sync()
        with self.assertRaisesRegex(ValueError, 'Missing or unsafe'):
            validate_site(self.out)

    def test_icon_dimensions_rejected(self):
        icon = self.out / 'icons/icon-192.png'
        icon.write_bytes((ROOT / 'icons/icon-512.png').read_bytes())
        with self.assertRaisesRegex(ValueError, 'dimensions'):
            validate_site(self.out)

    def test_symlink_rejected(self):
        (self.out / 'unsafe').symlink_to(ROOT / 'README.md')
        with self.assertRaisesRegex(ValueError, 'artifact link'):
            validate_site(self.out)

    def test_stale_worker_rejected(self):
        (self.out / 'service-worker.js').write_text('old worker')
        with self.assertRaisesRegex(ValueError, 'Stale PWA'):
            validate_site(self.out)

    def test_pipeline_is_serial_and_fail_closed(self):
        source = (ROOT / '.github/workflows/update-games.yml').read_text()
        self.assertIn('cancel-in-progress: false', source)
        self.assertIn('needs: update', source)
        self.assertIn('pages: write', source)
        self.assertIn('id-token: write', source)
        self.assertIn('name: github-pages', source)
        self.assertIn('ref: main', source)
        self.assertIn('set -euo pipefail', source)
        self.assertNotIn('continue-on-error', source)
        self.assertNotIn('if: always()', source)
        self.assertNotIn('--force', source)
        self.assertLess(source.index('python3 publish.py'), source.index('python3 validate_site.py'))
        self.assertLess(source.index('python3 validate_site.py'), source.index('cp -a "$site/." docs/'))
        self.assertLess(source.index('git push origin HEAD:main'), source.index('actions/upload-pages-artifact@'))
        self.assertEqual(source.count('actions/deploy-pages@'), 1)
        self.assertIn("cron: '15 5,15,19 * * 1-5'", source)
        self.assertIn("cron: '*/5 5-20 * * 0,6'", source)

    def test_non_main_manual_run_cannot_update_main(self):
        source = (ROOT / '.github/workflows/update-games.yml').read_text()
        update = source[source.index('  update:'):source.index('  deploy:')]
        self.assertIn("if: github.ref == 'refs/heads/main'", update)
        self.assertLess(update.index("if: github.ref"), update.index('steps:'))

    def test_staging_failure_cannot_copy_over_previous_data(self):
        source = (ROOT / '.github/workflows/update-games.yml').read_text()
        start = source.index('          set -euo pipefail', source.index('name: Hae ja tarkista'))
        end = source.index('      - name: Tallenna', start)
        block = '\n'.join(line[10:] for line in source[start:end].splitlines())
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / 'docs').mkdir()
            (folder / 'docs/games.json').write_text('previous publication')
            bin_dir = folder / 'bin'; bin_dir.mkdir()
            fake = bin_dir / 'python3'; fake.write_text('#!/bin/sh\nexit 1\n'); fake.chmod(0o755)
            import os
            env = {**os.environ, 'RUNNER_TEMP': str(folder / 'tmp'),
                   'GITHUB_STEP_SUMMARY': str(folder / 'summary'), 'PATH': str(bin_dir) + ':' + os.environ['PATH']}
            result = subprocess.run(['bash', '-c', block], cwd=folder, env=env, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual((folder / 'docs/games.json').read_text(), 'previous publication')


if __name__ == '__main__':
    unittest.main()
