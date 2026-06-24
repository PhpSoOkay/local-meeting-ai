#!/usr/bin/env python3
"""
Meeting Recorder — точка входа.
Импортирует CLI из пакета recorder.
"""
import os
import sys

# Отключение прокси
for var in ['http_proxy', 'https_proxy', 'all_proxy',
            'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY']:
    os.environ.pop(var, None)

# Добавляем директорию scripts в путь для импорта пакета recorder
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from recorder.cli import main

if __name__ == "__main__":
    main()