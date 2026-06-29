"""
Конфигурация AI-моделей для Meeting AI.
Загружает models.json и .env, выполняет валидацию.
"""

import json
import os
from pathlib import Path
from typing import Optional

# Пытаемся импортировать python-dotenv
try:
    from dotenv import load_dotenv as _load_dotenv
    _HAS_DOTENV = True
except ImportError:
    _HAS_DOTENV = False
    def _load_dotenv(*args, **kwargs):
        pass


PROJECT_DIR = Path(__file__).parent.parent.parent  # meeting-ai/
MODELS_FILE = PROJECT_DIR / "config" / "models.json"
ENV_FILE = PROJECT_DIR / ".env"

# Кеш
_models_cache: Optional[dict] = None
_models_mtime: float = 0.0
_env_loaded: bool = False


def _ensure_env():
    """Загрузить .env файл если ещё не загружен."""
    global _env_loaded
    if _env_loaded:
        return

    if ENV_FILE.exists():
        _load_dotenv(ENV_FILE)

    _env_loaded = True


def _env_file_path() -> Optional[Path]:
    """Путь к существующему .env файлу или None."""
    if ENV_FILE.exists():
        return ENV_FILE
    return None


def _find_models_file() -> Optional[Path]:
    """Найти models.json."""
    if MODELS_FILE.exists():
        return MODELS_FILE
    return None


def load_models(force_reload: bool = False) -> dict:
    """
    Загрузить и провалидировать конфигурацию моделей.

    Возвращает словарь с ключами:
        default_summarization, default_transcription, models

    Кеширует результат; сбрасывает кеш при изменении mtime файла.
    """
    global _models_cache, _models_mtime

    _ensure_env()

    # Пытаемся найти models.json
    models_file = _find_models_file()
    if models_file is None:
        raise FileNotFoundError(
            f"Конфиг моделей не найден: {MODELS_FILE}\n"
            f"Запустите: meeting models open — чтобы создать конфиг"
        )

    mtime = models_file.stat().st_mtime
    if not force_reload and _models_cache is not None and mtime == _models_mtime:
        return _models_cache

    try:
        raw = json.loads(models_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"Ошибка парсинга {models_file}: {e}")

    _validate_config(raw)

    _models_cache = raw
    _models_mtime = mtime
    return raw


def _validate_config(config: dict):
    """Валидация конфига моделей. Кидает ValueError при ошибках."""
    errors = []

    if not isinstance(config, dict):
        raise ValueError("Конфиг моделей должен быть JSON-объектом")

    models = config.get("models", {})
    if not isinstance(models, dict) or not models:
        errors.append("Секция 'models' пуста или отсутствует")

    default_summarization = config.get("default_summarization", "")
    default_transcription = config.get("default_transcription", "")

    # Проверка default_summarization
    if default_summarization and default_summarization not in models:
        errors.append(
            f"default_summarization='{default_summarization}' не найден в models. "
            f"Доступные модели: {', '.join(sorted(models.keys()))}"
        )

    # Проверка default_transcription (может быть "local")
    if default_transcription and default_transcription != "local" and default_transcription not in models:
        errors.append(
            f"default_transcription='{default_transcription}' не найден в models. "
            f"Доступные модели: local, {', '.join(sorted(models.keys()))}"
        )

    # Валидация каждой модели
    for model_key, model_def in models.items():
        if not isinstance(model_def, dict):
            errors.append(f"Модель '{model_key}': должно быть объектом")
            continue

        req_fields = {
            "name": str,
            "base_url": str,
            "type": str,
            "model_id": str,
        }

        for field, ftype in req_fields.items():
            if field not in model_def:
                errors.append(f"Модель '{model_key}': отсутствует поле '{field}'")
            elif not isinstance(model_def[field], ftype):
                errors.append(f"Модель '{model_key}': поле '{field}' должно быть типа {ftype.__name__}")

        # Проверка типа модели
        model_type = model_def.get("type", "")
        if model_type not in ("summarization", "transcription", "both"):
            errors.append(
                f"Модель '{model_key}': поле 'type' должно быть 'summarization', "
                f"'transcription' или 'both', а не '{model_type}'"
            )

        # Проверка api_key_env
        api_key_env = model_def.get("api_key_env")
        if api_key_env is not None:
            if not isinstance(api_key_env, str):
                errors.append(f"Модель '{model_key}': api_key_env должен быть строкой или null")
            elif not api_key_env.strip():
                errors.append(f"Модель '{model_key}': api_key_env не может быть пустой строкой")
            else:
                # Проверяем, что переменная окружения задана
                if not os.environ.get(api_key_env):
                    env_path = _env_file_path()
                    env_hint = f" (файл: {env_path})" if env_path else ""
                    errors.append(
                        f"Модель '{model_key}': переменная окружения '{api_key_env}' "
                        f"не найдена{env_hint}. Проверьте .env файл."
                    )

        # Проверка headers (опционально)
        headers = model_def.get("headers")
        if headers is not None and not isinstance(headers, dict):
            errors.append(f"Модель '{model_key}': 'headers' должен быть объектом")

        # Проверка params (опционально)
        params = model_def.get("params")
        if params is not None and not isinstance(params, dict):
            errors.append(f"Модель '{model_key}': 'params' должен быть объектом")

    # Проверка типов моделей для default_
    if default_summarization in models:
        mtype = models[default_summarization].get("type", "")
        if mtype not in ("summarization", "both"):
            errors.append(
                f"default_summarization='{default_summarization}' имеет type='{mtype}', "
                f"но должен быть 'summarization' или 'both'"
            )

    if default_transcription not in ("local", "") and default_transcription in models:
        mtype = models[default_transcription].get("type", "")
        if mtype not in ("transcription", "both"):
            errors.append(
                f"default_transcription='{default_transcription}' имеет type='{mtype}', "
                f"но должен быть 'transcription' или 'both'"
            )

    if errors:
        raise ValueError(
            "Ошибки валидации models.json:\n  - " + "\n  - ".join(errors)
        )


def get_model_config(model_key: str) -> dict:
    """Получить конфиг конкретной модели по ключу.

    Raises:
        ValueError: если модель не найдена
    """
    config = load_models()
    models = config.get("models", {})

    if model_key not in models:
        raise ValueError(
            f"Модель '{model_key}' не найдена в models.json. "
            f"Доступные: {', '.join(sorted(models.keys()))}"
        )

    return models[model_key]


def get_default_summarization_model() -> str:
    """Имя модели для суммаризации по умолчанию."""
    config = load_models()
    return config.get("default_summarization", "")


def get_default_transcription_model() -> str:
    """Имя модели для транскрипции по умолчанию ('local' или ключ из models)."""
    config = load_models()
    return config.get("default_transcription", "local")


def get_api_key(model_def: dict) -> Optional[str]:
    """Извлечь API-ключ из переменной окружения по имени из конфига модели."""
    env_var = model_def.get("api_key_env")
    if env_var is None:
        return None
    return os.environ.get(env_var)


def reload_models():
    """Принудительно перезагрузить конфиг (сбросить кеш)."""
    global _models_cache, _models_mtime, _env_loaded
    _models_cache = None
    _models_mtime = 0.0
    _env_loaded = False


def ensure_config_exists() -> list:
    """
    Проверить, что конфигурация существует и дать диагностику.

    Возвращает список проблем (пустой = всё ок).
    Не прерывает выполнение — только предупреждения.
    """
    issues = []

    # Проверяем .env
    env_path = _env_file_path()
    if env_path is None:
        issues.append(
            f".env файл не найден. Создайте {ENV_FILE}\n"
            f"  Пример: echo 'ROUTERAI_API_KEY=sk-...' > {ENV_FILE}"
        )
    else:
        # Проверяем, что он не пустой и не только комментарии
        try:
            content = env_path.read_text(encoding="utf-8").strip()
            if not content or all(line.strip().startswith("#") for line in content.splitlines() if line.strip()):
                issues.append(f".env найден ({env_path}), но не содержит ключей — только комментарии")
        except Exception:
            pass

    # Проверяем models.json через find_models_file
    models_file = _find_models_file()
    if models_file is None:
        issues.append(
            f"models.json не найден. Создайте {MODELS_FILE}\n"
            f"  Запустите: meeting models open"
        )
        return issues

    try:
        config = load_models()
    except (ValueError, FileNotFoundError) as e:
        issues.append(f"Ошибка в models.json: {e}")
        return issues

    # Проверяем, что default_* ссылаются на существующие модели
    models = config.get("models", {})
    default_sum = config.get("default_summarization", "")
    default_tr = config.get("default_transcription", "")

    if default_sum and default_sum not in models:
        issues.append(f"default_summarization='{default_sum}' — модель не найдена в models")
    if default_tr and default_tr != "local" and default_tr not in models:
        issues.append(f"default_transcription='{default_tr}' — модель не найдена в models")

    # Проверяем наличие ключей для моделей
    if env_path is not None:
        for key, model in models.items():
            api_env = model.get("api_key_env")
            if api_env and api_env not in os.environ:
                issues.append(f"Модель '{key}': переменная '{api_env}' не задана в .env")

    return issues
