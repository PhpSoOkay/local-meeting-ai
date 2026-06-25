#!/usr/bin/env python3
"""
Мост к CLI командам meeting recorder
Управление записью встреч через subprocess
"""
import os
import sys
import subprocess
import threading
from pathlib import Path
from typing import Optional, Callable
from queue import Queue, Empty
import json


class RecorderBridge:
    """Мост к CLI командам meeting recorder"""
    
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self._is_recording = False
        self._recording_type: Optional[str] = None
        self._status_callbacks: list[Callable] = []
        self._check_thread: Optional[threading.Thread] = None
        self._stop_check = False
    
    def add_status_callback(self, callback: Callable):
        """Добавить колбэк на изменение статуса записи"""
        self._status_callbacks.append(callback)
    
    def _notify_status_change(self):
        """Уведомить об изменении статуса записи"""
        for callback in self._status_callbacks:
            try:
                callback(self._is_recording, self._recording_type)
            except Exception:
                pass
    
    def _get_meeting_command(self) -> str:
        """Получить путь к команде meeting"""
        # Пробуем найти в venv
        meeting_cmd = self.base_dir / ".venv" / "bin" / "meeting"
        if meeting_cmd.exists():
            return str(meeting_cmd)
        
        # Пробуем глобальную команду
        return "meeting"
    
    def _run_command(self, args: list[str], capture: bool = False, background: bool = False) -> tuple[bool, str]:
        """Выполнить команду и вернуть результат"""
        cmd = [self._get_meeting_command()] + args
        
        env = os.environ.copy()
        env.pop("http_proxy", None)
        env.pop("https_proxy", None)
        env.pop("all_proxy", None)
        
        try:
            if background:
                # Запускаем в фоне, не ждём завершения
                subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                    env=env,
                    cwd=str(self.base_dir)
                )
                return True, "Command started in background"
            
            if capture:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    cwd=str(self.base_dir),
                    timeout=30
                )
                return result.returncode == 0, result.stdout + result.stderr
            else:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    cwd=str(self.base_dir),
                    timeout=30
                )
                return result.returncode == 0, result.stdout + result.stderr
        except subprocess.TimeoutExpired:
            return False, "Таймаут выполнения команды"
        except Exception as e:
            return False, str(e)
    
    def start_recording(self, meeting_type: str = "default") -> tuple[bool, str]:
        """Начать запись встречи"""
        # Запускаем в фоне, так как команда start сразу возвращает управление
        success, output = self._run_command(["start", "--type", meeting_type], background=True)
        
        if success:
            # Небольшая задержка чтобы процесс успел запуститься
            import time
            time.sleep(1)
            
            # Проверяем статус
            rec_status = self.get_status()
            if rec_status.get("recording"):
                self._is_recording = True
                self._recording_type = meeting_type
                self._notify_status_change()
                return True, "Recording started"
            else:
                # Если статус не обновился, всё равно считаем что запустили
                self._is_recording = True
                self._recording_type = meeting_type
                self._notify_status_change()
                return True, "Recording started"
                
        return success, output
    
    def stop_recording(self, process: bool = True) -> tuple[bool, str]:
        """Остановить запись встречи"""
        args = ["stop"]
        if not process:
            args.append("--no-process")
        
        success, output = self._run_command(args)
        
        if success:
            self._is_recording = False
            self._recording_type = None
            self._notify_status_change()
        
        return success, output
    
    def get_status(self) -> dict:
        """Получить статус записи"""
        success, output = self._run_command(["status"], capture=True)
        
        if not success:
            return {
                "recording": False,
                "type": None,
                "message": output
            }
        
        # Парсим вывод команды status
        is_recording = "Recording:" in output and "active" in output.lower()
        meeting_type = None
        
        if "backend daily" in output.lower():
            meeting_type = "bd"
        elif "default" in output.lower():
            meeting_type = "default"
        
        # Пробуем найти тип из строки вида "Type: bd" или "Type: default"
        for line in output.split('\n'):
            if 'type:' in line.lower():
                if 'bd' in line.lower() or 'backend' in line.lower():
                    meeting_type = "bd"
                elif 'default' in line.lower():
                    meeting_type = "default"
        
        self._is_recording = is_recording
        self._recording_type = meeting_type
        
        return {
            "recording": is_recording,
            "type": meeting_type,
            "message": output
        }
    
    def process_last_recording(self) -> tuple[bool, str]:
        """Обработать последнюю запись"""
        success, output = self._run_command(["process"])
        return success, output
    
    def get_config(self) -> dict:
        """Получить конфигурацию"""
        success, output = self._run_command(["config", "--show"], capture=True)
        
        if success:
            # Пытаемся распарсить JSON если есть
            try:
                # Ищем JSON в выводе
                start_idx = output.find('{')
                end_idx = output.rfind('}') + 1
                if start_idx >= 0 and end_idx > start_idx:
                    return json.loads(output[start_idx:end_idx])
            except:
                pass
        
        return {"raw": output}
    
    def show_config(self) -> tuple[bool, str]:
        """Показать конфигурацию (интерактивно)"""
        # Для интерактивной настройки нужно запустить в терминале
        success, output = self._run_command(["config"])
        return success, output
    
    def start_status_checker(self, interval: int = 5):
        """Запустить фоновую проверку статуса записи"""
        if self._check_thread and self._check_thread.is_alive():
            return
        
        self._stop_check = False
        
        def check_loop():
            while not self._stop_check:
                self.get_status()
                self._notify_status_change()
                
                for i in range(interval):
                    if self._stop_check:
                        break
                    import time
                    time.sleep(1)
        
        self._check_thread = threading.Thread(target=check_loop, daemon=True)
        self._check_thread.start()
    
    def stop_status_checker(self):
        """Остановить проверку статуса"""
        self._stop_check = True
        if self._check_thread:
            self._check_thread.join(timeout=2)
    
    @property
    def is_recording(self) -> bool:
        return self._is_recording
    
    @property
    def recording_type(self) -> Optional[str]:
        return self._recording_type
