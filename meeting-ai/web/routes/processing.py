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


@processing_bp.route('/process/summary-only/<meeting_name>', methods=['POST'])
def api_process_summary_only(meeting_name):
    """API: суммаризировать заново по существующему транскрипту"""
    import threading
    from ..helpers import get_processing_status, find_meeting_dir, BASE_DIR
    from pathlib import Path
    import json
    import os
    import sys
    from .logs import log_action
    
    # Проверяем, не идёт ли обработка другой встречи
    processing = get_processing_status()
    if processing.get("processing") and processing.get("current", {}).get("status") == "processing":
        return jsonify({"error": "Нельзя начать обработку — идёт обработка другой встречи", "processing": processing}), 409
    
    meeting_dir = find_meeting_dir(meeting_name)
    if not meeting_dir:
        return jsonify({"error": "Встреча не найдена"}), 404
    
    # Читаем тип встречи
    type_file = meeting_dir / ".meeting_type"
    meeting_type = "default"
    if type_file.exists():
        meeting_type = type_file.read_text().strip()
    
    log_action(meeting_name, "summary", "Запуск суммаризации (summary-only)", details={"type": meeting_type})
    
    def run_summary_only():
        sys.path.insert(0, str(BASE_DIR / "scripts"))
        from process_meeting import summarize_with_ai, save_results
        from recorder.models_config import get_default_summarization_model
        from progress import save_progress, clear_progress
        
        meeting_id = meeting_name
        save_progress(meeting_name, "processing", "Суммаризация транскрипта...", 70)
        
        try:
            # Ищем транскрипт
            transcript_file = None
            metadata_file = meeting_dir / "meeting_metadata.json"
            if metadata_file.exists():
                try:
                    metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
                    if "transcript_dir" in metadata:
                        transcript_file = Path(metadata["transcript_dir"]) / "transcript.txt"
                        log_action(meeting_name, "summary", f"Транскрипт найден: {transcript_file}", details={"path": str(transcript_file)})
                except Exception as e:
                    log_action(meeting_name, "summary", f"Ошибка чтения метаданных: {e}", level="warning")
            
            if not transcript_file or not transcript_file.exists():
                # Fallback
                transcript_file = BASE_DIR / "transcripts" / meeting_name / "transcript.txt"
                log_action(meeting_name, "summary", f"Транскрипт не найден в метаданных, fallback: {transcript_file}")
            
            if not transcript_file.exists():
                error_msg = "Транскрипт не найден"
                log_action(meeting_name, "summary", error_msg, level="error")
                save_progress(meeting_name, "error", error_msg, 70)
                return
            
            transcript_text = transcript_file.read_text(encoding="utf-8")
            if not transcript_text.strip():
                error_msg = "Транскрипт пустой"
                log_action(meeting_name, "summary", error_msg, level="warning")
                save_progress(meeting_name, "error", error_msg, 70)
                return
            
            log_action(meeting_name, "summary", f"Транскрипт прочитан: {len(transcript_text)} символов", details={"chars": len(transcript_text)})
            
            # Суммаризация
            model_key = get_default_summarization_model()
            save_progress(meeting_name, "processing", f"Вызов {model_key}...", 75)
            summary = summarize_with_ai(transcript_text, meeting_type)
            
            if not summary:
                warning_msg = f"Модель {model_key} не вернула суммаризацию"
                log_action(meeting_name, "summary", warning_msg, level="warning")
                summary = {
                    "title": "без_суммаризации",
                    "summary": "Не удалось получить суммаризацию от AI-модели",
                    "action_items": [],
                    "decisions": [],
                    "career_insights": []
                }
            else:
                log_action(meeting_name, "summary", f"Суммаризация получена: {summary.get('title', '')}", level="success")
            
            save_results(meeting_id, transcript_text, summary, meeting_type, meeting_dir=meeting_dir)
            save_progress(meeting_name, "done", "Суммаризация завершена", 100)
            log_action(meeting_name, "summary", "Суммаризация завершена успешно", level="success")
            clear_progress(meeting_name)
            
        except Exception as e:
            error_msg = f"Ошибка суммаризации: {str(e)}"
            log_action(meeting_name, "summary", error_msg, level="error", details={"error": str(e)})
            save_progress(meeting_name, "error", error_msg, 75)
    
    thread = threading.Thread(target=run_summary_only, daemon=True)
    thread.start()
    
    return jsonify({"status": "processing", "meeting": meeting_name, "step": "summary_only"})


# ==================== ЛОГИ ====================
from .logs import get_logs as _get_logs, clear_logs as _clear_logs

@processing_bp.route('/logs')
def api_get_logs():
    """API: получить логи обработки"""
    meeting = request.args.get("meeting")
    limit = request.args.get("limit", 100, type=int)
    level = request.args.get("level")
    
    logs = _get_logs(meeting_name=meeting, limit=limit, level=level)
    from ..helpers import BASE_DIR
    return jsonify({
        "logs": logs,
        "count": len(logs),
        "log_file": str(BASE_DIR / "logs" / "processing.log")
    })


@processing_bp.route('/logs/<meeting_name>', methods=['DELETE'])
def api_clear_meeting_logs(meeting_name):
    """API: очистить логи для конкретной встречи"""
    try:
        _clear_logs(meeting_name)
        return jsonify({"status": "ok", "meeting": meeting_name})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@processing_bp.route('/logs', methods=['DELETE'])
def api_clear_all_logs():
    """API: очистить все логи"""
    try:
        _clear_logs()
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
