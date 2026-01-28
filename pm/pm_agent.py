#!/usr/bin/env python3
"""
PM Agent - Proactive Product Manager agent for Claude Code sessions.

Provides cross-project intelligence, portfolio health, and conversational
questions at session start.

Usage:
    python3 pm_agent.py <project_id> inject    # For hook injection
    python3 pm_agent.py <project_id> portfolio # Full portfolio status
    python3 pm_agent.py <project_id> ask <question>  # Answer PM question
"""

import json
import sys
from datetime import datetime
from pathlib import Path

MEMORY_ROOT = Path.home() / ".claude-dash"
PM_ROOT = MEMORY_ROOT / "pm"

# Add PM_ROOT to path for imports
sys.path.insert(0, str(PM_ROOT))

from portfolio_analyzer import (
    load_all_roadmaps,
    analyze_portfolio_health,
    find_connections,
    format_portfolio_summary
)
from question_generator import (
    generate_question,
    format_question_output,
    get_session_info
)


def load_config() -> dict:
    """Load PM agent configuration."""
    config_path = PM_ROOT / "config.json"
    try:
        with open(config_path) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def get_pm_context(current_project: str) -> str:
    """
    Main entry point for PM context injection.

    Returns formatted context for <pm-agent> tag injection.
    """
    # Load all roadmaps
    roadmaps = load_all_roadmaps()

    if not roadmaps:
        return ""

    # Analyze portfolio health
    portfolio = analyze_portfolio_health(roadmaps)

    # Find connections for current project
    connections = find_connections(current_project, portfolio)

    # Get session info
    session_info = get_session_info(current_project)
    days_since = session_info.get("days_since", 0)

    # Generate question
    question = generate_question(
        current_project,
        portfolio,
        connections,
        days_since
    )

    # Format output
    return format_question_output(question, portfolio)


def get_portfolio_status(detail: str = "full") -> str:
    """Get full portfolio status."""
    roadmaps = load_all_roadmaps()
    if not roadmaps:
        return "No project roadmaps found."

    portfolio = analyze_portfolio_health(roadmaps)
    return format_portfolio_summary(portfolio, detail)


def answer_pm_question(question: str, current_project: str = None) -> str:
    """Answer a PM-related question about projects or priorities."""
    roadmaps = load_all_roadmaps()
    portfolio = analyze_portfolio_health(roadmaps)

    question_lower = question.lower()

    # Handle common question patterns
    if any(w in question_lower for w in ["what should", "what to work", "focus", "priority", "next"]):
        # What to work on
        lines = ["Based on the portfolio analysis:"]

        needs_attention = portfolio.get("needs_attention", [])
        if needs_attention:
            lines.append("\nNeeds Attention:")
            for item in needs_attention[:3]:
                lines.append(f"  - {item['message']}")

        # Get high priority items across projects
        high_priority = []
        for pid, health in portfolio.get("projects", {}).items():
            for item in health.get("pending_high_priority", []):
                high_priority.append({
                    "project": health.get("display_name", pid),
                    "title": item["title"],
                    "status": item["status"]
                })

        if high_priority:
            lines.append("\nHigh Priority Items:")
            for item in high_priority[:5]:
                lines.append(f"  - [{item['project']}] {item['title']}")

        if current_project:
            proj_health = portfolio.get("projects", {}).get(current_project, {})
            if proj_health.get("active_items", 0) > 0:
                lines.append(f"\nCurrent project ({proj_health.get('display_name', current_project)}) has {proj_health['active_items']} active items.")

        return "\n".join(lines)

    elif any(w in question_lower for w in ["status", "health", "overview", "portfolio"]):
        return get_portfolio_status("full")

    elif any(w in question_lower for w in ["stale", "quiet", "inactive"]):
        stale = [n for n in portfolio.get("needs_attention", []) if n["type"] == "stale"]
        if stale:
            lines = ["Stale projects:"]
            for s in stale:
                lines.append(f"  - {s['message']}")
            return "\n".join(lines)
        return "No stale projects detected."

    elif any(w in question_lower for w in ["milestone", "deadline", "due", "upcoming"]):
        milestones = portfolio.get("upcoming_milestones", [])
        if milestones:
            lines = ["Upcoming milestones:"]
            for m in milestones:
                lines.append(f"  - {m['display_name']}: {m['milestone']} in {m['days_until']} days")
            return "\n".join(lines)
        return "No upcoming milestones tracked."

    elif any(w in question_lower for w in ["blocker", "blocked", "issue"]):
        blockers = [n for n in portfolio.get("needs_attention", []) if n["type"] == "blocker"]
        if blockers:
            lines = ["Current blockers:"]
            for b in blockers:
                lines.append(f"  - {b['message']}")
            return "\n".join(lines)
        return "No blockers recorded."

    elif any(w in question_lower for w in ["related", "connection", "cross-project"]):
        connections = portfolio.get("cross_project_connections", [])
        if connections:
            lines = ["Cross-project connections:"]
            for c in connections:
                lines.append(f"  - {c['from_name']} <-> {c['to_name']}")
            return "\n".join(lines)
        return "No cross-project connections found."

    else:
        # Default: portfolio summary
        return get_portfolio_status("summary")


def main():
    """CLI interface for PM Agent."""
    if len(sys.argv) < 2:
        print("Usage: pm_agent.py <project_id> [action] [args...]")
        print("Actions: inject, portfolio, ask")
        sys.exit(1)

    project_id = sys.argv[1]
    action = sys.argv[2] if len(sys.argv) > 2 else "inject"

    if action == "inject":
        # For hook injection - returns formatted context
        result = get_pm_context(project_id)
        if result:
            print(result)

    elif action == "portfolio":
        detail = sys.argv[3] if len(sys.argv) > 3 else "full"
        print(get_portfolio_status(detail))

    elif action == "ask":
        if len(sys.argv) < 4:
            print("Usage: pm_agent.py <project_id> ask <question>")
            sys.exit(1)
        question = " ".join(sys.argv[3:])
        print(answer_pm_question(question, project_id))

    else:
        print(f"Unknown action: {action}")
        sys.exit(1)


if __name__ == "__main__":
    main()
