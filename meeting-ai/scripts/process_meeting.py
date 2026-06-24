#!/usr/bin/env python3
"""
Обработка записи встречи: транскрипция + суммаризация.
"""
import os
import sys
import subprocess
import json
from pathlib import Path
from datetime import datetime

# ANSI-коды цветов для вывода
YELLOW = '\033[93m'
RESET = '\033[0m'

# Отключение прокси
for var in ['http_proxy', 'https_proxy', 'all_proxy',
            'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY']:
    os.environ.pop(var, None)

from faster_whisper import WhisperModel

BASE_DIR = Path.home() / "Yandex.Disk/carrier/meeting-ai"
AUDIO_DIR = BASE_DIR / "audio"
TRANSCRIPTS_DIR = BASE_DIR / "transcripts"
SUMMARIES_DIR = BASE_DIR / "summaries"

# Импортируем модуль прогресса
sys.path.insert(0, str(BASE_DIR / "scripts"))
from progress import save_progress, clear_progress

# Загрузка модели Whisper
print("🔄 Загружаю модель faster-whisper...")
whisper_model = WhisperModel("medium", device="cpu", compute_type="int8")
print("✅ Whisper загружен")

# Глобальная переменная для модели диаризации (убрана)


def transcribe_audio(audio_path: str) -> list:
    """Транскрипция аудио, возврат сегментов с таймкодами"""
    try:
        segments, info = whisper_model.transcribe(
            audio_path,
            beam_size=5,
            language="ru",
            vad_filter=True,
            word_timestamps=False
        )

        result = []
        for seg in segments:
            result.append({
                "start": seg.start,
                "end": seg.end,
                "text": seg.text.strip()
            })
        return result
    except Exception as e:
        raise Exception(f"Ошибка транскрипции: {str(e)}")


def format_transcript(segments: list) -> str:
    """Форматирование транскрипта без диаризации"""
    if not segments:
        return ""

    lines = []
    for seg in segments:
        text = seg["text"]
        start = seg["start"]

        # Форматирование времени
        minutes = int(start // 60)
        seconds = int(start % 60)
        time_str = f"{minutes:02d}:{seconds:02d}"

        lines.append(f"[{time_str}] {text}")

    return "\n".join(lines)


def summarize_with_kodacode(transcript: str, meeting_type_key: str = "default") -> dict:
    """Суммаризация через KodaCode CLI с промптом из конфига"""
    from recorder import config

    meeting_type = config.get_meeting_type(meeting_type_key)
    prompt_template = meeting_type.get("prompt", "")

    if not prompt_template:
        print(f"{YELLOW}⚠️  Промпт не найден для типа {meeting_type_key}, использую default{RESET}")
        meeting_type = config.get_meeting_type("default")
        prompt_template = meeting_type.get("prompt", "")

    # Обрезаем транскрипт если слишком длинный
    max_chars = 15000
    if len(transcript) > max_chars:
        transcript = transcript[:max_chars] + "\n\n[... транскрипт обрезан ...]"

    # Подставляем транскрипт в промпт
    prompt = prompt_template.replace("{transcript}", transcript)

    print(f"🤖 Суммаризирую через KodaCode (тип: {meeting_type.get('name', meeting_type_key)})...")

    try:
        result = subprocess.run(
            ["koda", "-p", prompt],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(Path.home())
        )

        if result.returncode != 0:
            print(f"❌ Ошибка KodaCode: {result.stderr[:200]}")
            return {}

        response_text = result.stdout.strip()

        if not response_text:
            print("❌ Пустой ответ от KodaCode")
            return {}

        try:
            if "```json" in response_text:
                json_str = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                json_str = response_text.split("```")[1].split("```")[0].strip()
            else:
                json_str = response_text

            summary = json.loads(json_str)
            return summary

        except json.JSONDecodeError as e:
            print(f"⚠️ Не удалось распарсить JSON: {e}")
            return {"title": "без_названия", "summary": response_text,
                    "action_items": [], "career_insights": []}

    except subprocess.TimeoutExpired:
        print("❌ KodaCode не ответил за 120 секунд")
        return {}
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return {}


def save_results(meeting_id: str, transcript: str, summary: dict, meeting_type_key: str = "default", meeting_dir: Path = None):
    """Сохранение результатов с учётом типа встречи.

    meeting_dir — путь к аудио-папке, куда записывается meeting_metadata.json
    """
    from recorder import config

    meeting_type = config.get_meeting_type(meeting_type_key)
    transcript_subdir = meeting_type.get("transcript_subdir", "")
    summary_subdir = meeting_type.get("summary_subdir", "")

    timestamp = datetime.now().strftime("%Y%m%d")
    title = summary.get("title", "без_названия")

    # Для имени папки используем meeting_id (имя аудио-папки), чтобы совпадало с веб-интерфейсом
    result_id = meeting_id

    # Если есть подпапка для типа, создаём её
    if transcript_subdir:
        base_transcript_dir = TRANSCRIPTS_DIR / transcript_subdir
    else:
        base_transcript_dir = TRANSCRIPTS_DIR

    if summary_subdir:
        base_summary_dir = SUMMARIES_DIR / summary_subdir
    else:
        base_summary_dir = SUMMARIES_DIR

    transcript_dir = base_transcript_dir / result_id
    summary_dir = base_summary_dir / result_id
    transcript_dir.mkdir(parents=True, exist_ok=True)
    summary_dir.mkdir(parents=True, exist_ok=True)

    with open(transcript_dir / "transcript.txt", "w", encoding="utf-8") as f:
        f.write(transcript)

    with open(summary_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    with open(summary_dir / "summary.md", "w", encoding="utf-8") as f:
        f.write(f"# {title}\n\n")
        f.write(f"**Дата:** {timestamp}\n\n")
        f.write(f"**Тип:** {meeting_type.get('name', meeting_type_key)}\n\n")

        # Для backend daily — специальная структура
        if meeting_type_key == "bd":
            f.write("## Участники\n")
            for p in summary.get("participants", []):
                f.write(f"- {p}\n")

            f.write("\n## Что сделали вчера\n")
            for item in summary.get("yesterday", []):
                f.write(f"\n**{item.get('person', 'Неизвестный')}:**\n")
                for task in item.get("tasks", []):
                    f.write(f"- {task}\n")

            f.write("\n## Планы на сегодня\n")
            for item in summary.get("today", []):
                f.write(f"\n**{item.get('person', 'Неизвестный')}:**\n")
                for task in item.get("tasks", []):
                    f.write(f"- {task}\n")
                if item.get("estimated_time"):
                    f.write(f"  _Оценка: {item['estimated_time']}_\n")

            if summary.get("blockers"):
                f.write("\n## Блокеры\n")
                for item in summary.get("blockers", []):
                    f.write(f"\n**{item.get('person', 'Неизвестный')}:**\n")
                    f.write(f"- {item.get('blocker', 'Нет описания')}\n")
                    if item.get("needs_help_from"):
                        f.write(f"  _Нужна помощь от: {item['needs_help_from']}_\n")

            if summary.get("technical_decisions"):
                f.write("\n## Технические решения\n")
                for decision in summary.get("technical_decisions", []):
                    f.write(f"- {decision}\n")

            if summary.get("code_reviews"):
                f.write("\n## Code Reviews\n")
                for review in summary.get("code_reviews", []):
                    f.write(f"- {review}\n")

            if summary.get("estimates"):
                f.write("\n## Оценки задач\n")
                for est in summary.get("estimates", []):
                    f.write(f"- **{est.get('task', 'Задача')}**: {est.get('estimate', '?')} → {est.get('assignee', '?')}\n")

            if summary.get("follow_ups"):
                f.write("\n## Follow-ups\n")
                for fu in summary.get("follow_ups", []):
                    f.write(f"- {fu}\n")
        else:
            # Обычная структура для других типов
            f.write(f"## Краткое содержание\n{summary.get('summary', 'Нет данных')}\n\n")
            f.write("## Задачи\n")
            for item in summary.get("action_items", []):
                f.write(f"- {item}\n")
            f.write("\n## Решения\n")
            for decision in summary.get("decisions", []):
                f.write(f"- {decision}\n")
            f.write("\n## Карьерные инсайты\n")
            for insight in summary.get("career_insights", []):
                f.write(f"- {insight}\n")

    print(f"✅ Результаты сохранены в {summary_dir}")

    # Сохраняем метаданные в аудио-папку
    if meeting_dir:
        metadata = {
            "title": title,
            "transcript_dir": str(transcript_dir),
            "summary_dir": str(summary_dir),
            "type": meeting_type_key,
            "saved_at": datetime.now().isoformat()
        }
        metadata_file = meeting_dir / "meeting_metadata.json"
        with open(metadata_file, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
        print(f"📋 Метаданные сохранены: {metadata_file}")


def process_meeting(input_path: Path, meeting_type_key: str = "default"):
    """Обработка записи (файл или папка с сегментами)"""
    meeting_name = input_path.name

    # Если тип не указан явно, пробуем прочитать из метаданных
    if meeting_type_key == "default" and input_path.is_dir():
        type_file = input_path / ".meeting_type"
        if type_file.exists():
            meeting_type_key = type_file.read_text().strip()

    # Очищаем предыдущий прогресс перед началом
    clear_progress(meeting_name)
    save_progress(meeting_name, "processing", "Инициализация...", 0)

    try:
        if input_path.is_dir():
            # Папка с сегментами
            segments = sorted(input_path.glob("segment_*.wav"))
            if not segments:
                print("❌ Нет сегментов для обработки")
                save_progress(meeting_name, "error", "Нет сегментов для обработки", 0)
                return

            print(f"Обрабатываю папку: {input_path.name} ({len(segments)} сегментов)")
            save_progress(meeting_name, "processing", f"Транскрипция: 0/{len(segments)}", 0)

            all_transcripts = []
            total_seg = len(segments)
            for i, segment in enumerate(segments, 1):
                progress = ((i - 1) / total_seg) * 70  # 0-70% для транскрипции
                save_progress(meeting_name, "processing", f"Транскрипция сегмента {i}/{total_seg}: {segment.name}", progress)
                print(f"\n📼 Сегмент {i}/{total_seg}")

                # Транскрипция
                try:
                    whisper_segs = transcribe_audio(str(segment))
                    print(f"   Найдено {len(whisper_segs)} фраз")

                    if whisper_segs:
                        transcript = format_transcript(whisper_segs)
                        if transcript:
                            all_transcripts.append(transcript)
                except Exception as e:
                    error_msg = f"Ошибка транскрипции сегмента {segment.name}: {str(e)}"
                    print(f"❌ {error_msg}")
                    save_progress(meeting_name, "error", error_msg, progress)
                    return

        else:
            # Один файл
            print(f"Обрабатываю файл: {input_path.name}")
            save_progress(meeting_name, "processing", "Транскрипция одного файла", 0)

            try:
                whisper_segs = transcribe_audio(str(input_path))
                print(f"   Найдено {len(whisper_segs)} фраз")

                if whisper_segs:
                    transcript = format_transcript(whisper_segs)
                    all_transcripts = [transcript]
                else:
                    all_transcripts = []
            except Exception as e:
                error_msg = f"Ошибка транскрипции: {str(e)}"
                print(f"❌ {error_msg}")
                save_progress(meeting_name, "error", error_msg, 0)
                return

        if not all_transcripts:
            print("❌ Не удалось транскрибировать")
            save_progress(meeting_name, "error", "Не удалось транскрибировать аудио", 0)
            return

        full_transcript = "\n\n---\n\n".join(all_transcripts)
        print(f"\n📝 Полный транскрипт: {len(full_transcript)} символов")
        save_progress(meeting_name, "processing", "Транскрипция завершена", 70)

        # Суммаризация с учётом типа
        save_progress(meeting_name, "processing", "Суммаризация через KodaCode...", 75)
        try:
            summary = summarize_with_kodacode(full_transcript, meeting_type_key)
        except Exception as e:
            error_msg = f"Ошибка суммаризации: {str(e)}"
            print(f"❌ {error_msg}")
            save_progress(meeting_name, "error", error_msg, 75)
            return

        if not summary:
            print("⚠️ KodaCode не вернул суммаризацию, сохраняю только транскрипт")
            summary = {
                "title": "без_суммаризации",
                "summary": "Не удалось получить суммаризацию от KodaCode",
                "action_items": [],
                "decisions": [],
                "career_insights": []
            }

        meeting_id = input_path.stem if input_path.is_file() else input_path.name
        save_results(meeting_id, full_transcript, summary, meeting_type_key, meeting_dir=input_path)

        save_progress(meeting_name, "done", "Готово", 100)
        print(f"✅ Обработка завершена: {meeting_name}")

        # Удаляем файл прогресса после успешного завершения
        clear_progress(meeting_name)
        print("🗑️ Файл прогресса удалён")

    except Exception as e:
        error_msg = f"Неизвестная ошибка: {str(e)}"
        print(f"❌ {error_msg}")
        save_progress(meeting_name, "error", error_msg, 0)

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Обработка записи встречи")
    parser.add_argument("path", nargs="?",
                        help="Путь к файлу или папке с сегментами")
    parser.add_argument("--type", dest="meeting_type", default="default",
                        help="Тип встречи (например: bd для backend daily)")
    args = parser.parse_args()

    if args.path:
        target = Path(args.path).resolve()
        if not target.exists():
            print(f"❌ Не найдено: {target}")
            sys.exit(1)
        process_meeting(target, args.meeting_type)
    else:
        # Ищем последнюю папку или файл (включая подпапки)
        dirs = sorted(AUDIO_DIR.glob("**/meeting_*"), reverse=True)
        dirs = [d for d in dirs if d.is_dir()]
        files = sorted(AUDIO_DIR.glob("**/meeting_*.wav"), reverse=True)

        if dirs:
            process_meeting(dirs[0], args.meeting_type)
        elif files:
            process_meeting(files[0], args.meeting_type)
        else:
            print("❌ Нет записей для обработки")
            sys.exit(1)