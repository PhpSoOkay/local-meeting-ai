"""Общие функции для веб-приложения"""
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Пути
BASE_DIR = Path.home() / "Yandex.Disk/carrier/meeting-ai"
AUDIO_DIR = BASE_DIR / "audio"
TRANSCRIPTS_DIR = BASE_DIR / "transcripts"
SUMMARIES_DIR = BASE_DIR / "summaries"
CONFIG_FILE = BASE_DIR / "config" / "meeting_types.json"
PID_FILE = BASE_DIR / ".recorder.pid"


def find_meeting_dir(meeting_name):
    """Найти папку встречи по имени (в любых подпапках audio/)"""
    if not meeting_name.startswith("meeting_"):
        meeting_name = f"meeting_{meeting_name}"
    
    # Сначала пробуем прямой путь
    direct = AUDIO_DIR / meeting_name
    if direct.exists():
        return direct
    
    # Ищем рекурсивно
    for found in AUDIO_DIR.glob(f"**/{meeting_name}"):
        if found.is_dir():
            return found
    
    return None


def load_meeting_types():
    """Загрузить типы встреч"""
    if not CONFIG_FILE.exists():
        return {}
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def get_recording_status():
    """Проверить статус записи"""
    if not PID_FILE.exists():
        return {"recording": False}

    try:
        data = PID_FILE.read_text().strip()
        parts = data.split(",")
        if len(parts) >= 3:
            pid = int(parts[0])
            timestamp = parts[2]

            # Проверка, жив ли процесс
            try:
                os.kill(pid, 0)
                return {
                    "recording": True,
                    "pid": pid,
                    "timestamp": timestamp,
                    "meeting_dir": str(AUDIO_DIR / f"meeting_{timestamp}")
                }
            except ProcessLookupError:
                PID_FILE.unlink(missing_ok=True)
    except Exception:
        pass

    return {"recording": False}


def get_processing_status():
    """Проверить статус обработки (транскрипция/суммаризация)"""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    from progress import load_progress

    # Проверяем все встречи — если хотя бы одна в процессе, возвращаем true
    progress_dir = BASE_DIR / ".progress"
    if not progress_dir.exists():
        return {"processing": False, "current": None}

    for pf in progress_dir.glob("*.json"):
        try:
            data = json.loads(pf.read_text())
            if data.get("status") in ("processing", "done", "error"):
                return {
                    "processing": True,
                    "current": data,
                    "meeting_name": data.get("meeting_name")
                }
        except Exception:
            continue

    return {"processing": False, "current": None}


def list_meetings():
    """Список всех записей"""
    meetings = []

    for meeting_dir in sorted(AUDIO_DIR.glob("**/meeting_*"), reverse=True):
        if not meeting_dir.is_dir():
            continue

        if "transcripts" in str(meeting_dir) or "summaries" in str(meeting_dir):
            continue

        # Пытаемся прочитать метаданные из JSON
        metadata_file = meeting_dir / "meeting_metadata.json"
        metadata = {}
        if metadata_file.exists():
            try:
                metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
            except Exception:
                pass

        # Если есть метаданные, используем их
        if metadata:
            timestamp = meeting_dir.name.replace("meeting_", "")
            meeting_type = metadata.get("type", "default")
            is_processed = "summary_dir" in metadata and Path(metadata["summary_dir"]).exists()
            title = metadata.get("title", "")
        else:
            # Fallback: парсим из имени
            timestamp = meeting_dir.name.replace("meeting_", "")
            is_processed = (SUMMARIES_DIR / meeting_dir.name).exists()
            type_file = meeting_dir / ".meeting_type"
            meeting_type = "default"
            if type_file.exists():
                meeting_type = type_file.read_text().strip()
            title = ""

        segments = list(meeting_dir.glob("segment_*.wav"))
        total_duration = sum(max(0, (s.stat().st_size - 44)) / 32000 for s in segments)

        meetings.append({
            "name": meeting_dir.name,
            "path": str(meeting_dir),
            "timestamp": timestamp,
            "type": meeting_type,
            "segments": len(segments),
            "duration": format_duration(total_duration),
            "processed": is_processed,
            "title": title,
            "created": datetime.fromisoformat(
                timestamp.replace("_", "T")
            ).strftime("%Y-%m-%d %H:%M:%S")
        })

    return meetings


def format_duration(seconds):
    """Форматирование длительности"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def run_processing(meeting_name, meeting_type):
    """Запустить обработку в фоновом потоке"""
    meeting_dir = find_meeting_dir(meeting_name)
    if not meeting_dir:
        from .progress import save_progress
        save_progress(meeting_name, "error", "Папка встречи не найдена", 0)
        return

    env = os.environ.copy()
    env['http_proxy'] = ''
    env['https_proxy'] = ''
    env['all_proxy'] = ''
    # Добавляем web/routes в PYTHONPATH для subprocess
    if 'PYTHONPATH' in env:
        env['PYTHONPATH'] = str(BASE_DIR / "web" / "routes") + ":" + env['PYTHONPATH']
    else:
        env['PYTHONPATH'] = str(BASE_DIR / "web" / "routes")

    cmd = [
        sys.executable, str(BASE_DIR / "scripts" / "process_meeting.py"),
        str(meeting_dir), "--type", meeting_type
    ]

    subprocess.run(cmd, cwd=str(BASE_DIR), env=env, capture_output=True, text=True)
    # Статус обработки теперь управляется внутри process_meeting.py
