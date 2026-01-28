"""
Injection Adapters for inject_all_context.py

These adapter functions bridge the expected API (what inject_all_context.py calls)
with the actual implementations (what the modules export).

Created to fix function name mismatches that were causing silent failures.
"""

import sys
from pathlib import Path

MEMORY_ROOT = Path.home() / ".claude-dash"

# Add paths for imports
sys.path.insert(0, str(MEMORY_ROOT / "learning"))
sys.path.insert(0, str(MEMORY_ROOT / "memory"))


def get_session_context(project_id: str) -> str:
    """
    Adapter: inject_all_context.py expects get_session_context()
    Actual: session_context.py has format_session_context()
    """
    try:
        from session_context import format_session_context
        return format_session_context(project_id)
    except Exception:
        return ""


def check_health() -> str:
    """
    Adapter: inject_all_context.py expects check_health()
    Actual: session_health.py has check_gateway(), check_watcher(), etc.
    """
    try:
        from session_health import check_gateway, check_watcher, check_ollama, check_database

        issues = []

        gateway = check_gateway()
        if not gateway.get('running'):
            issues.append("Gateway not running")

        watcher = check_watcher()
        if not watcher.get('running'):
            issues.append("Watcher not running")

        ollama = check_ollama()
        if not ollama.get('available'):
            issues.append("Ollama not available")

        db = check_database()
        if not db.get('accessible'):
            issues.append("Database not accessible")

        if issues:
            return "System issues: " + ", ".join(issues)
        return ""
    except Exception:
        return ""


def get_changes_summary(project_path: str, project_id: str) -> str:
    """
    Adapter: inject_all_context.py expects get_changes_summary()
    Actual: git_awareness.py has get_commits_since(), get_files_changed_since()
    """
    try:
        from git_awareness import get_commits_since, get_files_changed_since, get_last_session_time

        last_time = get_last_session_time(project_id)
        if not last_time:
            return ""

        commits = get_commits_since(project_path, last_time)
        files = get_files_changed_since(project_path, last_time)

        if not commits and not files:
            return ""

        parts = []
        if commits:
            parts.append(f"Commits since last session: {len(commits)}")
            for c in commits[:3]:  # Show first 3
                parts.append(f"  - {c.get('message', 'No message')[:50]}")

        if files:
            parts.append(f"Files changed: {len(files)}")
            for f in files[:5]:  # Show first 5
                parts.append(f"  - {f}")

        return "\n".join(parts)
    except Exception:
        return ""


def get_high_confidence_preferences() -> str:
    """
    Adapter: inject_all_context.py expects get_high_confidence_preferences()
    Actual: preference_learner.py has load_preferences(), inferred preferences
    """
    try:
        from preference_learner import load_preferences

        prefs = load_preferences()
        if not prefs:
            return ""

        # Format high-confidence preferences
        inferred = prefs.get('inferred', {})
        if not inferred:
            return ""

        high_conf = []
        for category, items in inferred.items():
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict) and item.get('confidence', 0) >= 0.7:
                        high_conf.append(f"- {category}: {item.get('value', item)}")
                    elif isinstance(item, str):
                        high_conf.append(f"- {category}: {item}")

        if not high_conf:
            return ""

        return "Learned preferences:\n" + "\n".join(high_conf[:5])
    except Exception:
        return ""


def get_weak_areas() -> str:
    """
    Adapter: inject_all_context.py expects get_weak_areas()
    Actual: confidence_calibration.py has get_calibration()
    """
    try:
        from confidence_calibration import get_calibration

        cal = get_calibration()
        if not cal:
            return ""

        # Find domains with low accuracy
        weak = []
        for domain, stats in cal.get('domains', {}).items():
            accuracy = stats.get('accuracy', 1.0)
            if accuracy < 0.7 and stats.get('total', 0) >= 3:
                weak.append(f"- {domain}: {accuracy:.0%} accuracy ({stats.get('total')} predictions)")

        if not weak:
            return ""

        return "Areas needing extra care:\n" + "\n".join(weak)
    except Exception:
        return ""


def get_semantic_context(prompt: str, project_id: str) -> str:
    """
    Adapter: inject_all_context.py expects get_semantic_context()
    Actual: semantic_triggers.py has detect_topics(), search_decisions(), etc.
    """
    try:
        from semantic_triggers import detect_topics, search_decisions

        topics = detect_topics(prompt)
        if not topics:
            return ""

        parts = []

        # Search decisions for these topics
        for topic in topics[:2]:  # Limit to 2 topics
            decisions = search_decisions(topic, project_id)
            if decisions:
                parts.append(f"[RELEVANT MEMORY for: {topic}]")
                parts.append("Past decisions:")
                for d in decisions[:2]:  # Limit results
                    if isinstance(d, dict):
                        parts.append(f"  • {d.get('summary', str(d))[:100]}")
                    else:
                        parts.append(f"  • {str(d)[:100]}")

        if not parts:
            return ""

        return "\n".join(parts)
    except Exception:
        return ""
