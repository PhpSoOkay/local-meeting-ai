import json
import sys
from pathlib import Path
from flask import jsonify, send_file
from . import api_bp
from ..helpers import list_meetings, get_recording_status, load_meeting_types, find_meeting_dir, get_processing_status, BASE_DIR

# Добавляем scripts в путь для импорта progress
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))
from progress import load_progress as _load_progress


@api_bp.route('/status')
def api_status():
    """API: статус системы"""
    status = get_recording_status()
    processing = get_processing_status()
    meetings = list_meetings()
    
    return jsonify({
        "recording": status,
        "processing": processing,
        "total_meetings": len(meetings),
        "processed_meetings": len([m for m in meetings if m["processed"]])
    })


@api_bp.route('/meetings')
def api_meetings():
    """API: список всех записей"""
    return jsonify(list_meetings())


@api_bp.route('/meetings/<meeting_name>')
def api_meeting_detail(meeting_name):
    """API: детали конкретной записи"""
    meeting_dir = find_meeting_dir(meeting_name)

    if not meeting_dir:
        return jsonify({"error": "Not found"}), 404

    type_file = meeting_dir / ".meeting_type"
    meeting_type = "default"
    if type_file.exists():
        meeting_type = type_file.read_text().strip()

    # Пытаемся прочитать метаданные
    metadata_file = meeting_dir / "meeting_metadata.json"
    metadata = {}
    if metadata_file.exists():
        try:
            metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    segments = []
    for seg in sorted(meeting_dir.glob("segment_*.wav")):
        size = seg.stat().st_size
        duration = max(0, (size - 44)) / 32000
        segments.append({
            "name": seg.name,
            "path": str(seg),
            "size": size,
            "duration": duration
        })

    # Ищем транскрипт и суммаризацию через метаданные или fallback
    transcript = None
    if "transcript_dir" in metadata:
        transcript_file = Path(metadata["transcript_dir"]) / "transcript.txt"
    else:
        transcript_file = meeting_dir.parent.parent / "transcripts" / meeting_name / "transcript.txt"

    if transcript_file.exists():
        transcript = transcript_file.read_text(encoding="utf-8")

    summary = None
    if "summary_dir" in metadata:
        summary_json = Path(metadata["summary_dir"]) / "summary.json"
    else:
        summary_json = meeting_dir.parent.parent / "summaries" / meeting_name / "summary.json"

    if summary_json.exists():
        try:
            summary = summary_json.read_text(encoding="utf-8")
            summary = json.loads(summary)
        except Exception:
            pass

    return jsonify({
        "name": meeting_name,
        "type": meeting_type,
        "segments": segments,
        "transcript": transcript,
        "summary": summary,
        "processed": summary is not None
    })


@api_bp.route('/config')
def api_config():
    """API: получить конфигурацию типов встреч"""
    return jsonify(load_meeting_types())


@api_bp.route('/audio/<meeting_name>/<filename>')
def api_audio(meeting_name, filename):
    """API: потоковая передача аудио"""
    from ..helpers import find_meeting_dir, AUDIO_DIR

    meeting_dir = find_meeting_dir(meeting_name)
    if not meeting_dir:
        return jsonify({"error": "Meeting not found"}), 404

    audio_path = meeting_dir / filename

    if not audio_path.exists():
        return jsonify({"error": "File not found"}), 404

    return send_file(str(audio_path), mimetype='audio/wav')


@api_bp.route('/transcript/<meeting_name>')
def api_get_transcript(meeting_name):
    """API: скачать транскрипт"""
    meeting_dir = find_meeting_dir(meeting_name)
    if not meeting_dir:
        return jsonify({"error": "Meeting not found"}), 404
    
    # Пытаемся прочитать метаданные
    metadata_file = meeting_dir / "meeting_metadata.json"
    metadata = {}
    if metadata_file.exists():
        try:
            metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    if "transcript_dir" in metadata:
        transcript_file = Path(metadata["transcript_dir"]) / "transcript.txt"
    else:
        transcript_file = meeting_dir.parent.parent / "transcripts" / meeting_name / "transcript.txt"

    if not transcript_file.exists():
        return jsonify({"error": "Transcript not found"}), 404
    
    return send_file(
        str(transcript_file),
        mimetype='text/plain',
        as_attachment=True,
        download_name=f'transcript_{meeting_name}.txt'
    )


@api_bp.route('/summary/<meeting_name>')
def api_get_summary(meeting_name):
    """API: скачать суммаризацию"""
    meeting_dir = find_meeting_dir(meeting_name)
    if not meeting_dir:
        return jsonify({"error": "Meeting not found"}), 404
    
    # Пытаемся прочитать метаданные
    metadata_file = meeting_dir / "meeting_metadata.json"
    metadata = {}
    if metadata_file.exists():
        try:
            metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    if "summary_dir" in metadata:
        summary_file = Path(metadata["summary_dir"]) / "summary.md"
    else:
        summary_file = meeting_dir.parent.parent / "summaries" / meeting_name / "summary.md"

    if not summary_file.exists():
        return jsonify({"error": "Summary not found"}), 404
    
    return send_file(
        str(summary_file),
        mimetype='text/markdown',
        as_attachment=True,
        download_name=f'summary_{meeting_name}.md'
    )


@api_bp.route('/progress/<meeting_name>')
def api_get_progress(meeting_name):
    """API: получить прогресс обработки"""
    return jsonify(_load_progress(meeting_name))


@api_bp.route('/progress')
def api_get_all_progress():
    """API: получить все активные прогрессы"""
    from pathlib import Path
    
    progress_dir = BASE_DIR / ".progress"
    if not progress_dir.exists():
        return jsonify([])
    
    progress_list = []
    for pf in progress_dir.glob("*.json"):
        try:
            data = json.loads(pf.read_text(encoding="utf-8"))
            progress_list.append(data)
        except Exception:
            continue
    
    return jsonify(progress_list)

