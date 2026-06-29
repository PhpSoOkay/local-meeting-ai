"""
Конфигурация Meeting Recorder.
Управление настройками устройств и типов встреч.
"""
import json
from pathlib import Path
from datetime import datetime

BASE_DIR = Path.home() / "Yandex.Disk/carrier/meeting-ai"
PROJECT_DIR = BASE_DIR  # meeting-ai/ (совпадает с BASE_DIR)
CONFIG_FILE = PROJECT_DIR / "config" / "config.json"
MEETING_TYPES_FILE = PROJECT_DIR / "config" / "meeting_types.json"


def load_config() -> dict:
    """Загрузить конфигурацию устройств"""
    if not CONFIG_FILE.exists():
        return {}
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_config(config: dict):
    """Сохранить конфигурацию"""
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(
        json.dumps(config, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def get_configured_devices() -> tuple[str | None, str | None]:
    """Получить настроенные устройства (output, input)"""
    config = load_config()
    return config.get("output_device"), config.get("input_device")


def load_meeting_types() -> dict:
    """Загрузить типы встреч"""
    if not MEETING_TYPES_FILE.exists():
        return {}
    try:
        return json.loads(MEETING_TYPES_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def get_meeting_type(type_key: str) -> dict:
    """Получить конфигурацию типа встречи"""
    types = load_meeting_types()
    return types.get(type_key, types.get("default", {}))