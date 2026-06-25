#!/usr/bin/env python3
"""
Генерация и управление иконками для системного трея
"""
import io
from pathlib import Path
from typing import Optional, Tuple


class IconManager:
    """Управление иконками системного трея"""
    
    # Цвета для разных состояний (RGB)
    COLORS = {
        "green": (76, 175, 80),      # Запущен
        "yellow": (255, 193, 7),     # Запуск
        "red": (244, 67, 54),        # Ошибка/остановлен
        "gray": (158, 158, 158),     # Неактивен
        "recording": (244, 67, 54),  # Идёт запись (красный с индикатором)
    }
    
    def __init__(self, icons_dir: Optional[Path] = None):
        self.icons_dir = icons_dir or Path(__file__).parent.parent / "assets" / "icons"
        self._cache: dict[str, bytes] = {}
    
    def _create_icon(
        self,
        color: Tuple[int, int, int],
        size: int = 24,
        recording: bool = False
    ) -> bytes:
        """
        Создать PNG иконку программно.
        Рисуем микрофон с цветным индикатором.
        """
        try:
            from PIL import Image, ImageDraw
        except ImportError:
            # Если PIL нет, возвращаем заглушку
            return self._create_simple_icon(color, size, recording)
        
        # Создаём изображение с альфа-каналом
        img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        # Центр и размеры
        cx, cy = size // 2, size // 2
        mic_width = size // 3
        mic_height = size // 2
        
        # Рисуем микрофон (серый)
        mic_gray = (200, 200, 200, 255)
        
        # Тело микрофона (прямоугольник с закруглением)
        mic_left = cx - mic_width // 2
        mic_top = cy - mic_height // 2
        mic_right = cx + mic_width // 2
        mic_bottom = cy + mic_height // 2
        
        # Рисуем закруглённый прямоугольник для микрофона
        radius = mic_width // 2
        draw.rounded_rectangle(
            [mic_left, mic_top, mic_right, mic_bottom],
            radius=radius,
            fill=mic_gray
        )
        
        # Ножка микрофона
        stem_width = mic_width // 4
        stem_height = size // 6
        draw.rectangle(
            [cx - stem_width // 2, mic_bottom, cx + stem_width // 2, mic_bottom + stem_height],
            fill=mic_gray
        )
        
        # Основание
        base_width = mic_width
        base_height = size // 8
        draw.rounded_rectangle(
            [cx - base_width // 2, mic_bottom + stem_height - 2,
             cx + base_width // 2, mic_bottom + stem_height + base_height],
            radius=2,
            fill=mic_gray
        )
        
        # Индикатор состояния (точка сверху или сбоку)
        indicator_color = (*color, 255)
        indicator_size = size // 6
        
        if recording:
            # Пульсирующая точка сверху
            indicator_x = cx
            indicator_y = mic_top - indicator_size // 2 - 2
        else:
            # Точка в углу
            indicator_x = size - indicator_size - 2
            indicator_y = 2
        
        draw.ellipse(
            [indicator_x - indicator_size // 2, indicator_y - indicator_size // 2,
             indicator_x + indicator_size // 2, indicator_y + indicator_size // 2],
            fill=indicator_color
        )
        
        # Сохраняем в bytes
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        return buffer.getvalue()
    
    def _create_simple_icon(
        self,
        color: Tuple[int, int, int],
        size: int = 24,
        recording: bool = False
    ) -> bytes:
        """Создать простую иконку без PIL (заглушка)"""
        # Минимальный PNG 1x1 пиксель (будет масштабирован системой)
        # Это fallback если PIL не установлен
        
        # Простой PNG файл (серый квадрат)
        minimal_png = bytes([
            0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,
            0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,
            0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
            0x08, 0x02, 0x00, 0x00, 0x00, 0x90, 0x77, 0x53,
            0xDE, 0x00, 0x00, 0x00, 0x0C, 0x49, 0x44, 0x41,
            0x54, 0x08, 0xD7, 0x63, 0x00, 0x00, 0x00, 0x03,
            0x00, 0x01, 0x00, 0x18, 0xDD, 0x8D, 0xB4, 0x00,
            0x00, 0x00, 0x00, 0x49, 0x45, 0x4E, 0x44, 0xAE,
            0x42, 0x60, 0x82
        ])
        return minimal_png
    
    def get_icon(self, state: str, size: int = 24) -> bytes:
        """
        Получить иконку для состояния.
        
        Состояния:
        - running: сервер запущен (зелёный)
        - starting: запуск (жёлтый)
        - stopped: остановлен (красный/серый)
        - error: ошибка (красный)
        - recording: идёт запись (красный с индикатором)
        """
        cache_key = f"{state}_{size}"
        
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        color_map = {
            "running": self.COLORS["green"],
            "starting": self.COLORS["yellow"],
            "stopped": self.COLORS["gray"],
            "error": self.COLORS["red"],
            "recording": self.COLORS["recording"],
        }
        
        color = color_map.get(state, self.COLORS["gray"])
        recording = (state == "recording")
        
        icon_data = self._create_icon(color, size, recording)
        self._cache[cache_key] = icon_data
        
        return icon_data
    
    def get_icon_path(self, state: str, size: int = 24) -> Optional[Path]:
        """
        Сохранить иконку во временный файл и вернуть путь.
        Нужно для совместимости с GTK AppIndicator.
        """
        try:
            icon_data = self.get_icon(state, size)
            
            # Создаём директорию если нет
            self.icons_dir.mkdir(parents=True, exist_ok=True)
            
            # Сохраняем файл
            icon_file = self.icons_dir / f"tray_{state}_{size}.png"
            icon_file.write_bytes(icon_data)
            
            return icon_file
            
        except Exception as e:
            print(f"[IconManager] Ошибка создания иконки: {e}")
            return None
    
    def clear_cache(self):
        """Очистить кэш иконок"""
        self._cache.clear()
