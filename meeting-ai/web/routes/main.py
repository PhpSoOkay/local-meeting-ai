from flask import render_template
from pathlib import Path
from . import main_bp
from ..helpers import get_recording_status, list_meetings, load_meeting_types, find_meeting_dir, format_duration


@main_bp.route('/')
def index():
    """Главная страница — список встреч"""
    status = get_recording_status()
    meetings = list_meetings()
    meeting_types = load_meeting_types()
    
    return render_template('index.html',
                          meetings=meetings,
                          meeting_types=meeting_types,
                          is_recording=status['recording'],
                          total_meetings=len(meetings),
                          processed_meetings=len([m for m in meetings if m['processed']]))


@main_bp.route('/meeting/<meeting_name>')
def meeting_detail(meeting_name):
    """Страница деталей встречи"""
    meeting_dir = find_meeting_dir(meeting_name)

    if not meeting_dir:
        return "Meeting not found", 404

    # Определяем тип встречи
    type_file = meeting_dir / ".meeting_type"
    meeting_type = "default"
    if type_file.exists():
        meeting_type = type_file.read_text().strip()

    # Пытаемся прочитать метаданные
    metadata_file = meeting_dir / "meeting_metadata.json"
    metadata = {}
    if metadata_file.exists():
        try:
            import json
            metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    # Список сегментов
    segments = []
    total_duration_secs = 0
    for seg in sorted(meeting_dir.glob("segment_*.wav")):
        size = seg.stat().st_size
        duration = max(0, (size - 44)) / 32000
        total_duration_secs += duration
        segments.append({
            "name": seg.name,
            "path": str(seg),
            "size": size,
            "duration": format_duration(duration)
        })

    # Транскрипт — через метаданные или fallback
    transcript = None
    transcript_lines = []
    if "transcript_dir" in metadata:
        transcript_file = Path(metadata["transcript_dir"]) / "transcript.txt"
    else:
        transcript_file = meeting_dir.parent.parent / "transcripts" / meeting_name / "transcript.txt"

    if transcript_file.exists():
        transcript = transcript_file.read_text(encoding="utf-8")
        transcript_lines = transcript.split('\n')

    # Суммаризация — через метаданные или fallback
    summary = None
    if "summary_dir" in metadata:
        summary_json = Path(metadata["summary_dir"]) / "summary.json"
    else:
        summary_json = meeting_dir.parent.parent / "summaries" / meeting_name / "summary.json"

    if summary_json.exists():
        try:
            summary = summary_json.read_text(encoding="utf-8")
            summary = __import__('json').loads(summary)
        except Exception:
            pass

    # Дата создания
    timestamp = meeting_name.replace("meeting_", "")
    created = __import__('datetime').datetime.fromisoformat(timestamp.replace("_", "T")).strftime("%Y-%m-%d %H:%M:%S")

    return render_template('detail.html',
                          meeting={
                              "name": meeting_name,
                              "type": meeting_type,
                              "created": created,
                              "duration": format_duration(total_duration_secs),
                              "segments": len(segments),
                              "title": metadata.get("title", "")
                          },
                          segments=segments,
                          transcript=transcript,
                          transcript_lines=transcript_lines,
                          summary=summary,
                          is_recording=get_recording_status()['recording'])
