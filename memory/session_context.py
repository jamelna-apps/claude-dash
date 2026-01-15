#!/usr/bin/env python3
"""
Session Context Loader

Loads recent session context for continuity across sessions.
Called by inject-context.sh hook at session start.

Provides:
- Last session summary for current project
- Recent decisions and observations
- Ongoing work items (unfinished todos)
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timedelta

MEMORY_ROOT = Path.home() / ".claude-dash"
DIGESTS_DIR = MEMORY_ROOT / "sessions" / "digests"


def get_project_id(cwd=None):
    """Detect project from current directory."""
    cwd = Path(cwd) if cwd else Path.cwd()
    config_path = MEMORY_ROOT / "config.json"

    if not config_path.exists():
        return None

    try:
        config = json.loads(config_path.read_text())
        for project in config.get("projects", []):
            project_path = Path(project.get("path", "")).expanduser()
            if str(cwd).startswith(str(project_path)):
                return project.get("id")
    except (json.JSONDecodeError, IOError, KeyError):
        pass  # Config file unreadable or malformed

    return cwd.name.lower().replace(" ", "-")


def get_last_session_summary(project_id):
    """Get the summary from the last session for this project."""
    sessions_dir = MEMORY_ROOT / "sessions" / project_id if project_id else MEMORY_ROOT / "sessions"
    summary_file = MEMORY_ROOT / "sessions" / "summaries" / f"{project_id}.json" if project_id else None

    # Try project-specific summary first
    if summary_file and summary_file.exists():
        try:
            data = json.loads(summary_file.read_text())
            return data.get("summary", "")
        except (json.JSONDecodeError, IOError, KeyError):
            pass  # Summary file unreadable

    # Fall back to session index
    index_path = MEMORY_ROOT / "sessions" / "index.json"
    if index_path.exists():
        try:
            index = json.loads(index_path.read_text())
            sessions = index.get("sessions", [])

            # Find most recent session for this project
            for session in reversed(sessions):
                if not project_id or session.get("projectId") == project_id:
                    return session.get("summary", "")
        except (json.JSONDecodeError, IOError, KeyError):
            pass  # Index file unreadable

    return None


def get_recent_observations(project_id, limit=5):
    """Get recent observations for context."""
    obs_path = MEMORY_ROOT / "sessions" / "observations.json"

    if not obs_path.exists():
        return []

    try:
        data = json.loads(obs_path.read_text())
        observations = data.get("observations", [])

        # Filter by project if specified
        if project_id:
            observations = [o for o in observations if o.get("projectId") == project_id]

        # Get most recent, prioritizing decisions and patterns
        priority_categories = ["decision", "pattern", "gotcha"]
        prioritized = [o for o in observations if o.get("category") in priority_categories]
        others = [o for o in observations if o.get("category") not in priority_categories]

        result = prioritized[-limit:] if len(prioritized) >= limit else prioritized + others[-(limit-len(prioritized)):]
        return result[-limit:]
    except (json.JSONDecodeError, IOError, KeyError):
        return []  # Observations file unreadable


def get_recent_decisions(project_id, limit=3):
    """Get recent decisions for this project."""
    if not project_id:
        return []

    decisions_path = MEMORY_ROOT / "projects" / project_id / "decisions.json"

    if not decisions_path.exists():
        # Try global infrastructure decisions
        infra_path = MEMORY_ROOT / "global" / "infrastructure.json"
        if infra_path.exists():
            try:
                data = json.loads(infra_path.read_text())
                return data.get("decisions", [])[-limit:]
            except (json.JSONDecodeError, IOError, KeyError):
                pass  # Infrastructure file unreadable
        return []

    try:
        data = json.loads(decisions_path.read_text())
        return data.get("decisions", [])[-limit:]
    except (json.JSONDecodeError, IOError, KeyError):
        return []  # Decisions file unreadable


def get_infrastructure_context():
    """Get relevant infrastructure decisions."""
    infra_path = MEMORY_ROOT / "global" / "infrastructure.json"

    if not infra_path.exists():
        return None

    try:
        data = json.loads(infra_path.read_text())

        # Get recent decisions (last 3)
        decisions = data.get("decisions", [])[-3:]

        # Get current services
        services = data.get("services", {})

        return {
            "recent_decisions": decisions,
            "active_services": list(services.keys())
        }
    except (json.JSONDecodeError, IOError, KeyError):
        return None  # Infrastructure file unreadable


def search_digests(query, limit=3):
    """Search compacted session digests for historical context."""
    if not DIGESTS_DIR.exists():
        return []

    results = []
    query_lower = query.lower()

    for digest_path in sorted(DIGESTS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            digest = json.loads(digest_path.read_text())
            synthesis = digest.get("synthesis", "")

            # Check if query matches synthesis or files
            if query_lower in synthesis.lower():
                results.append({
                    "session": digest_path.stem,
                    "summary": synthesis[:200],
                    "files": digest.get("files", {}).get("edited", [])[:5]
                })
            elif any(query_lower in f.lower() for f in digest.get("files", {}).get("edited", [])):
                results.append({
                    "session": digest_path.stem,
                    "summary": synthesis[:150] if synthesis else "No summary",
                    "files": digest.get("files", {}).get("edited", [])[:5]
                })

            if len(results) >= limit:
                break
        except (json.JSONDecodeError, IOError, KeyError):
            continue  # Digest file unreadable

    return results


def format_session_context(project_id):
    """Format complete session context for injection."""
    lines = []

    # Last session summary
    last_summary = get_last_session_summary(project_id)
    if last_summary:
        lines.append(f"[LAST SESSION] {last_summary}")

    # Recent decisions
    decisions = get_recent_decisions(project_id)
    if decisions:
        lines.append("\n[RECENT DECISIONS]")
        for d in decisions[-3:]:
            decision_text = d.get("decision") if isinstance(d, dict) else str(d)
            lines.append(f"  • {decision_text[:100]}")

    # Recent observations (patterns, gotchas)
    observations = get_recent_observations(project_id, limit=3)
    important_obs = [o for o in observations if o.get("category") in ["pattern", "gotcha", "decision"]]
    if important_obs:
        lines.append("\n[LEARNED PATTERNS]")
        for o in important_obs[:3]:
            lines.append(f"  • [{o.get('category')}] {o.get('observation', '')[:80]}")

    # Infrastructure context (for non-project-specific work)
    if not project_id or project_id in ["projects", "documents"]:
        infra = get_infrastructure_context()
        if infra and infra.get("active_services"):
            lines.append(f"\n[ACTIVE SERVICES] {', '.join(infra['active_services'])}")

    return "\n".join(lines) if lines else None


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Load session context")
    parser.add_argument("--project", help="Project ID")
    parser.add_argument("--cwd", help="Current working directory")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    project_id = args.project or get_project_id(args.cwd)

    if args.json:
        context = {
            "project_id": project_id,
            "last_summary": get_last_session_summary(project_id),
            "recent_decisions": get_recent_decisions(project_id),
            "recent_observations": get_recent_observations(project_id),
            "infrastructure": get_infrastructure_context()
        }
        print(json.dumps(context, indent=2))
    else:
        context = format_session_context(project_id)
        if context:
            print(context)


if __name__ == "__main__":
    main()
