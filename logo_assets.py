"""Mirror verified PNG team crests into the Pages output (stdlib only).

A crest failure never aborts a match update. Cached good files survive upstream
errors; content-addressed names avoid stale browser/PWA images after refresh.
"""
from __future__ import annotations

import hashlib
import json
import time
import urllib.parse
import urllib.request
import zlib
from pathlib import Path
from typing import Any, Callable

from sisu_ottelut import BASE_URL, TEAM_LOGO_BASE, USER_AGENT, logo_url

MAX_IMAGE_BYTES = 1_048_576
REFRESH_SECONDS = 7 * 24 * 60 * 60
ALLOWED_HOSTS = {urllib.parse.urlsplit(BASE_URL).netloc, urllib.parse.urlsplit(TEAM_LOGO_BASE).netloc}


def _valid_png(data: bytes) -> bool:
    header_ok = (
        24 <= len(data) <= MAX_IMAGE_BYTES
        and data[:8] == b"\x89PNG\r\n\x1a\n"
        and data[12:16] == b"IHDR"
        and 0 < int.from_bytes(data[16:20], "big") <= 4096
        and 0 < int.from_bytes(data[20:24], "big") <= 4096
    )
    if not header_ok:
        return False
    offset, has_data = 8, False
    while offset + 12 <= len(data):
        length = int.from_bytes(data[offset:offset + 4], "big")
        end = offset + length + 12
        if end > len(data):
            return False
        kind = data[offset + 4:offset + 8]
        crc = int.from_bytes(data[end - 4:end], "big")
        if zlib.crc32(data[offset + 4:end - 4]) & 0xffffffff != crc:
            return False
        has_data = has_data or (kind == b"IDAT" and length > 0)
        if kind == b"IEND":
            return length == 0 and end == len(data) and has_data
        offset = end
    return False


def _allowed(url: str) -> bool:
    parsed = urllib.parse.urlsplit(url)
    return (parsed.scheme == "https" and parsed.netloc in ALLOWED_HOSTS
            and not parsed.username and parsed.path.endswith(".png"))


def download_png(url: str) -> bytes:
    if not _allowed(url):
        raise ValueError("Unsupported crest URL")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "image/png"})
    with urllib.request.urlopen(req, timeout=8) as response:
        if not _allowed(response.geturl()) or response.status != 200:
            raise ValueError("Unexpected crest response")
        if response.headers.get_content_type() != "image/png":
            raise ValueError("Crest response is not PNG")
        data = response.read(MAX_IMAGE_BYTES + 1)
    if not _valid_png(data):
        raise ValueError("Invalid or oversized PNG")
    return data


def _sides(payload: dict[str, Any]):
    groups = [payload.get(key) or [] for key in ("games", "upcoming", "live", "finished")]
    groups += [day.get("games") or [] for day in payload.get("coming_days") or []]
    for group in groups:
        for game in group:
            for key in ("home", "away"):
                if isinstance(game.get(key), dict):
                    yield game[key]


def localize_logos(payload: dict[str, Any], out_dir: Path, *,
                   downloader: Callable[[str], bytes] = download_png,
                   now: float | None = None) -> dict[str, int]:
    """Prefer team-specific logos, then the SAME association's crest, then initials."""
    now = time.time() if now is None else now
    directory = out_dir / "assets" / "team-logos"
    directory.mkdir(parents=True, exist_ok=True)
    index_file = directory / "index.json"
    try:
        index = json.loads(index_file.read_text(encoding="utf-8"))
        if not isinstance(index, dict):
            index = {}
    except (OSError, ValueError):
        index = {}
    fetched: dict[str, str | None] = {}
    stats = {"requests": 0, "downloaded": 0, "cached": 0, "unavailable": 0}

    def cached_file(entry: Any) -> str | None:
        if not isinstance(entry, dict):
            return None
        name = entry.get("file")
        # Never trust a cache manifest path outside its asset directory.
        if not isinstance(name, str) or len(name) != 68 or not name.endswith(".png"):
            return None
        if any(c not in "0123456789abcdef" for c in name[:-4]):
            return None
        try:
            return name if _valid_png((directory / name).read_bytes()) else None
        except OSError:
            return None

    def mirror(url: str) -> str | None:
        if url in fetched:
            return fetched[url]
        if not _allowed(url):
            fetched[url] = None
            return None
        entry = index.get(url) or {}
        old = cached_file(entry)
        try:
            fresh = old and now - float(entry.get("checked_at", 0)) < REFRESH_SECONDS
        except (TypeError, ValueError):
            fresh = False
        if fresh:
            stats["cached"] += 1
            fetched[url] = old
            return old
        stats["requests"] += 1
        try:
            data = downloader(url)
            if not _valid_png(data):
                raise ValueError("Invalid crest data")
            name = hashlib.sha256(data).hexdigest() + ".png"
            target = directory / name
            if not target.exists():
                temp = target.with_suffix(".tmp")
                temp.write_bytes(data)
                temp.replace(target)
            index[url] = {"file": name, "checked_at": now}
            stats["downloaded"] += 1
        except (OSError, ValueError, TimeoutError):
            name = old
            if old:
                stats["cached"] += 1
            else:
                stats["unavailable"] += 1
        fetched[url] = name
        return name

    for side in _sides(payload):
        external = side.get("logo_external") or side.get("logo")
        if not isinstance(external, str) or not external.startswith("https://"):
            continue
        external = logo_url(external)
        if not external:
            continue
        side["logo"] = external
        side["logo_external"] = external
        local = mirror(external)
        source = "team"
        if not local:
            association = str(side.get("association_id") or "")
            if association.isdigit():
                # The team's OWN club crest, never Sisu for an opponent.
                fallback = TEAM_LOGO_BASE + association + ".png"
                local = mirror(fallback)
                source = "association"
        if local:
            side["logo"] = "assets/team-logos/" + local
            side["logo_source"] = source
        else:
            side["logo_source"] = "external_or_initials"
    temp_index = index_file.with_suffix(".tmp")
    temp_index.write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temp_index.replace(index_file)
    return stats
