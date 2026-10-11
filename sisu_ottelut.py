#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, sys, time, urllib.error, urllib.parse, urllib.request
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

BASE_URL = "https://tulospalvelu.leijonat.fi"
HELPERS = f"{BASE_URL}/helpers"
PROXY_URL = "https://leijonat-proxy.jeolehto.workers.dev"
TZ = ZoneInfo("Europe/Helsinki")
CLUB_NAME_NEEDLE = "SISU HOCKEY HÄMEENLINNA"
DEFAULT_ASS_ID = "11015646"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"

DEFAULT_CLUB = {
    "AssID": DEFAULT_ASS_ID,
    "AssName": "SISU HOCKEY HÄMEENLINNA  RY",
    "AssAbbrv": "SiSu",
    "AssCity": "HÄMEENLINNA",
    "AssWeb": "www.sisuhockey.fi",
}

GAME_STATUS_MAP = {0: "upcoming", 1: "live", 2: "finished", 94: "finished"}
FINISHED_TYPE_MAP = {0: None, 1: "regulation", 2: "overtime", 3: "shootout"}
NO_SCORE_DURATION_MIN = 50

class ApiError(RuntimeError):
    pass

def http_get_json(url: str, params: dict[str, Any] | None = None, timeout: int = 45) -> Any:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params, doseq=True)}"
    if PROXY_URL:
        url = f"{PROXY_URL.rstrip('/')}/?{urllib.parse.urlencode({'url': url})}"
    last_error: Exception | None = None
    for attempt in range(4):
        req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
            if not raw:
                return None
            return json.loads(raw.decode("utf-8"))
        except Exception as exc:
            last_error = ApiError(f"Virhe haussa {url}: {exc}")
            if attempt < 3:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise last_error from exc
    raise last_error or ApiError(url)

def parse_date(value: str | None) -> datetime:
    if not value:
        return datetime.now(TZ)
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d.%m.%y"):
        try:
            return datetime.strptime(value.strip(), fmt).replace(tzinfo=TZ)
        except ValueError:
            continue
    raise SystemExit(f"Virheellinen päiväys: {value!r}")

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
        pass
    return {"SeasonNumber": 2027, "SeasonName": "2026-2027", "current": True}

def resolve_club(season: int, ass_id: str | None, lookup: bool) -> dict[str, Any]:
    if ass_id and str(ass_id) != DEFAULT_ASS_ID:
        return {"AssID": str(ass_id), "AssName": CLUB_NAME_NEEDLE, "AssAbbrv": "SiSu", "AssCity": None, "AssWeb": None}
    return dict(DEFAULT_CLUB)

def fetch_teams(season: int, ass_id: str) -> list[dict[str, Any]]:
    try:
        teams = http_get_json(f"{HELPERS}/getteams", {"season": season, "assid": ass_id}) or []
    except ApiError:
        teams = []
    return [{"team_id": t.get("TeamID"), "name": (t.get("TeamName") or "").strip()} for t in teams]

def fetch_club_games(season: int, ass_id: str, day: datetime) -> list[dict[str, Any]]:
    d = fi_date(day)
    params = {"season": season, "Filters[StartDate]": d, "Filters[EndDate]": d, "Filters[GameID]": "", "Filters[AssID]": ass_id, "Filters[TeamID]": "", "Filters[RinkID]": "", "Filters[Games]": "", "Filters[GamesTime]": ""}
    return http_get_json(f"{HELPERS}/getextsearchgames", params) or []

def fetch_club_games_range(season: int, ass_id: str, start: datetime, end: datetime) -> list[dict[str, Any]]:
    params = {"season": season, "Filters[StartDate]": fi_date(start), "Filters[EndDate]": fi_date(end), "Filters[GameID]": "", "Filters[AssID]": ass_id, "Filters[TeamID]": "", "Filters[RinkID]": "", "Filters[Games]": "", "Filters[GamesTime]": ""}
    return http_get_json(f"{HELPERS}/getextsearchgames", params) or []

def classify_status(game_status: int | None) -> str:
    if game_status is None:
        return "unknown"
    if game_status in GAME_STATUS_MAP:
        return GAME_STATUS_MAP[game_status]
    return "live" if game_status > 0 else "unknown"

def period_scores(summary: Any) -> dict[str, list[Any]] | None:
    if not isinstance(summary, dict):
        return None
    goals = summary.get("PeriodSummary") if "PeriodSummary" in summary else summary
    if not isinstance(goals, dict):
        return None
    pg = goals.get("PeriodGoals") or {}
    home, away = pg.get("Home") or [], pg.get("Away") or []
    return {"home": home, "away": away} if (home or away) else None

def team_side(raw: dict[str, Any], prefix: str, show_score: bool) -> dict[str, Any]:
    goals = raw.get(f"{prefix}Goals")
    score = goals if show_score and goals is not None else None
    img = raw.get(f"{prefix}Img")
    logo = f"{BASE_URL}/images/associations/weblogos/200x200/{img}" if img else None
    return {"team_id": raw.get(f"{prefix}Team"), "name": raw.get(f"{prefix}TeamName"), "abbreviation": raw.get(f"{prefix}Abbrv"), "association_id": raw.get(f"{prefix}Association"), "logo": logo, "goals": score}

def normalize_game(raw: dict[str, Any], ass_id: str, teams_by_id: dict[Any, str], day: datetime | None = None) -> dict[str, Any]:
    status_code = raw.get("GameStatus")
    status = classify_status(status_code)
    ft = FINISHED_TYPE_MAP.get(raw.get("FinishedType") or 0)
    if status == "upcoming" and (raw.get("FinishedType") or 0) >= 1:
        status = "finished"

    level = raw.get("LevelName") or ""
    lvl_low = level.casefold()
    small_area = bool(raw.get("SmallAreaGame"))
    denied_results = bool(raw.get("DeniedResults"))
    no_score_tracking = denied_results or small_area or ("leijonaliiga" in lvl_low)

    time_str = (raw.get("GameTime") or "").strip()[:5].replace(".", ":") or None
    date_str = (raw.get("GameDate") or "").strip()
    if status == "upcoming" and no_score_tracking and time_str:
        try:
            base_day = day
            if date_str:
                for dfmt in ("%Y-%m-%d", "%d.%m.%Y", "%d.%m.%y"):
                    try:
                        base_day = datetime.strptime(date_str, dfmt).replace(tzinfo=TZ)
                        break
                    except ValueError:
                        continue
            if base_day is not None:
                hh, mm = (int(x) for x in time_str.split(":", 1))
                start_dt = base_day.replace(hour=hh, minute=mm, second=0, microsecond=0, tzinfo=TZ)
                elapsed_min = (datetime.now(TZ) - start_dt).total_seconds() / 60.0
                if 0 <= elapsed_min < NO_SCORE_DURATION_MIN:
                    status = "live"
                elif elapsed_min >= NO_SCORE_DURATION_MIN:
                    status = "finished"
        except Exception:
            pass

    has_goals = (raw.get("HomeGoals") or 0) + (raw.get("AwayGoals") or 0) > 0
    show_score = (not no_score_tracking) and (status != "upcoming" or (raw.get("FinishedType") or 0) >= 1 or has_goals)
    home, away = team_side(raw, "Home", show_score), team_side(raw, "Away", show_score)
    if not home["name"] and home["team_id"] in teams_by_id:
        home["name"] = teams_by_id[home["team_id"]]
    if not away["name"] and away["team_id"] in teams_by_id:
        away["name"] = teams_by_id[away["team_id"]]
    if str(home.get("association_id")) == str(ass_id):
        venue, sisu_team = "home", home
    elif str(away.get("association_id")) == str(ass_id):
        venue, sisu_team = "away", away
    else:
        venue, sisu_team = "unknown", None
    result = f"{home['goals']}-{away['goals']}" if (status == "finished" and home["goals"] is not None and away["goals"] is not None) else None
    sisu_info = {"team_id": sisu_team.get("team_id"), "name": sisu_team.get("name"), "abbreviation": sisu_team.get("abbreviation")} if sisu_team else None
    game_id = raw.get("GameID")
    return {
        "game_id": game_id, "date": date_str, "time": time_str,
        "status": status, "status_code": status_code, "finished_type": ft, "level": level,
        "level_id": raw.get("LevelID"), "rink": raw.get("RinkName") or raw.get("RinkAbbrv"),
        "rink_id": raw.get("RinkID") or None, "small_area": small_area,
        "spectators": raw.get("Spectator") or 0, "venue": venue, "sisu_team": sisu_info,
        "home": home, "away": away, "score": result, "period_scores": period_scores(raw),
        "urls": {"gamecentre": f"{BASE_URL}/game?gameid={game_id}"},
        "denied_results": denied_results, "denied_stats": bool(raw.get("DeniedStats")),
        "no_score_tracking": no_score_tracking,
    }

def build_payload(*, day: datetime, season: dict[str, Any], club: dict[str, Any], teams: list[dict[str, Any]], raw_games: list[dict[str, Any]]) -> dict[str, Any]:
    ass_id = str(club.get("AssID"))
    teams_by_id = {t["team_id"]: t["name"] for t in teams}
    games = [normalize_game(g, ass_id, teams_by_id, day=day) for g in raw_games]
    games.sort(key=lambda g: (g.get("time") or "", g.get("game_id") or 0))
    upcoming = [g for g in games if g["status"] == "upcoming"]
    live = [g for g in games if g["status"] == "live"]
    finished = [g for g in games if g["status"] == "finished"]
    other = [g for g in games if g["status"] not in {"upcoming", "live", "finished"}]
    return {
        "generated_at": datetime.now(TZ).isoformat(timespec="seconds"), "date": iso_date(day), "date_fi": fi_date(day),
        "club": {"id": ass_id, "name": " ".join((club.get("AssName") or "").split()), "abbreviation": club.get("AssAbbrv"), "city": club.get("AssCity"), "web": club.get("AssWeb") or None},
        "season": {"number": season.get("SeasonNumber"), "name": season.get("SeasonName"), "current": bool(season.get("current"))},
        "source": {"site": BASE_URL, "endpoint": f"{HELPERS}/getextsearchgames", "format": "json"},
        "counts": {"total": len(games), "upcoming": len(upcoming), "live": len(live), "finished": len(finished), "other": len(other), "teams": len(teams)},
        "games": games, "upcoming": upcoming, "live": live, "finished": finished, "teams": teams,
    }

def fetch_payload(day: datetime | None = None, *, season_number: int | None = None, ass_id: str = DEFAULT_ASS_ID, lookup_club: bool = False) -> dict[str, Any]:
    day = day or datetime.now(TZ)
    season = current_season(season_number)
    season_no = int(season["SeasonNumber"])
    club = resolve_club(season_no, ass_id, lookup_club)
    club_id = str(club["AssID"])
    return build_payload(day=day, season=season, club=club, teams=fetch_teams(season_no, club_id), raw_games=fetch_club_games(season_no, club_id, day))

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--date")
    p.add_argument("--season", type=int)
    p.add_argument("--pretty", action="store_true")
    p.add_argument("--compact", action="store_true")
    p.add_argument("--ass-id", default=DEFAULT_ASS_ID)
    p.add_argument("--lookup-club", action="store_true")
    args = p.parse_args(argv)
    try:
        payload = fetch_payload(parse_date(args.date), season_number=args.season, ass_id=args.ass_id, lookup_club=args.lookup_club)
    except ApiError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    pretty = args.pretty or (sys.stdout.isatty() and not args.compact)
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2 if pretty else None)
    sys.stdout.write("\n")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
