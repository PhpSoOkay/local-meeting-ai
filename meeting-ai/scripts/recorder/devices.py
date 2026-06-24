"""
Работа с аудиоустройствами PipeWire/PulseAudio.
Список устройств, создание виртуальных sink'ов.
"""
import re
import subprocess
import time
from pathlib import Path

BASE_DIR = Path.home() / "Yandex.Disk/carrier/meeting-ai"
SINK_FILE = BASE_DIR / ".recorder_modules"


def log(message: str):
    """Логирование"""
    from datetime import datetime
    log_file = BASE_DIR / "recorder.log"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {message}\n")


def list_devices() -> dict:
    """Получить список всех аудиоустройств"""
    sinks = []
    sources = []

    # Sink'и (вывод)
    result = subprocess.run(
        ["pactl", "list", "short", "sinks"],
        capture_output=True, text=True
    )
    for line in result.stdout.strip().split("\n"):
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) >= 2:
            sink_name = parts[1]
            if "meeting_recorder" in sink_name or "loopback" in sink_name:
                continue
            sinks.append(sink_name)

    # Source'ы (ввод)
    result = subprocess.run(
        ["pactl", "list", "short", "sources"],
        capture_output=True, text=True
    )
    for line in result.stdout.strip().split("\n"):
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) >= 2:
            source_name = parts[1]
            if ".monitor" in source_name or "meeting_recorder" in source_name:
                continue
            sources.append(source_name)

    return {"sinks": sinks, "sources": sources}


def get_device_description(device_name: str) -> str:
    """Получить читаемое описание устройства"""
    # Проверяем sinks
    result = subprocess.run(
        ["pactl", "list", "sinks"],
        capture_output=True, text=True
    )
    for block in result.stdout.split("\n\n"):
        if device_name in block:
            match = re.search(r'device\.description\s*=\s*"([^"]+)"', block)
            if match:
                return match.group(1)
            match = re.search(r'alsa\.card_name\s*=\s*"([^"]+)"', block)
            if match:
                return match.group(1)

    # Проверяем sources
    result = subprocess.run(
        ["pactl", "list", "sources"],
        capture_output=True, text=True
    )
    for block in result.stdout.split("\n\n"):
        if device_name in block:
            match = re.search(r'device\.description\s*=\s*"([^"]+)"', block)
            if match:
                return match.group(1)
            match = re.search(r'alsa\.card_name\s*=\s*"([^"]+)"', block)
            if match:
                return match.group(1)

    return device_name


def create_virtual_sinks(output_device: str, input_device: str) -> list[str]:
    """
    Создать два виртуальных sink'а для раздельной записи.
    Возвращает список ID созданных модулей.
    """
    cleanup_virtual_sinks()
    time.sleep(0.3)

    module_ids = []

    # Sink для звука с ПК
    result = subprocess.run(
        ["pactl", "load-module", "module-null-sink",
         "sink_name=meeting_pc",
         "sink_properties=device.description=Meeting_PC",
         "rate=16000", "channels=1"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"Не удалось создать sink для ПК: {result.stderr}")
    module_ids.append(result.stdout.strip())

    # Loopback: монитор вывода ПК → meeting_pc
    result = subprocess.run(
        ["pactl", "load-module", "module-loopback",
         f"source={output_device}.monitor",
         "sink=meeting_pc"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        cleanup_virtual_sinks()
        raise RuntimeError(f"Не удалось создать loopback для ПК: {result.stderr}")
    module_ids.append(result.stdout.strip())

    # Sink для микрофона
    result = subprocess.run(
        ["pactl", "load-module", "module-null-sink",
         "sink_name=meeting_mic",
         "sink_properties=device.description=Meeting_Mic",
         "rate=16000", "channels=1"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        cleanup_virtual_sinks()
        raise RuntimeError(f"Не удалось создать sink для микрофона: {result.stderr}")
    module_ids.append(result.stdout.strip())

    # Loopback: микрофон → meeting_mic
    result = subprocess.run(
        ["pactl", "load-module", "module-loopback",
         f"source={input_device}",
         "sink=meeting_mic"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        cleanup_virtual_sinks()
        raise RuntimeError(f"Не удалось создать loopback для микрофона: {result.stderr}")
    module_ids.append(result.stdout.strip())

    # Сохраняем ID модулей
    SINK_FILE.write_text(",".join(module_ids))
    log(f"Созданы virtual sinks: {module_ids}")

    return module_ids


def cleanup_virtual_sinks():
    """Удалить все виртуальные sink'и и loopback-модули"""
    # Удаляем по сохранённым ID
    if SINK_FILE.exists():
        module_ids = SINK_FILE.read_text().strip().split(",")
        for module_id in module_ids:
            if module_id:
                subprocess.run(["pactl", "unload-module", module_id], capture_output=True)
        SINK_FILE.unlink(missing_ok=True)
        log(f"Удалены модули: {module_ids}")

    # Дополнительная очистка на случай если что-то осталось
    result = subprocess.run(
        ["pactl", "list", "short", "modules"],
        capture_output=True, text=True
    )
    for line in result.stdout.strip().split("\n"):
        if "module-loopback" in line or "module-null-sink" in line:
            parts = line.split("\t")
            if len(parts) >= 1:
                module_id = parts[0]
                # Проверяем, что это наши модули
                if any(x in line for x in ["meeting_pc", "meeting_mic"]):
                    subprocess.run(["pactl", "unload-module", module_id], capture_output=True)