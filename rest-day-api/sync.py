#!/usr/bin/env python3
"""Sync government-announced China holidays without installing dependencies.

The upstream data automatically tracks State Council (gov.cn) releases.
Unpublished placeholder years (empty papers/days) are rejected rather than guessed.
GitHub Actions invokes this daily, including every December 31.
"""
from __future__ import annotations

from datetime import datetime, date, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from urllib.request import Request, urlopen
from urllib.parse import urlsplit
import json
import os

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "data"
SOURCES = (
    "https://raw.githubusercontent.com/NateScarlet/holiday-cn/master/",
    "https://cdn.jsdelivr.net/gh/NateScarlet/holiday-cn@master/",
)
TIMEZONE = ZoneInfo("Asia/Shanghai")


def valid_calendar(payload: object, year: int) -> bool:
    if not isinstance(payload, dict) or payload.get("year") != year:
        return False
    papers, days = payload.get("papers"), payload.get("days")
    if not isinstance(papers, list) or not papers or not all(
        isinstance(p, str)
        and urlsplit(p).scheme == "https"
        and (
            urlsplit(p).hostname == "gov.cn"
            or (urlsplit(p).hostname or "").endswith(".gov.cn")
        )
        for p in papers
    ):
        return False
    if not isinstance(days, list) or not 25 <= len(days) <= 400:
        return False

    unique = set()
    off_days = 0
    makeup = 0
    for item in days:
        if not isinstance(item, dict):
            return False
        d = item.get("date")
        if not isinstance(d, str):
            return False
        try:
            parsed = date.fromisoformat(d)
        except ValueError:
            return False
        if parsed.isoformat() != d or abs(parsed.year - year) > 1 or d in unique:
            return False
        unique.add(d)
        if not isinstance(item.get("name"), str) or not item["name"].strip() or len(item["name"]) > 60:
            return False
        flag = item.get("isOffDay")
        if type(flag) is not bool:
            return False
        off_days += flag
        makeup += not flag

    if off_days < 20 or makeup < 1:
        return False
    for d in (f"{year}-01-01", f"{year}-05-01", f"{year}-10-01"):
        if not any(x["date"] == d and x["isOffDay"] for x in days):
            return False
    return True


def download(year: int) -> dict | None:
    for base in SOURCES:
        try:
            req = Request(
                base + f"{year}.json",
                headers={"User-Agent": "CN-RestDay-Shortcuts/2.0", "Accept": "application/json"},
            )
            with urlopen(req, timeout=12) as response:
                content = response.read(300_000)
            obj = json.loads(content)
            if valid_calendar(obj, year):
                return {
                    "year": year,
                    "papers": obj["papers"],
                    "days": [
                        {"date": x["date"], "name": x["name"], "isOffDay": x["isOffDay"]}
                        for x in obj["days"]
                    ],
                    "from": "holiday-cn",
                }
        except Exception as exc:
            print(f"Download {year} failed ({base}): {exc}")
    return None


def write_if_changed(path: Path, obj: dict) -> bool:
    content = json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def run(now: datetime | None = None) -> dict[int, bool]:
    now = now or datetime.now(timezone.utc).astimezone(TIMEZONE)
    years = [now.year]
    if now.month >= 9:
        years.append(now.year + 1)
    if now.month == 1:
        years.append(now.year - 1)
    outcome: dict[int, bool] = {}
    for year in years:
        if year < 2026:
            continue
        obj = download(year)
        outcome[year] = obj is not None
        if obj is None:
            print(f"{year}: official schedule not yet complete; keeping any prior verified file")
            continue
        changed = write_if_changed(OUT / f"{year}.json", obj)
        print(f"{year}: validated {len(obj['days'])} entries; updated={changed}")
    # Monthly heartbeat commits keep scheduled workflows active on public GitHub
    # repositories (GitHub disables schedules after ~60 days without activity).
    heartbeat = {
        "month": now.strftime("%Y-%m"),
        "source": "GitHub Actions verified annual CN holiday sync",
    }
    write_if_changed(OUT / "heartbeat.json", heartbeat)
    return outcome


if __name__ == "__main__":
    run()
