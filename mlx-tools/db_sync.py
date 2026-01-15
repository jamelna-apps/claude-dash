#!/usr/bin/env python3
"""
DB Sync - Incremental file sync from JSON to SQLite

Called by watcher.js after JSON updates to keep DB in sync.
Designed to be fast and run detached (non-blocking).

Usage:
    python db_sync.py <project_id> <file_path>
    python db_sync.py <project_id> --full  # Full project resync
"""

import sys
import json
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from memory_db import get_connection, upsert_file, upsert_function

MEMORY_ROOT = Path.home() / '.claude-dash'


def sync_file(project_id: str, file_path: str):
    """Sync a single file from summaries.json to SQLite."""
    summaries_path = MEMORY_ROOT / 'projects' / project_id / 'summaries.json'

    if not summaries_path.exists():
        return

    try:
        summaries = json.loads(summaries_path.read_text())
        files = summaries.get('files', {})

        # Find the file data (try both relative and absolute paths)
        data = files.get(file_path) or files.get(str(Path(file_path).name))

        if not data:
            # File might have been removed - delete from DB
            conn = get_connection()
            conn.execute(
                "DELETE FROM files WHERE project_id = ? AND path = ?",
                (project_id, file_path)
            )
            conn.commit()
            conn.close()
            return

        # Upsert the file
        file_id = upsert_file(
            project_id=project_id,
            path=file_path,
            summary=data.get('summary'),
            purpose=data.get('purpose'),
            component_name=data.get('componentName'),
            is_component=data.get('isComponent', False)
        )

        # Sync functions for this file
        conn = get_connection()

        # Remove old functions for this file
        conn.execute("DELETE FROM functions WHERE file_id = ?", (file_id,))

        # Add current functions
        for func in data.get('functions', []):
            upsert_function(
                file_id=file_id,
                name=func.get('name', ''),
                line_number=func.get('line', 0),
                func_type=func.get('type', 'function')
            )

        conn.commit()
        conn.close()

    except (json.JSONDecodeError, IOError) as e:
        print(f"Error syncing {file_path}: {e}", file=sys.stderr)


def sync_project(project_id: str):
    """Full resync of a project from JSON to SQLite."""
    summaries_path = MEMORY_ROOT / 'projects' / project_id / 'summaries.json'

    if not summaries_path.exists():
        print(f"No summaries.json for {project_id}")
        return

    try:
        summaries = json.loads(summaries_path.read_text())
        files = summaries.get('files', {})

        count = 0
        for path, data in files.items():
            file_id = upsert_file(
                project_id=project_id,
                path=path,
                summary=data.get('summary'),
                purpose=data.get('purpose'),
                component_name=data.get('componentName'),
                is_component=data.get('isComponent', False)
            )

            # Sync functions
            conn = get_connection()
            conn.execute("DELETE FROM functions WHERE file_id = ?", (file_id,))

            for func in data.get('functions', []):
                upsert_function(
                    file_id=file_id,
                    name=func.get('name', ''),
                    line_number=func.get('line', 0),
                    func_type=func.get('type', 'function')
                )

            conn.commit()
            conn.close()
            count += 1

        print(f"Synced {count} files for {project_id}")

    except (json.JSONDecodeError, IOError) as e:
        print(f"Error syncing project {project_id}: {e}", file=sys.stderr)


def main():
    if len(sys.argv) < 2:
        print("Usage: python db_sync.py <project_id> [file_path|--full]")
        sys.exit(1)

    project_id = sys.argv[1]

    if len(sys.argv) == 2 or sys.argv[2] == '--full':
        # Full project sync
        sync_project(project_id)
    else:
        # Single file sync
        file_path = sys.argv[2]
        sync_file(project_id, file_path)


if __name__ == '__main__':
    main()
