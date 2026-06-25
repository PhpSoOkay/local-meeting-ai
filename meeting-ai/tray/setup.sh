#!/bin/bash
# Скрипт инициализации Meeting AI System Tray

echo "🔧 Инициализация Meeting AI System Tray"
echo "========================================"

cd ~/Yandex.Disk/carrier/meeting-ai

# Активируем виртуальное окружение
if [ -f .venv/bin/activate ]; then
    source .venv/bin/activate
    echo "✅ Виртуальное окружение активировано"
else
    echo "❌ Виртуальное окружение не найдено в .venv/"
    echo "Создайте его: python3 -m venv .venv"
    exit 1
fi

# Запускаем инициализацию
python tray/init.py

# Если установка прошла успешно, предлагаем добавить на рабочий стол
if [ $? -eq 0 ]; then
    echo ""
    echo "========================================"
    echo "💡 Совет: Добавьте ярлык на рабочий стол"
    echo "========================================"
    echo ""
    echo "1. Скопируйте .desktop файл:"
    echo "   cp ~/.local/share/applications/meeting-ai.desktop ~/Рабочий\ стол/"
    echo ""
    echo "2. Или перетащите 'Meeting AI' из меню приложений на рабочий стол"
    echo ""
fi
