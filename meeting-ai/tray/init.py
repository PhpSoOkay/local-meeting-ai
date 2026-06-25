#!/usr/bin/env python3
"""
Инициализация директорий и обновление .desktop файла
Запускается перед первым использованием
"""
from pathlib import Path
from install import create_icon_directory, create_desktop_file


def init_directories():
    """Создать необходимые директории"""
    base_dir = Path(__file__).parent.parent
    
    directories = [
        base_dir / "assets" / "icons",
        base_dir / "audio",
        base_dir / "transcripts",
        base_dir / "summaries",
        base_dir / "chroma_db",
    ]
    
    for dir_path in directories:
        dir_path.mkdir(parents=True, exist_ok=True)
        print(f"✅ Создано: {dir_path}")


def main():
    """Основная функция инициализации"""
    print("🔧 Инициализация Meeting AI System Tray")
    print("="*60)
    
    base_dir = Path(__file__).parent.parent
    
    init_directories()
    
    if not create_icon_directory(base_dir):
        print("⚠️  Не удалось создать иконки")
        return False
    
    if not create_desktop_file(base_dir):
        print("⚠️  Не удалось создать .desktop файл")
        return False
    
    print("\n✅ Инициализация завершена!")
    print("\nЗапустите приложение:")
    print(f"  python {base_dir / 'tray' / 'app.py'}")
    print("\nИли найдите 'Meeting AI' в меню приложений")

    return True


if __name__ == "__main__":
    main()

