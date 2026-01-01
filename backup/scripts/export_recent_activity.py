"""
Export recent activity from persistence.db to a text file.

Includes LLM traces, tool logs, training metrics, play history, track intents,
feedback events, status logs, segments, DJ speech history, and sessions.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Optional


def _parse_dt(value: Any) -> Optional[datetime]:
    """Parse timestamps from strings or numeric values to UTC-aware datetimes."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc)

    raw = str(value).strip()
    if not raw:
        return None

    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"

    # Try common ISO formats first.
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
    ):
        try:
            parsed = datetime.strptime(raw, fmt)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            continue

    try:
        parsed = datetime.fromisoformat(raw)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _json_pretty(value: Any) -> str:
    """Pretty-format JSON-ish strings or objects."""
    if value is None:
        return "null"
    if isinstance(value, (dict, list)):
        return json.dumps(value, indent=2, sort_keys=True)
    if not isinstance(value, str):
        return str(value)
    text = value.strip()
    if not text:
        return ""
    try:
        parsed = json.loads(text)
        return json.dumps(parsed, indent=2, sort_keys=True)
    except (json.JSONDecodeError, TypeError):
        return text


def _write_section(handle, title: str) -> None:
    handle.write("\n" + "=" * 80 + "\n")
    handle.write(f"{title}\n")
    handle.write("=" * 80 + "\n")


def _iter_recent_rows(
    conn: sqlite3.Connection,
    query: str,
    time_column: str,
    cutoff: datetime,
    limit: int,
) -> Iterable[sqlite3.Row]:
    cursor = conn.cursor()
    cursor.execute(query)
    count = 0
    for row in cursor:
        if count >= limit:
            break
        count += 1
        timestamp = _parse_dt(row[time_column])
        if timestamp and timestamp < cutoff:
            break
        if timestamp and timestamp >= cutoff:
            yield row


def _write_rows(
    handle,
    rows: Iterable[sqlite3.Row],
    time_column: str,
    row_formatter,
) -> int:
    count = 0
    for row in rows:
        count += 1
        row_formatter(handle, row, time_column)
    return count


def _format_llm_trace(handle, row: sqlite3.Row, time_column: str) -> None:
    handle.write("\n-- LLM TRACE\n")
    handle.write(f"  id: {row['id']}\n")
    handle.write(f"  created_at: {row[time_column]}\n")
    handle.write(f"  agent_name: {row['agent_name']}\n")
    handle.write(f"  model: {row['model']}\n")
    handle.write(f"  session_id: {row['session_id']}\n")
    handle.write(f"  user_id: {row['user_id']}\n")
    handle.write(f"  mood_id: {row['mood_id']}\n")
    handle.write(f"  correlation_id: {row['correlation_id']}\n")
    handle.write("  prompt:\n")
    handle.write(_indent(_json_pretty(row["prompt"])) + "\n")
    handle.write("  response:\n")
    handle.write(_indent(_json_pretty(row["response"])) + "\n")


def _format_tool_log(handle, row: sqlite3.Row, time_column: str) -> None:
    handle.write("\n-- TOOL USAGE LOG\n")
    handle.write(f"  id: {row['id']}\n")
    handle.write(f"  created_at: {row[time_column]}\n")
    handle.write(f"  tool_name: {row['tool_name']}\n")
    handle.write(f"  success: {row['success']}\n")
    handle.write(f"  execution_time_ms: {row['execution_time_ms']}\n")
    handle.write(f"  session_id: {row['session_id']}\n")
    handle.write(f"  user_id: {row['user_id']}\n")
    handle.write(f"  mood_id: {row['mood_id']}\n")
    handle.write(f"  llm_trace_id: {row['llm_trace_id']}\n")
    handle.write("  tool_arguments:\n")
    handle.write(_indent(_json_pretty(row["tool_arguments"])) + "\n")
    handle.write("  tool_result:\n")
    handle.write(_indent(_json_pretty(row["tool_result"])) + "\n")
    if row["error_message"]:
        handle.write(f"  error_message: {row['error_message']}\n")


def _format_training_metric(handle, row: sqlite3.Row, time_column: str) -> None:
    handle.write("\n-- TRAINING METRIC\n")
    handle.write(f"  id: {row['id']}\n")
    handle.write(f"  created_at: {row[time_column]}\n")
    handle.write(f"  agent_name: {row['agent_name']}\n")
    handle.write(f"  feedback_type: {row['feedback_type']}\n")
    handle.write(f"  track_artist: {row['track_artist']}\n")
    handle.write(f"  track_title: {row['track_title']}\n")
    handle.write(f"  artists_added: {row['artists_added']}\n")
    handle.write(f"  artists_removed: {row['artists_removed']}\n")
    handle.write(f"  artists_demoted: {row['artists_demoted']}\n")
    handle.write(f"  tool_calls_made: {row['tool_calls_made']}\n")
    handle.write(f"  llm_tokens: {row['llm_tokens']}\n")
    handle.write(f"  user_id: {row['user_id']}\n")
    handle.write(f"  mood_id: {row['mood_id']}\n")
    handle.write("  artists_before:\n")
    handle.write(_indent(_json_pretty(row["artists_before"])) + "\n")
    handle.write("  artists_after:\n")
    handle.write(_indent(_json_pretty(row["artists_after"])) + "\n")
    handle.write("  llm_reasoning:\n")
    handle.write(_indent(str(row["llm_reasoning"] or "")) + "\n")


def _format_play_history(handle, row: sqlite3.Row, time_column: str) -> None:
    handle.write("\n-- PLAY HISTORY\n")
    handle.write(f"  id: {row['id']}\n")
    handle.write(f"  started_at: {row[time_column]}\n")
    handle.write(f"  ended_at: {row['ended_at']}\n")
    handle.write(f"  song_uuid: {row['song_uuid']}\n")
    handle.write(f"  song_artist: {row['song_artist']}\n")
    handle.write(f"  song_title: {row['song_title']}\n")
    handle.write(f"  session_id: {row['session_id']}\n")
    handle.write(f"  user_id: {row['user_id']}\n")
    handle.write(f"  mood_id: {row['mood_id']}\n")
    handle.write(f"  skipped: {row['skipped']}\n")
    handle.write(f"  transition_type: {row['transition_type']}\n")


def _format_track_intent(handle, row: sqlite3.Row, time_column: str) -> None:
    handle.write("\n-- TRACK INTENT\n")
    handle.write(f"  id: {row['id']}\n")
    handle.write(f"  created_at: {row[time_column]}\n")
    handle.write(f"  status: {row['status']}\n")
    handle.write(f"  selection_method: {row['selection_method']}\n")
    handle.write(f"  artist: {row['artist']}\n")
    handle.write(f"  title: {row['title']}\n")
    handle.write(f"  session_id: {row['session_id']}\n")
    handle.write(f"  user_id: {row['user_id']}\n")
    handle.write(f"  mood_id: {row['mood_id']}\n")
    handle.write("  selection_rationale:\n")
    handle.write(_indent(str(row["selection_rationale"] or "")) + "\n")


def _format_feedback(handle, row: sqlite3.Row, time_column: str) -> None:
    handle.write("\n-- FEEDBACK EVENT\n")
    handle.write(f"  id: {row['id']}\n")
    handle.write(f"  created_at: {row[time_column]}\n")
    handle.write(f"  value: {row['value']}\n")
    handle.write(f"  track_artist: {row['track_artist']}\n")
    handle.write(f"  track_title: {row['track_title']}\n")
    handle.write(f"  song_uuid: {row['song_uuid']}\n")
    handle.write(f"  user_id: {row['user_id']}\n")
    handle.write(f"  mood_id: {row['mood_id']}\n")
    handle.write(f"  reason_text: {row['reason_text']}\n")


def _format_status_log(handle, row: sqlite3.Row, time_column: str) -> None:
    handle.write("\n-- STATUS EVENT\n")
    handle.write(f"  id: {row['id']}\n")
    handle.write(f"  created_at: {row[time_column]}\n")
    handle.write(f"  category: {row['category']}\n")
    handle.write(f"  step: {row['step']}\n")
    handle.write(f"  severity: {row['severity']}\n")
    handle.write(f"  session_id: {row['session_id']}\n")
    handle.write(f"  user_id: {row['user_id']}\n")
    handle.write(f"  correlation_id: {row['correlation_id']}\n")
    handle.write(f"  user_message: {row['user_message']}\n")
    handle.write(f"  debug_message: {row['debug_message']}\n")
    handle.write("  payload_json:\n")
    handle.write(_indent(_json_pretty(row["payload_json"])) + "\n")


def _format_segment(handle, row: sqlite3.Row, time_column: str) -> None:
    handle.write("\n-- SEGMENT\n")
    handle.write(f"  id: {row['id']}\n")
    handle.write(f"  created_at: {row[time_column]}\n")
    handle.write(f"  session_id: {row['session_id']}\n")
    handle.write(f"  user_id: {row['user_id']}\n")
    handle.write(f"  mood_id: {row['mood_id']}\n")
    handle.write(f"  segment_index: {row['segment_index']}\n")
    handle.write(f"  song_uuid: {row['song_uuid']}\n")
    handle.write(f"  tts_used: {row['tts_used']}\n")
    handle.write(f"  transition_id: {row['transition_id']}\n")
    handle.write("  banter_text:\n")
    handle.write(_indent(str(row["banter_text"] or "")) + "\n")


def _format_dj_speech(handle, row: sqlite3.Row, time_column: str) -> None:
    handle.write("\n-- DJ SPEECH HISTORY\n")
    handle.write(f"  id: {row['id']}\n")
    handle.write(f"  created_at: {row[time_column]}\n")
    handle.write(f"  session_id: {row['session_id']}\n")
    handle.write(f"  user_id: {row['user_id']}\n")
    handle.write("  speech_text:\n")
    handle.write(_indent(str(row["speech_text"] or "")) + "\n")
    handle.write("  mentioned_artists:\n")
    handle.write(_indent(_json_pretty(row["mentioned_artists"])) + "\n")
    handle.write("  mentioned_tracks:\n")
    handle.write(_indent(_json_pretty(row["mentioned_tracks"])) + "\n")


def _format_session(handle, row: sqlite3.Row, time_column: str) -> None:
    handle.write("\n-- SESSION\n")
    handle.write(f"  session_id: {row['session_id']}\n")
    handle.write(f"  started_at: {row[time_column]}\n")
    handle.write(f"  ended_at: {row['ended_at']}\n")
    handle.write(f"  is_active: {row['is_active']}\n")
    handle.write(f"  mode: {row['mode']}\n")
    handle.write(f"  user_id: {row['user_id']}\n")
    handle.write(f"  mood_id: {row['mood_id']}\n")
    handle.write(f"  current_song_title: {row['current_song_title']}\n")
    handle.write(f"  current_song_artist: {row['current_song_artist']}\n")


def _indent(text: str, spaces: int = 4) -> str:
    pad = " " * spaces
    return "\n".join(pad + line for line in text.splitlines()) if text else pad


def _add_summary(handle, title: str, count: int) -> None:
    handle.write(f"{title}: {count}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Export recent activity from persistence.db")
    parser.add_argument("--db", default="data/persistence.db", help="Path to SQLite database")
    parser.add_argument("--hours", type=int, default=1, help="Hours to look back")
    parser.add_argument(
        "--output",
        default="data/recent_activity_last_hour.txt",
        help="Output text file path",
    )
    parser.add_argument("--limit", type=int, default=5000, help="Max rows per table to scan")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        raise SystemExit(f"Database not found: {db_path}")

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=args.hours)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as handle:
        _write_section(handle, "RECENT ACTIVITY EXPORT")
        handle.write(f"Generated at (UTC): {now.isoformat()}\n")
        handle.write(f"Lookback hours: {args.hours}\n")
        handle.write(f"Cutoff (UTC): {cutoff.isoformat()}\n")

        _write_section(handle, "SUMMARY COUNTS")

        # LLM traces
        llm_query = """
            SELECT id, session_id, user_id, mood_id, agent_name, prompt, response,
                   model, correlation_id, created_at
            FROM llm_trace
            ORDER BY created_at DESC
        """
        llm_rows = list(
            _iter_recent_rows(conn, llm_query, "created_at", cutoff, args.limit)
        )
        _add_summary(handle, "LLM traces", len(llm_rows))

        # Tool usage logs
        tool_query = """
            SELECT id, session_id, user_id, mood_id, llm_trace_id, tool_name,
                   tool_arguments, tool_result, execution_time_ms, success,
                   error_message, created_at
            FROM tool_usage_log
            ORDER BY created_at DESC
        """
        tool_rows = list(
            _iter_recent_rows(conn, tool_query, "created_at", cutoff, args.limit)
        )
        _add_summary(handle, "Tool usage logs", len(tool_rows))

        # Training metrics
        training_query = """
            SELECT id, user_id, mood_id, agent_name, feedback_type, track_artist,
                   track_title, artists_before, artists_after, artists_added,
                   artists_removed, artists_demoted, llm_reasoning, tool_calls_made,
                   llm_tokens, created_at
            FROM training_metrics
            ORDER BY created_at DESC
        """
        training_rows = list(
            _iter_recent_rows(conn, training_query, "created_at", cutoff, args.limit)
        )
        _add_summary(handle, "Training metrics", len(training_rows))

        # Play history
        play_query = """
            SELECT ph.id, ph.session_id, ph.user_id, ph.mood_id, ph.song_uuid,
                   ph.started_at, ph.ended_at, ph.skipped, ph.transition_type,
                   s.artist AS song_artist, s.title AS song_title
            FROM play_history ph
            LEFT JOIN songs s ON s.uuid = ph.song_uuid
            ORDER BY ph.started_at DESC
        """
        play_rows = list(
            _iter_recent_rows(conn, play_query, "started_at", cutoff, args.limit)
        )
        _add_summary(handle, "Play history entries", len(play_rows))

        # Track intents
        intent_query = """
            SELECT id, session_id, user_id, mood_id, title, artist, status,
                   selection_method, selection_rationale, created_at
            FROM track_intents
            ORDER BY created_at DESC
        """
        intent_rows = list(
            _iter_recent_rows(conn, intent_query, "created_at", cutoff, args.limit)
        )
        _add_summary(handle, "Track intents", len(intent_rows))

        # Feedback events
        feedback_query = """
            SELECT id, user_id, mood_id, song_uuid, track_title, track_artist,
                   value, reason_text, created_at
            FROM feedback_events
            ORDER BY created_at DESC
        """
        feedback_rows = list(
            _iter_recent_rows(conn, feedback_query, "created_at", cutoff, args.limit)
        )
        _add_summary(handle, "Feedback events", len(feedback_rows))

        # Status events
        status_query = """
            SELECT id, user_id, session_id, correlation_id, category, step,
                   severity, user_message, debug_message, payload_json, created_at
            FROM status_event_logs
            ORDER BY created_at DESC
        """
        status_rows = list(
            _iter_recent_rows(conn, status_query, "created_at", cutoff, args.limit)
        )
        _add_summary(handle, "Status event logs", len(status_rows))

        # Segments
        segment_query = """
            SELECT id, session_id, user_id, mood_id, segment_index, song_uuid,
                   tts_used, banter_text, transition_id, created_at
            FROM segments
            ORDER BY created_at DESC
        """
        segment_rows = list(
            _iter_recent_rows(conn, segment_query, "created_at", cutoff, args.limit)
        )
        _add_summary(handle, "Segments", len(segment_rows))

        # DJ speech history
        speech_query = """
            SELECT id, user_id, session_id, speech_text, mentioned_artists,
                   mentioned_tracks, created_at
            FROM dj_speech_history
            ORDER BY created_at DESC
        """
        speech_rows = list(
            _iter_recent_rows(conn, speech_query, "created_at", cutoff, args.limit)
        )
        _add_summary(handle, "DJ speech history", len(speech_rows))

        # Sessions
        session_query = """
            SELECT session_id, user_id, mood_id, started_at, ended_at, mode,
                   is_active, current_song_title, current_song_artist
            FROM sessions
            ORDER BY started_at DESC
        """
        session_rows = list(
            _iter_recent_rows(conn, session_query, "started_at", cutoff, args.limit)
        )
        _add_summary(handle, "Sessions", len(session_rows))

        # Write detailed sections
        _write_section(handle, "LLM TRACES")
        _write_rows(handle, llm_rows, "created_at", _format_llm_trace)

        _write_section(handle, "TOOL USAGE LOGS")
        _write_rows(handle, tool_rows, "created_at", _format_tool_log)

        _write_section(handle, "TRAINING METRICS")
        _write_rows(handle, training_rows, "created_at", _format_training_metric)

        _write_section(handle, "PLAY HISTORY")
        _write_rows(handle, play_rows, "started_at", _format_play_history)

        _write_section(handle, "TRACK INTENTS")
        _write_rows(handle, intent_rows, "created_at", _format_track_intent)

        _write_section(handle, "FEEDBACK EVENTS")
        _write_rows(handle, feedback_rows, "created_at", _format_feedback)

        _write_section(handle, "STATUS EVENT LOGS")
        _write_rows(handle, status_rows, "created_at", _format_status_log)

        _write_section(handle, "SEGMENTS")
        _write_rows(handle, segment_rows, "created_at", _format_segment)

        _write_section(handle, "DJ SPEECH HISTORY")
        _write_rows(handle, speech_rows, "created_at", _format_dj_speech)

        _write_section(handle, "SESSIONS")
        _write_rows(handle, session_rows, "started_at", _format_session)

    conn.close()
    print(f"Wrote recent activity to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
