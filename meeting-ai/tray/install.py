#!/usr/bin/env python3
"""
Скрипт установки Meeting AI System Tray
Устанавливает зависимости, иконки и .desktop файл
"""
import os
import sys
import subprocess
import shutil
from pathlib import Path


# Определяем базовую директорию проекта
BASE_DIR = Path(__file__).parent.parent


def print_step(message: str):
    print(f"\n{'='*60}")
    print(f"📦 {message}")
    print('='*60)


def run_command(cmd: list[str], description: str) -> bool:
    """Выполнить команду"""
    print(f"▶️  {description}...")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ {description} - успешно")
            return True
        else:
            print(f"❌ {description} - ошибка: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ {description} - исключение: {e}")
        return False


def check_dependencies() -> bool:
    """Проверить системные зависимости"""
    print_step("Проверка системных зависимостей")
    
    required_packages = [
        "python3-gi",
        "gir1.2-appindicator3-0.1",
        "gir1.2-gtk-3.0",
        "libnotify-bin",  # notify-send
    ]
    
    missing = []
    
    for package in required_packages:
        result = subprocess.run(
            ["dpkg", "-l", package],
            capture_output=True,
            text=True
        )
        if result.returncode != 0 or f"ii  {package}" not in result.stdout:
            missing.append(package)
    
    if missing:
        print(f"\n⚠️  Отсутствуют пакеты: {', '.join(missing)}")
        print("\nДля установки выполните:")
        print(f"sudo apt update && sudo apt install {' '.join(missing)}")
        
        response = input("\nУстановить сейчас? (y/n): ").strip().lower()
        if response == 'y':
            subprocess.run(["sudo", "apt", "update"])
            subprocess.run(["sudo", "apt", "install", "-y"] + missing)
        else:
            print("❌ Установка отменена. Без зависимостей tray не будет работать.")
            return False
    
    # Проверка Pillow для генерации иконок
    try:
        from PIL import Image
        print("✅ Pillow установлен")
    except ImportError:
        print("⚠️  Pillow не установлен, будет использован упрощённый режим иконок")
        print("   Для красивых иконок выполните: pip install Pillow")
    
    return True


def install_python_dependencies(base_dir: Path) -> bool:
    """Установить Python зависимости"""
    print_step("Установка Python зависимостей")
    
    venv_python = base_dir / ".venv" / "bin" / "python"
    
    if not venv_python.exists():
        print(f"❌ Виртуальное окружение не найдено: {venv_python}")
        print("   Создайте его командой: python3 -m venv .venv")
        return False
    
    # Устанавливаем Pillow если нет
    result = subprocess.run(
        [str(venv_python), "-m", "pip", "install", "Pillow"],
        capture_output=True,
        text=True
    )
    
    if result.returncode == 0:
        print("✅ Pillow установлен")
        return True
    else:
        print("⚠️  Не удалось установить Pillow, иконки будут упрощёнными")
        return True


def create_desktop_file(base_dir: Path) -> bool:
    """Создать .desktop файл"""
    print_step("Установка .desktop файла")
    
    user_home = Path.home()
    applications_dir = user_home / ".local" / "share" / "applications"
    desktop_file = applications_dir / "meeting-ai.desktop"
    
    # Создаём директорию если нет
    applications_dir.mkdir(parents=True, exist_ok=True)
    
    # Пути к проекту
    project_path = user_home / "Yandex.Disk" / "carrier" / "meeting-ai"
    python_path = project_path / ".venv" / "bin" / "python"
    app_path = project_path / "tray" / "app.py"
    icon_path = project_path / "assets" / "icons" / "tray.png"
    
    # Генерируем правильный .desktop файл
    content = f"""[Desktop Entry]
Version=1.0
Type=Application
Name=Meeting AI
GenericName=AI Meeting Assistant
Comment=Запись и анализ рабочих встреч с AI
Exec={python_path} {app_path}
Icon={icon_path}
Path={project_path}
Terminal=false
StartupNotify=true
Categories=Office;AudioVideo;Utility;
Keywords=meeting;recording;transcription;ai;whisper;
MimeType=
"""
    
    # Записываем файл
    desktop_file.write_text(content)
    desktop_file.chmod(0o755)
    
    print(f"✅ .desktop файл создан: {desktop_file}")
    print(f"   Путь к Python: {python_path}")
    print(f"   Путь к приложению: {app_path}")
    print(f"   Путь к иконке: {icon_path}")
    
    # Обновляем базу desktop
    try:
        subprocess.run(["update-desktop-database", str(applications_dir)], capture_output=True)
    except:
        pass
    
    return True


def create_icon_directory(base_dir: Path) -> bool:
    """Создать директорию для иконок и сгенерировать иконки"""
    print_step("Создание директории и иконок")
    
    icons_dir = base_dir / "assets" / "icons"
    icons_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"✅ Директория создана: {icons_dir}")
    
    # Копируем иконки в стандартное место если есть PIL
    try:
        from PIL import Image, ImageDraw
        
        colors = {
            "running": (76, 175, 80),
            "starting": (255, 193, 7),
            "stopped": (158, 158, 158),
            "error": (244, 67, 54),
            "recording": (244, 67, 54),
        }
        
        for state, color in colors.items():
            icon_file = icons_dir / f"tray_{state}_24.png"
            
            # Создаём изображение
            img = Image.new('RGBA', (24, 24), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            
            cx, cy = 12, 12
            
            # Микрофон (серый)
            mic_gray = (200, 200, 200, 255)
            draw.rounded_rectangle([8, 8, 16, 16], radius=4, fill=mic_gray)
            
            # Индикатор состояния
            indicator_color = (*color, 255)
            if state == "recording":
                draw.ellipse([10, 4, 14, 8], fill=indicator_color)
            else:
                draw.ellipse([18, 2, 22, 6], fill=indicator_color)
            
            img.save(icon_file, 'PNG')
            print(f"✅ Иконка: tray_{state}_24.png")
        
        # Создаём основную иконку
        main_icon = icons_dir / "tray.png"
        img = Image.new('RGBA', (24, 24), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle([8, 8, 16, 16], radius=4, fill=(100, 149, 237, 255))
        draw.ellipse([18, 2, 22, 6], fill=(76, 175, 80, 255))
        img.save(main_icon, 'PNG')
        print(f"✅ Основная иконка: tray.png")
        
        # Копируем иконку в стандартное место
        try:
            user_home = Path.home()
            icons_24_dir = user_home / ".local" / "share" / "icons" / "hicolor" / "24x24" / "apps"
            icons_24_dir.mkdir(parents=True, exist_ok=True)
            
            main_icon_dest = icons_24_dir / "meeting-ai.png"
            shutil.copy2(main_icon, main_icon_dest)
            print(f"✅ Иконка скопирована в: {main_icon_dest}")
        except Exception as e:
            print(f"⚠️  Не удалось скопировать иконку в стандартное место: {e}")
        
        return True

    except ImportError:
        print("⚠️  Pillow не установлен, иконки будут созданы при первом запуске")
        return True

    except ImportError:
        print("⚠️  Pillow не установлен, иконки будут созданы при первом запуске")
        return True


def setup_autostart(base_dir: Path, enable: bool = True) -> bool:
    """Настроить автозапуск"""
    print_step(f"{'Настройка' if enable else 'Отключение'} автозапуска")
    
    user_home = Path.home()
    autostart_dir = user_home / ".config" / "autostart"
    desktop_file = autostart_dir / "meeting-ai.desktop"
    
    if enable:
        # Создаём директорию если нет
        autostart_dir.mkdir(parents=True, exist_ok=True)
        
        # Копируем .desktop файл
        src_file = user_home / ".local" / "share" / "applications" / "meeting-ai.desktop"
        
        if src_file.exists():
            shutil.copy2(src_file, desktop_file)
            print(f"✅ Автозапуск настроен: {desktop_file}")
            return True
        else:
            print("⚠️  .desktop файл не найден, автозапуск не настроен")
            return False
    else:
        # Удаляем файл автозапуска
        if desktop_file.exists():
            desktop_file.unlink()
            print(f"✅ Автозапуск отключён")
        else:
            print("ℹ️  Автозапуск не был настроен")
        
        return True


def print_completion_message():
    """Вывести сообщение о завершении"""
    print("\n" + "="*60)
    print("✅ Установка завершена!")
    print("="*60)
    print("""
📌 Что было сделано:
   • Проверены системные зависимости
   • Установлены Python зависимости
   • Создан .desktop файл в меню приложений
   • Создана директория для иконок

🚀 Как использовать:
   1. Найдите "Meeting AI" в меню приложений
   2. Запустите — иконка появится в системном трее
   3. Через меню в трее можно:
      - Открыть веб-интерфейс
      - Начать/остановить запись
      - Просмотреть логи
      - Управлять сервером

💡 Совет:
   • Для размещения ярлыка на рабочем столе:
     - Откройте ~/.local/share/applications/
     - Скопируйте meeting-ai.desktop на рабочий стол
   
   • Для автозапуска при входе в систему:
     - Запустите этот скрипт с флагом --autostart

🔧 Если иконка не отображается в трее:
   • Перезайдите в систему
   • Или перезапустите GNOME Shell (Alt+F2, затем 'r')
""")


def main():
    """Основная функция"""
    # Определяем базовую директорию
    base_dir = Path(__file__).parent.parent
    
    print("\n" + "="*60)
    print("🎙️  Meeting AI System Tray - Установка")
    print("="*60)
    print(f"📁 Проект: {base_dir}")
    
    # Парсим аргументы
    enable_autostart = "--autostart" in sys.argv
    disable_autostart = "--no-autostart" in sys.argv
    
    # Проверяем зависимости
    if not check_dependencies():
        sys.exit(1)
    
    # Устанавливаем Python зависимости
    install_python_dependencies(base_dir)
    
    # Создаём директорию для иконок
    create_icon_directory(base_dir)
    
    # Устанавливаем .desktop файл
    if not create_desktop_file(base_dir):
        print("⚠️  .desktop файл не установлен, но приложение можно запустить вручную")
    
    # Настраиваем автозапуск
    if enable_autostart:
        setup_autostart(base_dir, enable=True)
    elif disable_autostart:
        setup_autostart(base_dir, enable=False)
    else:
        # Спрашиваем пользователя
        response = input("\nНастроить автозапуск при входе в систему? (y/n): ").strip().lower()
        if response == 'y':
            setup_autostart(base_dir, enable=True)
    
    # Выводим сообщение о завершении
    print_completion_message()


if __name__ == "__main__":
    main()
