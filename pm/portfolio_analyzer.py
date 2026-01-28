#!/usr/bin/env python3
"""
Portfolio Analyzer - Cross-project health analysis for PM Agent.
"""

import json
import os
from datetime import datetime, timedelta
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
        return {"active_projects": [], "preferences": {}}


def load_all_roadmaps() -> dict[str, dict]:
    """Load roadmaps for all registered projects."""
    config = load_config()
    roadmaps = {}

    for project_id in config.get("active_projects", []):
        roadmap_path = MEMORY_ROOT / "projects" / project_id / "roadmap.json"
        if roadmap_path.exists():
            try:
                with open(roadmap_path) as f:
                    roadmaps[project_id] = json.load(f)
            except (json.JSONDecodeError, IOError):
                pass

    return roadmaps


def get_project_display_name(project_id: str, roadmap: dict) -> str:
    """Get human-readable project name."""
    return roadmap.get("displayName", project_id.upper())


def analyze_project_health(project_id: str, roadmap: dict) -> dict:
    """Analyze health of a single project."""
    health = {
        "project_id": project_id,
        "display_name": get_project_display_name(project_id, roadmap),
        "status": "unknown",
        "version": roadmap.get("currentVersion", "?"),
        "days_since_update": 999,
        "active_items": 0,
        "blockers": [],
        "pending_high_priority": [],
        "milestones": [],
        "related_projects": []
    }

    # Calculate days since last update
    last_updated = roadmap.get("lastUpdated")
    if last_updated:
        try:
            if "T" in last_updated:
                update_date = datetime.fromisoformat(last_updated.replace("Z", "+00:00"))
            else:
                update_date = datetime.strptime(last_updated, "%Y-%m-%d")
            health["days_since_update"] = (datetime.now(update_date.tzinfo if update_date.tzinfo else None) - update_date).days
        except (ValueError, TypeError):
            pass

    # Get summary status
    summary = roadmap.get("summary", {})
    health["status"] = summary.get("status", "unknown")
    health["phase"] = summary.get("phase", "unknown")
    health["description"] = summary.get("description", "")

    # Count active sprint items
    sprint = roadmap.get("currentSprint", {})
    sprint_items = sprint.get("items", [])
    health["active_items"] = len([i for i in sprint_items if i.get("status") in ["pending", "in_progress"]])

    # Collect high-priority pending items
    for item in sprint_items:
        if item.get("priority") == "high" and item.get("status") in ["pending", "in_progress"]:
            health["pending_high_priority"].append({
                "id": item.get("id"),
                "title": item.get("title"),
                "status": item.get("status")
            })

    # Check backlog for high priority items
    backlog = roadmap.get("backlog", {})
    for timeframe in ["shortTerm", "mediumTerm"]:
        items = backlog.get(timeframe, {}).get("items", [])
        for item in items:
            if item.get("priority") == "high" and item.get("status") in ["not_started", "in_progress"]:
                health["pending_high_priority"].append({
                    "id": item.get("id"),
                    "title": item.get("title"),
                    "status": item.get("status"),
                    "timeframe": timeframe
                })
            # Collect related projects
            if item.get("relatedProject"):
                health["related_projects"].append(item.get("relatedProject"))

    # Get blockers
    blockers = roadmap.get("blockers", [])
    for blocker in blockers:
        if blocker.get("severity") in ["critical", "major"]:
            health["blockers"].append({
                "title": blocker.get("title"),
                "severity": blocker.get("severity")
            })

    # Get milestones with dates
    milestones = roadmap.get("milestones", [])
    for milestone in milestones:
        target_date = milestone.get("targetDate")
        if target_date:
            try:
                target = datetime.strptime(target_date, "%Y-%m-%d")
                days_until = (target - datetime.now()).days
                if days_until >= 0:  # Only future milestones
                    health["milestones"].append({
                        "name": milestone.get("title") or milestone.get("name", "Unnamed"),
                        "days_until": days_until,
                        "status": milestone.get("status", "upcoming")
                    })
            except ValueError:
                pass

    return health


def analyze_portfolio_health(roadmaps: dict[str, dict]) -> dict:
    """Analyze health across all projects."""
    config = load_config()
    preferences = config.get("preferences", {})
    stale_threshold = preferences.get("stale_threshold_days", 7)
    milestone_warning = preferences.get("milestone_warning_days", 30)

    portfolio = {
        "total_projects": len(roadmaps),
        "active_count": 0,
        "paused_count": 0,
        "stale_count": 0,
        "projects": {},
        "needs_attention": [],
        "upcoming_milestones": [],
        "cross_project_connections": [],
        "summary": {}
    }

    for project_id, roadmap in roadmaps.items():
        health = analyze_project_health(project_id, roadmap)
        portfolio["projects"][project_id] = health

        # Count by status
        if health["status"] == "active":
            portfolio["active_count"] += 1
        elif health["status"] in ["paused", "on-hold"]:
            portfolio["paused_count"] += 1

        # Check for stale projects
        if health["days_since_update"] >= stale_threshold and health["status"] == "active":
            portfolio["stale_count"] += 1
            portfolio["needs_attention"].append({
                "type": "stale",
                "project": project_id,
                "display_name": health["display_name"],
                "days": health["days_since_update"],
                "message": f"{health['display_name']} has been quiet for {health['days_since_update']} days"
            })

        # Check for blockers
        for blocker in health["blockers"]:
            portfolio["needs_attention"].append({
                "type": "blocker",
                "project": project_id,
                "display_name": health["display_name"],
                "severity": blocker["severity"],
                "message": f"{health['display_name']}: {blocker['title']}"
            })

        # Check for approaching milestones
        for milestone in health["milestones"]:
            if milestone["days_until"] <= milestone_warning:
                portfolio["upcoming_milestones"].append({
                    "project": project_id,
                    "display_name": health["display_name"],
                    "milestone": milestone["name"],
                    "days_until": milestone["days_until"]
                })
                if milestone["days_until"] <= 14:  # Urgent
                    portfolio["needs_attention"].append({
                        "type": "milestone",
                        "project": project_id,
                        "display_name": health["display_name"],
                        "message": f"{health['display_name']}: {milestone['name']} in {milestone['days_until']} days"
                    })

    # Build cross-project connections
    for project_id, health in portfolio["projects"].items():
        for related in health.get("related_projects", []):
            if related in portfolio["projects"]:
                connection = {
                    "from": project_id,
                    "to": related,
                    "from_name": health["display_name"],
                    "to_name": portfolio["projects"][related]["display_name"]
                }
                # Avoid duplicates
                existing = [c for c in portfolio["cross_project_connections"]
                           if (c["from"] == connection["from"] and c["to"] == connection["to"]) or
                              (c["from"] == connection["to"] and c["to"] == connection["from"])]
                if not existing:
                    portfolio["cross_project_connections"].append(connection)

    # Sort needs_attention by priority (blockers first, then milestones, then stale)
    priority_order = {"blocker": 0, "milestone": 1, "stale": 2}
    portfolio["needs_attention"].sort(key=lambda x: priority_order.get(x["type"], 3))

    # Sort upcoming milestones by date
    portfolio["upcoming_milestones"].sort(key=lambda x: x["days_until"])

    # Create summary
    portfolio["summary"] = {
        "active": portfolio["active_count"],
        "paused": portfolio["paused_count"],
        "stale": portfolio["stale_count"],
        "attention_items": len(portfolio["needs_attention"]),
        "upcoming_milestones": len(portfolio["upcoming_milestones"])
    }

    return portfolio


def find_connections(current_project: str, portfolio: dict) -> list:
    """Find connections between current project and others."""
    connections = []

    for conn in portfolio.get("cross_project_connections", []):
        if conn["from"] == current_project or conn["to"] == current_project:
            other_project = conn["to"] if conn["from"] == current_project else conn["from"]
            other_name = conn["to_name"] if conn["from"] == current_project else conn["from_name"]
            connections.append({
                "project_id": other_project,
                "display_name": other_name,
                "health": portfolio["projects"].get(other_project, {})
            })

    return connections


def format_portfolio_summary(portfolio: dict, detail: str = "summary") -> str:
    """Format portfolio health for display."""
    lines = []
    summary = portfolio["summary"]

    if detail == "summary":
        lines.append(f"Portfolio: {summary['active']} active, {summary['paused']} paused")
        if summary["stale"] > 0:
            lines.append(f"  Stale: {summary['stale']} projects need attention")
        if summary["upcoming_milestones"] > 0:
            lines.append(f"  Milestones: {summary['upcoming_milestones']} upcoming")
        return "\n".join(lines)

    # Detailed format
    lines.append("=== PORTFOLIO HEALTH ===")
    lines.append(f"Active: {summary['active']} | Paused: {summary['paused']} | Needs Attention: {summary['attention_items']}")

    if portfolio["needs_attention"]:
        lines.append("\n--- Needs Attention ---")
        for item in portfolio["needs_attention"][:5]:
            icon = "[!]" if item["type"] == "blocker" else "[*]" if item["type"] == "milestone" else "[?]"
            lines.append(f"{icon} {item['message']}")

    if portfolio["upcoming_milestones"]:
        lines.append("\n--- Upcoming Milestones ---")
        for m in portfolio["upcoming_milestones"][:3]:
            lines.append(f"  {m['display_name']}: {m['milestone']} ({m['days_until']} days)")

    lines.append("\n--- Projects ---")
    for project_id, health in portfolio["projects"].items():
        status_icon = "*" if health["status"] == "active" else "-" if health["status"] == "paused" else "?"
        lines.append(f"[{status_icon}] {health['display_name']} v{health['version']} ({health['status']})")
        if health["active_items"] > 0:
            lines.append(f"    {health['active_items']} active items")

    return "\n".join(lines)


if __name__ == "__main__":
    import sys

    roadmaps = load_all_roadmaps()
    portfolio = analyze_portfolio_health(roadmaps)

    detail = sys.argv[1] if len(sys.argv) > 1 else "full"
    print(format_portfolio_summary(portfolio, detail))
