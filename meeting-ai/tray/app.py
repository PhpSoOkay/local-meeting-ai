#!/usr/bin/env python3
"""
Meeting AI System Tray Application
Главное приложение системного трея для Ubuntu Linux
"""
import sys
import os
import signal
import subprocess
import webbrowser
import threading
import json
from pathlib import Path
from typing import Optional, Dict

# Добавляем parent directory для импортов
BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))

# Отключаем прокси
os.environ.pop("http_proxy", None)
os.environ.pop("https_proxy", None)
os.environ.pop("all_proxy", None)

# Проверяем GTK перед импортом
try:
    import gi
    gi.require_version('Gtk', '3.0')
    gi.require_version('AppIndicator3', '0.1')
    from gi.repository import Gtk, AppIndicator3, GLib, Gdk
except (ImportError, ValueError) as e:
    print(f"Ошибка: требуется GTK 3.0 и AppIndicator3")
    print(f"Установите: sudo apt install python3-gi gir1.2-appindicator3-0.1")
    print(f"Детали: {e}")
    sys.exit(1)

from tray.server_manager import ServerManager
from tray.recorder_bridge import RecorderBridge
from tray.log_viewer import LogViewerWindow
from tray.notifications import NotificationManager
from tray.icons import IconManager


class MeetingAITrayApp:
    """Основное приложение системного трея"""
    
    def __init__(self):
        self.base_dir = BASE_DIR
        self.port = int(os.environ.get("MEETING_PORT", "5000"))
        self.host = os.environ.get("MEETING_HOST", "127.0.0.1")
        
        # Загружаем типы встреч из конфига
        self.meeting_types: Dict[str, dict] = self._load_meeting_types()
        
        # Компоненты
        self.server_manager = ServerManager(self.base_dir, self.port, self.host)
        self.recorder_bridge = RecorderBridge(self.base_dir)
        self.notification_manager = NotificationManager(icon_path=self.base_dir / "assets" / "icons" / "tray.png")
        self.icon_manager = IconManager(self.base_dir / "assets" / "icons")
        
        # Окно логов
        self.log_viewer: Optional[LogViewerWindow] = None
        
        # Индикатор в трее
        self.indicator: Optional[AppIndicator3.Indicator] = None
        
        # Текущее состояние
        self._server_status = "stopped"
        self._is_recording = False
        
        # Кнопки меню записи (динамические)
        self.recording_buttons: list[Gtk.MenuItem] = []
        self.recording_separator: Optional[Gtk.MenuItem] = None
        
        # Регистрируем колбэки
        self._setup_callbacks()
    
    def _load_meeting_types(self) -> Dict[str, dict]:
        """Загрузка типов встреч из config/meeting_types.json"""
        config_path = self.base_dir / "config" / "meeting_types.json"
        
        try:
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            print(f"[Tray] Ошибка загрузки типов встреч: {e}")
        
        # Fallback на дефолтные типы
        return {
            "default": {"name": "Обычная встреча"},
            "bd": {"name": "Backend Daily"},
        }
    
    def _setup_callbacks(self):
        """Настройка колбэков"""
        self.server_manager.add_status_callback(self._on_server_status_changed)
        self.recorder_bridge.add_status_callback(self._on_recording_status_changed)
    
    def _on_server_status_changed(self, status: str, error: Optional[str]):
        """Обработчик изменения статуса сервера"""
        self._server_status = status
        
        # Обновляем иконку в главном потоке
        GLib.idle_add(self._update_tray_icon)
        
        # Уведомления
        if status == "running":
            GLib.idle_add(self.notification_manager.show_server_started)
        elif status == "error":
            GLib.idle_add(lambda: self.notification_manager.show_server_error(error or "Неизвестная ошибка"))
        elif status == "stopped":
            GLib.idle_add(self.notification_manager.show_server_stopped)
    
    def _on_recording_status_changed(self, is_recording: bool, meeting_type: Optional[str]):
        """Обработчик изменения статуса записи"""
        old_recording = self._is_recording
        self._is_recording = is_recording
        
        # Уведомления при изменении состояния
        if is_recording and not old_recording:
            # Получаем название типа из конфига
            type_name = "встречу"
            if meeting_type:
                type_info = self.meeting_types.get(meeting_type, {})
                type_name = type_info.get("name", "встречу")
            
            GLib.idle_add(
                lambda tn=type_name: self.notification_manager.show_recording_started(tn)
            )
        elif not is_recording and old_recording:
            GLib.idle_add(self.notification_manager.show_recording_stopped)
    
        # Обновляем иконку
        GLib.idle_add(self._update_tray_icon)
        
    def _update_tray_icon(self):
        """Обновить иконку в трее"""
        if not self.indicator:
            return
        
        # Определяем состояние для иконки
        if self._is_recording:
            icon_state = "recording"
        else:
            icon_state = self._server_status
        
        # Получаем путь к иконке
        icon_path = self.icon_manager.get_icon_path(icon_state, 24)
        
        if icon_path and icon_path.exists():
            # Используем полный путь для AppIndicator
            self.indicator.set_icon_full(str(icon_path), f"Meeting AI - {icon_state}")
    
    def _create_menu(self) -> Gtk.Menu:
        """Создать контекстное меню"""
        menu = Gtk.Menu()
        
        # Открыть веб-интерфейс
        web_item = Gtk.MenuItem(label="🌐 Открыть веб-интерфейс")
        web_item.connect("activate", self._on_open_web)
        menu.append(web_item)
        
        # Разделитель
        menu.append(Gtk.SeparatorMenuItem())
        
        # Динамически создаём кнопки для каждого типа встречи
        self._create_recording_buttons(menu)
        
        # Разделитель
        menu.append(Gtk.SeparatorMenuItem())
        
        # Открыть консоль логов
        console_item = Gtk.MenuItem(label="📋 Открыть консоль логов")
        console_item.connect("activate", self._on_open_console)
        menu.append(console_item)
        
        # Статус
        status_item = Gtk.MenuItem(label="ℹ️ Статус")
        status_item.connect("activate", self._on_show_status)
        menu.append(status_item)
        
        # Разделитель
        menu.append(Gtk.SeparatorMenuItem())
        
        # Перезапустить сервер
        restart_item = Gtk.MenuItem(label="🔄 Перезапустить сервер")
        restart_item.connect("activate", self._on_restart_server)
        menu.append(restart_item)
        
        # Остановить сервер
        stop_server_item = Gtk.MenuItem(label="⏹️ Остановить сервер")
        stop_server_item.connect("activate", self._on_stop_server)
        menu.append(stop_server_item)
        
        # Разделитель
        menu.append(Gtk.SeparatorMenuItem())
        
        # Настройки
        config_item = Gtk.MenuItem(label="⚙️ Настройки")
        config_item.connect("activate", self._on_open_config)
        menu.append(config_item)
        
        # Разделитель
        menu.append(Gtk.SeparatorMenuItem())
        
        # Выход
        quit_item = Gtk.MenuItem(label="✕ Выход")
        quit_item.connect("activate", self._on_quit)
        menu.append(quit_item)
        
        menu.show_all()
        return menu
    
    def _create_recording_buttons(self, menu: Gtk.Menu):
        """Создаёт кнопки запуска записи на основе типов из конфига"""
        self.recording_buttons = []
        
        # Заголовок как MenuItem (без padding)
        header = Gtk.MenuItem(label="🔴 Начать запись:")
        header.set_sensitive(False)
        menu.append(header)
        
        # Для каждого типа встречи создаём кнопку
        for type_key, type_info in self.meeting_types.items():
            button_name = type_info.get("name", type_key)
            
            btn = Gtk.MenuItem(label=f"🎙️ {button_name}")
            btn.connect("activate", self._on_start_recording, type_key)
            # Кнопки запуска всегда активны
            btn.set_sensitive(True)
            
            self.recording_buttons.append(btn)
            menu.append(btn)
        
        # Кнопка остановки (всегда активна)
        self.stop_record_item = Gtk.MenuItem(label="⏹️ Остановить запись")
        self.stop_record_item.connect("activate", self._on_stop_recording)
        # Кнопка остановки всегда активна - пользователь сам знает когда нажать
        self.stop_record_item.set_sensitive(True)
        menu.append(Gtk.SeparatorMenuItem())
        menu.append(self.stop_record_item)
        
    def _on_open_web(self, widget):
        """Открыть веб-интерфейс в браузере"""
        url = f"http://{self.host}:{self.port}"
        webbrowser.open(url)
        self.notification_manager.show_web_opened()
    
    def _on_start_recording(self, widget, meeting_type: str):
        """Начать запись"""
        type_name = self.meeting_types.get(meeting_type, {}).get("name", meeting_type)
        print(f"[Tray] Начало записи: {type_name} ({meeting_type})")
        
        success, message = self.recorder_bridge.start_recording(meeting_type)
        
        if success:
            # Сразу обновляем статус
            self._is_recording = True
            self._recording_type = meeting_type
            
            # Обновляем иконку
            self._update_tray_icon()
            
            print(f"[Tray] ✅ Запись начата: {meeting_type}")
        else:
            self.notification_manager.show_custom(
                "⚠️ Ошибка записи",
                f"Не удалось начать запись: {message[:100]}",
                "critical"
            )
            print(f"[Tray] ❌ Ошибка: {message}")
    
    def _on_stop_recording(self, widget):
        """Остановить запись"""
        print("[Tray] Остановка записи")
        
        success, message = self.recorder_bridge.stop_recording(process=True)
        
        if success:
            # Сразу обновляем статус
            self._is_recording = False
            self._recording_type = None
            
            # Обновляем иконку
            self._update_tray_icon()
            
            print("[Tray] ✅ Запись остановлена")
        else:
            self.notification_manager.show_custom(
                "⚠️ Ошибка",
                f"Не удалось остановить запись: {message[:100]}",
                "critical"
            )
            print(f"[Tray] ❌ Ошибка: {message}")
    
    def _on_open_console(self, widget):
        """Открыть окно логов"""
        if self.log_viewer and self.log_viewer.get_visible():
            self.log_viewer.present()
        else:
            self.log_viewer = LogViewerWindow(self.server_manager.log_queue)
            self.log_viewer.show_all()
            self.log_viewer.start_updates()
    
    def _on_show_status(self, widget):
        """Показать статус"""
        try:
            status_info = []
            status_info.append(f"Сервер: {self._server_status}")
            status_info.append(f"Запись: {'идёт' if self._is_recording else 'не идёт'}")
            
            if self._is_recording and self.recorder_bridge.recording_type:
                type_key = self.recorder_bridge.recording_type
                type_name = self.meeting_types.get(type_key, {}).get("name", type_key)
                status_info.append(f"Тип: {type_name}")
            
            status_info.append(f"Порт: {self.port}")
            status_info.append(f"Хост: {self.host}")
            
            # Получаем детальную информацию от recorder
            try:
                rec_status = self.recorder_bridge.get_status()
                if rec_status.get("message"):
                    # Добавляем только первые 200 символов сообщения
                    msg = rec_status["message"][:200]
                    status_info.append(f"Детали: {msg}")
            except Exception as e:
                status_info.append(f"Ошибка проверки записи: {e}")
            
            message = "\n".join(status_info)
            
            self.notification_manager.show_custom(
                "📊 Статус Meeting AI",
                message,
                "low"
            )
    
        except Exception as e:
            print(f"[Tray] Ошибка при показе статуса: {e}")
    
    def _on_restart_server(self, widget):
        """Перезапустить сервер"""
        print("[Tray] Перезапуск сервера")
        self.server_manager.restart()
    
    def _on_stop_server(self, widget):
        """Остановить сервер"""
        print("[Tray] Остановка сервера")
        
        # Если идёт запись, предупреждаем
        if self._is_recording:
            dialog = Gtk.MessageDialog(
                transient_for=None,
                flags=0,
                message_type=Gtk.MessageType.WARNING,
                buttons=Gtk.ButtonsType.YES_NO,
                text="Идёт запись встречи!"
            )
            dialog.format_secondary_text("Остановка сервера прервёт запись. Продолжить?")
            
            response = dialog.run()
            dialog.destroy()
            
            if response != Gtk.ResponseType.YES:
                return
        
        self.server_manager.stop()
        
    def _on_open_config(self, widget):
        """Открыть настройки"""
        # Открываем конфигуратор в терминале
        # Для этого нужно запустить команду в новом терминале
        try:
            # Пробуем разные варианты открытия терминала
            terminal_cmds = [
                ["gnome-terminal", "--", "meeting", "config"],
                ["xterm", "-e", "meeting", "config"],
                ["konsole", "-e", "meeting", "config"],
            ]
            
            for cmd in terminal_cmds:
                try:
                    subprocess.Popen(cmd, cwd=str(self.base_dir))
                    break
                except FileNotFoundError:
                    continue
            else:
                # Если терминал не найден, показываем сообщение
                self.notification_manager.show_custom(
                    "⚙️ Настройки",
                    "Запустите 'meeting config' в терминале для настройки",
                    "normal"
                )
                
        except Exception as e:
            self.notification_manager.show_custom(
                "⚠️ Ошибка",
                f"Не удалось открыть настройки: {e}",
                "critical"
            )
    
    def _on_quit(self, widget):
        """Выход из приложения"""
        print("[Tray] Выход из приложения")
        
        # Останавливаем запись если идёт
        if self._is_recording:
            self.recorder_bridge.stop_recording(process=True)
        
        # Останавливаем сервер
        self.server_manager.stop()
        
        # Закрываем окно логов
        if self.log_viewer:
            self.log_viewer.destroy()
        
        # Выход из главного цикла
        Gtk.main_quit()
    
    def run(self):
        """Запуск приложения"""
        print("\n" + "="*60)
        print("🎙️  Meeting AI System Tray")
        print("="*60)
        
        # Создаём индикатор
        self.indicator = AppIndicator3.Indicator.new(
            "meeting-ai",
            "emblem-system",  # Временная иконка
            AppIndicator3.IndicatorCategory.APPLICATION_STATUS
        )
        
        self.indicator.set_title("Meeting AI")
        self.indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
        
        # Устанавливаем меню
        self.indicator.set_menu(self._create_menu())
        
        # Запускаем сервер
        print(f"[Tray] Запуск сервера на {self.host}:{self.port}...")
        
        # Запускаем сервер в отдельном потоке
        GLib.idle_add(self._start_server_async)
        
        # Запускаем проверку статуса записи
        self.recorder_bridge.start_status_checker(interval=5)
        
        # Периодическая проверка статуса сервера
        GLib.timeout_add(5000, self._check_server_status)
        
        # Запускаем главный цикл GTK
        Gtk.main()
    
    def _start_server_async(self):
        """Асинхронный запуск сервера"""
        def start():
            self.server_manager.start()
            return False
        
        # Запускаем в отдельном потоке
        thread = threading.Thread(target=start, daemon=True)
        thread.start()
        
        return False
    
    def _check_server_status(self) -> bool:
        """Периодическая проверка статуса сервера"""
        self.server_manager.check_status()
        return True  # Продолжать проверку


def main():
    """Точка входа"""
    # Обработка сигналов
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    
    app = MeetingAITrayApp()
    app.run()


if __name__ == "__main__":
    main()
