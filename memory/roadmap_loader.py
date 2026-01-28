#!/usr/bin/env python3
"""
Roadmap Loader - Loads and formats project roadmaps for session injection.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

MEMORY_ROOT = Path.home() / ".claude-dash"


def load_roadmap(project_id: str) -> dict | None:
    """Load roadmap.json for a project."""
    roadmap_path = MEMORY_ROOT / "projects" / project_id / "roadmap.json"
    if not roadmap_path.exists():
        return None

    try:
        with open(roadmap_path) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def format_for_injection(roadmap: dict, verbose: bool = False) -> str:
    """Format roadmap for session injection (concise by default)."""
    if not roadmap:
        return ""

    lines = []

    # Summary
    summary = roadmap.get("summary", {})
    status = summary.get("status", "unknown")
    phase = summary.get("phase", "unknown")
    version = roadmap.get("currentVersion", "?")

    lines.append(f"[PROJECT STATUS] v{version} | {status} | {phase}")
    if summary.get("description"):
        lines.append(f"  {summary['description']}")

    # Current Sprint
    sprint = roadmap.get("currentSprint", {})
    if sprint:
        sprint_name = sprint.get("name", "Current Sprint")
        lines.append(f"\n[CURRENT SPRINT] {sprint_name}")

        # Sprint goals (brief)
        goals = sprint.get("goals", [])
        if goals:
            lines.append(f"  Goals: {'; '.join(goals[:3])}")

        # Active items
        items = sprint.get("items", [])
        in_progress = [i for i in items if i.get("status") == "in_progress"]
        pending = [i for i in items if i.get("status") == "pending"]

        if in_progress:
            lines.append("  In Progress:")
            for item in in_progress[:3]:
                lines.append(f"    - {item.get('title')} [{item.get('priority', 'medium')}]")

        if pending:
            lines.append("  Pending:")
            for item in pending[:3]:
                lines.append(f"    - {item.get('title')} [{item.get('priority', 'medium')}]")

    # Next Up (from backlog)
    backlog = roadmap.get("backlog", {})
    short_term = backlog.get("shortTerm", {}).get("items", [])
    if short_term:
        # Filter to not_started or planning
        upcoming = [i for i in short_term if i.get("status") in ["not_started", "planning"]][:5]
        if upcoming:
            lines.append("\n[NEXT UP] Short-term backlog:")
            for item in upcoming:
                priority = item.get("priority", "medium")
                status = item.get("status", "not_started")
                lines.append(f"  - {item.get('title')} [{priority}] ({status})")

    # Blockers
    blockers = roadmap.get("blockers", [])
    active_blockers = [b for b in blockers if b.get("severity") in ["critical", "major"]]
    if active_blockers:
        lines.append("\n[BLOCKERS]")
        for blocker in active_blockers:
            lines.append(f"  - [{blocker.get('severity')}] {blocker.get('title')}")

    # Technical Debt (high priority only)
    debt = roadmap.get("technicalDebt", [])
    high_debt = [d for d in debt if d.get("priority") == "high"][:2]
    if high_debt and verbose:
        lines.append("\n[TECH DEBT]")
        for item in high_debt:
            lines.append(f"  - {item.get('title')}")

    # Recently completed (for context)
    recent = roadmap.get("recentlyCompleted", [])[:3]
    if recent:
        lines.append("\n[RECENTLY COMPLETED]")
        for item in recent:
            lines.append(f"  - {item.get('item')} ({item.get('completedDate', '?')})")

    return "\n".join(lines)


def get_next_tasks(roadmap: dict, limit: int = 5) -> list:
    """Get the next tasks to work on (in priority order)."""
    tasks = []

    # Current sprint items first
    sprint = roadmap.get("currentSprint", {})
    for item in sprint.get("items", []):
        if item.get("status") in ["pending", "in_progress"]:
            tasks.append({
                "source": "sprint",
                "id": item.get("id"),
                "title": item.get("title"),
                "priority": item.get("priority", "medium"),
                "status": item.get("status")
            })

    # Then short-term backlog
    backlog = roadmap.get("backlog", {}).get("shortTerm", {}).get("items", [])
    for item in backlog:
        if item.get("status") in ["not_started", "planning"]:
            tasks.append({
                "source": "backlog",
                "id": item.get("id"),
                "title": item.get("title"),
                "priority": item.get("priority", "medium"),
                "status": item.get("status")
            })

    # Sort by priority
    priority_order = {"high": 0, "medium": 1, "low": 2}
    tasks.sort(key=lambda t: priority_order.get(t.get("priority"), 1))

    return tasks[:limit]


def update_item_status(project_id: str, item_id: str, new_status: str) -> bool:
    """Update a roadmap item's status."""
    roadmap_path = MEMORY_ROOT / "projects" / project_id / "roadmap.json"
    if not roadmap_path.exists():
        return False

    try:
        with open(roadmap_path) as f:
            roadmap = json.load(f)

        # Search in current sprint
        for item in roadmap.get("currentSprint", {}).get("items", []):
            if item.get("id") == item_id:
                item["status"] = new_status
                if new_status == "completed":
                    # Move to recently completed
                    roadmap.setdefault("recentlyCompleted", []).insert(0, {
                        "item": item["title"],
                        "completedDate": datetime.now().strftime("%Y-%m-%d"),
                        "version": roadmap.get("currentVersion", "?")
                    })
                roadmap["lastUpdated"] = datetime.now().isoformat()
                with open(roadmap_path, "w") as f:
                    json.dump(roadmap, f, indent=2)
                return True

        # Search in backlog
        for timeframe in ["shortTerm", "mediumTerm", "longTerm"]:
            items = roadmap.get("backlog", {}).get(timeframe, {}).get("items", [])
            for item in items:
                if item.get("id") == item_id:
                    item["status"] = new_status
                    roadmap["lastUpdated"] = datetime.now().isoformat()
                    with open(roadmap_path, "w") as f:
                        json.dump(roadmap, f, indent=2)
                    return True

        return False
    except (json.JSONDecodeError, IOError):
        return False


def add_item(project_id: str, title: str, priority: str = "medium",
             description: str = "", target: str = "sprint") -> bool:
    """Add a new item to the roadmap."""
    roadmap_path = MEMORY_ROOT / "projects" / project_id / "roadmap.json"
    if not roadmap_path.exists():
        return False

    try:
        with open(roadmap_path) as f:
            roadmap = json.load(f)

        # Generate ID
        item_id = title.lower().replace(" ", "-")[:30]

        new_item = {
            "id": item_id,
            "title": title,
            "priority": priority,
            "status": "pending",
            "description": description
        }

        if target == "sprint":
            roadmap.setdefault("currentSprint", {"name": "Current", "items": []})
            roadmap["currentSprint"]["items"].append(new_item)
        else:
            roadmap.setdefault("backlog", {}).setdefault("shortTerm", {"timeframe": "1-2 months", "items": []})
            new_item["status"] = "not_started"
            new_item["estimatedEffort"] = "medium"
            roadmap["backlog"]["shortTerm"]["items"].append(new_item)

        roadmap["lastUpdated"] = datetime.now().isoformat()

        with open(roadmap_path, "w") as f:
            json.dump(roadmap, f, indent=2)

        return True
    except (json.JSONDecodeError, IOError):
        return False


def main():
    """CLI interface for roadmap operations."""
    if len(sys.argv) < 2:
        print("Usage: roadmap_loader.py <project_id> [action] [args...]")
        print("Actions: status, next, complete <id>, add <title> [priority]")
        sys.exit(1)

    project_id = sys.argv[1]
    action = sys.argv[2] if len(sys.argv) > 2 else "status"

    roadmap = load_roadmap(project_id)

    if action == "status":
        if roadmap:
            print(format_for_injection(roadmap, verbose=True))
        else:
            print(f"No roadmap found for project: {project_id}")

    elif action == "next":
        if roadmap:
            tasks = get_next_tasks(roadmap)
            if tasks:
                print("Next tasks:")
                for t in tasks:
                    print(f"  [{t['priority']}] {t['title']} ({t['status']})")
            else:
                print("No pending tasks")
        else:
            print(f"No roadmap found for project: {project_id}")

    elif action == "complete":
        if len(sys.argv) < 4:
            print("Usage: complete <item_id>")
            sys.exit(1)
        item_id = sys.argv[3]
        if update_item_status(project_id, item_id, "completed"):
            print(f"Marked '{item_id}' as completed")
        else:
            print(f"Could not find item: {item_id}")

    elif action == "add":
        if len(sys.argv) < 4:
            print("Usage: add <title> [priority]")
            sys.exit(1)
        title = sys.argv[3]
        priority = sys.argv[4] if len(sys.argv) > 4 else "medium"
        if add_item(project_id, title, priority):
            print(f"Added: {title}")
        else:
            print("Failed to add item")

    elif action == "inject":
        # For hook injection - concise format
        if roadmap:
            print(format_for_injection(roadmap, verbose=False))

    else:
        print(f"Unknown action: {action}")
        sys.exit(1)


if __name__ == "__main__":
    main()
