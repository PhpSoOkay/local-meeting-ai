"""
Универсальный AI-клиент для Meeting AI.
OpenAI-compatible API: чат-комплишны (суммаризация) и аудио-транскрипции.
"""
import base64
import io
import json
import sys
import threading
import time
from pathlib import Path
from typing import Optional

import httpx

from .models_config import get_model_config, get_api_key, load_models

# Импортируем log_action (тот же, что используется в process_meeting.py)
BASE_DIR = Path.home() / "Yandex.Disk/carrier/meeting-ai"
sys.path.insert(0, str(BASE_DIR / "web" / "routes"))
from logs import log_action  # noqa: E402


class AIModelError(Exception):
    """Ошибка AI-модели."""


def _warn_if_slow(start_time: float, label: str, meeting_id: str, timeout: float):
    """
    Фоновый поток: если через 30 секунд запрос не завершён — пишет предупреждение в лог.
    """
    time.sleep(30)
    elapsed = time.time() - start_time
    if elapsed >= 30:
        log_action(meeting_id, "ai_client",
                   f"⏳ Жду ответ от {label}... (прошло {elapsed:.0f}с, таймаут {timeout:.0f}с)",
                   level="warning",
                   details={"label": label, "elapsed": elapsed, "timeout": timeout})


def _build_client(model_def: dict, timeout: float) -> httpx.Client:
    """Создать httpx.Client с нужными заголовками."""
    base_url = model_def["base_url"].rstrip("/")
    api_key = get_api_key(model_def)

    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Meeting-AI/1.0",
    }

    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    # Дополнительные заголовки из конфига
    extra_headers = model_def.get("headers", {})
    if isinstance(extra_headers, dict):
        headers.update(extra_headers)

    return httpx.Client(
        base_url=base_url,
        headers=headers,
        timeout=timeout,
    )


def _retry_request(
    client: httpx.Client,
    method: str,
    url: str,
    max_retries: int = 1,
    meeting_id: str = "UNKNOWN",
    **kwargs,
) -> httpx.Response:
    """
    Выполнить запрос с retry-логикой (1 повтор при таймаутах и 5xx).
    """
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            response = client.request(method, url, **kwargs)
            if response.status_code < 500:
                return response
            # 5xx — retry
            last_error = AIModelError(
                f"HTTP {response.status_code}: {response.text[:300]}"
            )
        except httpx.TimeoutException as e:
            last_error = AIModelError(f"Таймаут запроса: {e}")
        except httpx.RequestError as e:
            last_error = AIModelError(f"Ошибка запроса: {e}")

        if attempt < max_retries:
            wait_s = 1.0 * (attempt + 1)
            log_action(meeting_id, "ai_client",
                       f"🔄 Повторная попытка {attempt + 2}/{max_retries + 1} через {wait_s:.0f}с (ошибка: {last_error})",
                       level="warning",
                       details={"attempt": attempt + 2, "error": str(last_error)})
            time.sleep(wait_s)

    raise last_error


def chat_completion(
    model_key: str,
    messages: list[dict],
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    timeout: float = 120.0,
    meeting_id: str = "UNKNOWN",
) -> dict:
    """
    Выполнить chat completion через OpenAI-compatible API.

    Args:
        model_key: ключ модели в models.json
        messages: список сообщений [{"role": "system", "content": "..."}, ...]
        temperature: переопределить temperature из конфига
        max_tokens: переопределить max_tokens
        timeout: таймаут запроса в секундах
        meeting_id: идентификатор встречи для логов

    Returns:
        dict с ключами: choices[0].message.content, model, usage

    Raises:
        AIModelError: при ошибках API или сети
        ValueError: при неверной конфигурации модели
    """
    model_def = get_model_config(model_key)

    # Проверяем тип модели
    mtype = model_def.get("type", "")
    if mtype not in ("summarization", "both"):
        raise AIModelError(
            f"Модель '{model_key}' (type='{mtype}') не поддерживает суммаризацию"
        )

    model_id = model_def["model_id"]
    base_url = model_def.get("base_url", "")
    url = f"{base_url}/chat/completions"
    label = f"{model_key} ({model_id})"

    params = dict(model_def.get("params", {}))
    if temperature is not None:
        params["temperature"] = temperature
    if max_tokens is not None:
        params["max_tokens"] = max_tokens

    request_body = {
        "model": model_id,
        "messages": messages,
    }
    if params:
        request_body.update(params)

    # Лог: отправка запроса
    log_action(meeting_id, "ai_client",
               f"📤 Отправил запрос на суммаризацию → {label}",
               details={"model_key": model_key, "model_id": model_id, "url": url, "timeout": timeout})

    start_time = time.time()

    # Запускаем фоновый поток для предупреждения через 30 секунд
    warn_thread = threading.Thread(
        target=_warn_if_slow, args=(start_time, label, meeting_id, timeout), daemon=True
    )
    warn_thread.start()

    client = _build_client(model_def, timeout)
    try:
        response = _retry_request(
            client,
            "POST",
            "/chat/completions",
            json=request_body,
            meeting_id=meeting_id,
        )

        elapsed = time.time() - start_time

        if response.status_code == 401:
            log_action(meeting_id, "ai_client",
                       f"❌ Ошибка 401 (неверный ключ) от {label}",
                       level="error",
                       details={"model_key": model_key, "elapsed": elapsed})
            raise AIModelError(
                f"Неверный API-ключ для модели '{model_key}'. "
                f"Проверьте переменную окружения '{model_def.get('api_key_env', '?')}' в .env"
            )
        elif response.status_code == 403:
            log_action(meeting_id, "ai_client",
                       f"❌ Ошибка 403 (доступ запрещён) от {label}",
                       level="error",
                       details={"model_key": model_key, "elapsed": elapsed})
            raise AIModelError(
                f"Доступ запрещён для модели '{model_key}'. "
                f"Возможно, у вас нет доступа к модели '{model_id}'"
            )
        elif response.status_code == 429:
            log_action(meeting_id, "ai_client",
                       f"❌ Ошибка 429 (лимит запросов) от {label}",
                       level="error",
                       details={"model_key": model_key, "elapsed": elapsed})
            raise AIModelError(
                f"Превышен лимит запросов для модели '{model_key}'. "
                f"Попробуйте позже или смените модель в models.json"
            )
        elif response.status_code >= 400:
            log_action(meeting_id, "ai_client",
                       f"❌ Ошибка HTTP {response.status_code} от {label}",
                       level="error",
                       details={"model_key": model_key, "status": response.status_code,
                                "elapsed": elapsed, "response": response.text[:300]})
            raise AIModelError(
                f"Ошибка API для модели '{model_key}': "
                f"HTTP {response.status_code}: {response.text[:500]}"
            )

        data = response.json()
        usage = data.get("usage", {})
        log_action(meeting_id, "ai_client",
                   f"📥 Получил ответ от {label} (токенов: {usage.get('total_tokens', '?')}, {elapsed:.1f}с)",
                   details={"model_key": model_key, "elapsed": elapsed, "usage": usage})
        return data

    finally:
        client.close()


def audio_transcription(
    model_key: str,
    audio_path: str,
    language: Optional[str] = None,
    timeout: float = 120.0,
    meeting_id: str = "UNKNOWN",
) -> dict:
    """
    Транскрибация аудио через OpenAI-compatible /audio/transcriptions.

    Поддерживает два формата, в зависимости от провайдера:
      - multipart/form-data (стандартный OpenAI Whisper API)
      - JSON с base64 (MAI-Transcribe)

    Args:
        model_key: ключ модели в models.json
        audio_path: путь к аудиофайлу (.wav)
        language: код языка (по умолчанию из конфига модели)
        timeout: таймаут в секундах
        meeting_id: идентификатор встречи для логов

    Returns:
        dict с транскрипцией (формат зависит от провайдера)

    Raises:
        AIModelError: при ошибках API или сети
    """
    model_def = get_model_config(model_key)

    mtype = model_def.get("type", "")
    if mtype not in ("transcription", "both"):
        raise AIModelError(
            f"Модель '{model_key}' (type='{mtype}') не поддерживает транскрипцию"
        )

    model_id = model_def["model_id"]
    base_url = model_def.get("base_url", "")
    url = f"{base_url}/audio/transcriptions"
    label = f"{model_key} ({model_id})"
    lang = language or model_def.get("language", "ru")

    # Читаем аудиофайл
    _apath = Path(audio_path) if not isinstance(audio_path, Path) else audio_path
    if not _apath.exists():
        raise AIModelError(f"Аудиофайл не найден: {_apath}")

    file_size = _apath.stat().st_size

    with open(_apath, "rb") as f:
        audio_data = f.read()

    api_key = get_api_key(model_def)

    # Собираем заголовки без Content-Type (httpx сам выставит для multipart/json)
    req_headers = {"User-Agent": "Meeting-AI/1.0"}
    if api_key:
        req_headers["Authorization"] = f"Bearer {api_key}"
    extra_headers = model_def.get("headers", {})
    if isinstance(extra_headers, dict):
        req_headers.update(extra_headers)

    # Определяем формат запроса транскрипции:
    # 1. Явное поле transcription_format в конфиге модели ("json_base64" или "multipart")
    # 2. Авто-детект: RouterAI (routerai.ru) всегда JSON+base64
    # 3. Авто-детект: MAI-Transcribe использует JSON+base64
    # 4. По умолчанию: стандартный multipart/form-data (OpenAI Whisper API)

    fmt = model_def.get("transcription_format")
    if fmt == "json_base64":
        use_json_base64 = True
    elif fmt == "multipart":
        use_json_base64 = False
    else:
        # Авто-детект
        use_json_base64 = (
            "routerai.ru" in base_url.lower()
            or "mai-transcribe" in model_id.lower()
        )

    if use_json_base64:
        audio_b64 = base64.b64encode(audio_data).decode("utf-8")
        request_body = {
            "model": model_id,
            "input_audio": {"data": audio_b64, "format": "wav"},
            "language": lang,
            "response_format": "verbose_json",
        }
        req_headers["Content-Type"] = "application/json"
        httpx_kwargs = {"json": request_body}
    else:
        httpx_kwargs = {
            "files": {"file": (_apath.name, io.BytesIO(audio_data), "audio/wav")},
            "data": {
                "model": model_id,
                "language": lang,
                "response_format": "verbose_json",
            },
        }

    # Лог: отправка аудиофайла на транскрипцию
    log_action(meeting_id, "ai_client",
               f"📤 Отправил аудиофайл на транскрипцию → {label} ({file_size / 1024:.0f} КБ, формат {'JSON+base64' if use_json_base64 else 'multipart'})",
               details={"model_key": model_key, "model_id": model_id, "url": url,
                       "file_size": file_size, "format": "json_base64" if use_json_base64 else "multipart",
                       "language": lang, "timeout": timeout})

    start_time = time.time()

    # Фоновый поток для предупреждения через 30 секунд
    warn_thread = threading.Thread(
        target=_warn_if_slow, args=(start_time, label, meeting_id, timeout), daemon=True
    )
    warn_thread.start()

    client = httpx.Client(
        base_url=base_url,
        headers=req_headers,
        timeout=timeout,
    )
    try:
        response = _retry_request(
            client, "POST", "/audio/transcriptions", **httpx_kwargs, meeting_id=meeting_id
        )
        elapsed = time.time() - start_time
        return _handle_transcription_response(response, model_key, model_def, meeting_id, elapsed)
    finally:
        client.close()


def _handle_transcription_response(
    response: httpx.Response,
    model_key: str,
    model_def: dict,
    meeting_id: str = "UNKNOWN",
    elapsed: float = 0.0,
) -> dict:
    """Обработать ответ от /audio/transcriptions."""
    model_id = model_def.get("model_id", "?")
    label = f"{model_key} ({model_id})"

    if response.status_code == 401:
        log_action(meeting_id, "ai_client",
                   f"❌ Ошибка 401 (неверный ключ) от {label}",
                   level="error", details={"model_key": model_key, "elapsed": elapsed})
        raise AIModelError(
            f"Неверный API-ключ для модели '{model_key}'. "
            f"Проверьте переменную '{model_def.get('api_key_env', '?')}' в .env"
        )
    elif response.status_code == 429:
        log_action(meeting_id, "ai_client",
                   f"❌ Ошибка 429 (лимит запросов) от {label}",
                   level="error", details={"model_key": model_key, "elapsed": elapsed})
        raise AIModelError(
            f"Превышен лимит запросов для модели '{model_key}'"
        )
    elif response.status_code >= 400:
        log_action(meeting_id, "ai_client",
                   f"❌ Ошибка HTTP {response.status_code} от {label}",
                   level="error",
                   details={"model_key": model_key, "status": response.status_code,
                            "elapsed": elapsed, "response": response.text[:300]})
        raise AIModelError(
            f"Ошибка транскрипции для '{model_key}': "
            f"HTTP {response.status_code}: {response.text[:500]}"
        )

    data = response.json()
    text_len = len(data.get("text", ""))
    segments = len(data.get("segments", []))
    log_action(meeting_id, "ai_client",
               f"📥 Получил транскрипцию от {label} ({text_len} символов, {segments} сегментов, {elapsed:.1f}с)",
               details={"model_key": model_key, "text_chars": text_len,
                       "segments": segments, "elapsed": elapsed})
    return data


def chat_completion_text(
    model_key: str,
    system_prompt: str,
    user_prompt: str,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    timeout: float = 120.0,
    json_mode: bool = True,
    meeting_id: str = "UNKNOWN",
) -> str:
    """
    Упрощённый вызов chat completion — возвращает текст ответа.

    Args:
        model_key: ключ модели
        system_prompt: системный промпт
        user_prompt: пользовательский промпт
        temperature, max_tokens, timeout: параметры запроса
        json_mode: требовать JSON-ответ (response_format json_object)
        meeting_id: идентификатор встречи для логов

    Returns:
        текст ответа модели
    """
    model_def = get_model_config(model_key)
    model_id = model_def["model_id"]
    base_url = model_def.get("base_url", "")
    url = f"{base_url}/chat/completions"
    label = f"{model_key} ({model_id})"

    params = dict(model_def.get("params", {}))
    if temperature is not None:
        params["temperature"] = temperature
    if max_tokens is not None:
        params["max_tokens"] = max_tokens
    if json_mode:
        params["response_format"] = {"type": "json_object"}

    request_body = {
        "model": model_id,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    if params:
        request_body.update(params)

    # Лог: отправка запроса
    prompt_preview = user_prompt[:200].replace("\n", " ")
    log_action(meeting_id, "ai_client",
               f"📤 Отправил транскрипт на суммаризацию → {label} ({len(user_prompt)} символов)",
               details={"model_key": model_key, "model_id": model_id, "url": url,
                       "prompt_chars": len(user_prompt), "timeout": timeout})

    start_time = time.time()

    # Фоновый поток для предупреждения через 30 секунд
    warn_thread = threading.Thread(
        target=_warn_if_slow, args=(start_time, label, meeting_id, timeout), daemon=True
    )
    warn_thread.start()

    client = _build_client(model_def, timeout)
    try:
        response = _retry_request(
            client, "POST", "/chat/completions", json=request_body, meeting_id=meeting_id
        )

        elapsed = time.time() - start_time

        if response.status_code == 401:
            log_action(meeting_id, "ai_client",
                       f"❌ Ошибка 401 (неверный ключ) от {label}",
                       level="error", details={"model_key": model_key, "elapsed": elapsed})
            raise AIModelError(
                f"Неверный API-ключ для модели '{model_key}'. "
                f"Проверьте переменную '{model_def.get('api_key_env', '?')}' в .env"
            )
        elif response.status_code == 429:
            log_action(meeting_id, "ai_client",
                       f"❌ Ошибка 429 (лимит запросов) от {label}",
                       level="error", details={"model_key": model_key, "elapsed": elapsed})
            raise AIModelError(
                f"Превышен лимит запросов для модели '{model_key}'."
            )
        elif response.status_code >= 400:
            log_action(meeting_id, "ai_client",
                       f"❌ Ошибка HTTP {response.status_code} от {label}",
                       level="error",
                       details={"model_key": model_key, "status": response.status_code,
                                "elapsed": elapsed, "response": response.text[:300]})
            raise AIModelError(
                f"Ошибка API для '{model_key}': HTTP {response.status_code}: {response.text[:500]}"
            )

        data = response.json()
        usage = data.get("usage", {})
        choices = data.get("choices", [])
        if not choices:
            log_action(meeting_id, "ai_client",
                       f"❌ Пустой ответ от {label}",
                       level="error", details={"model_key": model_key, "elapsed": elapsed})
            raise AIModelError(f"Модель '{model_key}' вернула пустой ответ")

        content = choices[0].get("message", {}).get("content", "")
        log_action(meeting_id, "ai_client",
                   f"📥 Получил ответ от {label} (токенов: {usage.get('total_tokens', '?')}, {len(content)} символов, {elapsed:.1f}с)",
                   details={"model_key": model_key, "elapsed": elapsed,
                           "response_chars": len(content), "usage": usage})
        return content

    finally:
        client.close()

