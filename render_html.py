#!/usr/bin/env python3
"""Renderöi Sisu Hockeyn otteludata tyylikkääksi, mobiiliresponsiiviseksi HTML:ksi."""

from __future__ import annotations

import html
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Helsinki")

WEEKDAYS_FI = (
    "maanantai",
    "tiistai",
    "keskiviikko",
    "torstai",
    "perjantai",
    "lauantai",
    "sunnuntai",
)

STATUS_LABEL = {
    "upcoming": "Tulossa",
    "live": "Käynnissä",
    "finished": "Päättynyt",
    "unknown": "—",
}

VENUE_LABEL = {
    "home": "Koti",
    "away": "Vieras",
    "unknown": "",
}

FINISHED_FI = {
    "regulation": "",
    "overtime": "JA",
    "shootout": "VL",
}


def _e(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _parse_iso_date(value: str) -> datetime | None:
    try:
        return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=TZ)
    except (TypeError, ValueError):
        return None


def _human_date(iso: str, fi: str | None = None) -> str:
    dt = _parse_iso_date(iso)
    if dt:
        return f"{WEEKDAYS_FI[dt.weekday()]} {dt.strftime('%-d.%-m.%Y')}"
    return fi or iso or ""


def _sisu_result(game: dict[str, Any]) -> str | None:
    if game.get("status") != "finished":
        return None
    home = (game.get("home") or {}).get("goals")
    away = (game.get("away") or {}).get("goals")
    if home is None or away is None:
        return None
    venue = game.get("venue")
    if venue == "home":
        sisu, opp = home, away
    elif venue == "away":
        sisu, opp = away, home
    else:
        return None
    if sisu > opp:
        return "win"
    if sisu < opp:
        return "loss"
    return "tie"


def _team_label(side: dict[str, Any] | None) -> str:
    side = side or {}
    return side.get("abbreviation") or side.get("name") or "—"


def _logo(side: dict[str, Any] | None) -> str:
    side = side or {}
    url = side.get("logo") or ""
    name = _team_label(side)
    if url:
        return (
            f'<img class="crest" src="{_e(url)}" alt="{_e(name)}" '
            'width="40" height="40" loading="lazy">'
        )
    return f'<span class="crest crest-fallback">{_e(name[:2].upper())}</span>'


def _score_block(game: dict[str, Any]) -> str:
    status = game.get("status")
    home = (game.get("home") or {}).get("goals")
    away = (game.get("away") or {}).get("goals")
    extra = FINISHED_FI.get(game.get("finished_type") or "", "") or ""
    extra_html = f'<span class="extra">{_e(extra)}</span>' if extra else ""
    if status == "live":
        hs = "—" if home is None else home
        aws = "—" if away is None else away
        return (
            f'<div class="score live"><span class="num">{_e(hs)}</span>'
            f'<span class="sep">–</span><span class="num">{_e(aws)}</span>{extra_html}</div>'
        )
    if status == "finished" and home is not None and away is not None:
        return (
            f'<div class="score done"><span class="num">{_e(home)}</span>'
            f'<span class="sep">–</span><span class="num">{_e(away)}</span>{extra_html}</div>'
        )
    time = game.get("time") or "—"
    return f'<div class="score wait"><span class="kickoff">{_e(time)}</span></div>'


def _game_card(game: dict[str, Any]) -> str:
    status = game.get("status") or "unknown"
    result = _sisu_result(game)
    venue = game.get("venue") or "unknown"
    sisu = game.get("sisu_team") or {}
    level = game.get("level") or ""
    rink = game.get("rink") or ""
    small = " · pieni kaukalo" if game.get("small_area") else ""
    spectators = game.get("spectators") or 0
    url = ((game.get("urls") or {}).get("gamecentre")) or "#"
    result_class = f" result-{result}" if result else ""
    sisu_name = sisu.get("abbreviation") or sisu.get("name") or "Sisu"
    meta_bits = [bit for bit in (level, rink + small) if bit]
    if spectators and status == "finished":
        meta_bits.append(f"{spectators} katsojaa")

    return f"""
<article class="card status-{_e(status)}{_e(result_class)}">
  <a class="card-link" href="{_e(url)}" target="_blank" rel="noopener">
    <header class="card-top">
      <span class="badge badge-{_e(status)}">{_e(STATUS_LABEL.get(status, status))}</span>
      <span class="time">{_e(game.get("time") or "—")}</span>
      <span class="venue venue-{_e(venue)}">{_e(VENUE_LABEL.get(venue, ""))}</span>
    </header>
    <p class="sisu-line">{_e(sisu_name)}</p>
    <div class="match">
      <div class="team home">
        {_logo(game.get("home"))}
        <span class="tname">{_e(_team_label(game.get("home")))}</span>
      </div>
      {_score_block(game)}
      <div class="team away">
        {_logo(game.get("away"))}
        <span class="tname">{_e(_team_label(game.get("away")))}</span>
      </div>
    </div>
    <p class="meta">{_e(" · ".join(meta_bits))}</p>
  </a>
</article>
"""


def _chip(label: str, count: int, kind: str) -> str:
    return (
        f'<div class="chip chip-{_e(kind)}"><span class="chip-n">{count}</span>'
        f'<span class="chip-l">{_e(label)}</span></div>'
    )


def _section(title: str, games: list[dict[str, Any]], empty: str) -> str:
    if not games:
        return (
            f'<section class="block"><h2>{_e(title)}</h2>'
            f'<p class="empty">{_e(empty)}</p></section>'
        )
    cards = "\n".join(_game_card(g) for g in games)
    return f'<section class="block"><h2>{_e(title)}</h2><div class="grid">{cards}</div></section>'


def render_html(payload: dict[str, Any], extra_days: list[dict[str, Any]] | None = None) -> str:
    extra_days = extra_days or payload.get("coming_days") or []
    club = payload.get("club") or {}
    counts = payload.get("counts") or {}
    season = payload.get("season") or {}
    generated = payload.get("generated_at") or datetime.now(TZ).isoformat(timespec="seconds")
    date_iso = payload.get("date") or ""
    heading_date = _human_date(date_iso, payload.get("date_fi"))
    club_name = club.get("name") or "Sisu Hockey Hämeenlinna ry"

    live = payload.get("live") or []
    upcoming = payload.get("upcoming") or []
    finished = payload.get("finished") or []
    games = payload.get("games") or []

    if live:
        primary_title = "Käynnissä"
        primary_games = live
        rest_upcoming = upcoming
        rest_finished = finished
    elif upcoming and not finished:
        primary_title = "Päivän ottelut"
        primary_games = upcoming
        rest_upcoming = []
        rest_finished = []
    elif finished and not upcoming and not live:
        primary_title = "Päivän tulokset"
        primary_games = finished
        rest_upcoming = []
        rest_finished = []
    else:
        primary_title = "Päivän ottelut"
        primary_games = games
        rest_upcoming = []
        rest_finished = []

    extra_html = []
    for day in extra_days:
        day_games = day.get("games") or []
        if not day_games:
            continue
        label = _human_date(day.get("date", ""), day.get("date_fi"))
        extra_html.append(
            f'<section class="block muted"><h2>{_e(label)}</h2>'
            f'<div class="grid">{"".join(_game_card(g) for g in day_games)}</div></section>'
        )

    empty_today = not games
    empty_msg = (
        "Tänään Sisu Hockeylla ei ole merkittyjä otteluita."
        if empty_today
        else "Ei otteluita tässä osiossa."
    )

    next_block = "\n".join(extra_html)
    next_heading = (
        '<section class="block"><h2>Seuraavat pelipäivät</h2></section>'
        if extra_html and empty_today
        else ""
    )

    generated_human = generated.replace("T", " ")[:16]

    return f"""<!DOCTYPE html>
<html lang="fi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Sisu Hockey – päivän ottelut</title>
  <meta name="description" content="Sisu Hockey Hämeenlinna ry:n päivän ottelut ja tulokset.">
  <meta name="theme-color" content="#8b1a16">
  <link rel="icon" href="assets/logo.png">
  <style>
    :root {{
      --red: #e3302c;
      --red-dark: #8b1a16;
      --ice: #f4f7fb;
      --ink: #12151c;
      --muted: #5b6573;
      --card: #ffffff;
      --line: #e4e9f0;
      --live: #0b8a4a;
      --loss: #8a2430;
      --win: #1f7a4d;
      --shadow: 0 10px 30px rgba(18, 21, 28, .08);
    }}
    * {{ box-sizing: border-box; }}
    html, body {{ margin: 0; padding: 0; }}
    body {{
      font-family: "Segoe UI", system-ui, -apple-system, sans-serif;
      color: var(--ink);
      background:
        radial-gradient(1200px 500px at 10% -10%, rgba(227,48,44,.18), transparent 55%),
        linear-gradient(180deg, #f8fafc 0%, #eef2f7 100%);
      min-height: 100vh;
    }}
    .hero {{
      background: linear-gradient(135deg, #6d1410 0%, #c62823 55%, #e3302c 100%);
      color: #fff;
      padding: 1.4rem 1.1rem 1.7rem;
      box-shadow: 0 8px 24px rgba(139, 26, 22, .28);
    }}
    .hero-inner {{
      max-width: 920px;
      margin: 0 auto;
      display: flex;
      gap: 1rem;
      align-items: center;
    }}
    .hero img {{
      width: 64px; height: 64px;
      background: #fff; border-radius: 16px; padding: 4px;
    }}
    .hero h1 {{
      font-size: 1.35rem; margin: 0 0 .15rem; letter-spacing: .01em;
      text-transform: uppercase;
    }}
    .hero p {{ margin: 0; opacity: .92; font-size: .95rem; }}
    main {{ max-width: 920px; margin: 0 auto; padding: 1rem 1rem 3rem; }}
    .chips {{
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: .6rem;
      margin: -1.4rem 0 1.2rem;
    }}
    .chip {{
      background: var(--card);
      border-radius: 14px;
      padding: .7rem .55rem;
      text-align: center;
      box-shadow: var(--shadow);
      border: 1px solid var(--line);
    }}
    .chip-n {{ display: block; font-size: 1.25rem; font-weight: 800; }}
    .chip-l {{ font-size: .72rem; color: var(--muted); text-transform: uppercase; letter-spacing: .04em; }}
    .chip-live .chip-n {{ color: var(--live); }}
    .chip-finished .chip-n {{ color: var(--red); }}
    .block {{ margin: 1.4rem 0; }}
    .block h2 {{
      margin: 0 0 .8rem;
      font-size: 1.02rem;
      text-transform: uppercase;
      letter-spacing: .08em;
      color: var(--red-dark);
    }}
    .grid {{ display: grid; gap: .85rem; }}
    .card {{
      background: var(--card);
      border-radius: 18px;
      box-shadow: var(--shadow);
      border: 1px solid var(--line);
      overflow: hidden;
    }}
    .card.status-live {{ border-color: #9fe0bc; box-shadow: 0 8px 24px rgba(11,138,74,.16); }}
    .card.result-win {{ border-left: 5px solid var(--win); }}
    .card.result-loss {{ border-left: 5px solid var(--red); }}
    .card.result-tie {{ border-left: 5px solid #c9a227; }}
    .card-link {{ display: block; color: inherit; text-decoration: none; padding: .95rem 1rem 1rem; }}
    .card-top {{
      display: flex; align-items: center; gap: .5rem;
      font-size: .8rem; color: var(--muted); margin-bottom: .35rem;
    }}
    .badge {{
      border-radius: 999px; padding: .15rem .55rem;
      font-weight: 700; letter-spacing: .04em; text-transform: uppercase;
      font-size: .68rem; background: #eef2f7; color: #445;
    }}
    .badge-live {{ background: #d9f6e5; color: #0b8a4a; animation: pulse 1.6s ease-in-out infinite; }}
    .badge-upcoming {{ background: #e8eefc; color: #2b4ea2; }}
    .badge-finished {{ background: #fde8e7; color: #b42318; }}
    .time {{ margin-left: auto; font-variant-numeric: tabular-nums; font-weight: 700; color: var(--ink); }}
    .venue {{ border: 1px solid var(--line); border-radius: 999px; padding: .1rem .5rem; }}
    .venue-home {{ background: #fff4f3; border-color: #f3c7c5; color: var(--red-dark); }}
    .sisu-line {{
      margin: 0 0 .55rem; font-size: .8rem; color: var(--muted);
    }}
    .match {{
      display: grid;
      grid-template-columns: 1fr auto 1fr;
      gap: .6rem;
      align-items: center;
    }}
    .team {{ display: flex; flex-direction: column; align-items: center; gap: .35rem; text-align: center; }}
    .tname {{ font-weight: 700; font-size: .92rem; line-height: 1.2; }}
    .crest {{ width: 40px; height: 40px; object-fit: contain; border-radius: 50%; background: #fff; }}
    .crest-fallback {{
      width: 40px; height: 40px; border-radius: 50%; display: grid; place-items: center;
      background: #f3f5f8; font-size: .75rem; font-weight: 800;
    }}
    .score {{
      min-width: 92px; text-align: center;
      font-variant-numeric: tabular-nums;
    }}
    .score .num {{ font-size: 1.7rem; font-weight: 800; }}
    .score .sep {{ margin: 0 .15rem; color: var(--muted); font-size: 1.3rem; }}
    .score.wait .kickoff {{ font-size: 1.25rem; font-weight: 800; }}
    .score.live .num {{ color: var(--live); }}
    .extra {{ display: block; font-size: .7rem; color: var(--muted); font-weight: 700; }}
    .meta {{ margin: .7rem 0 0; color: var(--muted); font-size: .8rem; }}
    .empty {{
      background: var(--card); border-radius: 16px; padding: 1.2rem;
      color: var(--muted); box-shadow: var(--shadow);
    }}
    footer {{
      max-width: 920px; margin: 0 auto; padding: 0 1rem 2.5rem;
      color: var(--muted); font-size: .8rem;
    }}
    footer a {{ color: var(--red-dark); }}
    @keyframes pulse {{
      0%, 100% {{ opacity: 1; }}
      50% {{ opacity: .55; }}
    }}
    @media (max-width: 560px) {{
      .chips {{ grid-template-columns: repeat(2, 1fr); }}
      .hero h1 {{ font-size: 1.15rem; }}
      .tname {{ font-size: .84rem; }}
      .score .num {{ font-size: 1.45rem; }}
    }}
  </style>
</head>
<body>
  <header class="hero">
    <div class="hero-inner">
      <img src="assets/logo.png" alt="Sisu Hockey" width="64" height="64">
      <div>
        <h1>Sisu Hockey</h1>
        <p>{_e(heading_date)} · {_e(club_name)}</p>
      </div>
    </div>
  </header>
  <main>
    <div class="chips">
      {_chip("Ottelut", int(counts.get("total") or 0), "total")}
      {_chip("Tulossa", int(counts.get("upcoming") or 0), "upcoming")}
      {_chip("Käynnissä", int(counts.get("live") or 0), "live")}
      {_chip("Päättynyt", int(counts.get("finished") or 0), "finished")}
    </div>
    {_section(primary_title, primary_games, empty_msg)}
    {_section("Vielä pelaamatta", rest_upcoming, "") if rest_upcoming else ""}
    {_section("Valmistuneet", rest_finished, "") if rest_finished else ""}
    {next_heading}
    {next_block}
  </main>
  <footer>
    Päivitetty {_e(generated_human)} (Helsinki) · kausi {_e(season.get("name") or "")}.
    Lähde: <a href="https://tulospalvelu.leijonat.fi/">tulospalvelu.leijonat.fi</a>.
    JSON: <a href="games.json">games.json</a>.
  </footer>
</body>
</html>
"""
