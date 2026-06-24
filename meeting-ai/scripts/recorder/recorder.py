"""
Основная логика записи.
Сегментация по 10 минут, только mix, без debug.
"""
import os
import signal
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path
from datetime import datetime

from . import devices
from .vu_meter import dual_vu_meter, format_duration

# ANSI цвета
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"
BLINK = "\033[5m"

BASE_DIR = Path.home() / "Yandex.Disk/carrier/meeting-ai"
AUDIO_DIR = BASE_DIR / "audio"
PID_FILE = BASE_DIR / ".recorder.pid"
LOG_FILE = BASE_DIR / "recorder.log"


def log(message: str):
    """Логирование в файл"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {message}\n")


def get_pid() -> str | None:
    """Получить данные PID-файла"""
    if not PID_FILE.exists():
        return None
    try:
        data = PID_FILE.read_text().strip()
        parts = data.split(",")
        if len(parts) >= 2:
            os.kill(int(parts[0]), 0)
        return data
    except (ValueError, ProcessLookupError, PermissionError):
        PID_FILE.unlink(missing_ok=True)
        return None

def set_meeting_type(type_key: str):
    """Установить тип встречи для следующей записи"""
    start_recording._meeting_type = type_key

def start_recording(output_device: str, input_device: str):
    """Начать запись с сегментацией по 10 минут"""
    pid_data = get_pid()
    if pid_data:
        print(f"{YELLOW}⚠️  Запись уже идёт{RESET}")
        print(f"   Остановите: {BOLD}meeting stop{RESET}")
        return None

    AUDIO_DIR.mkdir(parents=True, exist_ok=True)

    # Создание папки созвона
    from . import config

    # Получаем тип встречи из аргументов (будет передан из cli)
    meeting_type_key = getattr(start_recording, '_meeting_type', 'default')
    meeting_type = config.get_meeting_type(meeting_type_key)
    audio_subdir = meeting_type.get("audio_subdir", "")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Если есть подпапка для типа, создаём её
    if audio_subdir:
        base_audio_dir = AUDIO_DIR / audio_subdir
    else:
        base_audio_dir = AUDIO_DIR

    meeting_dir = base_audio_dir / f"meeting_{timestamp}"
    meeting_dir.mkdir(parents=True, exist_ok=True)

    # Сохраняем тип встречи в метаданных
    (meeting_dir / ".meeting_type").write_text(meeting_type_key)

    # Создание виртуальных sink'ов
    print(f"{CYAN}🔧 Создаю виртуальные устройства...{RESET}")
    try:
        devices.create_virtual_sinks(output_device, input_device)
    except RuntimeError as e:
        print(f"{RED}❌ {e}{RESET}")
        return None

    time.sleep(0.5)

    # Запуск FFmpeg с сегментацией по 3 минуты
    segment_pattern = str(meeting_dir / "segment_%03d.wav")

    ffmpeg_cmd = [
        "ffmpeg", "-y", "-loglevel", "quiet",
        "-f", "pulse", "-i", "meeting_pc.monitor",
        "-f", "pulse", "-i", "meeting_mic.monitor",
        "-filter_complex",
        "[0:a][1:a]amix=inputs=2:duration=longest:normalize=0[out]",
        "-map", "[out]",
        "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
        "-f", "segment", "-segment_time", "180",
        "-reset_timestamps", "1",
        segment_pattern
    ]

    ffmpeg_proc = subprocess.Popen(ffmpeg_cmd, start_new_session=True)

    # Сохраняем PID и метаданные
    PID_FILE.write_text(f"{ffmpeg_proc.pid},,{timestamp}")
    (meeting_dir / ".metadata").write_text(timestamp)
    log(f"Запись начата: {meeting_dir}")

    # VU-метр
    levels = {"pc": 0.0, "mic": 0.0}
    levels_lock = threading.Lock()

    def read_level(device: str, key: str):
        try:
            proc = subprocess.Popen(
                ["parec", f"--device={device}",
                 "--rate=16000", "--channels=1",
                 "--format=s16le", "--latency-msec=100"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
            )
            while proc.poll() is None:
                raw = proc.stdout.read(3200)
                if raw and len(raw) >= 2:
                    n_samples = len(raw) // 2
                    samples = struct.unpack(f'<{n_samples}h', raw[:n_samples * 2])
                    rms = (sum(s * s for s in samples) / n_samples) ** 0.5
                    level = min(rms / 16384.0, 1.0)
                    with levels_lock:
                        levels[key] = level
        except Exception:
            pass

    thread_pc = threading.Thread(target=read_level, args=("meeting_pc.monitor", "pc"), daemon=True)
    thread_mic = threading.Thread(target=read_level, args=("meeting_mic.monitor", "mic"), daemon=True)
    thread_pc.start()
    thread_mic.start()

    # UI
    print(f"\n{BOLD}{RED}● REC{RESET} {DIM}Запись начата{RESET}")
    print(f"{DIM}Папка: {meeting_dir.name}{RESET}")
    print(f"{DIM}Сегменты: по 3 минуты{RESET}")
    print(f"{DIM}Ctrl+C для остановки{RESET}")
    print(f"{'─' * 60}")

    start_time = time.time()

    try:
        while ffmpeg_proc.poll() is None:
            elapsed = time.time() - start_time
            duration_str = format_duration(elapsed)

            with levels_lock:
                pc_level = levels["pc"]
                mic_level = levels["mic"]

            vu_display = dual_vu_meter(pc_level, mic_level)
            rec_dot = f"{RED}{BLINK}●{RESET}" if int(elapsed * 2) % 2 == 0 else f"{RED}●{RESET}"

            print(f"\033[2K\r{rec_dot} {BOLD}{duration_str}{RESET}")
            print(f"\033[2K{vu_display}", end="\r\033[2A", flush=True)

            time.sleep(0.1)

    except KeyboardInterrupt:
        pass

    # Остановка
    print(f"\n\n{YELLOW}⏹ Остановка записи...{RESET}")

    try:
        ffmpeg_proc.send_signal(signal.SIGINT)
        for _ in range(30):
            if ffmpeg_proc.poll() is not None:
                break
            time.sleep(0.1)
        else:
            ffmpeg_proc.kill()
    except Exception:
        pass

    devices.cleanup_virtual_sinks()
    PID_FILE.unlink(missing_ok=True)

    # Подсчёт сегментов
    segments = sorted(meeting_dir.glob("segment_*.wav"))
    if not segments:
        print(f"{RED}❌ Сегменты не созданы{RESET}")
        return None

    total_duration = sum(max(0, (s.stat().st_size - 44)) / 32000 for s in segments)

    if total_duration < 5:
        print(f"{YELLOW}⚠️  Запись слишком короткая ({total_duration:.1f} сек) — удаляю{RESET}")
        import shutil
        shutil.rmtree(meeting_dir)
        return None

    print(f"\n{GREEN}✅ Запись сохранена: {meeting_dir.name}{RESET}")
    print(f"{DIM}   Сегментов: {len(segments)}{RESET}")
    print(f"{DIM}   Длительность: {format_duration(total_duration)}{RESET}")

    return meeting_dir


def stop_recording():
    """Остановить запись"""
    pid_data = PID_FILE.read_text().strip() if PID_FILE.exists() else None
    if not pid_data:
        print(f"{YELLOW}⚠️  Запись не запущена{RESET}")
        return None

    parts = pid_data.split(",")
    if len(parts) < 3:
        PID_FILE.unlink(missing_ok=True)
        return None

    ffmpeg_pid, _, timestamp = parts[0], parts[1] if len(parts) > 1 else "", parts[2] if len(parts) > 2 else ""

    print(f"{YELLOW}⏹ Останавливаю запись...{RESET}")

    try:
        pid = int(ffmpeg_pid)
        os.kill(pid, signal.SIGINT)
        for _ in range(30):
            try:
                os.kill(pid, 0)
                time.sleep(0.1)
            except ProcessLookupError:
                break
    except (ValueError, ProcessLookupError):
        pass

    devices.cleanup_virtual_sinks()
    PID_FILE.unlink(missing_ok=True)

    # Найти папку созвона
    meeting_dir = AUDIO_DIR / f"meeting_{timestamp}"
    if not meeting_dir.exists():
        print(f"{RED}❌ Папка не найдена{RESET}")
        return None

    segments = sorted(meeting_dir.glob("segment_*.wav"))
    if not segments:
        print(f"{RED}❌ Сегменты не найдены{RESET}")
        return None

    total_duration = sum(max(0, (s.stat().st_size - 44)) / 32000 for s in segments)

    if total_duration < 5:
        print(f"{YELLOW}⚠️  Запись слишком короткая — удаляю{RESET}")
        import shutil
        shutil.rmtree(meeting_dir)
        return None

    print(f"{GREEN}✅ Запись остановлена: {meeting_dir.name}{RESET}")
    print(f"{DIM}   Сегментов: {len(segments)}, длительность: {format_duration(total_duration)}{RESET}")
    return meeting_dir


def show_status():
    """Показать статус"""
    pid_data = PID_FILE.read_text().strip() if PID_FILE.exists() else None

    if pid_data:
        parts = pid_data.split(",")
        if len(parts) >= 3:
            timestamp = parts[2]
            meeting_dir = AUDIO_DIR / f"meeting_{timestamp}"

            if meeting_dir.exists():
                segments = sorted(meeting_dir.glob("segment_*.wav"))
                if segments:
                    # Оценка по последнему сегменту
                    last_seg = segments[-1]
                    size = last_seg.stat().st_size
                    duration_sec = max(0, (size - 44)) / 32000
                    total_duration = (len(segments) - 1) * 180 + duration_sec
                    duration_str = format_duration(total_duration)
                else:
                    duration_str = "??:??"
            else:
                duration_str = "??:??"

            print(f"\n{RED}{BLINK}●{RESET} {BOLD}ЗАПИСЬ ИДЁТ{RESET}")
            print(f"  PID:          {parts[0]}")
            print(f"  Длительность: {duration_str}")
            print(f"  Режим:        {GREEN}Сегменты по 3 мин{RESET}")
            print(f"  Остановить:   {BOLD}meeting stop{RESET}\n")
    else:
        audio_dirs = list(AUDIO_DIR.glob("meeting_*"))
        audio_dirs = [d for d in audio_dirs if d.is_dir()]
        transcript_dirs = list((BASE_DIR / "transcripts").glob("meeting_*")) if (BASE_DIR / "transcripts").exists() else []

        from . import config
        output_dev, input_dev = config.get_configured_devices()
        configured = bool(output_dev and input_dev)

        print(f"\n{DIM}●{RESET} Запись не запущена")
        print(f"  Записей:      {len(audio_dirs)}")
        print(f"  Обработано:   {len(transcript_dirs)}")
        if configured:
            print(f"  Устройства:   {GREEN}настроены{RESET}")
        else:
            print(f"  Устройства:   {YELLOW}не настроены{RESET} ({BOLD}meeting config{RESET})")
        print(f"  Запустить:    {BOLD}meeting start{RESET}\n")


def process_latest():
    """Обработать последнюю запись"""
    print(f"\n{CYAN}🔄 Запускаю обработку...{RESET}\n")

    script = Path(__file__).parent.parent / "process_meeting.py"
    if not script.exists():
        print(f"{RED}❌ process_meeting.py не найден{RESET}")
        return

    subprocess.run([sys.executable, str(script)], cwd=str(BASE_DIR))