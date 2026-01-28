#!/usr/bin/env python3
"""
Git Awareness

Provides context about what changed since the last Claude session.
Helps maintain continuity and awareness of work done outside sessions.

Usage:
  python git_awareness.py /path/to/project [--since "2024-01-10"]
"""

import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

MEMORY_ROOT = Path.home() / ".claude-dash"


def get_last_session_time(project_id):
    """Get timestamp of last Claude session for this project."""
    session_file = MEMORY_ROOT / "sessions" / project_id / "session.json"

    if session_file.exists():
        try:
            data = json.loads(session_file.read_text())
            saved_at = data.get("savedAt")
            if saved_at:
                return saved_at
        except:
            pass

    # Fallback: check summaries
    summary_file = MEMORY_ROOT / "sessions" / "summaries" / f"{project_id}.json"
    if summary_file.exists():
        try:
            data = json.loads(summary_file.read_text())
            return data.get("last_updated")
        except:
            pass

    return None


def run_git_command(args, cwd):
    """Run a git command and return output.
    SECURITY: Uses array form to prevent shell injection.
    """
    try:
        result = subprocess.run(
            args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except:
        return None


def validate_date_string(date_str):
    """Validate date string to prevent injection."""
    import re
    # Allow ISO dates, relative dates like "7 days ago", or simple formats
    safe_patterns = [
        r'^\d{4}-\d{2}-\d{2}$',  # YYYY-MM-DD
        r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}',  # ISO format
        r'^\d+\s+(day|week|month|year)s?\s+ago$',  # Relative dates
        r'^yesterday$',
        r'^last\s+(week|month|year)$',
    ]
    return any(re.match(p, date_str, re.IGNORECASE) for p in safe_patterns)


def get_commits_since(project_path, since_date):
    """Get commits since a date."""
    # SECURITY: Validate date to prevent injection
    if not validate_date_string(since_date):
        return []

    output = run_git_command(
        ['git', 'log', f'--since={since_date}', '--pretty=format:%h|%an|%s|%ai', '--no-merges'],
        project_path
    )

    if not output:
        return []

    commits = []
    for line in output.split("\n"):
        if not line.strip():
            continue
        parts = line.split("|", 3)
        if len(parts) >= 4:
            commits.append({
                "hash": parts[0],
                "author": parts[1],
                "message": parts[2],
                "date": parts[3]
            })

    return commits


def get_files_changed_since(project_path, since_date):
    """Get files changed since a date."""
    # SECURITY: Validate date to prevent injection
    if not validate_date_string(since_date):
        return []

    # Get the commit hash from before the date first
    rev_output = run_git_command(
        ['git', 'rev-list', '-1', f'--before={since_date}', 'HEAD'],
        project_path
    )

    if rev_output:
        output = run_git_command(
            ['git', 'diff', '--name-only', rev_output, 'HEAD'],
            project_path
        )
    else:
        output = None

    if not output:
        # Fallback: get files from recent commits
        output = run_git_command(
            ['git', 'log', f'--since={since_date}', '--name-only', '--pretty=format:'],
            project_path
        )
        if output:
            # Remove duplicates
            output = '\n'.join(sorted(set(output.split('\n'))))

    if not output:
        return []

    files = [f.strip() for f in output.split("\n") if f.strip()]
    return list(set(files))


def get_current_branch(project_path):
    """Get current branch name."""
    return run_git_command("git branch --show-current", project_path)


def get_uncommitted_changes(project_path):
    """Get summary of uncommitted changes."""
    status = run_git_command("git status --porcelain", project_path)

    if not status:
        return {"staged": [], "modified": [], "untracked": []}

    staged = []
    modified = []
    untracked = []

    for line in status.split("\n"):
        if not line:
            continue
        status_code = line[:2]
        filename = line[3:]

        if status_code[0] in "MADRC":
            staged.append(filename)
        if status_code[1] == "M":
            modified.append(filename)
        if status_code == "??":
            untracked.append(filename)

    return {
        "staged": staged[:20],
        "modified": modified[:20],
        "untracked": untracked[:10]
    }


def identify_claude_commits(commits):
    """Identify which commits were likely made during Claude sessions."""
    claude_indicators = [
        "co-authored-by: claude",
        "generated with claude",
        "claude code",
    ]

    claude_commits = []
    other_commits = []

    for commit in commits:
        msg_lower = commit["message"].lower()
        is_claude = any(indicator in msg_lower for indicator in claude_indicators)

        if is_claude:
            claude_commits.append(commit)
        else:
            other_commits.append(commit)

    return claude_commits, other_commits


def analyze_changes(project_path, since_date=None, project_id=None):
    """Analyze what changed since last session."""
    # Determine since date
    if not since_date and project_id:
        since_date = get_last_session_time(project_id)

    if not since_date:
        # Default to 7 days ago
        since_date = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()

    # Gather git data
    commits = get_commits_since(project_path, since_date)
    files = get_files_changed_since(project_path, since_date)
    branch = get_current_branch(project_path)
    uncommitted = get_uncommitted_changes(project_path)

    # Separate Claude commits from user commits
    claude_commits, user_commits = identify_claude_commits(commits)

    # Categorize files by type
    file_categories = categorize_files(files)

    return {
        "project_path": str(project_path),
        "since": since_date,
        "current_branch": branch,
        "commits": {
            "total": len(commits),
            "by_user": len(user_commits),
            "by_claude": len(claude_commits),
            "user_commits": user_commits[:10],
            "claude_commits": claude_commits[:5]
        },
        "files_changed": {
            "total": len(files),
            "by_category": file_categories,
            "all_files": files[:30]
        },
        "uncommitted": uncommitted
    }


def categorize_files(files):
    """Categorize files by type."""
    categories = {
        "components": [],
        "screens": [],
        "api": [],
        "config": [],
        "tests": [],
        "styles": [],
        "other": []
    }

    for f in files:
        f_lower = f.lower()
        if "/components/" in f_lower or f_lower.endswith("component.tsx") or f_lower.endswith("component.js"):
            categories["components"].append(f)
        elif "/screens/" in f_lower or "/pages/" in f_lower or "screen." in f_lower:
            categories["screens"].append(f)
        elif "/api/" in f_lower or "api." in f_lower or "service" in f_lower:
            categories["api"].append(f)
        elif f_lower.endswith((".json", ".yaml", ".yml", ".env", ".config.js", ".config.ts")):
            categories["config"].append(f)
        elif "test" in f_lower or "spec" in f_lower or "__tests__" in f_lower:
            categories["tests"].append(f)
        elif f_lower.endswith((".css", ".scss", ".styled.ts", ".styled.tsx")):
            categories["styles"].append(f)
        else:
            categories["other"].append(f)

    # Remove empty categories
    return {k: v for k, v in categories.items() if v}


def format_for_injection(analysis):
    """Format analysis for context injection."""
    lines = ["[SINCE LAST SESSION]"]

    # Branch info
    if analysis["current_branch"]:
        lines.append(f"Branch: {analysis['current_branch']}")

    # Commits by user (not Claude)
    user_commits = analysis["commits"]["user_commits"]
    if user_commits:
        lines.append(f"\nYour commits ({len(user_commits)}):")
        for c in user_commits[:5]:
            lines.append(f"  - {c['message'][:60]}")

    # Files changed by category
    files = analysis["files_changed"]
    if files["total"] > 0:
        lines.append(f"\nFiles changed ({files['total']}):")
        for category, file_list in files["by_category"].items():
            if file_list:
                lines.append(f"  {category}: {', '.join(f[:30] for f in file_list[:3])}")
                if len(file_list) > 3:
                    lines.append(f"    ...and {len(file_list) - 3} more")

    # Uncommitted changes
    uncommitted = analysis["uncommitted"]
    if uncommitted["modified"] or uncommitted["staged"]:
        lines.append("\nUncommitted changes:")
        if uncommitted["staged"]:
            lines.append(f"  Staged: {', '.join(uncommitted['staged'][:3])}")
        if uncommitted["modified"]:
            lines.append(f"  Modified: {', '.join(uncommitted['modified'][:3])}")

    return "\n".join(lines) if len(lines) > 1 else None


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Git awareness for session continuity")
    parser.add_argument("project_path", nargs="?", default=".", help="Project path")
    parser.add_argument("--since", help="Since date (ISO format)")
    parser.add_argument("--project", help="Project ID for session lookup")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    project_path = Path(args.project_path).resolve()

    if not (project_path / ".git").exists():
        print("Not a git repository")
        sys.exit(1)

    analysis = analyze_changes(
        project_path,
        since_date=args.since,
        project_id=args.project
    )

    if args.json:
        print(json.dumps(analysis, indent=2))
    else:
        formatted = format_for_injection(analysis)
        if formatted:
            print(formatted)
        else:
            print("No changes since last session")


if __name__ == "__main__":
    main()
