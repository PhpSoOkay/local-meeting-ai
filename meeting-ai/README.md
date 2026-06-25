# LOCAL MEETING AI

Система автоматической записи, транскрибации и суммаризации рабочих встреч.

## Возможности

- 🎙️ **Запись звука** — запись с микрофона и звука компьютера через PulseAudio
- 📝 **Транскрибация** — преобразование речи в текст с помощью faster-whisper (medium)
- 👥 **Диаризация** — автоматическое определение и разделение спикеров (Resemblyzer)
- 📊 **Суммаризация** — создание структурированного резюме встречи через KodaCode CLI
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
pip install flask faster-whisper resemblyzer scikit-learn numpy
```

### Дополнительные требования

- **KodaCode CLI** (`koda`) — должен быть установлен и доступен в PATH
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

4. Проверьте доступность KodaCode CLI:
```bash
koda --version
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

3. **Транскрибация**: Каждый сегмент обрабатывается моделью faster-whisper (medium, CPU, int8).

4. **Диаризация**: 
   - Извлекаются эмбеддинги спикеров через Resemblyzer
   - Кластеризация (AgglomerativeClustering, cosine distance)
   - Определение количества спикеров и распределение реплик

5. **Суммаризация**:
   - Транскрипт обрезается до 15000 символов
   - Подставляется в промпт из `meeting_types.json`
   - Отправляется в KodaCode CLI (таймаут 120 сек)
   - Результат парсится как JSON

6. **Сохранение**:
   - Транскрипт → `transcripts/{subdir}/{id}/transcript.txt`
   - Суммари → `summaries/{subdir}/{id}/summary.json` + `summary.md`

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
- Проверьте установку KodaCode CLI: `koda --version`
- Убедитесь, что транскрипт не пустой
- Проверьте логи на предмет таймаутов

### PulseAudio ошибки
- Перезапустите PulseAudio: `pulseaudio -k && pulseaudio --start`
- Проверьте список устройств: `pactl list sources`

## Лицензия

Внутренний проект NLP-Core-Team.
