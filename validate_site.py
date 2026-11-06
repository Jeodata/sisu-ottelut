#!/usr/bin/env python3
"""Validate a staged Pages site without changing it or making network requests."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from logo_assets import _valid_png
from render_html import render_html

ROOT = Path(__file__).resolve().parent
HOME = 'https://tulospalvelu.leijonat.fi/'


def validate_site(directory: Path) -> dict[str, Any]:
    directory = directory.resolve()
    if not directory.is_dir():
        raise ValueError('Site directory is missing')
    # Pages artifacts must not contain symbolic links or hard links.
    for path in directory.rglob('*'):
        if path.is_symlink() or (path.is_file() and path.stat().st_nlink > 1):
            raise ValueError(f'Unsupported artifact link: {path}')
    raw = (directory / 'games.json').read_bytes()
    payload = json.loads(raw)
    if json.loads((directory / 'latest.json').read_text()) != payload:
        raise ValueError('games.json and latest.json disagree')
    date = payload['date']
    datetime.strptime(date, '%Y-%m-%d')
    if datetime.fromisoformat(payload['generated_at']).tzinfo is None:
        raise ValueError('generated_at must include a timezone')
    if json.loads((directory / 'archive' / f'{date}.json').read_text()) != payload:
        raise ValueError('Current-day archive disagrees with games.json')
    html = (directory / 'index.html').read_text(encoding='utf-8')
    if html != render_html(payload):
        raise ValueError('HTML does not match current renderer and JSON')
    if payload['counts']['total'] != len(payload['games']):
        raise ValueError('Daily game count disagrees with JSON')
    for filename in ('service-worker.js', 'manifest.webmanifest'):
        if (directory / filename).read_bytes() != (ROOT / filename).read_bytes():
            raise ValueError(f'Stale PWA shell: {filename}')
    manifest = json.loads((directory / 'manifest.webmanifest').read_text())
    if manifest.get('scope') != '/sisu-ottelut/' or manifest.get('start_url') != '/sisu-ottelut/':
        raise ValueError('Unexpected PWA scope or start URL')

    def local_file(relative: str) -> Path:
        path = (directory / relative).resolve()
        if path == directory or directory not in path.parents or not path.is_file():
            raise ValueError(f'Missing or unsafe local file: {relative}')
        return path

    for icon in manifest['icons']:
        body = local_file(icon['src']).read_bytes()
        if not _valid_png(body):
            raise ValueError('Invalid PWA icon')
        size = f'{int.from_bytes(body[16:20], "big")}x{int.from_bytes(body[20:24], "big")}'
        if size != icon['sizes']:
            raise ValueError('PWA icon dimensions disagree with manifest')
    for image in ('icons/apple-touch-icon.png', 'assets/logo.png'):
        if not _valid_png(local_file(image).read_bytes()):
            raise ValueError(f'Invalid PWA image: {image}')

    games = payload['games'] + [game for day in payload.get('coming_days', []) for game in day['games']]
    season = str(payload['season']['number'])
    resolved, local, fallback = 0, 0, 0
    for game in games:
        url = (game.get('urls') or {}).get('gamecentre') or HOME
        if game.get('link_is_specific'):
            parsed = urlsplit(url)
            query = parse_qs(parsed.query)
            ids = query.get('gameid', [])
            if (parsed.scheme != 'https' or parsed.netloc != 'tulospalvelu.leijonat.fi'
                    or parsed.path != '/game' or query.get('season') != [season]
                    or query.get('lang') != ['fi'] or len(ids) != 1 or not ids[0].isdigit()
                    or int(ids[0]) <= 0 or int(ids[0]) == int(game['game_id'])
                    or int(ids[0]) != int(game.get('public_game_id', ids[0]))):
                raise ValueError(f'Unsafe public game link: {url}')
            resolved += 1
        elif url != HOME:
            raise ValueError('Unverified game must use homepage fallback')
        for side in (game['home'], game['away']):
            logo = side.get('logo') or ''
            if logo.startswith('assets/team-logos/'):
                body = local_file(logo).read_bytes()
                if not _valid_png(body) or Path(logo).name != hashlib.sha256(body).hexdigest() + '.png':
                    raise ValueError(f'Invalid content-addressed logo: {logo}')
                local += 1
            else:
                # A crest failure is intentionally allowed: renderer shows initials.
                fallback += 1
    resolution = payload.get('public_link_resolution') or {}
    if resolution.get('total') != len(games) or resolution.get('resolved') != resolved:
        raise ValueError('Public-link coverage metadata disagrees with games')
    return {'date': date, 'generated_at': payload['generated_at'],
            'daily_games': len(payload['games']), 'all_games': len(games),
            'resolved_links': resolved, 'unresolved_links': len(games) - resolved,
            'local_logo_displays': local, 'fallback_logo_displays': fallback,
            'html_sha256': hashlib.sha256(html.encode()).hexdigest(),
            'json_sha256': hashlib.sha256(raw).hexdigest(), 'status': 'PASS'}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    try:
        result = validate_site(args.directory)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({'status': 'FAIL', 'error': str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
