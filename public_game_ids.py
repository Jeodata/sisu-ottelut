"""Resolve official Leijonat game-page IDs from /helpers/getgames.

The search endpoint /helpers/getextsearchgames has a DIFFERENT GameID and
LevelID namespace from /helpers/getgames. Never construct public game links
from search GameID, and never equate the two endpoints' LevelID values.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlencode

from sisu_ottelut import BASE_URL, HELPERS, ApiError, http_get_json

# User-verified official U16 subseries for 2026-10-24. This is a fallback;
# other ages are found using the Sisu team's ID without hard-coded subseries.
CONFIRMED_SUBSERIES = {2027: {"U16 Suomi-sarja": (4135,)}}
# Applies to requests for ALL upcoming days, not to each day individually.
# A normal run requests a single /getgames page per Sisu team/day, and stores
# confirmed IDs in docs/public_game_ids.json to eliminate repeat lookups.
MAX_LOOKUP_REQUESTS = 48


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _day(value: Any) -> str | None:
    text = str(value or "").strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d.%m.%y"):
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _time(value: Any) -> str:
    return str(value or "").strip()[:5].replace(".", ":")


def _name(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").casefold())


def _official_link(season: int, game_id: int) -> str:
    return f"{BASE_URL}/game?{urlencode({'season': season, 'gameid': game_id, 'lang': 'fi'})}"


def _games(data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, list):
        return []
    result = []
    for group in data:
        if isinstance(group, dict):
            for game in group.get("Games") or []:
                if isinstance(game, dict):
                    result.append(game)
    return result


def _match(game: dict[str, Any], official: dict[str, Any], season: int) -> bool:
    """Require exact day, time and both teams (IDs preferred).

    Do NOT compare LevelID fields: for the same U16 Suomi-sarja game the
    legacy search returns 1138, while official getgames returns 90.
    """
    if _day(game.get("date")) != _day(official.get("GameDateDB") or official.get("GameDate")):
        return False
    if not _day(game.get("date")) or _time(game.get("time")) != _time(official.get("GameTime")):
        return False
    if _int(official.get("Season")) not in (None, season):
        return False

    home, away = game.get("home") or {}, game.get("away") or {}
    h1, a1 = _int(home.get("team_id")), _int(away.get("team_id"))
    h2, a2 = _int(official.get("HomeTeam")), _int(official.get("AwayTeam"))
    if None not in (h1, a1, h2, a2):
        return h1 == h2 and a1 == a2

    # Only use names if both legacy and official team identifiers are absent;
    # a partially mismatched numeric team ID must not be silently bypassed.
    if any(x is not None for x in (h1, a1, h2, a2)):
        return False
    lh, la = home.get("abbreviation") or home.get("name"), away.get("abbreviation") or away.get("name")
    oh, oa = official.get("HomeTeamAbbrv"), official.get("AwayTeamAbbrv")
    return bool(_name(lh) and _name(la) and _name(lh) == _name(oh) and _name(la) == _name(oa))


def _cache_key(game: dict[str, Any], season: int) -> str:
    return f"{season}:{_day(game.get('date'))}:{game.get('game_id')}"


def _load_cache(path: Path) -> dict[str, int]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {str(k): int(v) for k, v in data.items() if _int(v) and _int(v) > 0}
    except (OSError, ValueError, TypeError):
        pass
    return {}


def enrich_public_links(
    day_groups: list[list[dict[str, Any]]],
    *,
    season: int,
    cache_file: Path,
    get_json: Callable[..., Any] = http_get_json,
) -> dict[str, int]:
    """Enrich all days with public links, without guessing a game ID.

    Fetches are grouped by (day, Sisu team) and confirmed results are cached.
    If no unique match exists, retain the safe tulospalvelu homepage fallback.
    """
    cached = _load_cache(cache_file)
    queries: dict[tuple[str, int, int, int], list[dict[str, Any]]] = {}
    by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for group in day_groups:
        for game in group:
            date = _day(game.get("date"))
            if date:
                by_date[date].append(game)

    def assign(game: dict[str, Any], official_id: int, source: str) -> None:
        game["urls"] = {**(game.get("urls") or {}), "gamecentre": _official_link(season, official_id)}
        game["public_game_id"] = official_id
        game["link_is_specific"] = True
        game["link_source"] = source
        cached[_cache_key(game, season)] = official_id

    def fetch(day: str, subserie: int = 0, team: int = 0, level: int = -1) -> list[dict[str, Any]]:
        key = (day, subserie, team, level)
        if key not in queries:
            if len(queries) >= MAX_LOOKUP_REQUESTS:
                return []
            params = {
                "dwl": 0, "season": season, "subSerieId": subserie,
                "teamid": team, "districtid": 0, "gamedays": 0,
                "dog": day, "levelid": level,
            }
            try:
                queries[key] = _games(get_json(f"{HELPERS}/getgames", params, timeout=9, max_attempts=1))
            except (ApiError, OSError, ValueError, TypeError):
                queries[key] = []
        return queries[key]

    def resolve(pending: list[dict[str, Any]], candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        remaining = []
        for game in pending:
            ids = {
                num for candidate in candidates
                if _match(game, candidate, season)
                if (num := _int(candidate.get("GameID"))) is not None and num > 0
            }
            if len(ids) == 1:
                assign(game, next(iter(ids)), "getgames")
            else:
                remaining.append(game)
        return remaining

    for day in sorted(by_date):
        pending = []
        for game in by_date[day]:
            if game.get("link_is_specific"):
                continue
            cached_id = cached.get(_cache_key(game, season))
            if cached_id:
                assign(game, cached_id, "getgames_cache")
            else:
                pending.append(game)
        if not pending:
            continue

        # First pass: one query per distinct Sisu team + day. Crucially,
        # do not use legacy LevelID or guess its corresponding public ID.
        candidates: list[dict[str, Any]] = []
        teams = sorted({
            team for game in pending
            if (team := _int((game.get("sisu_team") or {}).get("team_id"))) and team > 0
        })
        for team in teams:
            candidates.extend(fetch(day, team=team))
        pending = resolve(pending, candidates)
        if not pending:
            continue

        # Second pass: source-provided subseries where available, and a
        # verified fallback for U16. Different seasons/categories are never
        # assumed to share the same SubSerieID.
        subseries: set[int] = set()
        for game in pending:
            supplied = _int(game.get("sub_serie_id"))
            if supplied and supplied > 0:
                subseries.add(supplied)
            for label, ids in CONFIRMED_SUBSERIES.get(season, {}).items():
                if label.casefold() in str(game.get("level") or "").casefold():
                    subseries.update(ids)
        for subserie in sorted(subseries):
            candidates.extend(fetch(day, subserie=subserie))
        pending = resolve(pending, candidates)
        if not pending:
            continue

        # Final fallback: one general date query, if the endpoint can serve
        # junior games without a subseries/team filter. No wrong-game link.
        candidates.extend(fetch(day))
        resolve(pending, candidates)

    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(cached, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    all_games = [game for day in by_date.values() for game in day]
    resolved = sum(bool(game.get("link_is_specific")) for game in all_games)
    return {"resolved": resolved, "total": len(all_games), "unresolved": len(all_games) - resolved, "queries": len(queries)}
