import threading
from flask import jsonify, request
from . import processing_bp
from ..helpers import get_recording_status, run_processing, find_meeting_dir, BASE_DIR, get_processing_status


@processing_bp.route('/start', methods=['POST'])
def api_start():
    """API: начать запись"""
    # Проверяем, не запущена ли обработка
    processing = get_processing_status()
    if processing.get("processing") and processing.get("current", {}).get("status") == "processing":
        return jsonify({"error": "Нельзя начать запись — идёт обработка другой встречи", "processing": processing}), 409

    data = request.json or {}
    meeting_type = data.get('type', 'default')

    status = get_recording_status()
    if status["recording"]:
        return jsonify({"error": "Recording already in progress"}), 400

    def run_recording():
        import os
        import subprocess
        import sys
        
        env = os.environ.copy()
        env['http_proxy'] = ''
        env['https_proxy'] = ''
        env['all_proxy'] = ''

        cmd = [
            sys.executable, str(BASE_DIR / "scripts" / "recorder.py"),
            "start", "--type", meeting_type
        ]

        subprocess.run(cmd, cwd=str(BASE_DIR), env=env)

    thread = threading.Thread(target=run_recording, daemon=True)
    thread.start()

    return jsonify({"status": "started", "type": meeting_type})


@processing_bp.route('/stop', methods=['POST'])
def api_stop():
    """API: остановить запись"""
    status = get_recording_status()

    if not status["recording"]:
        return jsonify({"error": "Not recording"}), 400

    try:
        pid = status["pid"]
        import os
        os.kill(pid, 2)  # SIGINT
        return jsonify({"status": "stopped"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@processing_bp.route('/process/transcript/<meeting_name>', methods=['POST'])
def api_process_transcript(meeting_name):
    """API: транскрибировать заново"""
    meeting_dir = find_meeting_dir(meeting_name)
    if not meeting_dir:
        return jsonify({"error": "Meeting not found"}), 404

    type_file = meeting_dir / ".meeting_type"
    meeting_type = "default"
    if type_file.exists():
        meeting_type = type_file.read_text().strip()

    thread = threading.Thread(
        target=run_processing,
        args=(meeting_name, meeting_type),
        daemon=True
    )
    thread.start()

    return jsonify({"status": "processing", "meeting": meeting_name, "step": "transcript"})


@processing_bp.route('/process/summary/<meeting_name>', methods=['POST'])
def api_process_summary(meeting_name):
    """API: суммаризировать заново"""
    meeting_dir = find_meeting_dir(meeting_name)
    if not meeting_dir:
        return jsonify({"error": "Meeting not found"}), 404

    type_file = meeting_dir / ".meeting_type"
    meeting_type = "default"
    if type_file.exists():
        meeting_type = type_file.read_text().strip()

    thread = threading.Thread(
        target=run_processing,
        args=(meeting_name, meeting_type),
        daemon=True
    )
    thread.start()

    return jsonify({"status": "processing", "meeting": meeting_name, "step": "summary"})


@processing_bp.route('/process/all/<meeting_name>', methods=['POST'])
def api_process_all(meeting_name):
    """API: обработать всё (транскрипция + суммаризация)"""
    meeting_dir = find_meeting_dir(meeting_name)
    if not meeting_dir:
        return jsonify({"error": "Meeting not found"}), 404

    type_file = meeting_dir / ".meeting_type"
    meeting_type = "default"
    if type_file.exists():
        meeting_type = type_file.read_text().strip()

    thread = threading.Thread(
        target=run_processing,
        args=(meeting_name, meeting_type),
        daemon=True
    )
    thread.start()

    return jsonify({"status": "processing", "meeting": meeting_name, "step": "all"})


@processing_bp.route('/progress/<meeting_name>', methods=['DELETE'])
def api_delete_progress(meeting_name):
    """API: удалить файл прогресса (для ошибочных процессов)"""
    from ..helpers import BASE_DIR
    from pathlib import Path
    
    progress_file = BASE_DIR / ".progress" / f"{meeting_name}.json"
    
    if not progress_file.exists():
        return jsonify({"error": "Progress file not found"}), 404
    
    try:
        progress_file.unlink()
        return jsonify({"status": "deleted", "meeting": meeting_name})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
