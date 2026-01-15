#!/usr/bin/env python3
"""
Claude Memory SQLite Database

Unified storage replacing JSON files for:
- File summaries
- Function index
- Schema/collections
- Navigation graph
- Session observations
- Error patterns
- Embeddings

Benefits:
- Faster queries (indexed)
- Cross-project search
- Incremental updates
- Full-text search built-in
- ACID transactions
"""

import sqlite3
import json
import os
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any
from contextlib import contextmanager
import hashlib

MEMORY_ROOT = Path.home() / '.claude-dash'
DB_PATH = MEMORY_ROOT / 'memory.db'

# =============================================================================
# CONNECTION MANAGEMENT
# =============================================================================

# Thread-local storage for connections
_local = threading.local()

def get_connection() -> sqlite3.Connection:
    """
    Get a thread-local database connection with optimized settings.

    FIXED: Uses connection pooling to avoid creating new connections
    for every function call. Each thread gets its own connection.
    """
    if not hasattr(_local, 'connection') or _local.connection is None:
        conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")  # Better concurrent access
        conn.execute("PRAGMA synchronous=NORMAL")  # Faster writes
        conn.execute("PRAGMA foreign_keys=ON")
        _local.connection = conn

    return _local.connection


@contextmanager
def db_transaction():
    """
    Context manager for database transactions.

    Usage:
        with db_transaction() as conn:
            conn.execute(...)
            # Auto-commits on success, auto-rollbacks on exception
    """
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def close_connection():
    """Close the thread-local connection (call at end of script/thread)."""
    if hasattr(_local, 'connection') and _local.connection is not None:
        try:
            _local.connection.close()
        except Exception:
            pass
        _local.connection = None


# Register cleanup on program exit
import atexit
atexit.register(close_connection)

def init_database():
    """Initialize the database schema."""
    conn = get_connection()

    # Projects table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            path TEXT NOT NULL,
            type TEXT,  -- react-native, nextjs, swift, etc.
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Files table - replaces summaries.json
    conn.execute("""
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL REFERENCES projects(id),
            path TEXT NOT NULL,
            summary TEXT,
            purpose TEXT,
            component_name TEXT,
            is_component BOOLEAN DEFAULT FALSE,
            file_hash TEXT,  -- For change detection
            last_modified TIMESTAMP,
            indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(project_id, path)
        )
    """)

    # Functions table - replaces functions.json
    conn.execute("""
        CREATE TABLE IF NOT EXISTS functions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id INTEGER REFERENCES files(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            line_number INTEGER,
            type TEXT,  -- function, method, component, hook
            signature TEXT,
            indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Collections/Schema table - replaces schema.json
    conn.execute("""
        CREATE TABLE IF NOT EXISTS collections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL REFERENCES projects(id),
            name TEXT NOT NULL,
            fields TEXT,  -- JSON array of field names
            description TEXT,
            UNIQUE(project_id, name)
        )
    """)

    # Collection references - which files use which collections
    conn.execute("""
        CREATE TABLE IF NOT EXISTS collection_refs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            collection_id INTEGER REFERENCES collections(id) ON DELETE CASCADE,
            file_id INTEGER REFERENCES files(id) ON DELETE CASCADE,
            UNIQUE(collection_id, file_id)
        )
    """)

    # Navigation graph - replaces graph.json
    conn.execute("""
        CREATE TABLE IF NOT EXISTS navigation (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL REFERENCES projects(id),
            screen_name TEXT NOT NULL,
            file_id INTEGER REFERENCES files(id) ON DELETE CASCADE,
            navigates_to TEXT,  -- JSON array of screen names
            params TEXT,  -- JSON object of navigation params
            UNIQUE(project_id, screen_name)
        )
    """)

    # Session observations - replaces sessions/observations
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            project_id TEXT REFERENCES projects(id),
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ended_at TIMESTAMP,
            git_branch TEXT,
            git_commit_start TEXT,
            git_commit_end TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT REFERENCES sessions(id),
            project_id TEXT REFERENCES projects(id),
            category TEXT NOT NULL,  -- decision, pattern, bugfix, gotcha, feature
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            context TEXT,  -- JSON with file paths, functions, etc.
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Error patterns - new feature
    conn.execute("""
        CREATE TABLE IF NOT EXISTS errors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT REFERENCES projects(id),
            error_type TEXT NOT NULL,  -- TypeError, SyntaxError, etc.
            message TEXT NOT NULL,
            stack_trace TEXT,
            file_path TEXT,
            line_number INTEGER,
            signature TEXT,  -- Normalized error signature for matching
            occurred_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS error_solutions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            error_id INTEGER REFERENCES errors(id),
            solution TEXT NOT NULL,
            session_id TEXT REFERENCES sessions(id),
            observation_id INTEGER REFERENCES observations(id),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Embeddings table - for persistent vector storage
    conn.execute("""
        CREATE TABLE IF NOT EXISTS embeddings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id INTEGER REFERENCES files(id) ON DELETE CASCADE,
            model TEXT NOT NULL,  -- nomic-embed-text, voyage-ai, etc.
            embedding BLOB NOT NULL,  -- Stored as binary
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(file_id, model)
        )
    """)

    # Create indexes for fast queries
    conn.execute("CREATE INDEX IF NOT EXISTS idx_files_project ON files(project_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_files_path ON files(path)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_functions_name ON functions(name)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_functions_file ON functions(file_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_observations_category ON observations(category)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_observations_project ON observations(project_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_errors_signature ON errors(signature)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_errors_project ON errors(project_id)")

    # Full-text search virtual tables
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS files_fts USING fts5(
            path, summary, purpose, component_name,
            content='files',
            content_rowid='id'
        )
    """)

    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS observations_fts USING fts5(
            title, content, category,
            content='observations',
            content_rowid='id'
        )
    """)

    # Triggers to keep FTS in sync
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS files_ai AFTER INSERT ON files BEGIN
            INSERT INTO files_fts(rowid, path, summary, purpose, component_name)
            VALUES (new.id, new.path, new.summary, new.purpose, new.component_name);
        END
    """)

    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS files_ad AFTER DELETE ON files BEGIN
            INSERT INTO files_fts(files_fts, rowid, path, summary, purpose, component_name)
            VALUES ('delete', old.id, old.path, old.summary, old.purpose, old.component_name);
        END
    """)

    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS files_au AFTER UPDATE ON files BEGIN
            INSERT INTO files_fts(files_fts, rowid, path, summary, purpose, component_name)
            VALUES ('delete', old.id, old.path, old.summary, old.purpose, old.component_name);
            INSERT INTO files_fts(rowid, path, summary, purpose, component_name)
            VALUES (new.id, new.path, new.summary, new.purpose, new.component_name);
        END
    """)

    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS observations_ai AFTER INSERT ON observations BEGIN
            INSERT INTO observations_fts(rowid, title, content, category)
            VALUES (new.id, new.title, new.content, new.category);
        END
    """)

    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS observations_ad AFTER DELETE ON observations BEGIN
            INSERT INTO observations_fts(observations_fts, rowid, title, content, category)
            VALUES ('delete', old.id, old.title, old.content, old.category);
        END
    """)

    conn.commit()
    conn.close()
    print(f"Database initialized at {DB_PATH}")


# =============================================================================
# File Operations
# =============================================================================

def upsert_file(project_id: str, path: str, summary: str = None,
                purpose: str = None, component_name: str = None,
                is_component: bool = False, file_hash: str = None) -> int:
    """Insert or update a file record. Returns file ID."""
    conn = get_connection()
    cursor = conn.execute("""
        INSERT INTO files (project_id, path, summary, purpose, component_name, is_component, file_hash, indexed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(project_id, path) DO UPDATE SET
            summary = excluded.summary,
            purpose = excluded.purpose,
            component_name = excluded.component_name,
            is_component = excluded.is_component,
            file_hash = excluded.file_hash,
            indexed_at = CURRENT_TIMESTAMP
        RETURNING id
    """, (project_id, path, summary, purpose, component_name, is_component, file_hash))
    file_id = cursor.fetchone()[0]
    conn.commit()
    conn.close()
    return file_id


def upsert_function(file_id: int, name: str, line_number: int,
                    func_type: str = 'function', signature: str = None):
    """Insert or update a function record."""
    conn = get_connection()
    conn.execute("""
        INSERT INTO functions (file_id, name, line_number, type, signature)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT DO NOTHING
    """, (file_id, name, line_number, func_type, signature))
    conn.commit()
    conn.close()


def search_files(query: str, project_id: str = None, limit: int = 20) -> List[Dict]:
    """Full-text search across files."""
    conn = get_connection()

    if project_id:
        cursor = conn.execute("""
            SELECT f.*, fts.rank
            FROM files_fts fts
            JOIN files f ON f.id = fts.rowid
            WHERE files_fts MATCH ? AND f.project_id = ?
            ORDER BY fts.rank
            LIMIT ?
        """, (query, project_id, limit))
    else:
        cursor = conn.execute("""
            SELECT f.*, fts.rank
            FROM files_fts fts
            JOIN files f ON f.id = fts.rowid
            WHERE files_fts MATCH ?
            ORDER BY fts.rank
            LIMIT ?
        """, (query, limit))

    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results


def search_functions(name: str, project_id: str = None, limit: int = 20) -> List[Dict]:
    """Search functions by name."""
    conn = get_connection()

    if project_id:
        cursor = conn.execute("""
            SELECT fn.*, f.path, f.project_id
            FROM functions fn
            JOIN files f ON f.id = fn.file_id
            WHERE fn.name LIKE ? AND f.project_id = ?
            ORDER BY fn.name
            LIMIT ?
        """, (f'%{name}%', project_id, limit))
    else:
        cursor = conn.execute("""
            SELECT fn.*, f.path, f.project_id
            FROM functions fn
            JOIN files f ON f.id = fn.file_id
            WHERE fn.name LIKE ?
            ORDER BY fn.name
            LIMIT ?
        """, (f'%{name}%', limit))

    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results


# =============================================================================
# Cross-Project Search
# =============================================================================

def cross_project_search(query: str, limit: int = 20) -> List[Dict]:
    """Search across ALL projects."""
    conn = get_connection()
    cursor = conn.execute("""
        SELECT f.*, p.name as project_name, fts.rank
        FROM files_fts fts
        JOIN files f ON f.id = fts.rowid
        JOIN projects p ON p.id = f.project_id
        WHERE files_fts MATCH ?
        ORDER BY fts.rank
        LIMIT ?
    """, (query, limit))

    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results


# =============================================================================
# Error Pattern Matching
# =============================================================================

def normalize_error_signature(error_type: str, message: str) -> str:
    """Create a normalized signature for error matching."""
    # Remove specific values like line numbers, file paths, variable names
    import re
    normalized = message.lower()
    normalized = re.sub(r'\d+', 'N', normalized)  # Numbers
    normalized = re.sub(r'[\'"][^\'"]+[\'"]', 'STR', normalized)  # Strings
    normalized = re.sub(r'/[^\s]+', 'PATH', normalized)  # Paths
    return hashlib.md5(f"{error_type}:{normalized}".encode()).hexdigest()[:16]


def log_error(project_id: str, error_type: str, message: str,
              stack_trace: str = None, file_path: str = None,
              line_number: int = None) -> int:
    """Log an error and check for existing solutions."""
    signature = normalize_error_signature(error_type, message)

    conn = get_connection()
    cursor = conn.execute("""
        INSERT INTO errors (project_id, error_type, message, stack_trace,
                           file_path, line_number, signature)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        RETURNING id
    """, (project_id, error_type, message, stack_trace, file_path, line_number, signature))
    error_id = cursor.fetchone()[0]
    conn.commit()
    conn.close()
    return error_id


def find_similar_errors(error_type: str, message: str, limit: int = 5) -> List[Dict]:
    """Find similar errors and their solutions."""
    signature = normalize_error_signature(error_type, message)

    conn = get_connection()
    cursor = conn.execute("""
        SELECT e.*, es.solution, p.name as project_name
        FROM errors e
        LEFT JOIN error_solutions es ON es.error_id = e.id
        JOIN projects p ON p.id = e.project_id
        WHERE e.signature = ?
        ORDER BY e.occurred_at DESC
        LIMIT ?
    """, (signature, limit))

    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results


def add_error_solution(error_id: int, solution: str, session_id: str = None):
    """Link a solution to an error."""
    conn = get_connection()
    conn.execute("""
        INSERT INTO error_solutions (error_id, solution, session_id)
        VALUES (?, ?, ?)
    """, (error_id, solution, session_id))
    conn.commit()
    conn.close()


# =============================================================================
# Session Management
# =============================================================================

def start_session(session_id: str, project_id: str = None) -> str:
    """Start a new session."""
    import subprocess

    git_branch = None
    git_commit = None

    if project_id:
        try:
            config = json.load(open(MEMORY_ROOT / 'config.json'))
            project = next((p for p in config['projects'] if p['id'] == project_id), None)
            if project:
                git_branch = subprocess.check_output(
                    ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
                    cwd=project['path'], stderr=subprocess.DEVNULL
                ).decode().strip()
                git_commit = subprocess.check_output(
                    ['git', 'rev-parse', 'HEAD'],
                    cwd=project['path'], stderr=subprocess.DEVNULL
                ).decode().strip()[:8]
        except:
            pass

    conn = get_connection()
    conn.execute("""
        INSERT INTO sessions (id, project_id, git_branch, git_commit_start)
        VALUES (?, ?, ?, ?)
    """, (session_id, project_id, git_branch, git_commit))
    conn.commit()
    conn.close()
    return session_id


def end_session(session_id: str, project_id: str = None):
    """End a session and capture final git state."""
    import subprocess

    git_commit = None
    if project_id:
        try:
            config = json.load(open(MEMORY_ROOT / 'config.json'))
            project = next((p for p in config['projects'] if p['id'] == project_id), None)
            if project:
                git_commit = subprocess.check_output(
                    ['git', 'rev-parse', 'HEAD'],
                    cwd=project['path'], stderr=subprocess.DEVNULL
                ).decode().strip()[:8]
        except:
            pass

    conn = get_connection()
    conn.execute("""
        UPDATE sessions
        SET ended_at = CURRENT_TIMESTAMP, git_commit_end = ?
        WHERE id = ?
    """, (git_commit, session_id))
    conn.commit()
    conn.close()


def add_observation(session_id: str, project_id: str, category: str,
                    title: str, content: str, context: Dict = None):
    """Add an observation to a session."""
    conn = get_connection()
    conn.execute("""
        INSERT INTO observations (session_id, project_id, category, title, content, context)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (session_id, project_id, category, title, content, json.dumps(context) if context else None))
    conn.commit()
    conn.close()


def search_observations(query: str, project_id: str = None,
                        category: str = None, limit: int = 20) -> List[Dict]:
    """Search observations with full-text search."""
    conn = get_connection()

    sql = """
        SELECT o.*, s.git_branch, s.git_commit_start, s.git_commit_end, fts.rank
        FROM observations_fts fts
        JOIN observations o ON o.id = fts.rowid
        LEFT JOIN sessions s ON s.id = o.session_id
        WHERE observations_fts MATCH ?
    """
    params = [query]

    if project_id:
        sql += " AND o.project_id = ?"
        params.append(project_id)

    if category:
        sql += " AND o.category = ?"
        params.append(category)

    sql += " ORDER BY fts.rank LIMIT ?"
    params.append(limit)

    cursor = conn.execute(sql, params)
    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results


# =============================================================================
# Migration from JSON files
# =============================================================================

def migrate_from_json():
    """Migrate existing JSON files to SQLite."""
    config_path = MEMORY_ROOT / 'config.json'
    if not config_path.exists():
        print("No config.json found, skipping migration")
        return

    config = json.load(open(config_path))
    conn = get_connection()

    # Migrate projects
    for project in config.get('projects', []):
        conn.execute("""
            INSERT OR REPLACE INTO projects (id, name, path, type)
            VALUES (?, ?, ?, ?)
        """, (project['id'], project.get('name', project['id']),
              project['path'], project.get('type')))

    conn.commit()

    # Migrate each project's data
    for project in config.get('projects', []):
        project_id = project['id']
        project_dir = MEMORY_ROOT / 'projects' / project_id

        if not project_dir.exists():
            continue

        print(f"Migrating {project_id}...")

        # Migrate summaries.json
        summaries_path = project_dir / 'summaries.json'
        if summaries_path.exists():
            summaries = json.load(open(summaries_path))
            for path, data in summaries.get('files', {}).items():
                file_id = upsert_file(
                    project_id=project_id,
                    path=path,
                    summary=data.get('summary'),
                    purpose=data.get('purpose'),
                    component_name=data.get('componentName'),
                    is_component=data.get('isComponent', False)
                )

                # Migrate functions from the file
                for func in data.get('functions', []):
                    upsert_function(
                        file_id=file_id,
                        name=func.get('name', ''),
                        line_number=func.get('line', 0),
                        func_type=func.get('type', 'function')
                    )

        # Migrate schema.json
        schema_path = project_dir / 'schema.json'
        if schema_path.exists():
            schema = json.load(open(schema_path))
            for name, data in schema.get('collections', {}).items():
                conn.execute("""
                    INSERT OR REPLACE INTO collections (project_id, name, fields, description)
                    VALUES (?, ?, ?, ?)
                """, (project_id, name, json.dumps(data.get('fields', [])),
                      data.get('description')))

        conn.commit()

    # Migrate sessions
    sessions_dir = MEMORY_ROOT / 'sessions'
    if sessions_dir.exists():
        for session_file in sessions_dir.glob('*.json'):
            try:
                session = json.load(open(session_file))
                session_id = session_file.stem

                conn.execute("""
                    INSERT OR IGNORE INTO sessions (id, project_id, started_at)
                    VALUES (?, ?, ?)
                """, (session_id, session.get('project'), session.get('startedAt')))

                for obs in session.get('observations', []):
                    conn.execute("""
                        INSERT INTO observations (session_id, project_id, category, title, content, context, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (session_id, session.get('project'), obs.get('category', 'pattern'),
                          obs.get('title', ''), obs.get('content', ''),
                          json.dumps(obs.get('context')) if obs.get('context') else None,
                          obs.get('timestamp')))
            except Exception as e:
                print(f"Error migrating session {session_file}: {e}")

    conn.commit()
    conn.close()
    print("Migration complete!")


# =============================================================================
# Stats and Health
# =============================================================================

def get_stats() -> Dict:
    """Get database statistics."""
    conn = get_connection()

    stats = {}
    stats['projects'] = conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
    stats['files'] = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    stats['functions'] = conn.execute("SELECT COUNT(*) FROM functions").fetchone()[0]
    stats['observations'] = conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
    stats['errors'] = conn.execute("SELECT COUNT(*) FROM errors").fetchone()[0]
    stats['embeddings'] = conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]

    # Per-project breakdown
    cursor = conn.execute("""
        SELECT p.id, p.name, COUNT(f.id) as file_count
        FROM projects p
        LEFT JOIN files f ON f.project_id = p.id
        GROUP BY p.id
    """)
    stats['projects_detail'] = [dict(row) for row in cursor.fetchall()]

    conn.close()
    return stats


# =============================================================================
# CLI
# =============================================================================

def main():
    import sys

    if len(sys.argv) < 2:
        print("Usage: python memory_db.py <command>")
        print("\nCommands:")
        print("  init          Initialize database")
        print("  migrate       Migrate from JSON files")
        print("  stats         Show database statistics")
        print("  search <q>    Cross-project search")
        print("  functions <n> Search functions by name")
        return

    cmd = sys.argv[1]

    if cmd == 'init':
        init_database()
    elif cmd == 'migrate':
        init_database()
        migrate_from_json()
    elif cmd == 'stats':
        stats = get_stats()
        print(f"Projects: {stats['projects']}")
        print(f"Files: {stats['files']}")
        print(f"Functions: {stats['functions']}")
        print(f"Observations: {stats['observations']}")
        print(f"Errors: {stats['errors']}")
        print(f"Embeddings: {stats['embeddings']}")
        print("\nPer-project:")
        for p in stats['projects_detail']:
            print(f"  {p['id']}: {p['file_count']} files")
    elif cmd == 'search' and len(sys.argv) > 2:
        query = ' '.join(sys.argv[2:])
        results = cross_project_search(query)
        for r in results:
            print(f"[{r['project_id']}] {r['path']}")
            if r.get('purpose'):
                print(f"  {r['purpose']}")
    elif cmd == 'functions' and len(sys.argv) > 2:
        name = sys.argv[2]
        results = search_functions(name)
        for r in results:
            print(f"[{r['project_id']}] {r['name']}() at {r['path']}:{r['line_number']}")
    else:
        print(f"Unknown command: {cmd}")


if __name__ == '__main__':
    main()
