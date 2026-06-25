#!/usr/bin/env python3
"""
Всплывающие уведомления для Meeting AI
Использует стандартные уведомления Ubuntu (libnotify)
"""
import subprocess
from pathlib import Path
from typing import Optional


class NotificationManager:
    """Менеджер всплывающих уведомлений"""
    
    def __init__(self, app_name: str = "Meeting AI", icon_path: Optional[Path] = None):
        self.app_name = app_name
        self.icon_path = icon_path
    
    def _send_notification(
        self,
        title: str,
        message: str,
        urgency: str = "normal",
        icon: Optional[str] = None,
        timeout: int = 5000
    ):
        """Отправить уведомление через notify-send"""
        try:
            cmd = [
                "notify-send",
                "-a", self.app_name,
                "-u", urgency,
                "-t", str(timeout)
            ]
            
            if icon:
                cmd.extend(["-i", icon])
            elif self.icon_path and self.icon_path.exists():
                cmd.extend(["-i", str(self.icon_path)])
            
            cmd.extend([title, message])
            
            subprocess.run(cmd, capture_output=True, timeout=5)
            
        except Exception as e:
            print(f"[Notification] Ошибка отправки уведомления: {e}")
    
    def show_server_started(self):
        """Уведомление о запуске сервера"""
        self._send_notification(
            title="🎙️ Meeting AI",
            message="Сервер запущен и готов к работе",
            urgency="low",
            icon="emblem-ok"
        )
    
    def show_server_stopped(self):
        """Уведомление об остановке сервера"""
        self._send_notification(
            title="🎙️ Meeting AI",
            message="Сервер остановлен",
            urgency="low",
            icon="emblem-stop"
        )
    
    def show_server_error(self, error_message: str):
        """Уведомление об ошибке сервера"""
        self._send_notification(
            title="❌ Meeting AI - Ошибка",
            message=error_message[:100],  # Ограничиваем длину
            urgency="critical",
            icon="dialog-error",
            timeout=10000
        )
    
    def show_recording_started(self, meeting_type_name: str):
        """Уведомление о начале записи
        
        Args:
            meeting_type_name: Название типа встречи (из конфига)
        """
        # Проверяем, является ли аргумент ключом или названием
        type_name = meeting_type_name
        if meeting_type_name in ["bd", "fd", "default"]:
            type_name = {
                "bd": "Backend Daily",
                "fd": "Frontend Daily",
                "default": "Встреча"
            }.get(meeting_type_name, "Встреча")
        
        self._send_notification(
            title="🔴 Запись начата",
            message=f"Запись {type_name.lower()} идёт",
            urgency="normal",
            icon="audio-input-microphone",
            timeout=3000
        )
    
    def show_recording_stopped(self):
        """Уведомление об остановке записи"""
        self._send_notification(
            title="⏹️ Запись остановлена",
            message="Начинается обработка...",
            urgency="normal",
            icon="process-working",
            timeout=5000
        )
    
    def show_processing_complete(self):
        """Уведомление о завершении обработки"""
        self._send_notification(
            title="✅ Обработка завершена",
            message="Транскрипция и суммаризация готовы",
            urgency="low",
            icon="emblem-ok",
            timeout=5000
        )
    
    def show_web_opened(self):
        """Уведомление об открытии веб-интерфейса"""
        self._send_notification(
            title="🌐 Meeting AI",
            message="Веб-интерфейс открыт в браузере",
            urgency="low",
            timeout=2000
        )
    
    def show_custom(self, title: str, message: str, urgency: str = "normal"):
        """Пользовательское уведомление"""
        self._send_notification(
            title=title,
            message=message,
            urgency=urgency
        )
