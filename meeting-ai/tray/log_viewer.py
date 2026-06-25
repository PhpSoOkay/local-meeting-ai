#!/usr/bin/env python3
"""
Окно просмотра логов сервера
"""
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib, Pango
from typing import Optional
from queue import Queue


class LogViewerWindow(Gtk.Window):
    """Окно для просмотра логов сервера"""
    
    def __init__(self, log_queue: Queue):
        super().__init__(title="Meeting AI - Логи сервера")
        
        self.log_queue = log_queue
        self._update_timer: Optional[int] = None
        self._auto_scroll = True
        self._is_destroyed = False
        
        # Настройки окна
        self.set_default_size(800, 500)
        self.set_border_width(10)
        
        # Обработчик закрытия
        self.connect("delete-event", self.on_delete_event)
        
        # Создаём UI
        self._create_ui()
        
        # Тёмная тема
        self._apply_dark_theme()
    
    def _create_ui(self):
        """Создание интерфейса"""
        # Главный вертикальный бокс
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.add(main_box)
        
        # Заголовок
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        main_box.pack_start(header_box, False, False, 0)
        
        title_label = Gtk.Label(label="📋 Логи сервера Meeting AI")
        title_label.set_halign(Gtk.Align.START)
        header_box.pack_start(title_label, True, True, 0)
        
        # Кнопка очистки
        clear_btn = Gtk.Button(label="🗑 Очистить")
        clear_btn.connect("clicked", self.on_clear_clicked)
        header_box.pack_start(clear_btn, False, False, 0)
        
        # Чекбокс автоскролла
        auto_scroll_check = Gtk.CheckButton(label="⬇ Автоскролл")
        auto_scroll_check.set_active(True)
        auto_scroll_check.connect("toggled", self.on_auto_scroll_toggled)
        header_box.pack_start(auto_scroll_check, False, False, 0)
        
        # Кнопка закрытия (не останавливает сервер)
        close_btn = Gtk.Button(label="✕ Закрыть")
        close_btn.connect("clicked", self.on_close_clicked)
        header_box.pack_start(close_btn, False, False, 0)
        
        # ScrolledWindow для текстового поля
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        main_box.pack_start(scrolled, True, True, 0)
        
        # Текстовое поле для логов
        self.text_view = Gtk.TextView()
        self.text_view.set_editable(False)
        self.text_view.set_cursor_visible(False)
        self.text_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.text_view.set_monospace(True)
        
        # Настраиваем шрифт
        font_desc = Pango.FontDescription.from_string("Monospace 11")
        self.text_view.modify_font(font_desc)
        
        self.text_buffer = self.text_view.get_buffer()
        
        # Создаём теги для разных уровней логов
        self.text_buffer.create_tag("info", foreground="#2E7D32")  # Зелёный
        self.text_buffer.create_tag("warning", foreground="#F57C00")  # Оранжевый
        self.text_buffer.create_tag("error", foreground="#C62828")  # Красный
        self.text_buffer.create_tag("system", foreground="#1976D2")  # Синий
        self.text_buffer.create_tag("output", foreground="#616161")  # Серый
        
        scrolled.add(self.text_view)
        
        # Статус бар
        status_label = Gtk.Label(label="Обновляется в реальном времени")
        status_label.set_halign(Gtk.Align.START)
        status_label.get_style_context().add_class("dim-label")
        main_box.pack_start(status_label, False, False, 0)
    
    def _apply_dark_theme(self):
        """Применить тёмную тему"""
        css = b"""
        window {
            background-color: #1e1e1e;
            color: #e0e0e0;
        }
        textview {
            background-color: #1e1e1e;
            color: #e0e0e0;
        }
        button {
            background-color: #2d2d2d;
            color: #e0e0e0;
        }
        button:hover {
            background-color: #3d3d3d;
        }
        """
        
        style_provider = Gtk.CssProvider()
        style_provider.load_from_data(css)
        
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            style_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
    
    def _get_log_tag(self, log_line: str) -> str:
        """Определить тег для строки лога"""
        line_lower = log_line.lower()
        
        if "[sys]" in line_lower:
            return "system"
        elif "[err]" in line_lower or "error" in line_lower:
            return "error"
        elif "[warn]" in line_lower or "warning" in line_lower:
            return "warning"
        elif "[out]" in line_lower:
            return "output"
        else:
            return "info"
    
    def _update_logs(self) -> bool:
        """Обновить логи из очереди (вызывается в main thread)"""
        if self._is_destroyed:
            return False
        
        logs_added = False
        
        while True:
            try:
                log_line = self.log_queue.get_nowait()
                
                # Добавляем строку с соответствующим тегом
                tag_name = self._get_log_tag(log_line)
                tag = self.text_buffer.get_tag_by_name(tag_name)
                
                end_iter = self.text_buffer.get_end_iter()
                
                if tag:
                    self.text_buffer.insert_with_tags(end_iter, log_line + "\n", tag)
                else:
                    self.text_buffer.insert(end_iter, log_line + "\n")
                
                logs_added = True
                
            except:
                break
        
        # Автоскролл вниз
        if logs_added and self._auto_scroll:
            GLib.idle_add(self._scroll_to_bottom)
        
        return True  # Продолжать таймер
    
    def _scroll_to_bottom(self):
        """Прокрутить вниз"""
        if self._is_destroyed:
            return
        
        buffer = self.text_view.get_buffer()
        end_iter = buffer.get_end_iter()
        
        # Получаем видимый прямоугольник
        visible_rect = self.text_view.get_visible_rect()
        
        # Прокручиваем к концу
        self.text_view.scroll_to_iter(end_iter, 0.0, False, 0.0, 0.0)
    
    def start_updates(self):
        """Запустить обновление логов"""
        # Запускаем обновление каждые 500мс
        self._update_timer = GLib.timeout_add(500, self._update_logs)
    
    def stop_updates(self):
        """Остановить обновление логов"""
        if self._update_timer:
            GLib.source_remove(self._update_timer)
            self._update_timer = None
    
    def clear_logs(self):
        """Очистить логи"""
        self.text_buffer.set_text("")
    
    def on_delete_event(self, widget, event):
        """Обработчик события закрытия окна"""
        self.hide()
        return True  # Не уничтожать окно
    
    def on_close_clicked(self, button):
        """Кнопка закрытия"""
        self.hide()
    
    def on_clear_clicked(self, button):
        """Кнопка очистки логов"""
        self.clear_logs()
    
    def on_auto_scroll_toggled(self, checkbutton):
        """Переключение автоскролла"""
        self._auto_scroll = checkbutton.get_active()
    
    def destroy(self):
        """Уничтожение окна"""
        self._is_destroyed = True
        self.stop_updates()
        super().destroy()
