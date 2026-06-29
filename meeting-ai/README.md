# LOCAL MEETING AI

Система автоматической записи, транскрибации и суммаризации рабочих встреч.

## Возможности

- 🎙️ **Запись звука** — запись с микрофона и звука компьютера через PulseAudio
- 📝 **Транскрибация** — преобразование речи в текст с помощью faster-whisper (medium)
- 👥 **Диаризация** — автоматическое определение и разделение спикеров (Resemblyzer)
- 📊 **Суммаризация** — создание структурированного резюме через AI-модели (OpenAI-compatible API)
- 🌐 **Веб-интерфейс** — просмотр списка встреч, транскриптов и суммари
- 🔧 **CLI** — управление записью и обработкой из командной строки
- 🖥️ **System Tray** — запуск сервера из иконки в системном трее (Ubuntu)

## Требования

### Системные зависимости

```bash
# Ubuntu/Debian
sudo apt install pulseaudio ffmpeg

# Arch Linux
sudo pacman -S pulseaudio pulseaudio-alsa ffmpeg
```

### Python-пакеты

```bash
pip install flask faster-whisper resemblyzer scikit-learn numpy httpx python-dotenv
```

### Дополнительные требования

- **API-ключ** для AI-провайдера (RouterAI, OpenAI, OpenRouter или локальный Ollama)
- **Python 3.8+**

## Установка

1. Клонируйте репозиторий:
```bash
git clone <repository-url>
cd meeting-ai
```

2. Создайте виртуальное окружение:
```bash
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# или
.venv\Scripts\activate  # Windows
```

3. Установите зависимости:
```bash
pip install flask faster-whisper resemblyzer scikit-learn numpy
```

4. Настройте AI-модели:
```bash
# Создать конфиг моделей и .env
meeting models open
```

5. Добавьте API-ключ в `~/.config/meeting-ai/.env`:
```bash
ROUTERAI_API_KEY=sk-...
```

6. (опционально) Проверьте модели:
```bash
meeting models list
meeting models test routerai-gpt4o-mini
```

## Конфигурация

### Настройка устройств записи

Перед первым использованием настройте устройства PulseAudio:

```bash
# Интерактивная настройка
meeting config

# Показать текущие настройки
meeting config --show

# Список доступных устройств
meeting devices
```

При настройке выберите:
- **Monitor-устройство** — для записи звука компьютера (обычно `*.monitor`)
- **Микрофон** — для записи вашего голоса

### Типы встреч

Конфигурация типов встреч хранится в `config/meeting_types.json`. Доступны:

| Тип | Описание | Промпт |
|-----|----------|--------|
| `default` | Обычная рабочая встреча | Название, краткое содержание, задачи, решения, инсайты, навыки |
| `bd` | Backend Daily (стендап) | Участники, сделали/планы, блокеры, тех. решения, code reviews, оценки |

## Использование

### Веб-интерфейс

Запуск сервера:

```bash
# Через CLI
meeting app [--port 5000] [--host 0.0.0.0] [--no-browser]

# Или напрямую
python web/app.py
```

**Переменные окружения:**
- `MEETING_HOST` — хост (по умолчанию `127.0.0.1`)
- `MEETING_PORT` — порт (по умолчанию `5000`)

После запуска откройте в браузере: `http://localhost:5000`

### CLI-команды

```bash
# Начать запись (с автообработкой)
meeting start [--type bd|default]

# Остановить запись
meeting stop [--no-process]  # --no-process отключает автообработку

# Проверить статус записи
meeting status

# Обработать последнюю запись вручную
meeting process
```

**Примеры:**

```bash
# Начать обычный митинг
meeting start

# Начать backend daily
meeting start --type bd

# Остановить без обработки (обработать позже)
meeting stop --no-process

# Обработать запись позже
meeting process
```

## Структура проекта

```
meeting-ai/
├── web/
│   ├── app.py              # Flask-сервер
│   └── templates/          # HTML-шаблоны
├── scripts/
│   ├── recorder.py         # CLI для записи
│   ├── process_meeting.py  # Обработка встреч
│   └── recorder/           # Пакет записи
├── config/
│   └── meeting_types.json  # Конфигурация типов встреч
├── audio/                  # Аудиозаписи (игнорируется git)
├── transcripts/            # Транскрипты (игнорируется git)
├── summaries/              # Суммари (игнорируется git)
└── chroma_db/              # Векторное хранилище
```

## Как это работает

1. **Запись**: Создаются virtual sinks в PulseAudio, записываются отдельные потоки (ПК + микрофон), затем объединяются в один WAV-файл.

2. **Сегментация**: Аудио разбивается на сегменты по тишине для удобства обработки.

3. **Транскрибация**: 
   - По умолчанию — локальная модель faster-whisper (medium, CPU, int8)
   - При выборе облачной модели — отправка сегментов через `/audio/transcriptions` API
   - Выбор режима — `default_transcription` в `models.json` ("local" или имя модели)

4. **Диаризация**: 
   - Извлекаются эмбеддинги спикеров через Resemblyzer
   - Кластеризация (AgglomerativeClustering, cosine distance)
   - Определение количества спикеров и распределение реплик

5. **Суммаризация**:
   - Транскрипт обрезается до 15000 символов
   - Подставляется в промпт из `meeting_types.json`
   - Отправляется в AI-модель через OpenAI-compatible API (таймаут 120 сек)
   - Модель выбирается через `default_summarization` в `models.json`
   - Результат парсится как JSON

6. **Сохранение**:
   - Транскрипт → `transcripts/{subdir}/{id}/transcript.txt`
   - Суммари → `summaries/{subdir}/{id}/summary.json` + `summary.md`

## Управление AI-моделями

Выбор моделей для транскрипции и суммаризации осуществляется через конфигурационные файлы:

- **`~/.config/meeting-ai/models.json`** — список моделей и настройки по умолчанию
- **`~/.config/meeting-ai/.env`** — API-ключи (секреты)

### Команды

```bash
meeting models list          # Показать настроенные модели
meeting models test <name>   # Проверить доступность модели
meeting models open          # Открыть конфиг в редакторе
```

### Переключение модели

Отредактируйте `default_summarization` или `default_transcription` в `models.json`:

```json
{
  "default_summarization": "openrouter-claude",
  "default_transcription": "local",
  ...
}
```

### Добавление новой модели

1. Добавьте запись в `models` в `models.json`
2. Добавьте API-ключ в `.env` (если требуется)
3. Проверьте: `meeting models list`

## API

Веб-сервер предоставляет REST API:

| Метод | Эндпоинт | Описание |
|-------|----------|----------|
| GET | `/api/status` | Статус системы и текущей записи |
| GET | `/api/meetings` | Список всех встреч |
| GET | `/api/meetings/<name>` | Детали встречи (JSON) |
| POST | `/api/start` | Начать запись `{type: "bd"\|"default"}` |
| POST | `/api/stop` | Остановить запись |
| GET | `/api/config` | Конфигурация типов встреч |
| GET | `/api/audio/<path>` | Потоковая передача аудио |
| GET | `/api/transcript/<name>` | Скачать транскрипт |
| GET | `/api/summary/<name>` | Скачать суммари |
| POST | `/api/process/transcript/<name>` | Транскрибировать заново |
| POST | `/api/process/summary/<name>` | Суммаризировать заново |
| POST | `/api/process/all/<name>` | Обработать всё заново |

## System Tray (Ubuntu)

Для удобного запуска веб-сервера используйте приложение в системном трее.

### Установка

```bash
cd ~/Yandex.Disk/carrier/meeting-ai
python tray/install.py
```

Скрипт установит:
- Системные зависимости (GTK, AppIndicator)
- Python зависимости (Pillow)
- .desktop файл в меню приложений
- Иконки для разных состояний

### Использование

1. Найдите **Meeting AI** в меню приложений
2. Запустите — иконка появится в системном трее
3. Через меню в трее можно:
   - Открыть веб-интерфейс
   - Начать/остановить запись
   - Просмотреть логи сервера
   - Управлять сервером

**Подробная документация:** [tray/README.md](tray/README.md)

### Автозапуск

```bash
# Включить автозапуск при входе в систему
python tray/install.py --autostart

# Отключить автозапуск
python tray/install.py --no-autostart
```

---

## Логирование

Все операции записи логируются в `recorder.log`:
- Старт/стоп записей
- Создание virtual sinks
- Объединение аудиофайлов
- Длительность записей

## Решение проблем

### Нет звука в записи
- Проверьте настройки: `meeting config --show`
- Убедитесь, что выбраны правильные устройства: `meeting devices`
- Проверьте уровни звука в `pavucontrol`

### Ошибка при транскрибации
- Убедитесь, что модель faster-whisper загружена (первый запуск может занять время)
- Проверьте доступность файла аудио

### Ошибка суммаризации
- Проверьте настройки моделей: `meeting models list`
- Убедитесь, что API-ключ задан в `.env`: `cat ~/.config/meeting-ai/.env`
- Проверьте доступность модели: `meeting models test routerai-gpt4o-mini`
- Убедитесь, что транскрипт не пустой
- Проверьте логи на предмет таймаутов

### Облачная транскрипция не работает
- Проверьте интернет-соединение
- При недоступности облака система автоматически переключится на локальную модель
- Проверьте API-ключ и баланс провайдера

### PulseAudio ошибки
- Перезапустите PulseAudio: `pulseaudio -k && pulseaudio --start`
- Проверьте список устройств: `pactl list sources`

## Лицензия

Внутренний проект NLP-Core-Team.
