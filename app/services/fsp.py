"""Адаптер реестра ФСП.

API и структура данных ФСП в рамках хакатона не предоставляются, поэтому мы определили
собственный минимальный контракт (см. docs/DOCUMENTATION.md, §7) и реализовали его поверх
файла `data/fsp_registry.json` (синтетические данные). Для реальной интеграции достаточно
заменить `FileRegistry` на клиент HTTP-API ФСП/Keycloak — интерфейс `get(fsp_id)` не меняется.

Контракт записи участника:
  fsp_id, email (адрес, зарегистрированный в ФСП), full_name,
  events: [{id, title, type: contest|hackathon|training, date: YYYY-MM-DD,
            place, participants, points}]
"""
import json
import os
import threading
from datetime import date, datetime
from typing import Optional

_lock = threading.Lock()
_cache: dict = {"mtime": None, "path": None, "data": {}}


class FileRegistry:
    def __init__(self, path: str):
        self.path = path

    def _load(self) -> dict:
        with _lock:
            try:
                mtime = os.path.getmtime(self.path)
            except OSError:
                return {}
            if _cache["path"] != self.path or _cache["mtime"] != mtime:
                with open(self.path, encoding="utf-8") as f:
                    raw = json.load(f)
                _cache.update(path=self.path, mtime=mtime, data={r["fsp_id"].upper(): r for r in raw})
            return _cache["data"]

    def get(self, fsp_id: str) -> Optional[dict]:
        return self._load().get((fsp_id or "").strip().upper())


def verify_link(registry: FileRegistry, fsp_id: str, account_email: str) -> Optional[dict]:
    """Привязка ФСП ID допускается, только если e-mail аккаунта совпадает с e-mail участника в ФСП.

    В MVP это замена OAuth-входа через ФСП ID (в проде — Authorization Code + PKCE через Keycloak,
    привязка по `sub`/`fsp_id` из токена, без ввода идентификатора вручную).
    """
    rec = registry.get(fsp_id)
    if rec and rec.get("email", "").strip().lower() == account_email.strip().lower():
        return rec
    return None


def summarize(record: Optional[dict], today: Optional[date] = None) -> Optional[dict]:
    """Краткая сводка достижений + «сила» 0..1 для ранжирования. None — истории ФСП нет."""
    if not record or not record.get("events"):
        return None
    today = today or date.today()
    events = sorted(record["events"], key=lambda e: e["date"], reverse=True)
    best_pct, best_event = None, None
    for e in events:
        pct = 100.0 * e["place"] / max(e["participants"], 1)
        if best_pct is None or pct < best_pct:
            best_pct, best_event = pct, e
    last = datetime.strptime(events[0]["date"], "%Y-%m-%d").date()
    age_days = (today - last).days
    # сила: объём участия (35%), лучший относительный результат (40%), свежесть (25%)
    volume = min(len(events) / 6, 1.0)
    quality = max(0.0, 1.0 - best_pct / 100.0 * 1.6) if best_pct is not None else 0.0
    recency = max(0.0, 1.0 - age_days / 1095)
    strength = round(0.35 * volume + 0.40 * quality + 0.25 * recency, 3)
    return {
        "events_count": len(events),
        "best_place": f'{best_event["place"]} из {best_event["participants"]}',
        "best_top_percent": round(best_pct, 1),
        "best_event": best_event["title"],
        "last_event_date": events[0]["date"],
        "total_points": sum(e.get("points", 0) for e in events),
        "recent": [{"title": e["title"], "type": e["type"], "date": e["date"],
                    "place": f'{e["place"]}/{e["participants"]}'} for e in events[:4]],
        "strength": strength,
    }
