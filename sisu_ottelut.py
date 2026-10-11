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
PROXY_URL = "https://leijonat-proxy.jeolehto.workers.dev"
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
    if PROXY_URL:
        url = f"{PROXY_URL.rstrip('/')}/?{urllib.parse.urlencode({'url': url})}"
    last_error: Exception | None = None
    for attempt in range(4):
        req = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Accept-Language": "fi-FI,fi;q=0.9,en-US;q=0.8,en;q=0.7",
                "User-Agent": USER_AGENT,
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


def
