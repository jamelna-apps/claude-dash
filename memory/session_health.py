#!/usr/bin/env python3
"""
Session Health Check - Fast diagnostics for session start

Runs quick checks and outputs issues for context injection.
Designed to complete in <500ms.

Usage:
    python3 session_health.py [--json]
"""

import json
import os
import sys
import subprocess
from pathlib import Path
from datetime import datetime, timedelta

MEMORY_ROOT = Path.home() / '.claude-dash'
DB_PATH = MEMORY_ROOT / 'memory.db'
IMPROVEMENTS_PATH = MEMORY_ROOT / 'improvements.json'


def check_gateway():
    """Check if gateway is running."""
    try:
        result = subprocess.run(
            ['pgrep', '-f', 'gateway/server.js'],
            capture_output=True, timeout=1
        )
        return result.returncode == 0
    except:
        return False


def check_watcher():
    """Check if watcher is running."""
    try:
        result = subprocess.run(
            ['pgrep', '-f', 'watcher/watcher.js'],
            capture_output=True, timeout=1
        )
        return result.returncode == 0
    except:
        return False


def check_ollama():
    """Check if Ollama is responding."""
    try:
        result = subprocess.run(
            ['curl', '-s', '-o', '/dev/null', '-w', '%{http_code}',
             'http://localhost:11434/api/tags'],
            capture_output=True, timeout=2
        )
        return result.stdout.decode().strip() == '200'
    except:
        return False


def check_database():
    """Check database health."""
    issues = []
    try:
        import sqlite3
        conn = sqlite3.connect(str(DB_PATH), timeout=1)

        # Check FTS works
        try:
            result = conn.execute(
                "SELECT COUNT(*) FROM files_fts WHERE files_fts MATCH 'test'"
            ).fetchone()
        except Exception as e:
            issues.append(f"FTS error: {str(e)[:50]}")

        # Check file count
        file_count = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        if file_count == 0:
            issues.append("No files indexed in database")

        conn.close()
    except Exception as e:
        issues.append(f"Database error: {str(e)[:50]}")

    return issues


def check_recent_errors():
    """Check for recent errors in logs."""
    errors = []
    log_dir = MEMORY_ROOT / 'logs'

    if not log_dir.exists():
        return errors

    cutoff = datetime.now() - timedelta(hours=24)

    for log_file in log_dir.glob('*.log'):
        try:
            # Only check recently modified logs
            mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
            if mtime < cutoff:
                continue

            # Read last 50 lines
            content = log_file.read_text()
            lines = content.strip().split('\n')[-50:]

            for line in lines:
                lower = line.lower()
                if 'error' in lower or 'exception' in lower or 'traceback' in lower:
                    # Extract just the error message, not full stack
                    if len(line) > 100:
                        line = line[:100] + '...'
                    errors.append(f"{log_file.name}: {line}")
                    if len(errors) >= 3:  # Limit to 3 errors
                        return errors
        except:
            pass

    return errors


def check_stale_indexes():
    """Check for files modified but not re-indexed (simplified check)."""
    # This is a simplified check - just see if index is recent
    try:
        projects_dir = MEMORY_ROOT / 'projects'
        if not projects_dir.exists():
            return []

        stale = []
        for project_dir in projects_dir.iterdir():
            if not project_dir.is_dir():
                continue

            summaries = project_dir / 'summaries.json'
            if summaries.exists():
                mtime = datetime.fromtimestamp(summaries.stat().st_mtime)
                age = datetime.now() - mtime
                if age > timedelta(days=7):
                    stale.append(f"{project_dir.name}: summaries.json is {age.days} days old")

        return stale[:2]  # Limit to 2
    except:
        return []


def get_pending_improvements():
    """Get pending items from improvements backlog."""
    try:
        if not IMPROVEMENTS_PATH.exists():
            return []

        data = json.loads(IMPROVEMENTS_PATH.read_text())
        pending = []

        # Get critical/high priority pending ideas
        for idea in data.get('ideas', []):
            if idea.get('status') == 'pending' and idea.get('priority') in ['critical', 'high']:
                pending.append(f"[{idea['priority']}] {idea['title']}")

        # Get pending tech debt
        for debt in data.get('techDebt', []):
            if debt.get('status') == 'pending' and debt.get('priority') in ['critical', 'high']:
                pending.append(f"[debt] {debt['title']}")

        # Get unresolved issues
        for issue in data.get('issues', []):
            if issue.get('status') != 'resolved':
                pending.append(f"[issue] {issue['title']}")

        return pending[:3]  # Limit to 3
    except:
        return []


def log_issue_to_backlog(title, description, source='health_check'):
    """Log an issue to the improvements backlog (if not already there)."""
    try:
        from add_improvement import add_issue
        add_issue(title, description, source)
    except:
        pass  # Don't fail if logging fails


def run_health_check():
    """Run all health checks and return results."""
    results = {
        'timestamp': datetime.now().isoformat(),
        'services': {
            'gateway': check_gateway(),
            'watcher': check_watcher(),
            'ollama': check_ollama()
        },
        'issues': [],
        'improvements': []
    }

    # Check services
    if not results['services']['gateway']:
        results['issues'].append("Gateway not running")
        log_issue_to_backlog("Gateway not running", "MCP gateway service is down", "health_check")
    if not results['services']['watcher']:
        results['issues'].append("Watcher not running")
        log_issue_to_backlog("Watcher not running", "File watcher service is down", "health_check")
    if not results['services']['ollama']:
        results['issues'].append("Ollama not responding")
        log_issue_to_backlog("Ollama not responding", "Local AI service not responding", "health_check")

    # Database issues
    db_issues = check_database()
    results['issues'].extend(db_issues)
    for issue in db_issues:
        log_issue_to_backlog(issue, issue, "health_check")

    # Recent errors
    errors = check_recent_errors()
    if errors:
        results['issues'].append(f"Recent errors in logs: {len(errors)}")

    # Stale indexes
    stale = check_stale_indexes()
    results['issues'].extend(stale)

    # Pending improvements
    results['improvements'] = get_pending_improvements()

    return results


def format_for_injection(results):
    """Format results for context injection."""
    lines = []

    # Service status (only show if something is down)
    down_services = [s for s, ok in results['services'].items() if not ok]
    if down_services:
        lines.append(f"Services down: {', '.join(down_services)}")

    # Issues
    if results['issues']:
        lines.append("Issues detected:")
        for issue in results['issues'][:3]:
            lines.append(f"  - {issue}")

    # Pending improvements
    if results['improvements']:
        lines.append("Pending improvements:")
        for imp in results['improvements'][:2]:
            lines.append(f"  - {imp}")

    return '\n'.join(lines) if lines else None


def main():
    as_json = '--json' in sys.argv

    results = run_health_check()

    if as_json:
        print(json.dumps(results, indent=2))
    else:
        formatted = format_for_injection(results)
        if formatted:
            print(formatted)
        # If nothing to report, output nothing (healthy state)


if __name__ == '__main__':
    main()
