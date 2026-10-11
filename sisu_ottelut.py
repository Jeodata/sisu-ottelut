#!/usr/bin/env python3
"""Hae Sisu Hockey Hämeenlinna ry:n ottelut Leijonat-tulospalvelun JSON-APIsta."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
import time
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

BASE_URL = "https://tulospalvelu.leijonat.fi"
HELPERS = f"{BASE_URL}/helpers"
TZ = ZoneInfo("Europe/Helsinki")

CLUB_NAME_NEEDLE = "SISU HOCKEY HÄMEENLINNA"
DEFAULT_ASS_ID = "11015646"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
)

DEFAULT_CLUB = {
    "AssID": DEFAULT_ASS_ID,
    "AssName": "SISU HOCKEY HÄMEENLINNA  RY",
    "AssAbbrv": "SiSu",
    "AssCity": "HÄMEENLINNA",
    "AssWeb": "www.sisuhockey.fi",
}

GAME_STATUS_MAP = {
    0: "upcoming",
    1: "live",
    2: "finished",
    94: "finished",
}

FINISHED_TYPE_MAP = {
    0: None,
    1: "regulation",
    2: "overtime",
    3: "shootout",
}


class ApiError(RuntimeError):
    pass


def http_get_json(url: str, params: dict[str, Any] | None = None, timeout: int = 45) -> Any:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params, doseq=True)}"
    last_error: Exception | None = None
    for attempt in range(4):
        req = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Accept-Language": "fi-FI,fi;q=0.9,en-US;q=0.8,en;q=0.7",
                "User-Agent": USER_AGENT,
                "Referer": f"{BASE_URL}/serie?lang=fi",
                "Origin": BASE_URL,
                "X-Requested-With": "XMLHttpRequest",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
            if not raw:
                return None
            try:
                return json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError as exc:
                raise ApiError(f"Vastaus ei ollut JSON: {url}") from exc
        except urllib.error.HTTPError as exc:
            last_error = ApiError(f"HTTP {exc.code} {url}")
            if exc.code in (403, 429, 500, 502, 503, 504) and attempt < 3:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise last_error from exc
        except urllib.error.URLError as exc:
            last_error = ApiError(f"Yhteysvirhe: {exc.reason} ({url})")
            if attempt < 3:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise last_error from exc
    raise last_error or ApiError(url)


def parse_date(value: str | None) -> datetime:
    """Palauta Helsinki-päivä. Hyväksyy YYYY-MM-DD ja DD.MM.YYYY."""
    if not value:
        return datetime.now(TZ)
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d.%m.%y"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=TZ)
        except ValueError:
            continue
    raise SystemExit(f"Virheellinen päiväys: {value!r} (käytä YYYY-MM-DD tai DD.MM.YYYY)")


def fi_date(dt: datetime) -> str:
    return dt.strftime("%d.%m.%Y")


def iso_date(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


def current_season(season_override: int | None = None) -> dict[str, Any]:
    if season_override:
        return {"SeasonNumber": season_override, "SeasonName": "2026-2027", "current": True}
    try:
        seasons = http_get_json(f"{HELPERS}/getseasons") or []
        for s in seasons:
            if s.get("current"):
                return s
        if seasons:
            return seasons[0]
    except ApiError:
        return {"SeasonNumber": 2027, "SeasonName": "2026-2027", "current": True}
    return {"SeasonNumber": 2027, "SeasonName": "2026-2027", "current": True}


def find_club(season: int, needle: str = CLUB_NAME_NEEDLE) -> dict[str, Any]:
    associations = http_get_json(f"{HELPERS}/getass", {"season": season}) or []
    needle_n = _norm(needle)
    exact = []
    partial = []
    for ass in associations:
        name = ass.get("AssName") or ""
        n = _norm(name)
        if n == needle_n or needle_n in n:
            exact.append(ass)
        elif "sisu" in n and "hameenlinna" in n:
            partial.append(ass)
    hits = exact or partial
    if hits:
        return hits[0]
    for ass in associations:
        if str(ass.get("AssID")) == DEFAULT_ASS_ID:
            return ass
    raise ApiError(f"Seuraa ei löytynyt: {needle}")


def resolve_club(season: int, ass_id: str | None, lookup: bool) -> dict[str, Any]:
    if lookup:
        club = find_club(season)
        if ass_id and str(club.get("AssID")) != str(ass_id):
            club["AssID"] = ass_id
        return club
    if ass_id and str(ass_id) != DEFAULT_ASS_ID:
        return {
            "AssID": str(ass_id),
            "AssName": CLUB_NAME_NEEDLE,
            "AssAbbrv": "SiSu",
            "AssCity": None,
            "AssWeb": None,
        }
    return dict(DEFAULT_CLUB)


def _norm(text: str) -> str:
    return " ".join(text.casefold().replace("ä", "a").replace("ö", "o").replace("å", "a").split())


def fetch_teams(season: int, ass_id: str) -> list[dict[str, Any]]:
    try:
        teams = http_get_json(f"{HELPERS}/getteams", {"season": season, "assid": ass_id}) or []
    except ApiError:
        teams = []
    return [
        {"team_id": t.get("TeamID"), "name": (t.get("TeamName") or "").strip()}
        for t in teams
    ]


def fetch_club_games(season: int, ass_id: str, day: datetime) -> list[dict[str, Any]]:
    date_fi = fi_date(day)
    params = {
        "season": season,
        "Filters[StartDate]": date_fi,
        "Filters[EndDate]": date_fi,
        "Filters[GameID]": "",
        "Filters[AssID]": ass_id,
        "Filters[TeamID]": "",
        "Filters[RinkID]": "",
        "Filters[Games]": "",
        "Filters[GamesTime]": "",
    }
    return http_get_json(f"{HELPERS}/getextsearchgames", params) or []


def fetch_club_games_range(season: int, ass_id: str, start: datetime, end: datetime) -> list[dict[str, Any]]:
    params = {
        "season": season,
        "Filters[StartDate]": fi_date(start),
        "Filters[EndDate]": fi_date(end),
        "Filters[GameID]": "",
        "Filters[AssID]": ass_id,
        "Filters[TeamID]": "",
        "Filters[RinkID]": "",
        "Filters[Games]": "",
        "Filters[GamesTime]": "",
    }
    return http_get_json(f"{HELPERS}/getextsearchgames", params) or []


def fetch_payload(
    day: datetime | None = None,
    *,
    season_number: int | None = None,
    ass_id: str = DEFAULT_ASS_ID,
    lookup_club: bool = False,
) -> dict[str, Any]:
    if day is None:
        day = datetime.now(TZ)
    season = current_season(season_number)
    season_no = int(season["SeasonNumber"])
    club = resolve_club(season_no, ass_id, lookup_club)
    club_id = str(club["AssID"])
    teams = fetch_teams(season_no, club_id)
    raw_games = fetch_club_games(season_no, club_id, day)
    return build_payload(
        day=day,
        season=season,
        club=club,
        teams=teams,
        raw_games=raw_games,
    )


def classify_status(game_status: int | None) -> str:
    if game_status is None:
        return "unknown"
    if game_status in GAME_STATUS_MAP:
        return GAME_STATUS_MAP[game_status]
    if
