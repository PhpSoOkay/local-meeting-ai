#!/usr/bin/env python3
"""
Управление Flask-сервером Meeting AI в отдельном процессе
"""
import os
import sys
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional, Callable
from queue import Queue, Empty


class ServerManager:
    """Управляет процессом Flask-сервера"""
    
    def __init__(self, base_dir: Path, port: int = 5000, host: str = "127.0.0.1"):
        self.base_dir = base_dir
        self.port = port
        self.host = host
        self.process: Optional[subprocess.Popen] = None
        self.log_queue: Queue = Queue()
        self._stop_event = threading.Event()
        self._log_thread: Optional[threading.Thread] = None
        self._status = "stopped"  # stopped, starting, running, error
        self._error_message: Optional[str] = None
        self._status_callbacks: list[Callable] = []
        
    def add_status_callback(self, callback: Callable):
        """Добавить колбэк на изменение статуса"""
        self._status_callbacks.append(callback)
        
    def _notify_status_change(self):
        """Уведомить о изменении статуса"""
        for callback in self._status_callbacks:
            try:
                callback(self._status, self._error_message)
            except Exception:
                pass
    
    @property
    def status(self) -> str:
        return self._status
    
    @property
    def is_running(self) -> bool:
        return self._status == "running"
    
    def _set_status(self, status: str, error: Optional[str] = None):
        """Установить статус и уведомить"""
        self._status = status
        self._error_message = error
        self._notify_status_change()
    
    def _read_output(self, pipe, prefix: str = ""):
        """Чтение вывода процесса в неблокирующем режиме"""
        try:
            for line in iter(pipe.readline, ''):
                if line:
                    timestamp = time.strftime("%H:%M:%S")
                    log_line = f"[{timestamp}] {prefix}{line.strip()}"
                    self.log_queue.put(log_line)
        except Exception:
            pass
        finally:
            pipe.close()
    
    def _start_log_reader(self, process: subprocess.Popen):
        """Запуск потоков для чтения stdout/stderr"""
        def read_stdout():
            self._read_output(process.stdout, "[OUT] ")
        
        def read_stderr():
            self._read_output(process.stderr, "[ERR] ")
        
        self._log_thread = threading.Thread(target=read_stdout, daemon=True)
        stderr_thread = threading.Thread(target=read_stderr, daemon=True)
        
        self._log_thread.start()
        stderr_thread.start()
    
    def start(self) -> bool:
        """Запуск Flask-сервера"""
        if self.process and self.process.poll() is None:
            self.log_queue.put("[SYS] Сервер уже запущен")
            return True
        
        self._set_status("starting")
        self.log_queue.put("[SYS] Запуск сервера...")
        
        try:
            # Путь к скрипту веб-сервера
            server_script = self.base_dir / "web" / "app.py"
            venv_python = self.base_dir / ".venv" / "bin" / "python"
            
            if not venv_python.exists():
                venv_python = Path(sys.executable)
            
            # Окружение для subprocess
            env = os.environ.copy()
            env["MEETING_HOST"] = self.host
            env["MEETING_PORT"] = str(self.port)
            env["PYTHONUNBUFFERED"] = "1"
            
            # Отключаем прокси для subprocess
            env.pop("http_proxy", None)
            env.pop("https_proxy", None)
            env.pop("all_proxy", None)
            
            # Запуск процесса
            self.process = subprocess.Popen(
                [str(venv_python), str(server_script)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.PIPE,
                env=env,
                cwd=str(self.base_dir),
                preexec_fn=os.setsid,  # Создаём новую группу процессов
                text=True,
                bufsize=1
            )
            
            # Запуск чтения логов
            self._start_log_reader(self.process)
            
            # Ждём подтверждения запуска (3 секунды)
            start_time = time.time()
            while time.time() - start_time < 3:
                if self.process.poll() is not None:
                    # Процесс умер сразу
                    exit_code = self.process.returncode
                    self._set_status("error", f"Сервер не запустился (код {exit_code})")
                    self.log_queue.put(f"[SYS] Ошибка запуска: код выхода {exit_code}")
                    return False
                
                try:
                    log = self.log_queue.get_nowait()
                    if "Web interface:" in log or "Running on" in log:
                        self._set_status("running")
                        self.log_queue.put("[SYS] Сервер успешно запущен")
                        return True
                except Empty:
                    pass
                
                time.sleep(0.1)
            
            # Если прошли 3 секунды и процесс жив — считаем запущенным
            if self.process.poll() is None:
                self._set_status("running")
                self.log_queue.put("[SYS] Сервер запущен")
                return True
            
            self._set_status("error", "Таймаут запуска сервера")
            return False
            
        except Exception as e:
            self._set_status("error", str(e))
            self.log_queue.put(f"[SYS] Ошибка запуска: {e}")
            return False
    
    def stop(self, timeout: int = 5) -> bool:
        """Остановка Flask-сервера"""
        if not self.process or self.process.poll() is not None:
            self.log_queue.put("[SYS] Сервер не запущен")
            self._set_status("stopped")
            return True
        
        self.log_queue.put("[SYS] Остановка сервера...")
        
        try:
            # Graceful shutdown: сначала SIGTERM
            os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
            
            # Ждём завершения
            start_time = time.time()
            while time.time() - start_time < timeout:
                if self.process.poll() is not None:
                    self._set_status("stopped")
                    self.log_queue.put("[SYS] Сервер остановлен")
                    return True
                time.sleep(0.1)
            
            # Если не остановился — SIGKILL
            self.log_queue.put("[SYS] Принудительная остановка...")
            os.killpg(os.getpgid(self.process.pid), signal.SIGKILL)
            self.process.wait(timeout=2)
            
            self._set_status("stopped")
            self.log_queue.put("[SYS] Сервер остановлен (принудительно)")
            return True
            
        except Exception as e:
            self.log_queue.put(f"[SYS] Ошибка остановки: {e}")
            self._set_status("error", str(e))
            return False
    
    def restart(self) -> bool:
        """Перезапуск сервера"""
        self.log_queue.put("[SYS] Перезапуск сервера...")
        self.stop()
        time.sleep(0.5)
        return self.start()
    
    def get_logs(self, max_lines: int = 1000) -> list[str]:
        """Получить логи из очереди"""
        logs = []
        while len(logs) < max_lines:
            try:
                logs.append(self.log_queue.get_nowait())
            except Empty:
                break
        return logs
    
    def check_status(self) -> str:
        """Проверить статус процесса"""
        if not self.process:
            self._set_status("stopped")
            return "stopped"
        
        poll_result = self.process.poll()
        if poll_result is None:
            if self._status != "running":
                self._set_status("running")
            return "running"
        else:
            self._set_status("stopped")
            return "stopped"
