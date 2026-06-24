"""Модуль для отслеживания прогресса обработки встреч."""
import json
import os
from pathlib import Path

PROGRESS_DIR = Path.home() / "Yandex.Disk/carrier/meeting-ai" / ".progress"
PROGRESS_DIR.mkdir(exist_ok=True)


def get_progress_file(meeting_name: str) -> Path:
    """Путь к файлу прогресса для встречи."""
    safe_name = meeting_name.replace("/", "_").replace("\\", "_")
    return PROGRESS_DIR / f"{safe_name}.json"


def save_progress(meeting_name: str, status: str, step: str = "", progress: float = 0.0, detail: str = ""):
    """Сохранить прогресс обработки."""
    pf = get_progress_file(meeting_name)
    data = {
        "meeting_name": meeting_name,
        "status": status,  # "idle", "processing", "done", "error"
        "step": step,
        "progress": min(100.0, max(0.0, progress)),
        "detail": detail,
        "updated_at": __import__("datetime").datetime.now().isoformat()
    }
    pf.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_progress(meeting_name: str) -> dict:
    """Загрузить прогресс обработки."""
    pf = get_progress_file(meeting_name)
    if pf.exists():
        try:
            return json.loads(pf.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "meeting_name": meeting_name,
        "status": "idle",
        "step": "",
        "progress": 0.0,
        "detail": "",
        "updated_at": ""
    }


def clear_progress(meeting_name: str):
    """Удалить файл прогресса."""
    pf = get_progress_file(meeting_name)
    pf.unlink(missing_ok=True)
