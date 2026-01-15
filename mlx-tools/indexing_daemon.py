#!/usr/bin/env python3
"""
Claude Memory Indexing Daemon

Watches file system for changes and automatically:
- Updates file summaries
- Rebuilds function index
- Updates embeddings incrementally
- Syncs to SQLite database

Can run as:
- Background process (daemon mode)
- One-shot indexer (--once)
- Watch mode (--watch)
"""

import os
import sys
import json
import time
import hashlib
import argparse
import subprocess
from pathlib import Path
from datetime import datetime, timedelta
from typing import Set, Dict, List, Optional
import threading
import queue

# Add mlx-tools to path
MLX_DIR = Path(__file__).parent
sys.path.insert(0, str(MLX_DIR))

from memory_db import (
    get_connection, init_database, upsert_file, upsert_function,
    get_stats
)

MEMORY_ROOT = Path.home() / '.claude-dash'
CONFIG_PATH = MEMORY_ROOT / 'config.json'
PID_FILE = MEMORY_ROOT / 'daemon.pid'
LOG_FILE = MEMORY_ROOT / 'daemon.log'

# File extensions to index
INDEXABLE_EXTENSIONS = {
    '.js', '.jsx', '.ts', '.tsx',  # JavaScript/TypeScript
    '.py',  # Python
    '.swift',  # Swift
    '.kt', '.java',  # Kotlin/Java
    '.vue', '.svelte',  # Frameworks
    '.go', '.rs',  # Go/Rust
}

# Directories to ignore
IGNORE_DIRS = {
    'node_modules', '.git', '.next', 'build', 'dist',
    '.expo', '__pycache__', 'venv', '.venv', 'coverage',
    '.turbo', '.cache', 'android', 'ios'
}

# Maximum directory depth to prevent runaway scanning
MAX_SCAN_DEPTH = 15


def log(message: str):
    """Log to file and stdout."""
    timestamp = datetime.now().isoformat()
    line = f"[{timestamp}] {message}"
    print(line)
    try:
        with open(LOG_FILE, 'a') as f:
            f.write(line + '\n')
    except:
        pass


def file_hash(path: Path) -> str:
    """Calculate file hash for change detection."""
    try:
        content = path.read_bytes()
        return hashlib.md5(content).hexdigest()[:16]
    except:
        return ""


def should_index(path: Path) -> bool:
    """Check if a file should be indexed."""
    if path.suffix not in INDEXABLE_EXTENSIONS:
        return False

    # Check for ignored directories
    parts = path.parts
    for ignore in IGNORE_DIRS:
        if ignore in parts:
            return False

    return True


def get_changed_files(project_path: Path, project_id: str) -> List[Path]:
    """Find files that have changed since last index."""
    conn = get_connection()
    cursor = conn.execute("""
        SELECT path, file_hash FROM files WHERE project_id = ?
    """, (project_id,))
    indexed = {row['path']: row['file_hash'] for row in cursor.fetchall()}
    # Note: Don't close - using thread-local connection pooling from memory_db

    changed = []
    for file_path in project_path.rglob('*'):
        if not file_path.is_file() or not should_index(file_path):
            continue

        # Check depth limit to prevent scanning too deeply
        rel_path = str(file_path.relative_to(project_path))
        depth = len(Path(rel_path).parts)
        if depth > MAX_SCAN_DEPTH:
            continue

        current_hash = file_hash(file_path)

        if rel_path not in indexed or indexed[rel_path] != current_hash:
            changed.append(file_path)

    return changed


def extract_functions(file_path: Path) -> List[Dict]:
    """Extract function definitions from a file."""
    functions = []
    try:
        content = file_path.read_text(errors='ignore')
        lines = content.split('\n')

        for i, line in enumerate(lines, 1):
            # JavaScript/TypeScript functions
            if 'function ' in line or '=>' in line:
                # Named function
                if 'function ' in line:
                    parts = line.split('function ')
                    if len(parts) > 1:
                        name_part = parts[1].split('(')[0].strip()
                        if name_part and name_part.isidentifier():
                            functions.append({
                                'name': name_part,
                                'line': i,
                                'type': 'function'
                            })
                # Arrow function assigned to const/let
                elif ('const ' in line or 'let ' in line) and '=>' in line:
                    parts = line.split('=')[0]
                    for keyword in ['const ', 'let ', 'var ']:
                        if keyword in parts:
                            name = parts.split(keyword)[-1].strip()
                            if name and name.isidentifier():
                                functions.append({
                                    'name': name,
                                    'line': i,
                                    'type': 'function'
                                })
                            break

            # React components (capitalized functions)
            if 'export ' in line and ('function ' in line or 'const ' in line):
                for keyword in ['function ', 'const ']:
                    if keyword in line:
                        parts = line.split(keyword)
                        if len(parts) > 1:
                            name = parts[1].split('(')[0].split('=')[0].strip()
                            if name and name[0].isupper():
                                functions.append({
                                    'name': name,
                                    'line': i,
                                    'type': 'component'
                                })
                        break

            # Python functions
            if line.strip().startswith('def '):
                name = line.split('def ')[1].split('(')[0].strip()
                if name:
                    functions.append({
                        'name': name,
                        'line': i,
                        'type': 'function'
                    })

            # Python classes
            if line.strip().startswith('class '):
                name = line.split('class ')[1].split('(')[0].split(':')[0].strip()
                if name:
                    functions.append({
                        'name': name,
                        'line': i,
                        'type': 'class'
                    })

            # Swift functions
            if 'func ' in line:
                parts = line.split('func ')
                if len(parts) > 1:
                    name = parts[1].split('(')[0].strip()
                    if name:
                        functions.append({
                            'name': name,
                            'line': i,
                            'type': 'function'
                        })

    except Exception as e:
        log(f"Error extracting functions from {file_path}: {e}")

    return functions


def index_file(project_path: Path, project_id: str, file_path: Path,
               summarize: bool = False) -> bool:
    """Index a single file."""
    try:
        rel_path = str(file_path.relative_to(project_path))
        content_hash = file_hash(file_path)

        # Extract basic info
        functions = extract_functions(file_path)
        is_component = any(f['type'] == 'component' for f in functions)
        component_name = next(
            (f['name'] for f in functions if f['type'] == 'component'),
            None
        )

        # Get summary if available (from existing JSON or generate)
        summary = None
        purpose = None

        # Try to get from existing summaries.json
        summaries_path = MEMORY_ROOT / 'projects' / project_id / 'summaries.json'
        if summaries_path.exists():
            try:
                with open(summaries_path) as f:
                    summaries = json.load(f)
                file_data = summaries.get('files', {}).get(rel_path, {})
                summary = file_data.get('summary')
                purpose = file_data.get('purpose')
            except (json.JSONDecodeError, IOError):
                pass

        # Upsert to database
        file_id = upsert_file(
            project_id=project_id,
            path=rel_path,
            summary=summary,
            purpose=purpose,
            component_name=component_name,
            is_component=is_component,
            file_hash=content_hash
        )

        # Index functions
        for func in functions:
            upsert_function(
                file_id=file_id,
                name=func['name'],
                line_number=func['line'],
                func_type=func['type']
            )

        return True

    except Exception as e:
        log(f"Error indexing {file_path}: {e}")
        return False


def index_project(project_id: str, project_path: str, full: bool = False):
    """Index all files in a project."""
    project_path = Path(project_path)
    if not project_path.exists():
        log(f"Project path not found: {project_path}")
        return

    log(f"Indexing {project_id}...")

    if full:
        # Index all files (with depth limit)
        files = []
        for p in project_path.rglob('*'):
            if not p.is_file() or not should_index(p):
                continue
            # Respect depth limit
            try:
                rel_path = p.relative_to(project_path)
                if len(rel_path.parts) <= MAX_SCAN_DEPTH:
                    files.append(p)
            except ValueError:
                continue
    else:
        # Only changed files (depth limit enforced in get_changed_files)
        files = get_changed_files(project_path, project_id)

    if not files:
        log(f"No changes in {project_id}")
        return

    log(f"Found {len(files)} files to index in {project_id}")

    indexed = 0
    for file_path in files:
        if index_file(project_path, project_id, file_path):
            indexed += 1

    log(f"Indexed {indexed}/{len(files)} files in {project_id}")


def index_all_projects(full: bool = False):
    """Index all registered projects."""
    if not CONFIG_PATH.exists():
        log("No config.json found")
        return

    with open(CONFIG_PATH) as f:
        config = json.load(f)

    for project in config.get('projects', []):
        try:
            index_project(project['id'], project['path'], full=full)
        except Exception as e:
            log(f"Error indexing {project['id']}: {e}")


class FileWatcher:
    """Watch for file changes using polling."""

    def __init__(self, interval: int = 30):
        self.interval = interval
        self.running = False
        self.last_check: Dict[str, float] = {}

    def start(self):
        """Start watching for changes."""
        self.running = True
        log("File watcher started")

        while self.running:
            try:
                self.check_for_changes()
            except Exception as e:
                log(f"Watcher error: {e}")

            time.sleep(self.interval)

    def stop(self):
        """Stop the watcher."""
        self.running = False
        log("File watcher stopped")

    def check_for_changes(self):
        """Check all projects for changes."""
        if not CONFIG_PATH.exists():
            return

        with open(CONFIG_PATH) as f:
            config = json.load(f)
        now = time.time()

        for project in config.get('projects', []):
            project_id = project['id']
            project_path = Path(project['path'])

            if not project_path.exists():
                continue

            # Get most recent modification time
            latest_mod = 0
            for file_path in project_path.rglob('*'):
                if not file_path.is_file() or not should_index(file_path):
                    continue

                # Check depth limit
                try:
                    rel_path = file_path.relative_to(project_path)
                    if len(rel_path.parts) > MAX_SCAN_DEPTH:
                        continue
                    mtime = file_path.stat().st_mtime
                    if mtime > latest_mod:
                        latest_mod = mtime
                except (OSError, ValueError):
                    pass  # File may have been deleted or is inaccessible

            # Check if project has changes since last check
            last_check = self.last_check.get(project_id, 0)
            if latest_mod > last_check:
                log(f"Changes detected in {project_id}")
                index_project(project_id, project['path'])
                self.last_check[project_id] = now


def write_pid():
    """Write PID file."""
    PID_FILE.write_text(str(os.getpid()))


def read_pid() -> Optional[int]:
    """Read PID from file."""
    if PID_FILE.exists():
        try:
            return int(PID_FILE.read_text().strip())
        except:
            pass
    return None


def is_running() -> bool:
    """Check if daemon is already running."""
    pid = read_pid()
    if pid:
        try:
            os.kill(pid, 0)  # Check if process exists
            return True
        except OSError:
            pass
    return False


def daemon_main():
    """Main daemon loop."""
    if is_running():
        print("Daemon is already running")
        sys.exit(1)

    write_pid()
    log("Daemon started")

    try:
        # Initial full index
        init_database()
        index_all_projects(full=True)

        # Start file watcher
        watcher = FileWatcher(interval=60)
        watcher.start()

    except KeyboardInterrupt:
        log("Daemon stopped by user")
    finally:
        if PID_FILE.exists():
            PID_FILE.unlink()


def main():
    parser = argparse.ArgumentParser(description='Claude Memory Indexing Daemon')
    parser.add_argument('command', nargs='?', default='status',
                        choices=['start', 'stop', 'status', 'once', 'watch', 'full'],
                        help='Command to run')
    parser.add_argument('--project', '-p', help='Index specific project only')

    args = parser.parse_args()

    if args.command == 'start':
        print("Starting daemon...")
        # Fork to background
        if os.fork() > 0:
            sys.exit(0)
        os.setsid()
        if os.fork() > 0:
            sys.exit(0)
        daemon_main()

    elif args.command == 'stop':
        pid = read_pid()
        if pid:
            try:
                os.kill(pid, 15)  # SIGTERM
                print(f"Stopped daemon (PID {pid})")
                if PID_FILE.exists():
                    PID_FILE.unlink()
            except OSError:
                print("Daemon not running")
        else:
            print("No daemon PID file found")

    elif args.command == 'status':
        if is_running():
            pid = read_pid()
            print(f"Daemon running (PID {pid})")

            # Show stats
            stats = get_stats()
            print(f"\nDatabase stats:")
            print(f"  Projects: {stats['projects']}")
            print(f"  Files: {stats['files']}")
            print(f"  Functions: {stats['functions']}")
            print(f"  Observations: {stats['observations']}")
        else:
            print("Daemon not running")

    elif args.command == 'once':
        # One-shot indexing
        init_database()
        if args.project:
            with open(CONFIG_PATH) as f:
                config = json.load(f)
            project = next((p for p in config['projects'] if p['id'] == args.project), None)
            if project:
                index_project(project['id'], project['path'])
            else:
                print(f"Project not found: {args.project}")
        else:
            index_all_projects()

    elif args.command == 'full':
        # Full re-index
        init_database()
        if args.project:
            with open(CONFIG_PATH) as f:
                config = json.load(f)
            project = next((p for p in config['projects'] if p['id'] == args.project), None)
            if project:
                index_project(project['id'], project['path'], full=True)
            else:
                print(f"Project not found: {args.project}")
        else:
            index_all_projects(full=True)

    elif args.command == 'watch':
        # Watch mode (foreground)
        init_database()
        index_all_projects(full=True)
        watcher = FileWatcher(interval=30)
        try:
            watcher.start()
        except KeyboardInterrupt:
            watcher.stop()


if __name__ == '__main__':
    main()
