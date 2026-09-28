#!/usr/bin/env python3
"""Hae Sisu Hockeyn ottelut, kirjoita HTML + JSON julkaisuhakemistoon.

Käyttö:
  python3 publish.py --out docs
  python3 publish.py --date 2026-10-03 --out /tmp/site
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from render_html import render_html
from sisu_ottelut import (
    DEFAULT_ASS_ID,
    TZ,
    ApiError,
    fetch_club_games_range,
    fetch_payload,
    iso_date,
    normalize_game,
    parse_date,
)

ROOT = Path(__file__).resolve().parent
COMING_DAYS = 10


def parse_game_date(raw: dict[str, Any]) -> str | None:
    value = raw.get("GameDate") or ""
    for fmt in ("%d.%m.%Y", "%d.%m.%y"):
        try:
            return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def upcoming_days(payload: dict[str, Any], coming: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ryhmitä seuraavien päivien ottelut (ei kuluva päivä)."""
    today = payload.get("date")
    teams_by_id = {t["team_id"]: t["name"] for t in payload.get("teams") or []}
    ass_id = (payload.get("club") or {}).get("id")
    by_day: dict[str, list[dict[str, Any]]] = {}
    for raw in coming:
        day = parse_game_date(raw)
        if not day or day == today:
            continue
        by_day.setdefault(day, []).append(normalize_game(raw, ass_id, teams_by_id))
    days = []
    for day in sorted(by_day):
        games = sorted(by_day[day], key=lambda g: (g.get("time") or "", g.get("game_id") or 0))
        dt = datetime.strptime(day, "%Y-%m-%d")
        days.append(
            {
                "date": day,
                "date_fi": dt.strftime("%d.%m.%Y"),
                "games": games,
            }
        )
    return days


def build_site_payload(day: datetime, lookup_club: bool = False) -> dict[str, Any]:
    payload = fetch_payload(day, lookup_club=lookup_club)
    season_no = int((payload.get("season") or {}).get("number") or 0)
    ass_id = str((payload.get("club") or {}).get("id") or DEFAULT_ASS_ID)
    end = day + timedelta(days=COMING_DAYS)
    coming_raw = fetch_club_games_range(season_no, ass_id, day + timedelta(days=1), end)
    payload["coming_days"] = upcoming_days(payload, coming_raw)
    return payload


def write_site(payload: dict[str, Any], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    assets_src = ROOT / "assets"
    assets_dst = out_dir / "assets"
    if assets_src.exists():
        assets_dst.mkdir(parents=True, exist_ok=True)
        for item in assets_src.iterdir():
            if item.is_file():
                shutil.copy2(item, assets_dst / item.name)
    html = render_html(payload)
    (out_dir / "index.html").write_text(html, encoding="utf-8")
    (out_dir / "games.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (out_dir / "latest.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    date = payload.get("date") or iso_date(datetime.now(TZ))
    archive = out_dir / "archive"
    archive.mkdir(exist_ok=True)
    (archive / f"{date}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Julkaise Sisu Hockeyn päivän ottelut HTML+JSON.")
    p.add_argument("--date", help="Päivä YYYY-MM-DD (oletus: tänään).")
    p.add_argument("--out", default="docs", help="Julkaisuhakemisto (oletus: docs).")
    p.add_argument("--lookup-club", action="store_true")
    args = p.parse_args(argv)
    day = parse_date(args.date)
    try:
        payload = build_site_payload(day, lookup_club=args.lookup_club)
    except ApiError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    out = Path(args.out)
    write_site(payload, out)
    print(
        f"Kirjoitettu {out}/index.html ja {out}/games.json "
        f"({payload['counts']['total']} ottelua {payload['date']})",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
