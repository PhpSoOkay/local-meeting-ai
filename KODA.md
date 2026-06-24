# Meeting AI — Контекстный файл проекта

## Обзор

**Meeting AI** — это Python-система для записи, транскрибации и суммаризации рабочих встреч.
Проект автоматически записывает звук с компьютера и микрофона, транскрибирует речь с помощью
локальной модели **faster-whisper** (medium), выполняет диаризацию (разделение по спикерам)
через **Resemblyzer**, а затем суммаризирует результат через **KodaCode CLI** (`koda`) с
конфигурируемыми промптами, зависящими от типа встречи.

## Архитектура

```
meeting-ai/
├── web/
│   ├── app.py              # Flask-сервер (REST API + шаблоны)
│   └── templates/
│       ├── base.html       # Базовый шаблон с хедером и тустом
│       ├── index.html      # Главная — список встреч
│       ├── detail.html     # Детали встречи с табами
│       └── index_old.html  # Старый SPA (удалить)
├── scripts/
│   ├── recorder.py         # Точка входа CLI (импортирует recorder.cli)
│   ├── process_meeting.py  # Обработка: транскрипция → диаризация → суммаризация
│   └── recorder/           # Пакет записи
│       ├── __init__.py
│       ├── cli.py           # CLI-команды (start/stop/status/process/config/devices/app)
│       ├── config.py        # Загрузка/сохранение настроек + типы встреч
│       ├── devices.py       # Перечисление PulseAudio устройств
│       ├── recorder.py      # Логика записи через pacat/pactl
│       └── vu_meter.py      # Визуальный индикатор уровня звука
├── config/
│   └── meeting_types.json  # Промпты и настройки для типов встреч
├── audio/                  # Папки с записями (meeting_YYYYMMDD_HHMMSS/)
│   └── backend_daily/      # Подпапка для backend daily
├── transcripts/            # Результат транскрибации (transcript.txt)
├── summaries/              # Результат суммаризации (summary.json, summary.md)
├── chroma_db/              # Vector store (пока пустой)
└── recorder.log            # Лог всех операций записи
```

## Основные технологии

| Компонент       | Технология                         |
|----------------|-------------------------------------|
| Язык           | Python 3                            |
| Веб-фреймворк  | Flask (без SocketIO)                |
| Фронтенд       | HTML + Tailwind CSS                 |
| Транскрипция   | faster-whisper (model: medium, CPU, int8) |
| Диаризация     | Resemblyzer + sklearn (AgglomerativeClustering) |
| Суммаризация   | KodaCode CLI (`koda`)               |
| Запись звука   | PulseAudio (pacat, pactl)           |
| Взаимодействие | HTTP-запросы, автообновление каждые 3 сек |

## Типы встреч

Конфигурация хранится в `config/meeting_types.json`:

- **`default`** — обычная рабочая встреча. Суммаризация возвращает: название, краткое содержание, задачи, решения, карьерные инсайты, продемонстрированные навыки.
- **`bd`** — Backend Daily (стендап). Структурированный вывод: участники, что сделали вчера/планы, блокеры, технические решения, code reviews, оценки задач, follow-ups.

Каждый тип содержит:
- `prompt` — промпт для KodaCode с шаблоном `{transcript}`
- `audio_subdir`, `transcript_subdir`, `summary_subdir` — подпапки для хранения результатов

## Запуск

### Веб-интерфейс

```bash
# Через CLI
meeting app [--port 5000] [--host 0.0.0.0] [--no-browser]

# Или напрямую
python meeting-ai/web/app.py

# Переменные окружения:
MEETING_HOST=0.0.0.0
MEETING_PORT=5000
```

### CLI-команды

```bash
# Настройка устройств (после установки пакета recorder)
meeting config                    # интерактивная настройка
meeting config --show             # показать текущие настройки
meeting config --reset            # сбросить настройки
meeting devices                   # список доступных устройств

# Запись и обработка
meeting start [--type bd]         # начать запись + автообработка
meeting stop [--no-process]       # остановить запись (опционально без обработки)
meeting status                    # статус текущей записи
meeting process                   # обработать последнюю запись

# Типы встреч: bd (backend daily), default (обычная встреча)
```

### Установка зависимостей

Проект использует следующие Python-пакеты:

```
flask
faster-whisper
resemblyzer
scikit-learn
numpy
```

Также требуется:
- **PulseAudio** — для записи звука
- **KodaCode CLI** (`koda`) — для суммаризации
- **ffmpeg** — для обработки аудиофайлов

### Базовая директория

Все пути жёстко заданы относительно:
```
~/Yandex.Disk/carrier/meeting-ai/
```

## Как работает обработка

1. **Запись**: создаются virtual sinks через PulseAudio, записываются отдельные файлы для звука ПК и микрофона, затем объединяются в один WAV.
2. **Сегментация**: запись разбивается на сегменты `segment_*.wav` внутри папки `meeting_YYYYMMDD_HHMMSS/`.
3. **Транскрипция**: `faster-whisper` транскрибирует каждый сегмент.
4. **Диаризация**: `Resemblyzer` извлекает embedding'и для каждого фразового сегмента, `sklearn` кластеризует (AgglomerativeClustering, cosine distance) для определения количества спикеров.
5. **Суммаризация**: транскрипт подставляется в промпт из `meeting_types.json`, результат отправляется в `koda`, ответ парсится как JSON.
6. **Сохранение**: транскрипт в `transcripts/{subdir}/{id}/transcript.txt`, суммаризация в `summaries/{subdir}/{id}/summary.json` и `summary.md`.

## Правила разработки

- Все пути жёстко привязаны к `~/Yandex.Disk/carrier/meeting-ai/` (переменная `BASE_DIR`).
- Прокси-переменные (`http_proxy`, `https_proxy`, `all_proxy`) принудительно отключаются в каждом скрипте.
- Обработка запускается в фоновых потоках (threading) и subprocess.
- Веб-интерфейс использует HTTP-запросы, перезагрузка по действию пользователя.
- Тип встречи определяется либо аргументом `--type`, либо файлом `.meeting_type` в папке записи.
- Диаризация откатывается к одному спикеству при ошибках или недостатке данных.
- Транскрипт обрезается до 15000 символов перед отправкой в KodaCode.
- KodaCode CLI имеет таймаут 120 секунд.
- Папки встреч ищутся рекурсивно через `AUDIO_DIR.rglob()`.

## Роуты веб-интерфейса

### HTML-страницы
- `GET /` — список встреч
- `GET /meeting/<meeting_name>` — детали встречи

### API endpoints
- `GET /api/status` — статус системы и записи
- `GET /api/meetings` — список всех записей
- `GET /api/meetings/<meeting_name>` — детали встречи (JSON)
- `POST /api/start` — начать запись (`{type: "bd"|"default"}`)
- `POST /api/stop` — остановить запись
- `GET /api/config` — конфигурация типов встреч
- `GET /api/audio/<path>` — потоковая передача аудио
- `GET /api/transcript/<meeting_name>` — скачать транскрипт
- `GET /api/summary/<meeting_name>` — скачать суммаризацию
- `POST /api/process/transcript/<meeting_name>` — транскрибировать заново
- `POST /api/process/summary/<meeting_name>` — суммаризировать заново
- `POST /api/process/all/<meeting_name>` — обработать всё заново

## Структура данных

### Папка встречи
```
meeting_YYYYMMDD_HHMMSS/
├── segment_001.wav
├── segment_002.wav
├── .meeting_type    # (опционально) "bd" или "default"
```

### Результат транскрипции
```
transcript.txt
[00:01] Говорящий 1:
  Текст первой реплики
[00:05] Говорящий 2:
  Текст второй реплики
```

### Результат суммаризации (JSON)
```json
{
  "title": "...",
  "summary": "...",
  "action_items": ["..."],
  "decisions": ["..."],
  "career_insights": ["..."],
  "sentiment": "позитивный"
}
```

## Логирование

Все операции записи пишутся в `recorder.log`:
- Старт/стоп записей
- Создание/удаление virtual sinks
- Объединение аудиофайлов
- Длительность записей
