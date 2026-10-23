"""Find official Leijonat game-page IDs using /helpers/getgames.

Legacy /helpers/getextsearchgames.GameID can be different from the public ID.
Only accept an exact, unique date/time/team match; otherwise keep the safe fallback.
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

# The user verified the 2026-10-24 U16 match on subSerieId 4135. The
# source data may provide SubSerieID dynamically for other competitions.
# This single fallback only assists when the legacy endpoint lacks one.
CONFIRMED_SUBSERIES = {2027: {90: (4135,)}}
MAX_LOOKUP_REQUESTS = 16  # Keep the five-minute GitHub Actions runs bounded.


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
    return f"{BASE_URL}/game?{urlencode({'season':season, 'gameid':game_id, 'lang':'fi'})}"


def _games(data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, list):
        return []
    games = []
    for group in data:
        if isinstance(group, dict):
            for game in group.get("Games") or []:
                if isinstance(game, dict):
                    games.append(game)
    return games


def _match(game: dict[str, Any], official: dict[str, Any], season: int) -> bool:
    """Do not match on date/time alone; prevent wrong links."""
    game_date = _day(game.get("date"))
    official_date = _day(official.get("GameDateDB") or official.get("GameDate"))
    if not game_date or game_date != official_date or _time(game.get("time")) != _time(official.get("GameTime")):
        return False
    if _int(official.get("Season")) not in (None, season):
        return False
    level1, level2 = _int(game.get("level_id")), _int(official.get("LevelID"))
    if level1 is not None and level2 is not None and level1 != level2:
        return False
    home, away = game.get("home") or {}, game.get("away") or {}
    h1, a1 = _int(home.get("team_id")), _int(away.get("team_id"))
    h2, a2 = _int(official.get("HomeTeam")), _int(official.get("AwayTeam"))
    if None not in (h1, a1, h2, a2):
        return h1 == h2 and a1 == a2
    # Only allow name fallback if BOTH names are supplied and precisely agree.
    return bool(
        _name(home.get("abbreviation") or home.get("name"))
        and _name(away.get("abbreviation") or away.get("name"))
        and _name(home.get("abbreviation") or home.get("name")) == _name(official.get("HomeTeamAbbrv"))
        and _name(away.get("abbreviation") or away.get("name")) == _name(official.get("AwayTeamAbbrv"))
    )


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
    """Update normalized game dictionaries in-place with safely resolved links.

    A failed or unavailable endpoint is nonfatal. Only verified one-to-one
    matches replace the existing homepage/override link.
    """
    cached = _load_cache(cache_file)
    queries: dict[tuple[str, int, int, int], list[dict[str, Any]]] = {}
    tried: set[tuple[str, int, int, int]] = set()
    by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for group in day_groups:
        for game in group:
            if _day(game.get("date")):
                by_date[_day(game["date"])].append(game)

    def assign(game: dict[str, Any], official_id: int, source: str) -> None:
        game["urls"] = {**(game.get("urls") or {}), "gamecentre": _official_link(season, official_id)}
        game["public_game_id"] = official_id
        game["link_is_specific"] = True
        game["link_source"] = source
        cached[_cache_key(game, season)] = official_id

    def fetch(day: str, subserie: int = 0, team: int = 0, level: int = -1) -> list[dict[str, Any]]:
        key = (day, subserie, team, level)
        if key not in queries:
            if len(tried) >= MAX_LOOKUP_REQUESTS:
                return []
            tried.add(key)
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

    for day, games in by_date.items():
        pending = []
        for game in games:
            if game.get("link_is_specific"):
                # Keep legacy, explicitly verified overrides as fallbacks.
                continue
            key = _cache_key(game, season)
            if key in cached:
                assign(game, cached[key], "getgames_cache")
            else:
                pending.append(game)
        if not pending:
            continue
        catalogue = fetch(day)  # Broad daily search (may not include junior games).
        for game in pending:
            level = _int(game.get("level_id")) or -1
            # Query the returned series ID first, then any experimentally
            # confirmed fallback series for that level and season.
            for series_id in ([game.get("sub_serie_id")] + list(CONFIRMED_SUBSERIES.get(season, {}).get(level, ()))):
                series_id = _int(series_id)
                if series_id and series_id > 0:
                    catalogue.extend(fetch(day, subserie=series_id))
        # Filter from the pooled catalogue by exact teams/date/time, ensuring
        # ID uniqueness even if the same fixture is returned by many queries.
        def matches(game: dict[str, Any]) -> set[int]:
            return {
                _int(candidate.get("GameID"))
                for candidate in catalogue
                if _match(game, candidate, season) and _int(candidate.get("GameID"))
            }
        remaining = []
        for game in pending:
            ids = matches(game)
            if len(ids) == 1:
                assign(game, next(iter(ids)), "getgames")
            else:
                remaining.append(game)
        # Team or level search is an optional last resort where a subseries
        # identifier was absent in the legacy endpoint.
        for game in remaining:
            team = _int((game.get("sisu_team") or {}).get("team_id"))
            level = _int(game.get("level_id"))
            if team:
                catalogue.extend(fetch(day, team=team))
            if level is not None:
                catalogue.extend(fetch(day, level=level))
            ids = matches(game)
            if len(ids) == 1:
                assign(game, next(iter(ids)), "getgames")

    # Persist confirmed IDs for the next 5-minute run. The cache contains
    # only successfully matched public IDs; no guessed numeric offsets.
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(cached, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"resolved": sum(1 for g in by_date.values() for x in g if x.get("link_is_specific")),
            "total": sum(map(len, by_date.values())), "queries": len(tried)}
