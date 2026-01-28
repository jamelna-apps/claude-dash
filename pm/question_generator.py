#!/usr/bin/env python3
"""
Question Generator - Generates conversational PM questions for session start.
"""

import json
import random
from datetime import datetime
from pathlib import Path
from typing import Any

MEMORY_ROOT = Path.home() / ".claude-dash"
PM_ROOT = MEMORY_ROOT / "pm"


def load_config() -> dict:
    """Load PM agent configuration."""
    config_path = PM_ROOT / "config.json"
    try:
        with open(config_path) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {"preferences": {}}


def get_session_info(project_id: str) -> dict:
    """Get information about the last session for this project."""
    sessions_dir = MEMORY_ROOT / "sessions"
    session_files = list(sessions_dir.glob(f"{project_id}_*.json")) if sessions_dir.exists() else []

    if not session_files:
        return {"days_since": 999, "last_topic": None}

    # Get most recent session file
    latest = max(session_files, key=lambda p: p.stat().st_mtime)
    try:
        with open(latest) as f:
            data = json.load(f)
            return {
                "days_since": (datetime.now() - datetime.fromtimestamp(latest.stat().st_mtime)).days,
                "last_topic": data.get("topic"),
                "observations": data.get("observations", [])
            }
    except (json.JSONDecodeError, IOError):
        return {"days_since": 0, "last_topic": None}


def generate_question(
    current_project: str,
    portfolio: dict,
    connections: list,
    days_since_session: int = 0
) -> dict:
    """Generate a conversational PM question based on context."""

    project_health = portfolio.get("projects", {}).get(current_project, {})
    needs_attention = portfolio.get("needs_attention", [])
    upcoming_milestones = portfolio.get("upcoming_milestones", [])

    question = None
    context = None
    priority = "normal"

    # Priority 1: Critical blockers
    blockers = [n for n in needs_attention if n["type"] == "blocker" and n["project"] == current_project]
    if blockers:
        blocker = blockers[0]
        question = f"There's a blocker on {blocker['display_name']}: {blocker['message'].split(': ', 1)[-1]}. Want to tackle that first?"
        context = "blocker"
        priority = "high"

    # Priority 2: Milestone approaching
    elif upcoming_milestones:
        project_milestones = [m for m in upcoming_milestones if m["project"] == current_project]
        if project_milestones:
            m = project_milestones[0]
            if m["days_until"] <= 7:
                question = f"{m['milestone']} is coming up in {m['days_until']} days! How's that tracking?"
                priority = "high"
            else:
                question = f"{m['milestone']} is {m['days_until']} days out. Want to review progress?"
            context = "milestone"
        else:
            # Milestone on another project
            m = upcoming_milestones[0]
            question = f"{m['display_name']} has {m['milestone']} in {m['days_until']} days. Should we focus there instead?"
            context = "cross_project_milestone"

    # Priority 3: High-priority sprint items
    elif project_health.get("pending_high_priority"):
        items = project_health["pending_high_priority"]
        if len(items) == 1:
            item = items[0]
            question = f"You've got a high-priority item: \"{item['title']}\". Ready to work on that?"
        else:
            question = f"There are {len(items)} high-priority items pending. Want to start with \"{items[0]['title']}\"?"
        context = "high_priority"

    # Priority 4: Cross-project opportunities
    elif connections:
        # Check if connected projects have relevant work
        for conn in connections:
            conn_health = conn["health"]
            if conn_health.get("status") == "active":
                # Look for shared features
                question = f"{conn['display_name']} is related to this project. Any cross-cutting work today?"
                context = "cross_project"
                break

    # Priority 5: Stale project detection
    stale_projects = [n for n in needs_attention if n["type"] == "stale"]
    if not question and stale_projects:
        if any(s["project"] == current_project for s in stale_projects):
            days = project_health.get("days_since_update", 0)
            question = f"It's been {days} days since this project was updated. Picking up where we left off?"
            context = "stale_current"
        else:
            stale = stale_projects[0]
            question = f"{stale['display_name']} has been quiet for {stale['days']} days. Intentional pause or should we switch?"
            context = "stale_other"

    # Priority 6: Regular active items
    if not question and project_health.get("active_items", 0) > 0:
        count = project_health["active_items"]
        if count == 1:
            question = f"You have 1 active sprint item. Ready to continue?"
        else:
            question = f"You have {count} sprint items in progress. What's the focus today?"
        context = "active_work"

    # Priority 7: Portfolio overview (fallback)
    if not question:
        summary = portfolio.get("summary", {})
        active = summary.get("active", 0)
        attention = summary.get("attention_items", 0)

        if attention > 0:
            question = f"Portfolio has {active} active projects, {attention} items need attention. Where should we focus?"
        else:
            question = f"Portfolio looks healthy - {active} active projects. What are we building today?"
        context = "portfolio_overview"

    return {
        "question": question,
        "context": context,
        "priority": priority,
        "project": current_project,
        "display_name": project_health.get("display_name", current_project)
    }


def generate_portfolio_greeting(portfolio: dict, current_project: str) -> str:
    """Generate a brief portfolio status greeting."""
    summary = portfolio.get("summary", {})
    projects = portfolio.get("projects", {})

    active_names = [p["display_name"] for pid, p in projects.items() if p.get("status") == "active"]
    paused_names = [p["display_name"] for pid, p in projects.items() if p.get("status") in ["paused", "on-hold"]]

    lines = []

    # Brief status
    if len(active_names) <= 4:
        lines.append(f"Active: {', '.join(active_names)}")
    else:
        lines.append(f"Active: {len(active_names)} projects")

    if paused_names:
        if len(paused_names) <= 2:
            lines.append(f"Paused: {', '.join(paused_names)}")
        else:
            lines.append(f"Paused: {len(paused_names)} projects")

    # Current project context
    current = projects.get(current_project, {})
    if current:
        lines.append(f"Current: {current.get('display_name', current_project)} v{current.get('version', '?')} ({current.get('phase', 'unknown')})")

    return "\n".join(lines)


def format_question_output(question: dict, portfolio: dict) -> str:
    """Format the question with portfolio context for injection."""
    lines = []

    # Brief portfolio status
    greeting = generate_portfolio_greeting(portfolio, question["project"])
    lines.append(greeting)

    # The question
    lines.append("")
    lines.append(f"[PM] {question['question']}")

    # Add any urgent items
    needs_attention = portfolio.get("needs_attention", [])
    urgent = [n for n in needs_attention if n["type"] == "blocker" or
              (n["type"] == "milestone" and n.get("days_until", 999) <= 7)]

    if urgent and question["context"] not in ["blocker", "milestone"]:
        lines.append("")
        lines.append("Urgent:")
        for item in urgent[:2]:
            lines.append(f"  - {item['message']}")

    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(PM_ROOT))
    from portfolio_analyzer import load_all_roadmaps, analyze_portfolio_health, find_connections

    project_id = sys.argv[1] if len(sys.argv) > 1 else "gyst"

    roadmaps = load_all_roadmaps()
    portfolio = analyze_portfolio_health(roadmaps)
    connections = find_connections(project_id, portfolio)

    question = generate_question(project_id, portfolio, connections)
    output = format_question_output(question, portfolio)
    print(output)
