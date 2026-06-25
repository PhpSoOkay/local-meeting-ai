#!/usr/bin/env python3
"""
Вспомогательный скрипт для запуска Meeting AI Tray
"""
import sys
import os
from pathlib import Path

# Добавляем parent directory
BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))

# Отключаем прокси
os.environ.pop("http_proxy", None)
os.environ.pop("https_proxy", None)
os.environ.pop("all_proxy", None)

# Проверяем зависимости
try:
    import gi
    gi.require_version('Gtk', '3.0')
    gi.require_version('AppIndicator3', '0.1')
except ImportError:
    print("❌ Ошибка: требуются GTK 3.0 и AppIndicator3")
    print("Установите: sudo apt install python3-gi gir1.2-appindicator3-0.1")
    sys.exit(1)

# Импортируем tray приложение
from tray.app import main

if __name__ == "__main__":
    main()
