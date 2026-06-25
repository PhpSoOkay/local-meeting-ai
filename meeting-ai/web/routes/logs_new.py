"""Логирование процессов транскрипции и суммаризации"""
import json
from datetime import datetime
from pathlib import Path


LOG_DIR = None
PROCESSING_LOG = None


def _ensure_init():
    """Ленивая инициализация"""
    global LOG_DIR, PROCESSING_LOG
    if LOG_DIR is not None:
        return
    
    from ..helpers import BASE_DIR
    LOG_DIR = BASE_DIR / "logs"
    LOG_DIR.mkdir(exist_ok=True)
    PROCESSING_LOG = LOG_DIR / "processing.log"


def log_action(meeting_name: str, step: str, message: str, level: str = "info", details: dict = None):
    """Записать действие в лог"""
    _ensure_init()
    
    entry = {
        "timestamp": datetime.now().isoformat(),
        "meeting_name": meeting_name,
        "step": step,
        "level": level,
        "message": message,
        "details": details or {}
    }
    
    try:
        with open(PROCESSING_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"Failed to write to log: {e}")


def get_logs(meeting_name: str = None, limit: int = 100, level: str = None):
    """Получить логи"""
    _ensure_init()
    
    if not PROCESSING_LOG.exists():
        return []
    
    logs = []
    try:
        with open(PROCESSING_LOG, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if meeting_name and entry.get("meeting_name") != meeting_name:
                        continue
                    if level and entry.get("level") != level:
                        continue
                    logs.append(entry)
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        print(f"Failed to read logs: {e}")
    
    logs.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return logs[:limit]


def clear_logs(meeting_name: str = None):
    """Очистить логи"""
    _ensure_init()
    
    if not PROCESSING_LOG.exists():
        return
    
    if meeting_name is None:
        PROCESSING_LOG.unlink()
        return
    
    logs = get_logs()
    filtered = [l for l in logs if l.get("meeting_name") != meeting_name]
    
    with open(PROCESSING_LOG, "w", encoding="utf-8") as f:
        for entry in filtered:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"Failed to write to log: {e}")


def get_logs(meeting_name: str = None, limit: int = 100, level: str = None):
    """Получить логи"""
    _ensure_init()
    
    if not PROCESSING_LOG.exists():
        return []
    
    logs = []
    try:
        with open(PROCESSING_LOG, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if meeting_name and entry.get("meeting_name") != meeting_name:
                        continue
                    if level and entry.get("level") != level:
                        continue
                    logs.append(entry)
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        print(f"Failed to read logs: {e}")
    
    logs.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return logs[:limit]


def clear_logs(meeting_name: str = None):
    """Очистить логи"""
    _ensure_init()
    
    if not PROCESSING_LOG.exists():
        return
    
    if meeting_name is None:
        PROCESSING_LOG.unlink()
        return
    
    logs = get_logs()
    filtered = [l for l in logs if l.get("meeting_name") != meeting_name]
    
    with open(PROCESSING_LOG, "w", encoding="utf-8") as f:
        for entry in filtered:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
