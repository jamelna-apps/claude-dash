#!/usr/bin/env python3
"""
Git-Roadmap Sync - Detects completed tasks from git commits and updates roadmaps.

Can be run:
1. As a git post-commit hook
2. At session start to check recent commits
3. Manually to sync roadmap with git history
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

MEMORY_ROOT = Path.home() / ".claude-dash"
CONFIG_PATH = MEMORY_ROOT / "config.json"


def load_config():
    """Load claude-dash config."""
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {"projects": []}


def detect_project(cwd: str) -> str | None:
    """Detect project ID from current directory."""
    config = load_config()
    for project in config.get("projects", []):
        if cwd.startswith(project.get("path", "")):
            return project.get("id")
    return None


def get_recent_commits(repo_path: str, since_days: int = 1) -> list:
    """Get recent commit messages from git."""
    try:
        since_date = (datetime.now() - timedelta(days=since_days)).strftime("%Y-%m-%d")
        result = subprocess.run(
            ["git", "log", f"--since={since_date}", "--pretty=format:%H|%s|%b|||"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode != 0:
            return []

        commits = []
        for entry in result.stdout.split("|||"):
            entry = entry.strip()
            if not entry:
                continue
            parts = entry.split("|", 2)
            if len(parts) >= 2:
                commits.append({
                    "hash": parts[0],
                    "subject": parts[1],
                    "body": parts[2] if len(parts) > 2 else ""
                })
        return commits
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []


def get_last_commit(repo_path: str) -> dict | None:
    """Get the most recent commit."""
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--pretty=format:%H|%s|%b"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode != 0:
            return None

        parts = result.stdout.strip().split("|", 2)
        if len(parts) >= 2:
            return {
                "hash": parts[0],
                "subject": parts[1],
                "body": parts[2] if len(parts) > 2 else ""
            }
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def extract_completion_signals(commit: dict) -> list:
    """Extract task completion signals from commit message."""
    signals = []
    full_message = f"{commit.get('subject', '')} {commit.get('body', '')}"

    # Patterns for task references
    patterns = [
        # Direct task ID reference: [task-id], #task-id, closes #task-id
        r"(?:closes?|fixes?|completes?|done)\s*[#\[]?([a-z0-9-]+)[#\]]?",
        r"\[([a-z0-9-]+)\]\s*(?:completed|done|finished)",

        # Feature/fix descriptions
        r"(?:feat|fix|complete|implement|add|finish)(?:\([^)]+\))?:\s*(.+?)(?:\n|$)",

        # Common patterns
        r"(?:completed|finished|implemented|added)\s+(.+?)(?:\n|$)",
    ]

    for pattern in patterns:
        matches = re.findall(pattern, full_message, re.IGNORECASE)
        signals.extend(matches)

    return list(set(s.strip() for s in signals if s.strip()))


def load_roadmap(project_id: str) -> dict | None:
    """Load roadmap for a project."""
    roadmap_path = MEMORY_ROOT / "projects" / project_id / "roadmap.json"
    try:
        with open(roadmap_path) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def save_roadmap(project_id: str, roadmap: dict) -> bool:
    """Save roadmap for a project."""
    roadmap_path = MEMORY_ROOT / "projects" / project_id / "roadmap.json"
    try:
        roadmap["lastUpdated"] = datetime.now().isoformat()
        with open(roadmap_path, "w") as f:
            json.dump(roadmap, f, indent=2)
        return True
    except IOError:
        return False


def match_signal_to_task(signal: str, roadmap: dict) -> dict | None:
    """Match a completion signal to a roadmap task."""
    signal_lower = signal.lower().strip()
    signal_words = set(re.findall(r'\w+', signal_lower))

    # First, try exact ID match
    for item in roadmap.get("currentSprint", {}).get("items", []):
        if item.get("id", "").lower() == signal_lower:
            return {"source": "sprint", "item": item}

    for timeframe in ["shortTerm", "mediumTerm", "longTerm"]:
        for item in roadmap.get("backlog", {}).get(timeframe, {}).get("items", []):
            if item.get("id", "").lower() == signal_lower:
                return {"source": f"backlog.{timeframe}", "item": item}

    # Then try fuzzy title match
    for item in roadmap.get("currentSprint", {}).get("items", []):
        title_lower = item.get("title", "").lower()
        title_words = set(re.findall(r'\w+', title_lower))
        overlap = len(signal_words & title_words)
        if overlap >= 2 or signal_lower in title_lower:
            return {"source": "sprint", "item": item}

    for timeframe in ["shortTerm", "mediumTerm", "longTerm"]:
        for item in roadmap.get("backlog", {}).get(timeframe, {}).get("items", []):
            title_lower = item.get("title", "").lower()
            title_words = set(re.findall(r'\w+', title_lower))
            overlap = len(signal_words & title_words)
            if overlap >= 2 or signal_lower in title_lower:
                return {"source": f"backlog.{timeframe}", "item": item}

    return None


def complete_task(roadmap: dict, match: dict) -> bool:
    """Mark a task as completed in the roadmap."""
    source = match["source"]
    item_id = match["item"].get("id")
    item_title = match["item"].get("title")

    if source == "sprint":
        for item in roadmap.get("currentSprint", {}).get("items", []):
            if item.get("id") == item_id and item.get("status") != "completed":
                item["status"] = "completed"
                roadmap.setdefault("recentlyCompleted", []).insert(0, {
                    "item": item_title,
                    "completedDate": datetime.now().strftime("%Y-%m-%d"),
                    "version": roadmap.get("currentVersion", "?"),
                    "source": "git"
                })
                return True
    elif source.startswith("backlog."):
        timeframe = source.split(".")[1]
        for item in roadmap.get("backlog", {}).get(timeframe, {}).get("items", []):
            if item.get("id") == item_id and item.get("status") != "completed":
                item["status"] = "completed"
                roadmap.setdefault("recentlyCompleted", []).insert(0, {
                    "item": item_title,
                    "completedDate": datetime.now().strftime("%Y-%m-%d"),
                    "version": roadmap.get("currentVersion", "?"),
                    "source": "git"
                })
                return True

    return False


def sync_commits_to_roadmap(project_id: str, commits: list, dry_run: bool = False) -> list:
    """Sync commits to roadmap, returning list of updates made."""
    roadmap = load_roadmap(project_id)
    if not roadmap:
        return []

    updates = []

    for commit in commits:
        signals = extract_completion_signals(commit)
        for signal in signals:
            match = match_signal_to_task(signal, roadmap)
            if match and match["item"].get("status") != "completed":
                if not dry_run:
                    if complete_task(roadmap, match):
                        updates.append({
                            "commit": commit["hash"][:8],
                            "signal": signal,
                            "task": match["item"].get("title")
                        })

    if updates and not dry_run:
        # Keep only last 10 recently completed
        roadmap["recentlyCompleted"] = roadmap.get("recentlyCompleted", [])[:10]
        save_roadmap(project_id, roadmap)

    return updates


def main():
    parser = argparse.ArgumentParser(description="Sync git commits to project roadmap")
    parser.add_argument("--repo", default=os.getcwd(), help="Repository path")
    parser.add_argument("--project", help="Project ID (auto-detected if not specified)")
    parser.add_argument("--since-days", type=int, default=1, help="Check commits from last N days")
    parser.add_argument("--last-commit-only", action="store_true", help="Only check last commit (for post-commit hook)")
    parser.add_argument("--dry-run", action="store_true", help="Don't modify roadmap")

    args = parser.parse_args()

    # Detect project
    project_id = args.project or detect_project(args.repo)
    if not project_id:
        print("Could not detect project")
        return

    # Check if roadmap exists
    roadmap = load_roadmap(project_id)
    if not roadmap:
        print(f"No roadmap found for project: {project_id}")
        return

    # Get commits
    if args.last_commit_only:
        commit = get_last_commit(args.repo)
        commits = [commit] if commit else []
    else:
        commits = get_recent_commits(args.repo, args.since_days)

    if not commits:
        print("No commits to analyze")
        return

    print(f"Analyzing {len(commits)} commit(s) for project '{project_id}'...")

    # Sync
    updates = sync_commits_to_roadmap(project_id, commits, args.dry_run)

    if updates:
        print(f"\n{'Would update' if args.dry_run else 'Updated'} {len(updates)} task(s):")
        for u in updates:
            print(f"  [{u['commit']}] {u['signal']} -> {u['task']}")
    else:
        print("No matching tasks found in commits")


if __name__ == "__main__":
    main()
