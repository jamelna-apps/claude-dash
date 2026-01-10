#!/usr/bin/env python3
"""
Process Pending Summarizations

Runs MLX summarizer on all files marked with needsResummarization: true.
Designed to be run periodically or triggered by the file watcher.

Usage:
  source ~/.claude-dash/mlx-env/bin/activate
  python process_pending.py [--all-projects]
"""

import json
import subprocess
import sys
from pathlib import Path

MEMORY_ROOT = Path.home() / ".claude-dash"

def get_pending_count(project_id):
    """Count files needing re-summarization."""
    path = MEMORY_ROOT / "projects" / project_id / "summaries.json"
    if not path.exists():
        return 0

    summaries = json.loads(path.read_text())
    return sum(
        1 for data in summaries.get("files", {}).values()
        if data.get("needsResummarization", False)
    )

def get_all_projects():
    """Get list of all projects."""
    config_path = MEMORY_ROOT / "config.json"
    if not config_path.exists():
        return []
    config = json.loads(config_path.read_text())
    return [p["id"] for p in config.get("projects", [])]

def process_project(project_id, limit=10):
    """Run MLX summarizer on a project."""
    pending = get_pending_count(project_id)
    if pending == 0:
        print(f"  {project_id}: No files pending")
        return 0

    print(f"  {project_id}: {pending} files pending, processing up to {limit}...")

    # Run summarizer
    cmd = [
        sys.executable,
        str(MEMORY_ROOT / "mlx-tools" / "summarizer.py"),
        project_id,
        "--limit", str(min(pending, limit))
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"    Done!")
            return min(pending, limit)
        else:
            print(f"    Error: {result.stderr}")
            return 0
    except Exception as e:
        print(f"    Error: {e}")
        return 0

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--all-projects", action="store_true",
                        help="Process all projects")
    parser.add_argument("--project", help="Specific project to process")
    parser.add_argument("--limit", type=int, default=10,
                        help="Max files per project")
    args = parser.parse_args()

    if args.project:
        projects = [args.project]
    elif args.all_projects:
        projects = get_all_projects()
    else:
        # Show status only
        projects = get_all_projects()
        print("Pending summarizations:")
        total = 0
        for p in projects:
            count = get_pending_count(p)
            total += count
            print(f"  {p}: {count}")
        print(f"\nTotal: {total}")
        print("\nRun with --all-projects or --project <id> to process")
        return

    print("Processing pending summarizations...")
    processed = 0
    for project_id in projects:
        processed += process_project(project_id, args.limit)

    print(f"\nTotal processed: {processed}")

if __name__ == "__main__":
    main()
