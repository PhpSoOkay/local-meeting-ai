"""
API и страница управления AI-моделями.
CRUD для models.json, проверка доступности моделей.
"""
import json
import os
import threading
from pathlib import Path

from flask import render_template, jsonify, request
from .logs import log_action
from . import models_bp

# Определяем пути к конфигам — только из проекта
PROJECT_DIR = Path(__file__).parent.parent.parent  # meeting-ai/
MODELS_FILE = PROJECT_DIR / "config" / "models.json"
ENV_FILE = PROJECT_DIR / ".env"


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

def _find_models_file() -> Path:
    """Найти models.json — в проекте."""
    return MODELS_FILE


def _find_env_file() -> Path:
    """Найти .env файл — в проекте."""
    if ENV_FILE.exists():
        return ENV_FILE
    return None


def _read_models() -> dict:
    """Прочитать models.json (всегда из актуального файла)."""
    mf = _find_models_file()
    if not mf.exists():
        return {"default_summarization": "", "default_transcription": "local", "models": {}}
    try:
        return json.loads(mf.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, Exception):
        return {"default_summarization": "", "default_transcription": "local", "models": {}}


def _write_models(config: dict):
    """Записать models.json в проект."""
    MODELS_FILE.parent.mkdir(parents=True, exist_ok=True)
    MODELS_FILE.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_env() -> dict:
    """Прочитать .env файл и вернуть словарь переменных."""
    env_path = _find_env_file()
    result = {}
    if env_path and env_path.exists():
        try:
            content = env_path.read_text(encoding="utf-8")
            for line in content.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, value = line.partition("=")
                    result[key.strip()] = value.strip().strip("\"'")
        except Exception:
            pass
    return result


def _write_env(env_dict: dict):
    """Записать .env файл в проект."""
    env_path = ENV_FILE

    # Читаем существующий .env, обновляем нужные ключи
    existing = _read_env()
    existing.update(env_dict)

    lines = []
    for key, value in existing.items():
        lines.append(f"{key}={value}")

    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _format_model_for_api(key: str, model: dict, env_vars: dict) -> dict:
    """Форматировать модель для API-ответа: добавить статус ключа, убрать лишнее."""
    api_key_env = model.get("api_key_env")
    key_status = "not_set"
    if api_key_env is None:
        key_status = "no_key"
    elif api_key_env in env_vars and env_vars[api_key_env]:
        key_status = "ok"

    return {
        "key": key,
        "name": model.get("name", key),
        "base_url": model.get("base_url", ""),
        "api_key_env": api_key_env,
        "key_status": key_status,
        "type": model.get("type", "summarization"),
        "model_id": model.get("model_id", ""),
        "params": model.get("params", {}),
        "headers": model.get("headers"),
        "language": model.get("language"),
    }


# ---------------------------------------------------------------------------
# HTML-страница
# ---------------------------------------------------------------------------

@models_bp.route("/models")
def models_page():
    """Страница управления моделями."""
    from ..helpers import get_recording_status
    return render_template("models.html", is_recording=get_recording_status()['recording'])


# ---------------------------------------------------------------------------
# API: список/получение моделей (LIST и CREATE — без path-параметра)
# ---------------------------------------------------------------------------

@models_bp.route("/api/models", methods=["GET"])
def api_list_models():
    """Список всех моделей с информацией о статусе ключей."""
    config = _read_models()
    env_vars = _read_env()
    models = config.get("models", {})

    result = {
        "default_summarization": config.get("default_summarization", ""),
        "default_transcription": config.get("default_transcription", "local"),
        "models": [_format_model_for_api(key, model, env_vars) for key, model in models.items()],
    }
    return jsonify(result)


@models_bp.route("/api/models", methods=["POST"])
def api_create_model():
    """Создать новую модель."""
    data = request.json or {}

    # Валидация обязательных полей
    required = ["key", "name", "base_url", "model_id", "type"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({"error": f"Отсутствуют поля: {', '.join(missing)}"}), 400

    key = data["key"].strip()
    if not key:
        return jsonify({"error": "Ключ модели не может быть пустым"}), 400

    config = _read_models()
    models = config.get("models", {})

    if key in models:
        return jsonify({"error": f"Модель '{key}' уже существует"}), 409

    if data["type"] not in ("summarization", "transcription", "both"):
        return jsonify({"error": "type должен быть 'summarization', 'transcription' или 'both'"}), 400

    model_def = {
        "name": data["name"].strip(),
        "base_url": data["base_url"].strip().rstrip("/"),
        "api_key_env": data.get("api_key_env") or None,
        "type": data["type"],
        "model_id": data["model_id"].strip(),
        "params": data.get("params") or {},
        "headers": data.get("headers") or None,
    }

    # language только для транскрипции
    if data.get("language"):
        model_def["language"] = data["language"]

    models[key] = model_def
    config["models"] = models
    _write_models(config)

    # Если указан api_key и передан api_key_value — сохранить в .env
    api_key_env = data.get("api_key_env")
    api_key_value = data.get("api_key_value")
    if api_key_env and api_key_value:
        _write_env({api_key_env: api_key_value})

    log_action("UNKNOWN", "models", f"Модель создана: {key}", level="success",
               details={"model": key, "type": data["type"]})

    # Инвалидируем кеш models_config
    _invalidate_cache()

    return jsonify({"status": "ok", "key": key}), 201


# ---------------------------------------------------------------------------
# API: фиксированные маршруты (defaults, test, env) — ДО параметризованных!
# ---------------------------------------------------------------------------

@models_bp.route("/api/models/defaults", methods=["PUT"])
def api_update_defaults():
    """Обновить default_summarization и/или default_transcription."""
    data = request.json or {}
    config = _read_models()
    models = config.get("models", {})

    if "default_summarization" in data:
        val = data["default_summarization"]
        if val and val not in models:
            return jsonify({"error": f"Модель '{val}' не найдена"}), 400
        if val and models[val].get("type") not in ("summarization", "both"):
            return jsonify({"error": f"Модель '{val}' имеет type='{models[val].get('type')}', должен быть 'summarization' или 'both'"}), 400
        config["default_summarization"] = val

    if "default_transcription" in data:
        val = data["default_transcription"]
        if val and val != "local" and val not in models:
            return jsonify({"error": f"Модель '{val}' не найдена"}), 400
        if val and val != "local" and models[val].get("type") not in ("transcription", "both"):
            return jsonify({"error": f"Модель '{val}' имеет type='{models[val].get('type')}', должен быть 'transcription' или 'both'"}), 400
        config["default_transcription"] = val

    _write_models(config)
    _invalidate_cache()

    log_action("UNKNOWN", "models", "Значения по умолчанию обновлены", level="success",
               details=data)

    return jsonify({"status": "ok"})


@models_bp.route("/api/models/test", methods=["POST"])
def api_test_model():
    """Протестировать модель — отправить тестовый запрос."""
    data = request.json or {}
    model_key = data.get("key", "").strip()
    if not model_key:
        return jsonify({"error": "Не указан ключ модели"}), 400

    config = _read_models()
    models = config.get("models", {})
    if model_key not in models:
        return jsonify({"error": f"Модель '{model_key}' не найдена"}), 404

    model_def = models[model_key]
    model_type = model_def.get("type", "summarization")

    result_holder = {"done": False, "result": None, "error": None}

    def run_test():
        try:
            import sys
            sys.path.insert(0, str(PROJECT_DIR / "scripts"))
            from recorder.models_config import reload_models
            from recorder.ai_client import chat_completion, AIModelError
            reload_models()

            if model_type in ("summarization", "both"):
                response = chat_completion(
                    model_key,
                    messages=[{"role": "user", "content": "Привет! Ответь кратко: ты работаешь?"}],
                    max_tokens=50,
                )
                text = response["choices"][0]["message"]["content"]
                result_holder["result"] = {
                    "success": True,
                    "model": response.get("model", model_key),
                    "response": text[:500],
                    "usage": response.get("usage", {}),
                }
            else:
                result_holder["result"] = {
                    "success": True,
                    "model": model_key,
                    "response": "Модель типа 'transcription' — чат-тест не поддерживается",
                }
        except AIModelError as e:
            result_holder["error"] = str(e)
        except Exception as e:
            result_holder["error"] = f"Ошибка: {e}"
        finally:
            result_holder["done"] = True

    thread = threading.Thread(target=run_test, daemon=True)
    thread.start()
    thread.join(timeout=15)

    if not result_holder["done"]:
        return jsonify({"success": False, "error": "Таймаут: модель не ответила за 15 секунд"}), 504

    if result_holder["error"]:
        return jsonify({"success": False, "error": result_holder["error"]})

    return jsonify(result_holder["result"])


@models_bp.route("/api/models/env", methods=["GET"])
def api_get_env():
    """Получить список переменных .env (только ключи, с маскированными значениями)."""
    env_vars = _read_env()
    result = {}
    for key, value in env_vars.items():
        if value:
            masked = value[:4] + "…" + value[-4:] if len(value) > 10 else "***"
        else:
            masked = ""
        result[key] = masked
    return jsonify(result)


@models_bp.route("/api/models/env", methods=["PUT"])
def api_update_env():
    """Обновить переменную в .env (только одну за раз)."""
    data = request.json or {}
    key = data.get("key", "").strip()
    value = data.get("value", "").strip()

    if not key:
        return jsonify({"error": "Не указан ключ переменной"}), 400

    _write_env({key: value})
    _invalidate_cache()

    log_action("UNKNOWN", "models", f"Переменная .env обновлена: {key}", level="success")

    return jsonify({"status": "ok", "key": key})


# ---------------------------------------------------------------------------
# API: параметризованные маршруты (конкретная модель)
# ---------------------------------------------------------------------------

@models_bp.route("/api/models/<path:model_key>", methods=["GET"])
def api_get_model(model_key):
    """Получить одну модель."""
    config = _read_models()
    models = config.get("models", {})
    if model_key not in models:
        return jsonify({"error": f"Модель '{model_key}' не найдена"}), 404

    env_vars = _read_env()
    return jsonify(_format_model_for_api(model_key, models[model_key], env_vars))


@models_bp.route("/api/models/<path:model_key>", methods=["PUT"])
def api_update_model(model_key):
    """Обновить существующую модель."""
    config = _read_models()
    models = config.get("models", {})

    if model_key not in models:
        return jsonify({"error": f"Модель '{model_key}' не найдена"}), 404

    data = request.json or {}
    model_def = models[model_key]

    if "name" in data:
        model_def["name"] = data["name"].strip()
    if "base_url" in data:
        model_def["base_url"] = data["base_url"].strip().rstrip("/")
    if "api_key_env" in data:
        model_def["api_key_env"] = data["api_key_env"] or None
    if "type" in data:
        if data["type"] not in ("summarization", "transcription", "both"):
            return jsonify({"error": "type должен быть 'summarization', 'transcription' или 'both'"}), 400
        model_def["type"] = data["type"]
    if "model_id" in data:
        model_def["model_id"] = data["model_id"].strip()
    if "params" in data:
        model_def["params"] = data["params"] or {}
    if "headers" in data:
        model_def["headers"] = data["headers"] or None
    if "language" in data:
        if data["language"]:
            model_def["language"] = data["language"]
        else:
            model_def.pop("language", None)

    _write_models(config)

    api_key_env = data.get("api_key_env")
    api_key_value = data.get("api_key_value")
    if api_key_env and api_key_value:
        _write_env({api_key_env: api_key_value})

    log_action("UNKNOWN", "models", f"Модель обновлена: {model_key}", level="success",
               details={"model": model_key})

    _invalidate_cache()

    return jsonify({"status": "ok", "key": model_key})


@models_bp.route("/api/models/<path:model_key>", methods=["DELETE"])
def api_delete_model(model_key):
    """Удалить модель."""
    config = _read_models()
    models = config.get("models", {})

    if model_key not in models:
        return jsonify({"error": f"Модель '{model_key}' не найдена"}), 404

    reset_defaults = {}
    if config.get("default_summarization") == model_key:
        reset_defaults["default_summarization"] = ""
    if config.get("default_transcription") == model_key:
        reset_defaults["default_transcription"] = "local"

    del models[model_key]
    config["models"] = models

    if reset_defaults:
        config.update(reset_defaults)

    _write_models(config)

    log_action("UNKNOWN", "models", f"Модель удалена: {model_key}", level="success",
               details={"model": model_key, "reset_defaults": reset_defaults})

    _invalidate_cache()

    return jsonify({"status": "ok", "key": model_key, "reset_defaults": reset_defaults})


# ---------------------------------------------------------------------------
# Вспомогательное: инвалидация кеша
# ---------------------------------------------------------------------------

def _invalidate_cache():
    """Сбросить кеш models_config (если загружен)."""
    try:
        import sys
        sys.path.insert(0, str(PROJECT_DIR / "scripts"))
        from recorder.models_config import reload_models
        reload_models()
    except Exception:
        pass  # не критично — кеш обновится по mtime при следующем обращении
