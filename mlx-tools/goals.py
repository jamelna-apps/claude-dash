#!/usr/bin/env python3
"""
Goals Manager for Claude Memory System

Captures intent and context for projects - the "why" behind tasks.
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict
import uuid

MEMORY_ROOT = Path.home() / '.claude-dash'


def get_goals_path(project_id: str) -> Path:
    """Get path to project's goals.json"""
    return MEMORY_ROOT / 'projects' / project_id / 'goals.json'


def load_goals(project_id: str) -> Dict:
    """Load goals for a project"""
    path = get_goals_path(project_id)
    if path.exists():
        return json.loads(path.read_text())
    return {
        "activeGoals": [],
        "completedGoals": [],
        "archivedGoals": []
    }


def save_goals(project_id: str, goals: Dict):
    """Save goals for a project"""
    path = get_goals_path(project_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(goals, indent=2))


def add_goal(project_id: str, summary: str, why: str = "", constraints: List[str] = None):
    """Add a new active goal"""
    goals = load_goals(project_id)

    goal = {
        "id": str(uuid.uuid4())[:8],
        "summary": summary,
        "why": why,
        "constraints": constraints or [],
        "status": "active",
        "createdAt": datetime.now().isoformat(),
        "updatedAt": datetime.now().isoformat(),
        "relatedDecisions": [],
        "notes": []
    }

    goals["activeGoals"].append(goal)
    save_goals(project_id, goals)

    print(f"Added goal [{goal['id']}]: {summary}")
    return goal


def complete_goal(project_id: str, goal_id: str, outcome: str = ""):
    """Mark a goal as completed"""
    goals = load_goals(project_id)

    for i, goal in enumerate(goals["activeGoals"]):
        if goal["id"] == goal_id or goal["summary"].lower().startswith(goal_id.lower()):
            goal["status"] = "completed"
            goal["completedAt"] = datetime.now().isoformat()
            goal["outcome"] = outcome
            goals["completedGoals"].append(goal)
            goals["activeGoals"].pop(i)
            save_goals(project_id, goals)
            print(f"Completed: {goal['summary']}")
            return goal

    print(f"Goal not found: {goal_id}")
    return None


def archive_goal(project_id: str, goal_id: str, reason: str = ""):
    """Archive a goal (abandoned/deferred)"""
    goals = load_goals(project_id)

    for i, goal in enumerate(goals["activeGoals"]):
        if goal["id"] == goal_id or goal["summary"].lower().startswith(goal_id.lower()):
            goal["status"] = "archived"
            goal["archivedAt"] = datetime.now().isoformat()
            goal["archiveReason"] = reason
            goals["archivedGoals"].append(goal)
            goals["activeGoals"].pop(i)
            save_goals(project_id, goals)
            print(f"Archived: {goal['summary']}")
            return goal

    print(f"Goal not found: {goal_id}")
    return None


def update_goal(project_id: str, goal_id: str, field: str, value: str):
    """Update a field on a goal"""
    goals = load_goals(project_id)

    for goal in goals["activeGoals"]:
        if goal["id"] == goal_id or goal["summary"].lower().startswith(goal_id.lower()):
            if field == "constraints":
                if "constraints" not in goal:
                    goal["constraints"] = []
                goal["constraints"].append(value)
            elif field == "note":
                if "notes" not in goal:
                    goal["notes"] = []
                goal["notes"].append({
                    "text": value,
                    "addedAt": datetime.now().isoformat()
                })
            elif field == "decision":
                if "relatedDecisions" not in goal:
                    goal["relatedDecisions"] = []
                goal["relatedDecisions"].append(value)
            else:
                goal[field] = value

            goal["updatedAt"] = datetime.now().isoformat()
            save_goals(project_id, goals)
            print(f"Updated {field} on: {goal['summary']}")
            return goal

    print(f"Goal not found: {goal_id}")
    return None


def list_goals(project_id: str, show_all: bool = False):
    """List goals for a project"""
    goals = load_goals(project_id)

    if not goals["activeGoals"] and not show_all:
        print(f"No active goals for {project_id}")
        print(f"Add one with: mlx goal add {project_id} \"Your goal\" --why \"Reason\"")
        return

    if goals["activeGoals"]:
        print(f"\n=== Active Goals ({project_id}) ===\n")
        for goal in goals["activeGoals"]:
            print(f"[{goal['id']}] {goal['summary']}")
            if goal.get("why"):
                print(f"    Why: {goal['why']}")
            if goal.get("constraints"):
                print(f"    Constraints: {', '.join(goal['constraints'])}")
            if goal.get("notes"):
                print(f"    Notes: {len(goal['notes'])} note(s)")
            print()

    if show_all:
        if goals["completedGoals"]:
            print(f"\n=== Completed Goals ===\n")
            for goal in goals["completedGoals"][-5:]:  # Last 5
                print(f"[{goal['id']}] {goal['summary']}")
                if goal.get("outcome"):
                    print(f"    Outcome: {goal['outcome']}")
                print()

        if goals["archivedGoals"]:
            print(f"\n=== Archived Goals ===\n")
            for goal in goals["archivedGoals"][-3:]:  # Last 3
                print(f"[{goal['id']}] {goal['summary']}")
                if goal.get("archiveReason"):
                    print(f"    Reason: {goal['archiveReason']}")
                print()


def get_active_goals_summary(project_id: str) -> str:
    """Get a brief summary of active goals for session hooks"""
    goals = load_goals(project_id)

    if not goals["activeGoals"]:
        return ""

    lines = [f"Active goals for {project_id}:"]
    for goal in goals["activeGoals"]:
        line = f"  - {goal['summary']}"
        if goal.get("why"):
            line += f" (why: {goal['why']})"
        lines.append(line)

    return "\n".join(lines)


def get_all_active_goals() -> str:
    """Get active goals across all projects"""
    config_path = MEMORY_ROOT / 'config.json'
    if not config_path.exists():
        return ""

    config = json.loads(config_path.read_text())
    all_goals = []

    for project in config.get("projects", []):
        project_id = project["id"]
        goals = load_goals(project_id)
        if goals["activeGoals"]:
            all_goals.append(f"\n{project_id}:")
            for goal in goals["activeGoals"]:
                line = f"  [{goal['id']}] {goal['summary']}"
                all_goals.append(line)

    if not all_goals:
        return ""

    return "=== Active Goals ===" + "".join(all_goals)


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  mlx goal list <project>              # List active goals")
        print("  mlx goal list <project> --all        # Include completed/archived")
        print("  mlx goal add <project> \"summary\"     # Add new goal")
        print("  mlx goal add <project> \"summary\" --why \"reason\" --constraint \"rule\"")
        print("  mlx goal complete <project> <id>     # Mark goal complete")
        print("  mlx goal archive <project> <id>      # Archive/abandon goal")
        print("  mlx goal note <project> <id> \"note\"  # Add note to goal")
        print("  mlx goal all                         # Show all active goals")
        sys.exit(1)

    command = sys.argv[1]

    if command == "all":
        print(get_all_active_goals() or "No active goals across any projects")
        return

    if len(sys.argv) < 3:
        print("Error: project required")
        sys.exit(1)

    project_id = sys.argv[2]

    if command == "list":
        show_all = "--all" in sys.argv
        list_goals(project_id, show_all)

    elif command == "add":
        if len(sys.argv) < 4:
            print("Error: summary required")
            sys.exit(1)

        summary = sys.argv[3]
        why = ""
        constraints = []

        # Parse optional args
        i = 4
        while i < len(sys.argv):
            if sys.argv[i] == "--why" and i + 1 < len(sys.argv):
                why = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] == "--constraint" and i + 1 < len(sys.argv):
                constraints.append(sys.argv[i + 1])
                i += 2
            else:
                i += 1

        add_goal(project_id, summary, why, constraints)

    elif command == "complete":
        if len(sys.argv) < 4:
            print("Error: goal id required")
            sys.exit(1)
        goal_id = sys.argv[3]
        outcome = sys.argv[4] if len(sys.argv) > 4 else ""
        complete_goal(project_id, goal_id, outcome)

    elif command == "archive":
        if len(sys.argv) < 4:
            print("Error: goal id required")
            sys.exit(1)
        goal_id = sys.argv[3]
        reason = sys.argv[4] if len(sys.argv) > 4 else ""
        archive_goal(project_id, goal_id, reason)

    elif command == "note":
        if len(sys.argv) < 5:
            print("Error: goal id and note required")
            sys.exit(1)
        goal_id = sys.argv[3]
        note = sys.argv[4]
        update_goal(project_id, goal_id, "note", note)

    elif command == "why":
        if len(sys.argv) < 5:
            print("Error: goal id and why required")
            sys.exit(1)
        goal_id = sys.argv[3]
        why = sys.argv[4]
        update_goal(project_id, goal_id, "why", why)

    elif command == "constraint":
        if len(sys.argv) < 5:
            print("Error: goal id and constraint required")
            sys.exit(1)
        goal_id = sys.argv[3]
        constraint = sys.argv[4]
        update_goal(project_id, goal_id, "constraints", constraint)

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
