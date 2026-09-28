#!/usr/bin/env python3
"""Hae Sisu Hockey Hämeenlinna ry:n ottelut Leijonat-tulospalvelun JSON-APIsta.

Sivusto https://tulospalvelu.leijonat.fi/ on JavaScript-sovellus. Data ei ole
DOM-rakenteessa valmiina vaan ladataan JSON-kutsuilla osoitteesta
https://tulospalvelu.leijonat.fi/helpers/...

Tärkeimmät endpointit (kaikki GET, Accept: application/json):

  /helpers/getseasons
      Kausiluettelo. current=true merkitsee käynnissä olevan kauden
      (SeasonNumber, esim. 2027 = kausi 2026-2027).

  /helpers/getass?season={season}
      Seuraluettelo. Sisu Hockey Hämeenlinna ry: AssID=11015646.

  /helpers/getteams?season={season}&assid={ass_id}
      Seuran joukkueet (TeamID, TeamName).

  /helpers/getextsearchgames?season={season}&Filters[StartDate]=pp.kk.vvvv
      &Filters[EndDate]=pp.kk.vvvv&Filters[AssID]={ass_id}
      &Filters[TeamID]=&Filters[RinkID]=&Filters[GameID]=
      &Filters[Games]=&Filters[GamesTime]=
      Palauttaa seuran kaikkien joukkueiden ottelut aikavälillä.
      Tämä on sama kutsu, jota sivuston sarjahaku käyttää
      (serie/js/ui_2.js -> GetExtSearchGames).

  /helpers/getgames?season=&subSerieId=&teamid=&districtid=&gamedays=&dog=&levelid=
      Päivän/sarjan ottelulista. Pääsivun district-näkymä (did=-1) palauttaa
      vain pääsarjat, ei juniori-/harrasteotteluita. Siksi seuran päivän
      otteluihin käytetään getextsearchgames-kutsua.

  /serie/helpers/search-players-and-teams?season=&playerName=&teamName=Sisu
      Joukkue-/pelaajahaku sarjoihin.

GameStatus: 0 = ei alkanut, 1 = käynnissä, 2 = päättynyt, 94 = päättynyt (erikois).
FinishedType: 1 = varsinainen, 2 = jatkoaika (JA), 3 = voittomaalikilpailu (VL).

Käyttö:
  python3 sisu_ottelut.py
  python3 sisu_ottelut.py --date 2026-09-26
  python3 sisu_ottelut.py --date 03.10.2026 --pretty
"""

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
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
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
                "Accept": "application/json",
                "User-Agent": USER_AGENT,
                "Referer": f"{BASE_URL}/serie?lang=fi",
                "Origin": BASE_URL,
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
    seasons = http_get_json(f"{HELPERS}/getseasons") or []
    if season_override:
        for s in seasons:
            if int(s.get("SeasonNumber") or 0) == season_override:
                return s
        return {"SeasonNumber": season_override, "SeasonName": str(season_override), "current": False}
    for s in seasons:
        if s.get("current"):
            return s
    if seasons:
        return seasons[0]
    raise ApiError("Kausitietoja ei saatu (getseasons).")


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
    # varajärjestelmä, jos seuranimi muuttuu mutta id pysyy
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
    teams = http_get_json(f"{HELPERS}/getteams", {"season": season, "assid": ass_id}) or []
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
    """Hae ja normalisoi päivän ottelut. Käytetään myös HTML-julkaisussa."""
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
    if game_status > 0:
        return "live"
    return "unknown"


def period_scores(summary: Any) -> dict[str, list[Any]] | None:
    if not isinstance(summary, dict):
        return None
    goals = summary.get("PeriodSummary") if "PeriodSummary" in summary else summary
    if not isinstance(goals, dict):
        return None
    period_goals = goals.get("PeriodGoals") or {}
    home = period_goals.get("Home") or []
    away = period_goals.get("Away") or []
    if not home and not away:
        return None
    return {"home": home, "away": away}


def team_side(raw: dict[str, Any], prefix: str) -> dict[str, Any]:
    goals = raw.get(f"{prefix}Goals")
    status = classify_status(raw.get("GameStatus"))
    finished_type = raw.get("FinishedType") or 0
    # Junioriotteluissa GameStatus voi jäädä 0:ksi vaikka tulos on kirjattu.
    show_score = status != "upcoming" or finished_type >= 1 or (
        status == "upcoming" and (raw.get("HomeGoals") or 0) + (raw.get("AwayGoals") or 0) > 0
    )
    score = goals if show_score and goals is not None else None
    return {
        "team_id": raw.get(f"{prefix}Team"),
        "name": raw.get(f"{prefix}TeamName"),
        "abbreviation": raw.get(f"{prefix}Abbrv"),
        "association_id": raw.get(f"{prefix}Association"),
        "logo": (
            f"{BASE_URL}/images/associations/weblogos/200x200/{raw.get(prefix + 'Img')}"
            if raw.get(f"{prefix}Img")
            else None
        ),
        "goals": score,
    }


def normalize_game(raw: dict[str, Any], ass_id: str, teams_by_id: dict[Any, str]) -> dict[str, Any]:
    status_code = raw.get("GameStatus")
    status = classify_status(status_code)
    finished_type = FINISHED_TYPE_MAP.get(raw.get("FinishedType") or 0)
    if status == "upcoming" and (raw.get("FinishedType") or 0) >= 1:
        status = "finished"
    home = team_side(raw, "Home")
    away = team_side(raw, "Away")
    # täydennä joukkueen virallinen nimi seuran joukkuelistasta
    if not home["name"] and home["team_id"] in teams_by_id:
        home["name"] = teams_by_id[home["team_id"]]
    if not away["name"] and away["team_id"] in teams_by_id:
        away["name"] = teams_by_id[away["team_id"]]

    sisu_is_home = str(home.get("association_id")) == str(ass_id)
    sisu_is_away = str(away.get("association_id")) == str(ass_id)
    if sisu_is_home:
        venue = "home"
        sisu_team = home
    elif sisu_is_away:
        venue = "away"
        sisu_team = away
    else:
        venue = "unknown"
        sisu_team = None

    result = None
    if status == "finished" and home["goals"] is not None and away["goals"] is not None:
        result = f"{home['goals']}-{away['goals']}"

    game_id = raw.get("GameID")
    return {
        "game_id": game_id,
        "date": raw.get("GameDate"),
        "time": (raw.get("GameTime") or "")[:5] or None,
        "status": status,
        "status_code": status_code,
        "finished_type": finished_type,
        "level": raw.get("LevelName"),
        "level_id": raw.get("LevelID"),
        "rink": raw.get("RinkName") or raw.get("RinkAbbrv"),
        "rink_id": raw.get("RinkID") or None,
        "small_area": bool(raw.get("SmallAreaGame")),
        "spectators": raw.get("Spectator") or 0,
        "venue": venue,
        "sisu_team": {
            "team_id": sisu_team.get("team_id"),
            "name": sisu_team.get("name"),
            "abbreviation": sisu_team.get("abbreviation"),
        }
        if sisu_team
        else None,
        "home": home,
        "away": away,
        "score": result,
        "period_scores": period_scores(raw),
        "urls": {
            "gamecentre": f"{BASE_URL}/game?gameid={game_id}",
        },
        "denied_results": bool(raw.get("DeniedResults")),
        "denied_stats": bool(raw.get("DeniedStats")),
    }


def build_payload(
    *,
    day: datetime,
    season: dict[str, Any],
    club: dict[str, Any],
    teams: list[dict[str, Any]],
    raw_games: list[dict[str, Any]],
) -> dict[str, Any]:
    ass_id = str(club.get("AssID"))
    teams_by_id = {t["team_id"]: t["name"] for t in teams}
    games = [normalize_game(g, ass_id, teams_by_id) for g in raw_games]
    games.sort(key=lambda g: (g.get("time") or "", g.get("game_id") or 0))

    upcoming = [g for g in games if g["status"] == "upcoming"]
    live = [g for g in games if g["status"] == "live"]
    finished = [g for g in games if g["status"] == "finished"]
    other = [g for g in games if g["status"] not in {"upcoming", "live", "finished"}]

    return {
        "generated_at": datetime.now(TZ).isoformat(timespec="seconds"),
        "date": iso_date(day),
        "date_fi": fi_date(day),
        "club": {
            "id": ass_id,
            "name": " ".join((club.get("AssName") or "").split()),
            "abbreviation": club.get("AssAbbrv"),
            "city": club.get("AssCity"),
            "web": club.get("AssWeb") or None,
        },
        "season": {
            "number": season.get("SeasonNumber"),
            "name": season.get("SeasonName"),
            "current": bool(season.get("current")),
        },
        "source": {
            "site": BASE_URL,
            "endpoint": f"{HELPERS}/getextsearchgames",
            "format": "json",
        },
        "counts": {
            "total": len(games),
            "upcoming": len(upcoming),
            "live": len(live),
            "finished": len(finished),
            "other": len(other),
            "teams": len(teams),
        },
        "games": games,
        "upcoming": upcoming,
        "live": live,
        "finished": finished,
        "teams": teams,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Palauta Sisu Hockey Hämeenlinna ry:n päivän ottelut JSON-muodossa."
    )
    p.add_argument(
        "--date",
        help="Päivä YYYY-MM-DD tai DD.MM.YYYY (oletus: kuluva Helsinki-päivä).",
    )
    p.add_argument("--season", type=int, help="Kausinumero (oletus: käynnissä oleva kausi).")
    p.add_argument(
        "--pretty",
        action="store_true",
        help="Sisennetty JSON (oletus, jos stdout on TTY).",
    )
    p.add_argument(
        "--compact",
        action="store_true",
        help="Yhden rivin JSON.",
    )
    p.add_argument(
        "--ass-id",
        default=DEFAULT_ASS_ID,
        help=f"Seuran AssID (oletus: {DEFAULT_ASS_ID} = Sisu Hockey Hämeenlinna ry).",
    )
    p.add_argument(
        "--lookup-club",
        action="store_true",
        help="Hae seura nimellä getass-listasta (hitaampi, varmistaa AssID:n).",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    day = parse_date(args.date)
    try:
        payload = fetch_payload(
            day,
            season_number=args.season,
            ass_id=args.ass_id,
            lookup_club=args.lookup_club,
        )
    except ApiError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1

    pretty = args.pretty or (sys.stdout.isatty() and not args.compact)
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2 if pretty else None)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
