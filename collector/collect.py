#!/usr/bin/env python3
"""OpenCode Meter : collecte le quota OpenCode Go et calcule les projections.

Sources :
  * https://opencode.ai/zen/go/v1/usage  (rolling / weekly / monthly)
  * ~/.local/share/opencode/opencode.db  (tokens par jour, lecture seule)

Sorties :
  ~/.cache/opencode-meter/usage.json     (lu par le plasmoid)
  ~/.cache/opencode-meter/history.sqlite (snapshots, pour la courbe réelle)
"""

from __future__ import annotations

import argparse
import calendar
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

USAGE_URL = "https://opencode.ai/zen/go/v1/usage"
WINDOWS = ("rolling", "weekly", "monthly")
WINDOW_LABELS = {"rolling": "5 h", "weekly": "Semaine", "monthly": "Mois"}

HOME = Path.home()
CACHE_DIR = HOME / ".cache/opencode-meter"
STATE_DB = CACHE_DIR / "history.sqlite"
USAGE_JSON = CACHE_DIR / "usage.json"
OPENCODE_ACCOUNT = HOME / ".local/share/opencode/account.json"
OPENCODE_DB = HOME / ".local/share/opencode/opencode.db"

# Rythme au-delà duquel on prévient (ratio rythme réel / rythme soutenable).
NOTIFY_RATIO = 1.0
NOTIFY_PERCENT = 85.0


# --------------------------------------------------------------------------
# Authentification
# --------------------------------------------------------------------------


def read_api_key() -> str | None:
    env = os.environ.get("OPENCODE_GO_API_KEY")
    if env:
        return env.strip()
    try:
        data = json.loads(OPENCODE_ACCOUNT.read_text())
        active = data.get("active", {}).get("opencode-go")
        accounts = data.get("accounts", {})
        if active and active in accounts:
            key = accounts[active].get("credential", {}).get("key")
            if key:
                return key.strip()
    except (OSError, ValueError):
        pass
    return None


# --------------------------------------------------------------------------
# Récupération du quota
# --------------------------------------------------------------------------


def fetch_usage(api_key: str, timeout: float = 15.0) -> dict:
    req = urllib.request.Request(
        USAGE_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "User-Agent": "opencode-meter/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        raise ValueError("réponse inattendue : champ 'usage' absent")
    out = {}
    for name in WINDOWS:
        raw = usage.get(name)
        if not isinstance(raw, dict):
            raise ValueError(f"fenêtre '{name}' absente de la réponse")
        percent = raw.get("percent")
        resets_at = raw.get("resetsAt")
        if not isinstance(percent, (int, float)):
            raise ValueError(f"fenêtre '{name}' : 'percent' invalide")
        out[name] = {
            "status": raw.get("status", "ok"),
            "percent": float(percent),
            # normalisé : la clé de jointure des snapshots doit être stable
            "resets_at": parse_iso_utc(resets_at).isoformat(),
        }
    return out


# --------------------------------------------------------------------------
# Fenêtres et projections
# --------------------------------------------------------------------------


def parse_iso_utc(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def minus_one_month(dt: datetime) -> datetime:
    year = dt.year - 1 if dt.month == 1 else dt.year
    month = 12 if dt.month == 1 else dt.month - 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def window_start(name: str, resets_at: datetime) -> datetime:
    if name == "rolling":
        return resets_at - timedelta(hours=5)
    if name == "weekly":
        return resets_at - timedelta(days=7)
    return minus_one_month(resets_at)


def ratio_state(ratio: float | None, percent: float) -> str:
    if percent >= 100:
        return "exhausted"
    if ratio is None:
        return "warn" if percent >= 85 else "ok"
    if ratio >= 1.10:
        return "over"
    if ratio >= 0.95:
        return "warn"
    return "ok"


def observed_pace(rows: list[tuple[int, float]]) -> float | None:
    """Rythme %/jour observé sur les snapshots de la fenêtre courante."""
    if len(rows) < 2:
        return None
    first_ts, first_pct = rows[0]
    last_ts, last_pct = rows[-1]
    span_days = (last_ts - first_ts) / 86400
    if span_days < 0.25:  # moins de 6 h d'historique : trop bruité
        return None
    return max(0.0, (last_pct - first_pct) / span_days)


def build_window(name: str, raw: dict, now: datetime, snapshots: list) -> dict:
    percent = 100.0 if raw["status"] == "rate-limited" else raw["percent"]
    resets_at = parse_iso_utc(raw["resets_at"])
    start = window_start(name, resets_at)
    total_days = max((resets_at - start).total_seconds() / 86400, 1e-6)
    elapsed_days = min(max((now - start).total_seconds() / 86400, 0.0), total_days)
    remaining_days = max(total_days - elapsed_days, 0.0)

    pace = observed_pace(snapshots)
    source = "observé"
    if pace is None and elapsed_days > 0.02:
        pace = percent / elapsed_days
        source = "moyen"
    if pace is None:
        pace = 0.0
        source = "n/d"

    remaining_percent = max(100.0 - percent, 0.0)
    # Sous ~5 h restantes (ou 5 % de la fenêtre), un rythme soutenable n'a plus
    # de sens : il tend vers l'infini. On l'omet, la projection reste valable.
    sustainable = (
        (remaining_percent / remaining_days)
        if remaining_days > max(0.2, total_days * 0.05)
        else None
    )
    ratio = (pace / sustainable) if sustainable and sustainable > 0 else None
    projected = min(percent + pace * remaining_days, 999.0)
    eta_days = (remaining_percent / pace) if pace > 0.001 else None

    return {
        "label": WINDOW_LABELS[name],
        "status": raw["status"],
        "percent": round(percent, 1),
        "remaining_percent": round(remaining_percent, 1),
        "resets_at": resets_at.isoformat(),
        "reset_in_seconds": int(max((resets_at - now).total_seconds(), 0)),
        "window_start": start.isoformat(),
        "window_days": round(total_days, 2),
        "elapsed_days": round(elapsed_days, 2),
        "remaining_days": round(remaining_days, 2),
        "pace_per_day": round(pace, 2),
        "pace_source": source,
        "sustainable_per_day": round(sustainable, 2) if sustainable else None,
        "ratio": round(ratio, 2) if ratio is not None else None,
        "projected_percent": round(projected, 1),
        "eta_days": round(eta_days, 1) if eta_days is not None else None,
        "projection_source": "linéaire",
        "projected_linear_percent": None,
        "saturation_in_days": None,
        "state": ratio_state(ratio, percent),
    }


# --------------------------------------------------------------------------
# Profil d'activité et projection pondérée
# --------------------------------------------------------------------------


def _next_midnight(moment: datetime) -> datetime:
    return (moment.replace(hour=0, minute=0, second=0, microsecond=0)
            + timedelta(days=1))


def weighted_units(start: datetime, end: datetime, factors: list[float]) -> float:
    """Nombre de « journées moyennes » entre deux dates, pondéré par jour de semaine."""
    if end <= start:
        return 0.0
    total = 0.0
    cursor = start
    while cursor < end:
        boundary = min(_next_midnight(cursor), end)
        fraction = (boundary - cursor).total_seconds() / 86400
        total += fraction * factors[(cursor.weekday() + 1) % 7]
        cursor = boundary
    return total


def saturation_days(percent: float, now: datetime, reset: datetime,
                    factors: list[float], rate_per_unit: float) -> float | None:
    """Jours avant d'atteindre 100 %, en suivant le profil hebdomadaire."""
    remaining = 100.0 - percent
    if remaining <= 0:
        return 0.0
    if rate_per_unit <= 0:
        return None
    elapsed = 0.0
    cursor = now
    while cursor < reset:
        boundary = min(_next_midnight(cursor), reset)
        days = (boundary - cursor).total_seconds() / 86400
        remaining -= rate_per_unit * days * factors[(cursor.weekday() + 1) % 7]
        elapsed += days
        cursor = boundary
        if remaining <= 0:
            return elapsed
    return None


def apply_activity_profile(window: dict, stats: dict, now: datetime) -> None:
    """Remplace la projection linéaire par une projection basée sur les habitudes."""
    weekday = stats.get("weekday") or []
    if len(weekday) != 7 or (stats.get("profile_days") or 0) < 14:
        return
    factors = [float(day["factor"]) for day in weekday]
    if not any(factors):
        return
    start = parse_iso_utc(window["window_start"]).astimezone()
    reset = parse_iso_utc(window["resets_at"]).astimezone()
    now_local = now.astimezone()
    elapsed_units = weighted_units(start, now_local, factors)
    remaining_units = weighted_units(now_local, reset, factors)
    if elapsed_units < 0.3:
        return
    rate = window["percent"] / elapsed_units
    projected = window["percent"] + rate * remaining_units
    window["projected_linear_percent"] = window["projected_percent"]
    window["projected_percent"] = round(min(projected, 999.0), 1)
    window["projection_source"] = "habitudes"
    saturation = saturation_days(window["percent"], now_local, reset, factors, rate)
    window["saturation_in_days"] = round(saturation, 1) if saturation is not None else None
    # La couleur suit la projection, pas le pourcentage brut.
    if window["percent"] >= 100:
        window["state"] = "exhausted"
    elif window["projected_percent"] >= 100:
        window["state"] = "over"
    elif window["projected_percent"] >= 90:
        window["state"] = "warn"
    else:
        window["state"] = "ok"


# --------------------------------------------------------------------------
# Historique
# --------------------------------------------------------------------------


def open_state_db() -> sqlite3.Connection:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(STATE_DB)
    db.execute(
        """CREATE TABLE IF NOT EXISTS snapshots (
               ts INTEGER NOT NULL,
               window TEXT NOT NULL,
               percent REAL NOT NULL,
               resets_at TEXT NOT NULL,
               PRIMARY KEY (ts, window)
           )"""
    )
    return db


def store_snapshots(db: sqlite3.Connection, windows: dict, now: datetime) -> None:
    ts = int(now.timestamp()) // 60 * 60
    for name, data in windows.items():
        db.execute(
            "INSERT OR REPLACE INTO snapshots(ts, window, percent, resets_at) VALUES (?,?,?,?)",
            (ts, name, data["percent"], data["resets_at"]),
        )
    db.execute(
        "DELETE FROM snapshots WHERE ts < ?", (int(now.timestamp()) - 90 * 86400,)
    )
    db.commit()


def window_snapshots(
    db: sqlite3.Connection, name: str, resets_at_iso: str, since: datetime
):
    rows = db.execute(
        "SELECT ts, percent FROM snapshots WHERE window=? AND resets_at=? AND ts>=? ORDER BY ts",
        (name, resets_at_iso, int(since.timestamp())),
    ).fetchall()
    return [(int(ts), float(pct)) for ts, pct in rows]


def daily_series(db: sqlite3.Connection, name: str, days: int = 14) -> list[dict]:
    """Max de % atteint par jour, jours manquants à zéro."""
    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=days - 1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    rows = db.execute(
        "SELECT ts, percent FROM snapshots WHERE window=? AND ts>=? ORDER BY ts",
        (name, int(start.timestamp())),
    ).fetchall()
    by_day: dict[str, float] = {}
    for ts, pct in rows:
        day = datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d")
        by_day[day] = max(by_day.get(day, 0.0), float(pct))
    series = []
    for i in range(days):
        day = (start + timedelta(days=i)).strftime("%Y-%m-%d")
        series.append({"date": day, "percent": round(by_day.get(day, 0.0), 1)})
    return series


# --------------------------------------------------------------------------
# Tokens locaux (proxy d'activité)
# --------------------------------------------------------------------------


def quota_tokens_since(start_ms: int) -> int:
    """Tokens opencode-go consommés depuis un instant (ms epoch)."""
    if not OPENCODE_DB.exists():
        return 0
    tokens_expr = (
        "COALESCE(json_extract(data,'$.tokens.input'),0)"
        " + COALESCE(json_extract(data,'$.tokens.output'),0)"
        " + COALESCE(json_extract(data,'$.tokens.reasoning'),0)"
    )
    try:
        con = sqlite3.connect(f"file:{OPENCODE_DB}?mode=ro", uri=True, timeout=3)
        try:
            row = con.execute(
                f"""SELECT SUM({tokens_expr}) FROM session_message
                    WHERE type='assistant' AND time_created >= ?
                      AND json_extract(data,'$.model.providerID') = 'opencode-go'""",
                (start_ms,),
            ).fetchone()
        finally:
            con.close()
    except sqlite3.Error:
        return 0
    return int(row[0] or 0)


def _project_label(directory: str) -> str:
    """Nom lisible : les worktrees T3 sont ramenés au projet d'origine."""
    if not directory:
        return "?"
    parts = Path(directory).parts
    if ".t3" in parts:
        i = parts.index(".t3")
        if i + 2 < len(parts) and parts[i + 1] == "worktrees":
            return parts[i + 2]
    if Path(directory) == HOME:
        return "home"
    return Path(directory).name or directory


def local_stats(days: int = 28, month_days: int = 30, chart_days: int = 14) -> dict:
    """Tokens par jour, modèles, projets et heures de consommation."""
    result = {
        "tokens": [],
        "weekday": [],
        "weekend_ratio": None,
        "active_days_per_week": None,
        "profile_days": 0,
        "today_tokens": 0,
        "baseline_tokens": None,
        "habit_ratio": None,
        "models": [],
        "projects": [],
        "hourly": [0] * 24,
    }
    if not OPENCODE_DB.exists():
        return result

    now = datetime.now(timezone.utc)
    since_ms = int((now - timedelta(days=days)).timestamp() * 1000)
    month_ms = int((now - timedelta(days=month_days)).timestamp() * 1000)
    tokens_expr = (
        "COALESCE(json_extract(data,'$.tokens.input'),0)"
        " + COALESCE(json_extract(data,'$.tokens.output'),0)"
        " + COALESCE(json_extract(data,'$.tokens.reasoning'),0)"
    )

    try:
        con = sqlite3.connect(f"file:{OPENCODE_DB}?mode=ro", uri=True, timeout=3)
        try:
            daily = con.execute(
                f"""SELECT date(time_created/1000,'unixepoch','localtime') AS d,
                           SUM({tokens_expr})
                    FROM session_message
                    WHERE type='assistant' AND time_created >= ?
                    GROUP BY d ORDER BY d""",
                (since_ms,),
            ).fetchall()
            models = con.execute(
                f"""SELECT json_extract(data,'$.model.id') AS m,
                           SUM({tokens_expr}) AS t
                    FROM session_message
                    WHERE type='assistant' AND time_created >= ?
                      AND json_extract(data,'$.model.id') IS NOT NULL
                    GROUP BY m ORDER BY t DESC LIMIT 5""",
                (month_ms,),
            ).fetchall()
            hourly = con.execute(
                f"""SELECT CAST(strftime('%H', time_created/1000,'unixepoch','localtime') AS INTEGER) AS h,
                           SUM({tokens_expr})
                    FROM session_message
                    WHERE type='assistant' AND time_created >= ?
                    GROUP BY h""",
                (month_ms,),
            ).fetchall()
            projects = con.execute(
                """SELECT directory,
                          SUM(tokens_input + tokens_output + tokens_reasoning) AS t
                   FROM session_v2
                   WHERE time_created >= ?
                   GROUP BY directory""",
                (month_ms,),
            ).fetchall()
        finally:
            con.close()
    except sqlite3.Error:
        return result

    for day, tokens in daily:
        if day:
            result["tokens"].append({"date": day, "tokens": int(tokens or 0)})

    # Profil hebdomadaire : moyenne de tokens par jour de semaine sur 4 semaines.
    day_map = {day: int(tokens or 0) for day, tokens in daily if day}
    today_date = datetime.now().date()
    start_date = today_date - timedelta(days=days - 1)
    weekday_totals = [0.0] * 7
    weekday_counts = [0] * 7
    active_days = 0
    for i in range(days):
        current = start_date + timedelta(days=i)
        tokens = day_map.get(current.isoformat(), 0)
        dow = (current.weekday() + 1) % 7  # 0 = dimanche
        weekday_totals[dow] += tokens
        weekday_counts[dow] += 1
        if tokens > 50_000:
            active_days += 1
    weekday_avg = [
        weekday_totals[i] / weekday_counts[i] if weekday_counts[i] else 0.0
        for i in range(7)
    ]
    overall_avg = sum(weekday_avg) / 7
    if overall_avg > 0:
        result["weekday"] = [
            {
                "dow": i,
                "tokens": int(weekday_avg[i]),
                "factor": round(weekday_avg[i] / overall_avg, 3),
            }
            for i in range(7)
        ]
        weekdays = sum(weekday_avg[1:6]) / 5
        weekend = (weekday_avg[0] + weekday_avg[6]) / 2
        if weekdays > 0:
            result["weekend_ratio"] = round(weekend / weekdays - 1, 3)
        result["active_days_per_week"] = round(active_days / days * 7, 1)
        result["profile_days"] = days

    # La courbe du popup reste sur 14 jours pour rester lisible.
    result["tokens"] = result["tokens"][-chart_days:]

    today = datetime.now().strftime("%Y-%m-%d")
    if result["tokens"] and result["tokens"][-1]["date"] == today:
        result["today_tokens"] = result["tokens"][-1]["tokens"]
    past = [d["tokens"] for d in result["tokens"] if d["date"] != today][-7:]
    past = [t for t in past if t > 0]
    if len(past) >= 3:
        baseline = int(sum(past) / len(past))
        result["baseline_tokens"] = baseline
        if baseline > 0:
            result["habit_ratio"] = round(result["today_tokens"] / baseline, 2)

    total_models = sum(int(t or 0) for _, t in models)
    if total_models > 0:
        result["models"] = [
            {
                "name": name,
                "tokens": int(tokens or 0),
                "share": round(int(tokens or 0) / total_models, 3),
            }
            for name, tokens in models
        ]

    by_project: dict[str, int] = {}
    for directory, tokens in projects:
        label = _project_label(directory or "")
        by_project[label] = by_project.get(label, 0) + int(tokens or 0)
    total_projects = sum(by_project.values())
    if total_projects > 0:
        result["projects"] = [
            {"name": name, "tokens": tokens, "share": round(tokens / total_projects, 3)}
            for name, tokens in sorted(
                by_project.items(), key=lambda kv: kv[1], reverse=True
            )[:5]
        ]

    for hour, tokens in hourly:
        if hour is not None and 0 <= int(hour) < 24:
            result["hourly"][int(hour)] = int(tokens or 0)

    return result


def add_today_budget(payload: dict, stats: dict, now: datetime) -> None:
    """Part du budget du jour déjà consommée (100 % = pile dans les temps)."""
    window = payload["windows"].get("monthly")
    if not window:
        return
    weekday = stats.get("weekday") or []
    factors = [float(d["factor"]) for d in weekday] if len(weekday) == 7 else [1.0] * 7
    if not any(factors):
        factors = [1.0] * 7
    start = parse_iso_utc(window["window_start"]).astimezone()
    reset = parse_iso_utc(window["resets_at"]).astimezone()
    now_local = now.astimezone()
    remaining_units = weighted_units(now_local, reset, factors)
    if remaining_units <= 0.1:
        return
    today_dow = (now_local.weekday() + 1) % 7
    budget_today = window["remaining_percent"] / remaining_units * factors[today_dow]
    if budget_today <= 0:
        return

    midnight = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    tokens_window = quota_tokens_since(int(start.timestamp() * 1000))
    tokens_today = quota_tokens_since(int(midnight.timestamp() * 1000))
    if tokens_window >= 1_000_000 and window["percent"] > 0:
        per_token = window["percent"] / tokens_window
        used_today = tokens_today * per_token
        source = "tokens"
    else:
        # Repli : delta de quota entre le premier relevé du jour et maintenant.
        used_today = 0.0
        source = "relevés"
        db = open_state_db()
        row = db.execute(
            "SELECT percent FROM snapshots WHERE window='monthly' AND ts >= ? ORDER BY ts LIMIT 1",
            (int(midnight.timestamp()),),
        ).fetchone()
        db.close()
        if row is None:
            return
        used_today = max(window["percent"] - float(row[0]), 0.0)

    ratio = used_today / budget_today
    stats["today_quota_percent"] = round(used_today, 2)
    stats["today_budget_percent"] = round(budget_today, 2)
    stats["today_budget_ratio"] = round(ratio, 3)
    stats["today_budget_source"] = source


# --------------------------------------------------------------------------
# Notification
# --------------------------------------------------------------------------


def maybe_notify(payload: dict, previous: dict) -> bool:
    monthly = payload["windows"]["monthly"]
    ratio = monthly.get("ratio")
    percent = monthly["percent"]
    triggered = (
        ratio is not None and ratio > NOTIFY_RATIO
    ) or percent >= NOTIFY_PERCENT
    # Profil hebdomadaire : moyenne de tokens par jour de semaine sur 4 semaines.
    day_map = {day: int(tokens or 0) for day, tokens in daily if day}
    today_date = datetime.now().date()
    start_date = today_date - timedelta(days=days - 1)
    weekday_totals = [0.0] * 7
    weekday_counts = [0] * 7
    active_days = 0
    for i in range(days):
        current = start_date + timedelta(days=i)
        tokens = day_map.get(current.isoformat(), 0)
        dow = (current.weekday() + 1) % 7  # 0 = dimanche
        weekday_totals[dow] += tokens
        weekday_counts[dow] += 1
        if tokens > 50_000:
            active_days += 1
    weekday_avg = [
        weekday_totals[i] / weekday_counts[i] if weekday_counts[i] else 0.0
        for i in range(7)
    ]
    overall_avg = sum(weekday_avg) / 7
    if overall_avg > 0:
        result["weekday"] = [
            {
                "dow": i,
                "tokens": int(weekday_avg[i]),
                "factor": round(weekday_avg[i] / overall_avg, 3),
            }
            for i in range(7)
        ]
        weekdays = sum(weekday_avg[1:6]) / 5
        weekend = (weekday_avg[0] + weekday_avg[6]) / 2
        if weekdays > 0:
            result["weekend_ratio"] = round(weekend / weekdays - 1, 3)
        result["active_days_per_week"] = round(active_days / days * 7, 1)
        result["profile_days"] = days

    # La courbe du popup reste sur 14 jours pour rester lisible.
    result["tokens"] = result["tokens"][-chart_days:]

    today = datetime.now().strftime("%Y-%m-%d")
    if not triggered or previous.get("last_date") == today:
        return False
    if not shutil.which("notify-send"):
        return False
    if ratio is not None:
        detail = (
            f"{percent:.0f} % utilisé · rythme {monthly['pace_per_day']:.1f} %/j "
            f"vs {monthly['sustainable_per_day'] or 0:.1f} %/j soutenable"
        )
        projection = f"Projection : {monthly['projected_percent']:.0f} % au reset."
    else:
        detail = f"{percent:.0f} % utilisé"
        projection = "Rythme encore inconnu, continue pour affiner la projection."
    body = f"Quota mensuel OpenCode Go : {detail}\n{projection}"
    try:
        subprocess.run(
            [
                "notify-send",
                "-a",
                "OpenCode Meter",
                "-u",
                "normal",
                "-i",
                "office-chart-bar",
                "OpenCode Meter : attention au quota",
                body,
            ],
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    payload.setdefault("notify", {})["last_date"] = today
    return True


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def fmt_duration(seconds: int) -> str:
    if seconds <= 0:
        return "maintenant"
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    if days:
        return f"{days} j {hours} h"
    if hours:
        return f"{hours} h {minutes:02d}"
    return f"{minutes} min"


def print_human(payload: dict) -> None:
    if not payload.get("ok"):
        print(f"❌ {payload.get('error') or 'erreur inconnue'}", file=sys.stderr)
        return

    bold = "\033[1m"
    dim = "\033[2m"
    colors = {
        "ok": "\033[32m",
        "warn": "\033[33m",
        "over": "\033[31m",
        "exhausted": "\033[31m",
    }
    reset = "\033[0m"

    print(
        f"{bold}OpenCode Go{reset} {dim}(maj {payload['generated_at'][11:16]} UTC){reset}"
    )
    for name in WINDOWS:
        w = payload["windows"][name]
        color = colors.get(w["state"], "")
        bar_width = 24
        filled = round(w["percent"] / 100 * bar_width)
        bar = "█" * filled + "░" * (bar_width - filled)
        print(
            f"  {w['label']:<8} {color}{bar}{reset} {w['percent']:5.1f} %"
            f"  {dim}reset dans {fmt_duration(w['reset_in_seconds'])}{reset}"
        )
        if w["sustainable_per_day"] is not None:
            print(
                f"  {dim}{'':<8} rythme {w['pace_per_day']:.1f} %/j ({w['pace_source']}) · "
                f"soutenable {w['sustainable_per_day']:.1f} %/j · "
                f"projection {w['projected_percent']:.0f} %"
                f"{' (habitudes)' if w.get('projection_source') == 'habitudes' else ''}{reset}"
            )
        else:
            print(
                f"  {dim}{'':<8} rythme {w['pace_per_day']:.1f} %/j ({w['pace_source']}) · "
                f"projection {w['projected_percent']:.0f} %"
                f"{' (habitudes)' if w.get('projection_source') == 'habitudes' else ''}{reset}"
            )
    stats = payload.get("stats") or {}
    if stats.get("weekend_ratio") is not None or stats.get("active_days_per_week"):
        habit = f"  {dim}profil : {stats.get('active_days_per_week')} j actifs/7"
        if stats.get("weekend_ratio") is not None:
            habit += f" · week-end {stats['weekend_ratio'] * 100:+.0f} %"
        print(f"{habit}{reset}")
    if stats.get("today_budget_ratio") is not None:
        print(
            f"  {dim}aujourd'hui : {stats['today_budget_ratio'] * 100:.0f} % du budget du jour "
            f"({stats['today_quota_percent']:.1f} / {stats['today_budget_percent']:.1f} % du quota){reset}"
        )
    if stats.get("today_tokens"):
        line = f"  {dim}aujourd'hui : {stats['today_tokens']:,} tokens"
        if stats.get("habit_ratio") is not None:
            line += f" ({stats['habit_ratio']:.1f}× ta moyenne 7 j)"
        print(f"{line}{reset}")
    for m in (stats.get("models") or [])[:3]:
        print(f"  {dim}  {m['name']:<26} {m['share'] * 100:4.0f} %{reset}")
    for p in (stats.get("projects") or [])[:3]:
        print(f"  {dim}  {p['name']:<26} {p['share'] * 100:4.0f} %  projet{reset}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Suivi du quota OpenCode Go")
    parser.add_argument("--json", action="store_true", help="affiche le JSON complet")
    parser.add_argument(
        "--notify", action="store_true", help="notifie en cas de dépassement (1×/jour)"
    )
    parser.add_argument(
        "--quiet", action="store_true", help="n'affiche rien en cas de succès"
    )
    parser.add_argument("--timeout", type=float, default=15.0)
    args = parser.parse_args()

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    previous: dict = {}
    try:
        previous = json.loads(USAGE_JSON.read_text())
    except (OSError, ValueError):
        pass

    payload: dict = {
        "generated_at": now.isoformat(),
        "ok": False,
        "error": None,
        "provider": "opencode-go",
        "windows": {},
        "monthly_series": [],
        "tokens": [],
        "stats": {},
        "notify": previous.get("notify", {}),
    }

    api_key = read_api_key()
    if not api_key:
        payload["error"] = (
            "clé API opencode-go introuvable (~/.local/share/opencode/account.json)"
        )
    else:
        try:
            raw = fetch_usage(api_key, timeout=args.timeout)
            db = open_state_db()
            store_snapshots(db, raw, now)
            for name in WINDOWS:
                resets_at = parse_iso_utc(raw[name]["resets_at"])
                start = window_start(name, resets_at)
                snaps = window_snapshots(db, name, resets_at.isoformat(), start)
                payload["windows"][name] = build_window(name, raw[name], now, snaps)
            payload["monthly_series"] = daily_series(db, "monthly")
            db.close()
            stats = local_stats()
            payload["stats"] = stats
            payload["tokens"] = stats["tokens"]
            for name in ("weekly", "monthly"):
                if name in payload["windows"]:
                    apply_activity_profile(payload["windows"][name], stats, now)
            add_today_budget(payload, stats, now)
            payload["ok"] = True
        except urllib.error.HTTPError as exc:
            payload["error"] = f"HTTP {exc.code} : quota indisponible"
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            payload["error"] = f"{type(exc).__name__}: {exc}"

    if args.notify:
        maybe_notify(payload, previous)

    USAGE_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=1))

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=1))
    elif not args.quiet:
        print_human(payload)
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
