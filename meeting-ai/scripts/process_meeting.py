#!/usr/bin/env python3
"""
Обработка записи встречи: транскрипция + суммаризация.
Поддерживает локальную (faster-whisper) и облачную транскрипцию,
а также универсальную AI-суммаризацию через OpenAI-compatible API.
"""
import os
import sys
import json
from pathlib import Path
from datetime import datetime

# ANSI-коды цветов для вывода
YELLOW = '\033[93m'
CYAN = '\033[96m'
RESET = '\033[0m'

# Отключение прокси
for var in ['http_proxy', 'https_proxy', 'all_proxy',
            'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY']:
    os.environ.pop(var, None)

BASE_DIR = Path.home() / "Yandex.Disk/carrier/meeting-ai"

# Импортируем модуль логирования
sys.path.insert(0, str(BASE_DIR / "web" / "routes"))
from logs import log_action

AUDIO_DIR = BASE_DIR / "audio"
TRANSCRIPTS_DIR = BASE_DIR / "transcripts"
SUMMARIES_DIR = BASE_DIR / "summaries"

# Импортируем модуль прогресса
sys.path.insert(0, str(BASE_DIR / "scripts"))
from progress import save_progress, clear_progress

# Импортируем конфиг моделей (перед загрузкой whisper, чтобы не ждать)
from recorder.models_config import (
    get_default_summarization_model,
    get_default_transcription_model,
    load_models,
    ensure_config_exists,
)
from recorder.ai_client import chat_completion_text, audio_transcription, AIModelError

# Проверяем конфиг перед загрузкой тяжелых моделей
_config_issues = ensure_config_exists()
if _config_issues:
    print(f"{YELLOW}⚠️  Проблемы с конфигурацией AI-моделей:{RESET}")
    for issue in _config_issues:
        print(f"   - {issue}")
    print()

# Определяем режим транскрипции ДО загрузки whisper (экономия памяти)
TRANSCRIPTION_MODE = get_default_transcription_model()

# Загружаем локальную модель только если она нужна
whisper_model = None
if TRANSCRIPTION_MODE == "local":
    from faster_whisper import WhisperModel
    print("🔄 Загружаю модель faster-whisper (medium, CPU, int8)...")
    whisper_model = WhisperModel("medium", device="cpu", compute_type="int8")
    print("✅ Whisper загружен")
else:
    print(f"{CYAN}☁️  Транскрипция через облачную модель: {TRANSCRIPTION_MODE}{RESET}")
    print(f"{CYAN}   Локальная модель Whisper не загружена (экономия ~2GB RAM){RESET}")


def transcribe_audio(audio_path, meeting_id: str = "UNKNOWN") -> list:
    """
    Транскрипция аудио — локальная или облачная, в зависимости от конфига.

    Читает default_transcription из models.json:
      - "local" → faster-whisper
      - имя модели → облачная транскрипция через API
    """
    mode = get_default_transcription_model()

    if mode == "local":
        return _transcribe_local(audio_path)
    else:
        return _transcribe_cloud(audio_path, mode, meeting_id=meeting_id)


def _transcribe_local(audio_path) -> list:
    """Локальная транскрипция через faster-whisper."""
    global whisper_model
    if whisper_model is None:
        from faster_whisper import WhisperModel
        print("🔄 Загружаю модель faster-whisper (lazy)...")
        whisper_model = WhisperModel("medium", device="cpu", compute_type="int8")
        print("✅ Whisper загружен")

    audio_path = str(audio_path)
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
        raise Exception(f"Ошибка локальной транскрипции: {str(e)}")


def _transcribe_cloud(audio_path, model_key: str, meeting_id: str = "UNKNOWN") -> list:
    """
    Облачная транскрипция через OpenAI-compatible /audio/transcriptions.

    Конвертирует ответ API в формат, совместимый с локальной транскрипцией:
    [{"start": float, "end": float, "text": str}, ...]
    """
    try:
        response = audio_transcription(model_key, str(audio_path), meeting_id=meeting_id)
    except AIModelError as e:
        # Fallback на локальную при недоступности облака
        print(f"{YELLOW}⚠️  Облачная транскрипция недоступна: {e}{RESET}")
        print(f"{YELLOW}   Переключаюсь на локальную транскрипцию...{RESET}")
        log_action(meeting_id, "transcript",
                   f"Облачная транскрипция недоступна, fallback на локальную: {e}",
                   level="warning", details={"model": model_key})
        return _transcribe_local(audio_path)
    except Exception as e:
        print(f"{YELLOW}⚠️  Ошибка облачной транскрипции: {e}{RESET}")
        print(f"{YELLOW}   Переключаюсь на локальную транскрипцию...{RESET}")
        log_action(meeting_id, "transcript",
                   f"Fallback на локальную транскрипцию из-за ошибки: {e}",
                   level="warning", details={"model": model_key})
        return _transcribe_local(audio_path)

    # Парсим ответ — зависит от формата провайдера
    return _parse_transcription_response(response, model_key)


def _parse_transcription_response(response: dict, model_key: str) -> list:
    """
    Разобрать ответ облачной транскрипции в список сегментов.

    Поддерживает форматы:
      - verbose_json OpenAI: {"segments": [{"start": ..., "end": ..., "text": ...}]}
      - MAI-Transcribe: {"text": "..."} (без сегментов)
    """
    # verbose_json с сегментами
    segments = response.get("segments")
    if segments:
        result = []
        for seg in segments:
            result.append({
                "start": seg.get("start", 0),
                "end": seg.get("end", 0),
                "text": (seg.get("text", "") or "").strip()
            })
        return result

    # Просто текст (MAI-Transcribe и подобные)
    full_text = response.get("text", "")
    if full_text:
        # Возвращаем как один сегмент
        return [{"start": 0.0, "end": 0.0, "text": full_text.strip()}]

    # Неизвестный формат — пробуем сериализовать
    print(f"{YELLOW}⚠️  Неизвестный формат ответа транскрипции от '{model_key}'{RESET}")
    log_action("UNKNOWN", "transcript",
               f"Неизвестный формат ответа транскрипции",
               level="warning",
               details={"model": model_key, "response_keys": list(response.keys())})
    return []


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


def summarize_with_ai(transcript: str, meeting_type_key: str = "default", meeting_id: str = "UNKNOWN") -> dict:
    """
    Суммаризация через AI-модель из models.json.

    Использует default_summarization из models.json.
    Промпт берётся из meeting_types.json (как раньше).
    """
    from recorder import config as meeting_config

    meeting_type = meeting_config.get_meeting_type(meeting_type_key)
    prompt_template = meeting_type.get("prompt", "")

    if not prompt_template:
        print(f"{YELLOW}⚠️  Промпт не найден для типа {meeting_type_key}, использую default{RESET}")
        meeting_type = meeting_config.get_meeting_type("default")
        prompt_template = meeting_type.get("prompt", "")

    # Обрезаем транскрипт если слишком длинный
    max_chars = 15000
    if len(transcript) > max_chars:
        transcript = transcript[:max_chars] + "\n\n[... транскрипт обрезан ...]"

    # Подставляем транскрипт в промпт
    user_prompt = prompt_template.replace("{transcript}", transcript)

    # Получаем имя модели из конфига
    model_key = get_default_summarization_model()
    if not model_key:
        error_msg = "default_summarization не задан в models.json"
        print(f"❌ {error_msg}")
        log_action(meeting_id, "summary", error_msg, level="error")
        return {}

    print(f"🤖 Суммаризирую через {model_key} (тип: {meeting_type.get('name', meeting_type_key)})...")

    try:
        response_text = chat_completion_text(
            model_key=model_key,
            system_prompt="Ты — AI-ассистент для анализа рабочих встреч. Отвечай строго в формате JSON.",
            user_prompt=user_prompt,
            timeout=120,
            json_mode=True,
            meeting_id=meeting_id,
        )

        if not response_text:
            error_msg = "Пустой ответ от модели"
            print(f"❌ {error_msg}")
            log_action(meeting_id, "summary", error_msg, level="error")
            return {}

        # Парсим JSON из ответа
        try:
            if "```json" in response_text:
                json_str = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                json_str = response_text.split("```")[1].split("```")[0].strip()
            else:
                json_str = response_text

            summary = json.loads(json_str)
            print(f"✅ Суммаризация получена: {summary.get('title', 'без_названия')}")
            log_action(meeting_id, "summary",
                       f"Суммаризация получена: {summary.get('title', 'без_названия')}",
                       level="success",
                       details={"model": model_key, "response_length": len(response_text)})
            return summary

        except json.JSONDecodeError as e:
            error_msg = f"Не удалось распарсить JSON: {e}"
            print(f"⚠️ {error_msg}")
            log_action(meeting_id, "summary", error_msg, level="error",
                       details={"json_error": str(e), "response_preview": response_text[:500]})
            return {"title": "без_названия", "summary": response_text,
                    "action_items": [], "career_insights": []}

    except AIModelError as e:
        error_msg = f"Ошибка AI-модели: {e}"
        print(f"❌ {error_msg}")
        log_action(meeting_id, "summary", error_msg, level="error",
                   details={"model": model_key, "error": str(e)})
        return {}

    except Exception as e:
        error_msg = f"Неизвестная ошибка суммаризации: {e}"
        print(f"❌ {error_msg}")
        log_action(meeting_id, "summary", error_msg, level="error",
                   details={"model": model_key, "error": str(e)})
        return {}


# Обратная совместимость: старый код может вызывать summarize_with_kodacode
def summarize_with_kodacode(transcript: str, meeting_type_key: str = "default") -> dict:
    """Устаревшая функция — перенаправляет на summarize_with_ai."""
    return summarize_with_ai(transcript, meeting_type_key)


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

    # Определяем модель транскрипции для логирования
    transcription_model = get_default_transcription_model()

    # Логирование
    log_action(meeting_name, "all", f"Начало обработки: {input_path.name}, тип: {meeting_type_key}",
               details={"transcription_model": transcription_model})

    try:
        if input_path.is_dir():
            # Папка с сегментами
            segments = sorted(input_path.glob("segment_*.wav"))
            if not segments:
                error_msg = "Нет сегментов для обработки"
                print(f"❌ {error_msg}")
                save_progress(meeting_name, "error", error_msg, 0)
                log_action(meeting_name, "all", error_msg, level="error")
                return

            print(f"Обрабатываю папку: {input_path.name} ({len(segments)} сегментов)")
            print(f"   Модель транскрипции: {transcription_model}")
            save_progress(meeting_name, "processing", f"Транскрипция: 0/{len(segments)}", 0)
            log_action(meeting_name, "transcript", f"Найдено {len(segments)} сегментов",
                       details={"model": transcription_model})

            all_transcripts = []
            total_seg = len(segments)
            for i, segment in enumerate(segments, 1):
                progress = ((i - 1) / total_seg) * 70  # 0-70% для транскрипции
                save_progress(meeting_name, "processing", f"Транскрипция сегмента {i}/{total_seg}: {segment.name} [{transcription_model}]", progress)
                print(f"\n📼 Сегмент {i}/{total_seg} [{transcription_model}]")
                log_action(meeting_name, "transcript", f"Транскрипция сегмента {i}/{total_seg}: {segment.name}",
                           details={"model": transcription_model})

                # Транскрипция
                try:
                    whisper_segs = transcribe_audio(str(segment), meeting_id=meeting_name)
                    print(f"   Найдено {len(whisper_segs)} фраз")
                    log_action(meeting_name, "transcript", f"Сегмент {segment.name}: {len(whisper_segs)} фраз",
                               details={"count": len(whisper_segs), "model": transcription_model})

                    if whisper_segs:
                        transcript = format_transcript(whisper_segs)
                        if transcript:
                            all_transcripts.append(transcript)
                except Exception as e:
                    error_msg = f"Ошибка транскрипции сегмента {segment.name}: {str(e)}"
                    print(f"❌ {error_msg}")
                    save_progress(meeting_name, "error", error_msg, progress)
                    log_action(meeting_name, "transcript", error_msg, level="error",
                               details={"segment": segment.name, "error": str(e), "model": transcription_model})
                    return

        else:
            # Один файл
            print(f"Обрабатываю файл: {input_path.name} [{transcription_model}]")
            save_progress(meeting_name, "processing", f"Транскрипция одного файла [{transcription_model}]", 0)
            log_action(meeting_name, "transcript", f"Транскрипция одного файла: {input_path.name}",
                       details={"model": transcription_model})

            try:
                whisper_segs = transcribe_audio(str(input_path), meeting_id=meeting_name)
                print(f"   Найдено {len(whisper_segs)} фраз")
                log_action(meeting_name, "transcript", f"Файл {input_path.name}: {len(whisper_segs)} фраз",
                           details={"count": len(whisper_segs), "model": transcription_model})

                if whisper_segs:
                    transcript = format_transcript(whisper_segs)
                    all_transcripts = [transcript]
                else:
                    all_transcripts = []
            except Exception as e:
                error_msg = f"Ошибка транскрипции: {str(e)}"
                print(f"❌ {error_msg}")
                save_progress(meeting_name, "error", error_msg, 0)
                log_action(meeting_name, "transcript", error_msg, level="error",
                           details={"error": str(e), "model": transcription_model})
                return

        if not all_transcripts:
            error_msg = "Не удалось транскрибировать"
            print(f"❌ {error_msg}")
            save_progress(meeting_name, "error", error_msg, 0)
            log_action(meeting_name, "transcript", error_msg, level="error",
                       details={"model": transcription_model})
            return

        full_transcript = "\n\n---\n\n".join(all_transcripts)
        print(f"\n📝 Полный транскрипт: {len(full_transcript)} символов [{transcription_model}]")
        save_progress(meeting_name, "processing", "Транскрипция завершена", 70)
        log_action(meeting_name, "transcript", f"Транскрипция завершена: {len(full_transcript)} символов",
                   details={"chars": len(full_transcript), "model": transcription_model})

        # Суммаризация с учётом типа
        model_key = get_default_summarization_model()
        save_progress(meeting_name, "processing", f"Суммаризация через {model_key}...", 75)
        log_action(meeting_name, "summary", f"Начало суммаризации через {model_key}", details={"type": meeting_type_key, "model": model_key})
        try:
            summary = summarize_with_ai(full_transcript, meeting_type_key, meeting_id=meeting_name)
        except Exception as e:
            error_msg = f"Ошибка суммаризации: {str(e)}"
            print(f"❌ {error_msg}")
            save_progress(meeting_name, "error", error_msg, 75)
            log_action(meeting_name, "summary", error_msg, level="error", details={"error": str(e)})
            return

        if not summary:
            warning_msg = f"Модель {model_key} не вернула суммаризацию, сохраняю только транскрипт"
            print(f"⚠️ {warning_msg}")
            log_action(meeting_name, "summary", warning_msg, level="warning")
            summary = {
                "title": "без_суммаризации",
                "summary": "Не удалось получить суммаризацию от AI-модели",
                "action_items": [],
                "decisions": [],
                "career_insights": []
            }
        else:
            log_action(meeting_name, "summary", "Суммаризация успешно получена", details={"title": summary.get("title", ""), "model": model_key})

        meeting_id = input_path.stem if input_path.is_file() else input_path.name
        save_results(meeting_id, full_transcript, summary, meeting_type_key, meeting_dir=input_path)

        save_progress(meeting_name, "done", "Готово", 100)
        log_action(meeting_name, "all", "Обработка завершена успешно", level="success")
        print(f"✅ Обработка завершена: {meeting_name}")

        # Удаляем файл прогресса после успешного завершения
        clear_progress(meeting_name)
        print("🗑️ Файл прогресса удалён")

    except Exception as e:
        error_msg = f"Неизвестная ошибка: {str(e)}"
        print(f"❌ {error_msg}")
        save_progress(meeting_name, "error", error_msg, 0)
        log_action(meeting_name, "all", error_msg, level="error", details={"error": str(e), "traceback": str(e)})

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