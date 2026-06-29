"""
CLI-интерфейс Meeting Recorder.
Парсинг аргументов и вызов соответствующих функций.
"""
import argparse
import sys
import os
import json
import subprocess
from pathlib import Path

from . import config, devices, recorder

# ANSI цвета
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def interactive_config():
    """Интерактивная настройка устройств"""
    print(f"\n{BOLD}🎛️  Настройка устройств записи{RESET}\n")

    devs = devices.list_devices()

    if not devs["sinks"]:
        print(f"{RED}❌ Не найдено устройств вывода{RESET}")
        return
    if not devs["sources"]:
        print(f"{RED}❌ Не найдено устройств ввода (микрофонов){RESET}")
        return

    # Выбор устройства вывода
    print(f"{CYAN}📢 Выберите устройство вывода (звук с ПК):{RESET}")
    for i, sink in enumerate(devs["sinks"], 1):
        desc = devices.get_device_description(sink)
        print(f"  {BOLD}{i}{RESET}. {desc}")
        print(f"     {DIM}{sink}{RESET}")

    selected_sink = None
    while True:
        try:
            choice = input(f"\nВаш выбор [1-{len(devs['sinks'])}]: ").strip()
            idx = int(choice) - 1
            if 0 <= idx < len(devs["sinks"]):
                selected_sink = devs["sinks"][idx]
                break
            print(f"{RED}Неверный выбор{RESET}")
        except (ValueError, EOFError):
            print(f"{RED}Введите число{RESET}")

    # Выбор микрофона
    print(f"\n{CYAN}🎤 Выберите микрофон:{RESET}")
    for i, source in enumerate(devs["sources"], 1):
        desc = devices.get_device_description(source)
        print(f"  {BOLD}{i}{RESET}. {desc}")
        print(f"     {DIM}{source}{RESET}")

    selected_source = None
    while True:
        try:
            choice = input(f"\nВаш выбор [1-{len(devs['sources'])}]: ").strip()
            idx = int(choice) - 1
            if 0 <= idx < len(devs["sources"]):
                selected_source = devs["sources"][idx]
                break
            print(f"{RED}Неверный выбор{RESET}")
        except (ValueError, EOFError):
            print(f"{RED}Введите число{RESET}")

    # Сохранение
    from datetime import datetime
    new_config = {
        "output_device": selected_sink,
        "input_device": selected_source,
        "updated_at": datetime.now().isoformat()
    }
    config.save_config(new_config)

    print(f"\n{GREEN}✅ Настройки сохранены в {config.CONFIG_FILE}{RESET}")
    print(f"   Вывод: {selected_sink}")
    print(f"   Вход:  {selected_source}\n")


def show_config():
    """Показать текущую конфигурацию"""
    cfg = config.load_config()
    if not cfg:
        print(f"\n{YELLOW}⚠️  Настройки не заданы{RESET}")
        print(f"   Запустите: {BOLD}meeting config{RESET}\n")
        return

    print(f"\n{BOLD}🎛️  Текущие настройки{RESET}")
    print(f"  Вывод (ПК): {cfg.get('output_device', 'не задан')}")
    print(f"  Вход (микрофон): {cfg.get('input_device', 'не задан')}")
    print(f"  Обновлено: {cfg.get('updated_at', '—')}\n")


def show_devices():
    """Показать все доступные устройства"""
    devs = devices.list_devices()

    print(f"\n{BOLD}📢 Устройства вывода (звук с ПК):{RESET}")
    if devs["sinks"]:
        for sink in devs["sinks"]:
            desc = devices.get_device_description(sink)
            print(f"  • {desc}")
            print(f"    {DIM}{sink}{RESET}")
    else:
        print(f"  {DIM}не найдено{RESET}")

    print(f"\n{BOLD}🎤 Микрофоны:{RESET}")
    if devs["sources"]:
        for source in devs["sources"]:
            desc = devices.get_device_description(source)
            print(f"  • {desc}")
            print(f"    {DIM}{source}{RESET}")
    else:
        print(f"  {DIM}не найдено{RESET}")
    print()

def cmd_start(args):
    """Команда start — только запись"""
    output_dev, input_dev = config.get_configured_devices()
    if not output_dev or not input_dev:
        print(f"{YELLOW}⚠️  Сначала настройте устройства:{RESET}")
        print(f"   {BOLD}meeting config{RESET}\n")
        sys.exit(1)

    # Устанавливаем тип встречи
    meeting_type_key = args.meeting_type
    meeting_type = config.get_meeting_type(meeting_type_key)

    if meeting_type_key != "default":
        print(f"{DIM}Тип встречи: {meeting_type.get('name', meeting_type_key)}{RESET}\n")

    recorder.set_meeting_type(meeting_type_key)

    # Запуск записи
    meeting_dir = recorder.start_recording(output_dev, input_dev)

    if meeting_dir:
        print(f"\n{GREEN}✅ Запись сохранена в {meeting_dir}{RESET}\n")
        print(f"{CYAN}💡 Обработайте запись через веб-интерфейс:{RESET}")
        print(f"   http://localhost:5000/meeting/{meeting_dir.name}")
        print(f"   Нажмите 'Обработать всё' для транскрипции и суммаризации\n")


def cmd_stop(args):
    """Команда stop — только остановка записи"""
    audio_file = recorder.stop_recording()
    if audio_file:
        print(f"\n{GREEN}✅ Запись остановлена: {audio_file}{RESET}\n")


def cmd_status(args):
    """Команда status"""
    recorder.show_status()


def cmd_process(args):
    """Команда process"""
    recorder.process_latest()


def cmd_config(args):
    """Команда config"""
    if args.reset:
        if config.CONFIG_FILE.exists():
            config.CONFIG_FILE.unlink()
            print(f"{GREEN}✅ Настройки сброшены{RESET}")
        else:
            print(f"{DIM}Настройки не заданы{RESET}")
    elif args.show:
        show_config()
    else:
        interactive_config()


def cmd_devices(args):
    """Команда devices"""
    show_devices()

def cmd_models(args):
    """Команда models — управление AI-моделями"""
    from . import models_config

    if args.subcommand == "list":
        _cmd_models_list()
    elif args.subcommand == "test":
        _cmd_models_test(args.model_name)
    elif args.subcommand == "open":
        _cmd_models_open()


def _cmd_models_list():
    """Показать список настроенных моделей"""
    from . import models_config

    print(f"\n{BOLD}🤖 Настроенные AI-модели{RESET}\n")

    try:
        config = models_config.load_models()
    except (FileNotFoundError, ValueError) as e:
        print(f"{RED}❌ {e}{RESET}")
        print(f"\n{DIM}Создайте models.json в {models_config.MODELS_FILE.parent}/{RESET}")
        return

    default_sum = config.get("default_summarization", "")
    default_tr = config.get("default_transcription", "")

    print(f"{CYAN}Суммаризация по умолчанию:{RESET} {BOLD}{default_sum}{RESET}")
    print(f"{CYAN}Транскрипция по умолчанию:{RESET}  {BOLD}{default_tr}{RESET}")
    print()

    models = config.get("models", {})
    if not models:
        print(f"{DIM}Модели не настроены{RESET}")
        return

    for key, model in sorted(models.items()):
        is_sum_default = " ★" if key == default_sum else ""
        is_tr_default = " ★" if key == default_tr else ""

        mtype = model.get("type", "?")
        model_id = model.get("model_id", "?")
        name = model.get("name", key)
        base_url = model.get("base_url", "?")
        api_env = model.get("api_key_env", "нет")

        badges = []
        if is_sum_default:
            badges.append(f"{GREEN}СУММ{is_sum_default}{RESET}")
        if is_tr_default:
            badges.append(f"{CYAN}ТРАНС{is_tr_default}{RESET}")
        badge_str = f" [{' | '.join(badges)}]" if badges else ""

        status = _check_model_status(key, model)

        print(f"  {BOLD}{key}{RESET}{badge_str}")
        print(f"    {DIM}{name} — {model_id} ({mtype}){RESET}")
        print(f"    {DIM}URL: {base_url}{RESET}")
        print(f"    {DIM}Ключ: {api_env}{RESET}")
        print(f"    {status}")
        print()


def _check_model_status(key: str, model: dict) -> str:
    """Проверить доступность модели (без реального запроса)"""
    import os
    api_env = model.get("api_key_env")
    if api_env and not os.environ.get(api_env):
        return f"{RED}⚠️  API-ключ '{api_env}' не задан в .env{RESET}"
    return f"{GREEN}✓ готов{RESET}"


def _cmd_models_test(model_name: str):
    """Протестировать доступность модели"""
    from . import models_config, ai_client

    print(f"\n{CYAN}🧪 Тестирую модель: {model_name}...{RESET}\n")

    try:
        model_def = models_config.get_model_config(model_name)
    except ValueError as e:
        print(f"{RED}❌ {e}{RESET}")
        return

    mtype = model_def.get("type", "")

    if mtype in ("summarization", "both"):
        print(f"{DIM}Отправляю тестовый chat completion...{RESET}")
        try:
            text = ai_client.chat_completion_text(
                model_key=model_name,
                system_prompt="Ответь ровно одним словом.",
                user_prompt="Скажи 'работает' если ты работаешь.",
                timeout=30,
                json_mode=False,
            )
            print(f"{GREEN}✅ Ответ: {text}{RESET}")
        except Exception as e:
            print(f"{RED}❌ Ошибка: {e}{RESET}")

    if mtype in ("transcription", "both"):
        print(f"\n{DIM}Проверяю эндпоинт транскрипции (без отправки аудио)...{RESET}")
        base_url = model_def.get("base_url", "").rstrip("/")
        print(f"  URL: {base_url}/audio/transcriptions")
        print(f"  Модель: {model_def.get('model_id', '?')}")
        print(f"{DIM}  (полный тест транскрипции требует аудиофайл){RESET}")

    print()


def _cmd_models_open():
    """Открыть конфиг в редакторе"""
    from . import models_config
    import subprocess

    config_dir = models_config.MODELS_FILE.parent
    config_dir.mkdir(parents=True, exist_ok=True)

    # Создаём файлы если их нет
    if not models_config.MODELS_FILE.exists():
        _create_default_models_config()
    if not models_config.ENV_FILE.exists():
        _create_default_env_file()

    # Открываем директорию конфигов
    editor = os.environ.get("EDITOR", os.environ.get("VISUAL", "nano"))
    print(f"\n{CYAN}📂 Директория конфигов:{RESET} {config_dir}")
    print(f"{DIM}  models.json — настройки моделей{RESET}")
    print(f"{DIM}  .env       — API-ключи (секреты){RESET}")
    print(f"\n{DIM}Открываю редактор: {editor}{RESET}")
    try:
        subprocess.run([editor, str(models_config.MODELS_FILE)])
    except Exception as e:
        print(f"{RED}❌ Не удалось открыть редактор: {e}{RESET}")
        print(f"   Откройте вручную: {models_config.MODELS_FILE}")


def _create_default_models_config():
    """Создать models.json по умолчанию с базовыми моделями."""
    from . import models_config

    default_config = {
        "default_summarization": "routerai-gpt4o-mini",
        "default_transcription": "local",
        "models": {
            "routerai-gpt4o-mini": {
                "name": "GPT-4o Mini (RouterAI)",
                "base_url": "https://routerai.ru/api/v1",
                "api_key_env": "ROUTERAI_API_KEY",
                "type": "summarization",
                "model_id": "gpt-4o-mini",
                "params": {"temperature": 0.3},
            },
            "routerai-gpt4o": {
                "name": "GPT-4o (RouterAI)",
                "base_url": "https://routerai.ru/api/v1",
                "api_key_env": "ROUTERAI_API_KEY",
                "type": "summarization",
                "model_id": "gpt-4o",
                "params": {"temperature": 0.3},
            },
            "routerai-mai-transcribe": {
                "name": "MAI-Transcribe 1.5 (RouterAI)",
                "base_url": "https://routerai.ru/api/v1",
                "api_key_env": "ROUTERAI_API_KEY",
                "type": "transcription",
                "model_id": "microsoft/mai-transcribe-1.5",
                "language": "ru",
            },
            "ollama-llama3": {
                "name": "Llama 3.1 (локально)",
                "base_url": "http://localhost:11434/v1",
                "api_key_env": None,
                "type": "summarization",
                "model_id": "llama3.1",
                "params": {"temperature": 0.3},
            },
        },
    }

    models_config.MODELS_FILE.parent.mkdir(parents=True, exist_ok=True)
    models_config.MODELS_FILE.write_text(
        json.dumps(default_config, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"{GREEN}✅ Создан models.json по умолчанию{RESET}")


def _create_default_env_file():
    """Создать .env.example."""
    from . import models_config

    env_content = (
        "# API-ключи для AI-моделей Meeting AI\n"
        "# Раскомментируйте и укажите свои ключи:\n\n"
        "# ROUTERAI_API_KEY=sk-...\n"
        "# OPENAI_API_KEY=sk-...\n"
        "# OPENROUTER_API_KEY=sk-or-...\n"
        "# ANTHROPIC_API_KEY=sk-ant-...\n"
    )

    models_config.ENV_FILE.write_text(env_content, encoding="utf-8")
    print(f"{GREEN}✅ Создан .env шаблон{RESET}")


def cmd_app(args):
    """Команда app — запуск веб-интерфейса"""
    import webbrowser
    import threading

    web_dir = Path(__file__).parent.parent.parent / "web"
    app_script = web_dir / "app.py"

    if not app_script.exists():
        print(f"{RED}❌ Веб-приложение не найдено: {app_script}{RESET}")
        print(f"   Создайте директорию web/ с app.py")
        sys.exit(1)

    # Установка переменных окружения
    env = os.environ.copy()
    for var in ['http_proxy', 'https_proxy', 'all_proxy',
                'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY']:
        env.pop(var, None)

    env['MEETING_PORT'] = str(args.port)
    env['MEETING_HOST'] = args.host

    # Открыть браузер через 2 секунды
    if not args.no_browser:
        def open_browser():
            import time
            time.sleep(2)
            url = f"http://localhost:{args.port}"
            print(f"\n{CYAN}🌐 Открываю {url} в браузере...{RESET}\n")
            try:
                webbrowser.open(url)
            except Exception:
                pass

        threading.Thread(target=open_browser, daemon=True).start()

    print(f"\n{BOLD}🎙️  Meeting AI - Web Interface{RESET}")
    print(f"{'─' * 60}")
    print(f"{DIM}📁 База:       {web_dir.parent}{RESET}")
    print(f"{DIM}🌐 URL:        http://localhost:{args.port}{RESET}")
    print(f"{DIM}🔌 Сервер:    активен{RESET}")
    print(f"{DIM}Ctrl+C для остановки{RESET}")
    print(f"{'─' * 60}\n")

    try:
        subprocess.run(
            [sys.executable, str(app_script)],
            cwd=str(web_dir),
            env=env
        )
    except KeyboardInterrupt:
        print(f"\n{YELLOW}👋 Веб-сервер остановлен{RESET}")

def main():
    """Главная точка входа CLI"""
    parser = argparse.ArgumentParser(
        description="Meeting Recorder — запись встреч с ПК + микрофон",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:
  meeting start              Начать запись (ПК + микрофон)
  meeting stop               Остановить запись
  meeting status             Показать статус
  meeting process            Обработать последнюю запись
  meeting config             Настроить устройства
  meeting config --show      Показать текущие настройки
  meeting config --reset     Сбросить настройки
  meeting devices            Список устройств
  meeting app                запуск веб сервера
        """
    )

    subparsers = parser.add_subparsers(dest="command")
    subparsers.required = True

    # start
    p_start = subparsers.add_parser("start", help="Начать запись")
    p_start.add_argument("--type", dest="meeting_type", default="default",
                         help="Тип встречи (например: bd для backend daily)")

    subparsers.add_parser("stop", help="Остановить запись")

    subparsers.add_parser("status", help="Показать статус")
    subparsers.add_parser("process", help="Обработать последнюю запись")

    p_config = subparsers.add_parser("config", help="Настроить устройства")
    p_config.add_argument("--reset", action="store_true", help="Сбросить настройки")
    p_config.add_argument("--show", action="store_true", help="Показать текущие")

    subparsers.add_parser("devices", help="Список устройств")
    # models
    p_models = subparsers.add_parser("models", help="Управление AI-моделями")
    p_models_sub = p_models.add_subparsers(dest="subcommand")
    p_models_sub.required = True
    p_models_sub.add_parser("list", help="Список настроенных моделей")
    p_models_test = p_models_sub.add_parser("test", help="Проверить доступность модели")
    p_models_test.add_argument("model_name", help="Имя модели для теста")
    p_models_sub.add_parser("open", help="Открыть конфиг в редакторе")
    # app
    p_app = subparsers.add_parser("app", help="Запустить веб-интерфейс")
    p_app.add_argument("--port", type=int, default=5000, help="Порт (по умолчанию 5000)")
    p_app.add_argument("--host", type=str, default="0.0.0.0", help="Хост (по умолчанию 0.0.0.0)")
    p_app.add_argument("--no-browser", action="store_true", help="Не открывать браузер")

    args = parser.parse_args()

    commands = {
        "start": cmd_start,
        "stop": cmd_stop,
        "status": cmd_status,
        "process": cmd_process,
        "config": cmd_config,
        "devices": cmd_devices,
        "models": cmd_models,
        "app": cmd_app,
    }

    commands[args.command](args)