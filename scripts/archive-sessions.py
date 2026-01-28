#!/usr/bin/env python3
"""
Session Archival for Claude-Dash

Archives old session data to reduce storage:
- Sessions >30 days → compressed archive
- Keep only last 50 observations per project active
- Transcripts stored separately and compressed

Run periodically via cron or manually.
"""

import json
import gzip
import shutil
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Any
import sys

MEMORY_ROOT = Path.home() / ".claude-dash"
SESSIONS_DIR = MEMORY_ROOT / "sessions"
ARCHIVE_DIR = MEMORY_ROOT / "archives" / "sessions"
MAX_AGE_DAYS = 30
MAX_OBSERVATIONS_PER_PROJECT = 50


def archive_old_sessions():
    """Archive session directories older than MAX_AGE_DAYS."""
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    cutoff = datetime.now() - timedelta(days=MAX_AGE_DAYS)
    archived_count = 0
    archived_size = 0

    for session_dir in SESSIONS_DIR.iterdir():
        if not session_dir.is_dir():
            continue

        # Skip metadata files and active directories
        if session_dir.name in ['summaries', 'transcripts', 'index.json', 'observations.json']:
            continue

        # Check last modified time
        try:
            mtime = datetime.fromtimestamp(session_dir.stat().st_mtime)
            if mtime < cutoff:
                # Archive the directory
                archive_path = ARCHIVE_DIR / f"{session_dir.name}-{mtime.strftime('%Y%m%d')}.tar.gz"

                if not archive_path.exists():
                    # Get size before archiving
                    dir_size = sum(f.stat().st_size for f in session_dir.rglob('*') if f.is_file())

                    # Create compressed archive
                    shutil.make_archive(
                        str(archive_path).replace('.tar.gz', ''),
                        'gztar',
                        session_dir.parent,
                        session_dir.name
                    )

                    # Remove original directory
                    shutil.rmtree(session_dir)
                    archived_count += 1
                    archived_size += dir_size
                    print(f"  Archived: {session_dir.name} ({dir_size // 1024}KB)")
        except Exception as e:
            print(f"  Error archiving {session_dir.name}: {e}", file=sys.stderr)

    return archived_count, archived_size


def trim_observations():
    """Keep only the most recent observations per project."""
    obs_file = SESSIONS_DIR / "observations.json"
    if not obs_file.exists():
        return 0

    try:
        data = json.loads(obs_file.read_text())
        observations = data.get('observations', [])

        if not observations:
            return 0

        original_count = len(observations)

        # Group by project
        by_project: Dict[str, List] = {}
        for obs in observations:
            project = obs.get('projectId', obs.get('project', 'unknown'))
            if project not in by_project:
                by_project[project] = []
            by_project[project].append(obs)

        # Keep only last N per project
        trimmed = []
        for project, obs_list in by_project.items():
            # Sort by timestamp descending
            obs_list.sort(
                key=lambda x: x.get('timestamp', x.get('date', '')),
                reverse=True
            )
            trimmed.extend(obs_list[:MAX_OBSERVATIONS_PER_PROJECT])

        # Sort all by timestamp
        trimmed.sort(
            key=lambda x: x.get('timestamp', x.get('date', '')),
            reverse=True
        )

        # Save trimmed observations
        data['observations'] = trimmed
        obs_file.write_text(json.dumps(data, indent=2))

        removed = original_count - len(trimmed)
        if removed > 0:
            print(f"  Trimmed observations: {original_count} → {len(trimmed)} ({removed} removed)")

        return removed

    except Exception as e:
        print(f"  Error trimming observations: {e}", file=sys.stderr)
        return 0


def compress_transcripts():
    """Compress old transcripts."""
    transcripts_dir = SESSIONS_DIR / "transcripts"
    if not transcripts_dir.exists():
        return 0

    cutoff = datetime.now() - timedelta(days=MAX_AGE_DAYS)
    compressed_count = 0

    for transcript in transcripts_dir.glob("*.json"):
        if transcript.suffix == '.gz':
            continue

        try:
            mtime = datetime.fromtimestamp(transcript.stat().st_mtime)
            if mtime < cutoff:
                # Compress
                with open(transcript, 'rb') as f_in:
                    with gzip.open(str(transcript) + '.gz', 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)
                transcript.unlink()
                compressed_count += 1
        except Exception as e:
            print(f"  Error compressing {transcript.name}: {e}", file=sys.stderr)

    if compressed_count > 0:
        print(f"  Compressed {compressed_count} old transcripts")

    return compressed_count


def cleanup_archives():
    """Delete archives older than 90 days."""
    if not ARCHIVE_DIR.exists():
        return 0

    cutoff = datetime.now() - timedelta(days=90)
    deleted = 0

    for archive in ARCHIVE_DIR.glob("*.tar.gz"):
        try:
            mtime = datetime.fromtimestamp(archive.stat().st_mtime)
            if mtime < cutoff:
                archive.unlink()
                deleted += 1
        except Exception:
            pass

    if deleted > 0:
        print(f"  Deleted {deleted} old archives (>90 days)")

    return deleted


def get_storage_stats() -> Dict[str, Any]:
    """Get current storage statistics."""
    def dir_size(path: Path) -> int:
        if not path.exists():
            return 0
        return sum(f.stat().st_size for f in path.rglob('*') if f.is_file())

    return {
        'sessions_mb': dir_size(SESSIONS_DIR) / (1024 * 1024),
        'archives_mb': dir_size(ARCHIVE_DIR) / (1024 * 1024) if ARCHIVE_DIR.exists() else 0,
        'projects_mb': dir_size(MEMORY_ROOT / 'projects') / (1024 * 1024),
        'total_mb': dir_size(MEMORY_ROOT) / (1024 * 1024)
    }


def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Starting session archival...")

    # Get before stats
    before = get_storage_stats()
    print(f"\nBefore: Sessions={before['sessions_mb']:.1f}MB, Total={before['total_mb']:.1f}MB")

    # Run archival
    print("\nArchiving old sessions...")
    archived, archived_size = archive_old_sessions()

    print("\nTrimming observations...")
    trimmed = trim_observations()

    print("\nCompressing transcripts...")
    compressed = compress_transcripts()

    print("\nCleaning up old archives...")
    cleaned = cleanup_archives()

    # Get after stats
    after = get_storage_stats()
    saved = before['total_mb'] - after['total_mb']

    print(f"\nAfter: Sessions={after['sessions_mb']:.1f}MB, Total={after['total_mb']:.1f}MB")
    print(f"Saved: {saved:.1f}MB")

    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Archival complete")
    print(f"  Sessions archived: {archived}")
    print(f"  Observations trimmed: {trimmed}")
    print(f"  Transcripts compressed: {compressed}")
    print(f"  Old archives deleted: {cleaned}")


if __name__ == "__main__":
    main()
