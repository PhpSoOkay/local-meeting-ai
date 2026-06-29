#!/usr/bin/env python3
"""
Web интерфейс для Meeting AI
Точка входа — регистрация Blueprints и запуск сервера.
"""
import os
import sys
from pathlib import Path
from flask import Flask

# Добавляем parent directory в путь для импорта
sys.path.insert(0, str(Path(__file__).parent.parent))

from web.routes import main_bp as main_blueprint
from web.routes import api_bp as api_blueprint
from web.routes import processing_bp as processing_blueprint
from web.routes import models_bp as models_blueprint

# Импортируем модули с маршрутами, чтобы декораторы зарегистрировались
from web.routes import main
from web.routes import api
from web.routes import processing
from web.routes import models


def create_app():
    """Создание и настройка приложения"""
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'meeting-ai-secret-key'

    # Регистрация Blueprint-ов
    app.register_blueprint(main_blueprint)
    app.register_blueprint(api_blueprint, url_prefix='/api')
    app.register_blueprint(processing_blueprint, url_prefix='/api')
    app.register_blueprint(models_blueprint)

    return app


if __name__ == '__main__':
    host = os.environ.get('MEETING_HOST', '0.0.0.0')
    port = int(os.environ.get('MEETING_PORT', '5000'))

    print("\n" + "="*60)
    print("🎙️  Meeting AI - Web Interface")
    print("="*60)
    print(f"🌐 Web interface: http://localhost:{port}")
    print("="*60 + "\n")

    app = create_app()
    app.run(host=host, port=port, debug=False)
