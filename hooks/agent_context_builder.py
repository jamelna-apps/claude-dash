#!/usr/bin/env python3
"""
Agent Context Builder - Build context for Task tool sub-agents

Provides relevant context when spawning sub-agents via the Task tool:
- Planning agents get: recent decisions, architecture notes
- Implementation agents get: corrections, patterns, preferences
- Exploration agents get: lightweight context only

Usage:
    python3 agent_context_builder.py <project_id> <task_type>

Task types: plan, implement, explore, debug
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

MEMORY_ROOT = Path.home() / ".claude-dash"


def get_recent_decisions(project_id: str, limit: int = 5) -> List[Dict]:
    """Get recent decisions for planning context."""
    decisions_path = MEMORY_ROOT / "projects" / project_id / "decisions.json"

    if not decisions_path.exists():
        # Try global infrastructure decisions
        infra_path = MEMORY_ROOT / "global" / "infrastructure.json"
        if infra_path.exists():
            try:
                data = json.loads(infra_path.read_text())
                return data.get("decisions", [])[-limit:]
            except (json.JSONDecodeError, IOError):
                pass
        return []

    try:
        data = json.loads(decisions_path.read_text())
        return data.get("decisions", [])[-limit:]
    except (json.JSONDecodeError, IOError):
        return []


def get_correction_patterns(project_id: str) -> List[Dict]:
    """Get learned correction patterns for implementation context."""
    patterns_file = MEMORY_ROOT / "learning" / "learned_patterns.json"

    if not patterns_file.exists():
        return []

    try:
        data = json.loads(patterns_file.read_text())
        patterns = []

        # Global patterns (high priority)
        for p in data.get("patterns", []):
            if p.get("priority") == "high":
                patterns.append(p)

        # Project-specific patterns
        project_patterns = data.get("project_patterns", {}).get(project_id, [])
        for p in project_patterns:
            if p.get("priority") == "high":
                patterns.append(p)

        return patterns
    except (json.JSONDecodeError, IOError):
        return []


def get_preferences(project_id: str) -> Dict:
    """Get coding preferences for implementation context."""
    # Try project-specific first
    prefs_path = MEMORY_ROOT / "projects" / project_id / "preferences.json"

    if prefs_path.exists():
        try:
            return json.loads(prefs_path.read_text())
        except (json.JSONDecodeError, IOError):
            pass

    # Fall back to global
    global_prefs = MEMORY_ROOT / "global" / "preferences.json"
    if global_prefs.exists():
        try:
            return json.loads(global_prefs.read_text())
        except (json.JSONDecodeError, IOError):
            pass

    return {}


def build_planning_context(project_id: str) -> str:
    """Build context for planning sub-agents."""
    lines = []

    # Recent decisions
    decisions = get_recent_decisions(project_id)
    if decisions:
        lines.append("## Recent Decisions")
        for d in decisions:
            if isinstance(d, dict):
                decision_text = d.get("decision", str(d))
            else:
                decision_text = str(d)
            lines.append(f"- {decision_text[:150]}")
        lines.append("")

    # Key preferences (for pattern consistency)
    prefs = get_preferences(project_id)
    if prefs.get("patterns") or prefs.get("conventions"):
        lines.append("## Code Patterns")
        for p in prefs.get("patterns", [])[:3]:
            lines.append(f"- {p}")
        for c in prefs.get("conventions", [])[:3]:
            lines.append(f"- {c}")
        lines.append("")

    return "\n".join(lines) if lines else ""


def build_implementation_context(project_id: str) -> str:
    """Build context for implementation sub-agents."""
    lines = []

    # Correction patterns (critical warnings)
    corrections = get_correction_patterns(project_id)
    if corrections:
        lines.append("## IMPORTANT: Learned Corrections")
        for c in corrections:
            lines.append(f"- {c.get('pattern', '')}")
        lines.append("")

    # Preferences
    prefs = get_preferences(project_id)

    if prefs.get("use"):
        lines.append("## Preferred Libraries/Patterns")
        for item in prefs.get("use", [])[:5]:
            if isinstance(item, dict):
                lines.append(f"- Use {item.get('use', '')} (not {', '.join(item.get('notThese', []))})")
            else:
                lines.append(f"- {item}")
        lines.append("")

    if prefs.get("avoid"):
        lines.append("## Avoid")
        for item in prefs.get("avoid", [])[:5]:
            lines.append(f"- {item}")
        lines.append("")

    return "\n".join(lines) if lines else ""


def build_exploration_context(project_id: str) -> str:
    """Build lightweight context for exploration sub-agents."""
    # Exploration agents need minimal context - just project info
    config_path = MEMORY_ROOT / "config.json"

    if not config_path.exists():
        return ""

    try:
        config = json.loads(config_path.read_text())
        for project in config.get("projects", []):
            if project.get("id") == project_id:
                return f"Project: {project.get('name', project_id)}\nType: {project.get('type', 'unknown')}"
    except (json.JSONDecodeError, IOError):
        pass

    return ""


def build_debug_context(project_id: str) -> str:
    """Build context for debugging sub-agents."""
    lines = []

    # All correction patterns (not just high priority)
    patterns_file = MEMORY_ROOT / "learning" / "learned_patterns.json"
    if patterns_file.exists():
        try:
            data = json.loads(patterns_file.read_text())
            all_patterns = data.get("patterns", [])
            project_patterns = data.get("project_patterns", {}).get(project_id, [])

            if all_patterns or project_patterns:
                lines.append("## Known Gotchas & Patterns")
                for p in (all_patterns + project_patterns)[:8]:
                    lines.append(f"- {p.get('pattern', '')}")
                lines.append("")
        except (json.JSONDecodeError, IOError):
            pass

    # Recent decisions (may contain workarounds)
    decisions = get_recent_decisions(project_id, limit=3)
    if decisions:
        lines.append("## Recent Decisions/Workarounds")
        for d in decisions:
            if isinstance(d, dict):
                decision_text = d.get("decision", str(d))
            else:
                decision_text = str(d)
            lines.append(f"- {decision_text[:150]}")
        lines.append("")

    return "\n".join(lines) if lines else ""


def build_context(project_id: str, task_type: str) -> str:
    """Build context for a sub-agent based on task type."""
    if task_type == "plan":
        return build_planning_context(project_id)
    elif task_type == "implement":
        return build_implementation_context(project_id)
    elif task_type == "explore":
        return build_exploration_context(project_id)
    elif task_type == "debug":
        return build_debug_context(project_id)
    else:
        # Default to implementation context
        return build_implementation_context(project_id)


def main():
    """CLI interface."""
    if len(sys.argv) < 3:
        print("Usage: python3 agent_context_builder.py <project_id> <task_type>")
        print("")
        print("Task types: plan, implement, explore, debug")
        print("")
        print("Examples:")
        print("  python3 agent_context_builder.py gyst implement")
        print("  python3 agent_context_builder.py coachdesk plan")
        sys.exit(1)

    project_id = sys.argv[1]
    task_type = sys.argv[2]

    context = build_context(project_id, task_type)

    if context:
        print(context)
    else:
        print(f"# No context available for {project_id}/{task_type}")


if __name__ == "__main__":
    main()
