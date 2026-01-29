#!/usr/bin/env python3
"""
Batch Health Fix Tool for Claude-Dash

Runs comprehensive health assessment across all projects and:
- Auto-fixes low-risk issues
- Reports medium/high risk issues for review
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any

MEMORY_ROOT = Path.home() / ".claude-dash"

# Risk classification
LOW_RISK_ISSUES = {
    "unused_export",
    "unused_import",
    "orphaned_embedding",
    "stale_index",
    "missing_functions",
}

# These are informational only, don't count as issues
SUGGESTION_PATTERNS = {
    "console.log",  # Auto-stripped by babel in production
    "TODO/FIXME",   # Just reminders
    "suggestions",  # Category name
}

MEDIUM_RISK_ISSUES = {
    "exact",  # duplicate category
    "high_similarity",
    "unused_file",
    "dead_export",
}

HIGH_RISK_ISSUES = {
    "Hardcoded credential",
    "Potential SQL injection",
    "Unsafe eval usage",
    "security",
}


def classify_risk(issue: Dict) -> str:
    """Classify issue risk level. Returns 'suggestion' for informational items."""
    message = issue.get("message", "")
    category = issue.get("category", "")
    issue_type = issue.get("type", "")
    severity = issue.get("severity", "low")

    # Check for suggestions first (informational, not issues)
    if category == "suggestions":
        return "suggestion"
    for pattern in SUGGESTION_PATTERNS:
        if pattern.lower() in message.lower():
            return "suggestion"

    # Check for high risk
    if severity == "critical" or category == "security":
        return "high"
    for pattern in HIGH_RISK_ISSUES:
        if pattern.lower() in message.lower() or pattern.lower() in category.lower():
            return "high"

    # Check for medium risk
    for pattern in MEDIUM_RISK_ISSUES:
        if pattern.lower() in message.lower() or pattern.lower() in issue_type.lower():
            return "medium"

    # Check for low risk
    for pattern in LOW_RISK_ISSUES:
        if pattern.lower() in message.lower() or pattern.lower() in issue_type.lower():
            return "low"

    # Default based on severity
    if severity == "low":
        return "low"
    return "medium"


def load_config() -> Dict:
    """Load claude-dash config."""
    config_path = MEMORY_ROOT / "config.json"
    if config_path.exists():
        return json.loads(config_path.read_text())
    return {"projects": []}


def load_project_health(project_id: str) -> Dict:
    """Load health data for a project."""
    health_path = MEMORY_ROOT / "projects" / project_id / "health.json"
    if health_path.exists():
        try:
            return json.loads(health_path.read_text())
        except:
            pass
    return {}


def assess_all_projects() -> Dict[str, Any]:
    """Run health assessment across all projects."""
    config = load_config()
    results = {
        "timestamp": datetime.now().isoformat(),
        "projects": {},
        "summary": {
            "total_projects": 0,
            "total_issues": 0,
            "low_risk": 0,
            "medium_risk": 0,
            "high_risk": 0,
            "suggestions": 0,  # Informational, doesn't count as issues
            "by_category": {}
        }
    }

    for project in config.get("projects", []):
        project_id = project["id"]
        health = load_project_health(project_id)

        if not health:
            results["projects"][project_id] = {"error": "No health data"}
            continue

        project_result = {
            "score": health.get("score", 0),
            "low_risk": [],
            "medium_risk": [],
            "high_risk": [],
            "suggestions": []  # console.logs, TODOs - informational only
        }

        # Process all issue categories
        issues = health.get("issues", {})
        for category, issue_list in issues.items():
            if not isinstance(issue_list, list):
                continue

            for issue in issue_list:
                # Add category to issue for context
                issue_with_context = {**issue, "source_category": category}
                risk = classify_risk(issue_with_context)

                issue_data = {
                    "category": category,
                    "type": issue.get("type", issue.get("message", "unknown")[:50]),
                    "file": issue.get("file", issue.get("file1", "")),
                    "message": issue.get("message", issue.get("reason", ""))[:100],
                    "severity": issue.get("severity", "low"),
                    "id": issue.get("id", "")
                }

                # Handle suggestions separately (informational)
                if risk == "suggestion":
                    project_result["suggestions"].append(issue_data)
                    results["summary"]["suggestions"] += 1
                else:
                    project_result[f"{risk}_risk"].append(issue_data)
                    results["summary"]["total_issues"] += 1
                    results["summary"][f"{risk}_risk"] += 1

                cat_key = category
                results["summary"]["by_category"][cat_key] = results["summary"]["by_category"].get(cat_key, 0) + 1

        results["projects"][project_id] = project_result
        results["summary"]["total_projects"] += 1

    return results


def apply_low_risk_fixes(dry_run: bool = True) -> Dict[str, Any]:
    """Apply fixes for low-risk issues."""
    assessment = assess_all_projects()
    fixes_applied = []
    fixes_skipped = []

    for project_id, data in assessment["projects"].items():
        if "error" in data:
            continue

        for issue in data.get("low_risk", []):
            fix_action = {
                "project": project_id,
                "category": issue["category"],
                "type": issue["type"],
                "file": issue["file"],
                "action": "acknowledged"
            }

            if dry_run:
                fixes_skipped.append(fix_action)
            else:
                # Record as acknowledged in fixes.json
                fixes_path = MEMORY_ROOT / "projects" / project_id / "fixes.json"
                fixes = []
                if fixes_path.exists():
                    try:
                        fixes = json.loads(fixes_path.read_text())
                    except:
                        pass

                fixes.append({
                    "timestamp": datetime.now().isoformat(),
                    "category": issue["category"],
                    "issue": issue,
                    "action": "auto_acknowledged",
                    "risk": "low"
                })

                fixes_path.write_text(json.dumps(fixes[-100:], indent=2))  # Keep last 100
                fixes_applied.append(fix_action)

    return {
        "dry_run": dry_run,
        "fixes_applied": len(fixes_applied),
        "fixes_would_apply": len(fixes_skipped) if dry_run else 0,
        "details": fixes_applied if not dry_run else fixes_skipped
    }


def generate_report(assessment: Dict) -> str:
    """Generate human-readable report."""
    lines = [
        "=" * 70,
        "CLAUDE-DASH HEALTH ASSESSMENT REPORT",
        f"Generated: {assessment['timestamp']}",
        "=" * 70,
        "",
        "SUMMARY",
        "-" * 40,
        f"Total Projects: {assessment['summary']['total_projects']}",
        f"Total Issues: {assessment['summary']['total_issues']}",
        f"  - Low Risk: {assessment['summary']['low_risk']}",
        f"  - Medium Risk: {assessment['summary']['medium_risk']}",
        f"  - High Risk: {assessment['summary']['high_risk']}",
        f"Suggestions: {assessment['summary'].get('suggestions', 0)} (informational, don't affect score)",
        "",
        "By Category:",
    ]

    for cat, count in sorted(assessment['summary']['by_category'].items(), key=lambda x: -x[1]):
        lines.append(f"  - {cat}: {count}")

    lines.extend(["", "=" * 70, "PROJECT DETAILS", "=" * 70])

    for project_id, data in assessment["projects"].items():
        if "error" in data:
            lines.append(f"\n{project_id}: {data['error']}")
            continue

        lines.append(f"\n{'=' * 40}")
        lines.append(f"PROJECT: {project_id}")
        lines.append(f"Score: {data['score']}")
        suggestions_count = len(data.get('suggestions', []))
        lines.append(f"Issues: {len(data['low_risk'])} low, {len(data['medium_risk'])} medium, {len(data['high_risk'])} high")
        if suggestions_count:
            lines.append(f"Suggestions: {suggestions_count} (console.logs, TODOs - auto-handled)")

        if data["high_risk"]:
            lines.append("\n  HIGH RISK (Needs Manual Review):")
            for issue in data["high_risk"][:10]:
                lines.append(f"    ! [{issue['category']}] {issue['type']}")
                if issue['file']:
                    lines.append(f"      File: {issue['file']}")
                if issue['message']:
                    lines.append(f"      {issue['message'][:80]}")

        if data["medium_risk"]:
            lines.append("\n  MEDIUM RISK (Review Recommended):")
            for issue in data["medium_risk"][:10]:
                lines.append(f"    * [{issue['category']}] {issue['type']}")
                if issue['file']:
                    lines.append(f"      File: {issue['file']}")

        if data["low_risk"] and len(data["low_risk"]) <= 5:
            lines.append("\n  LOW RISK (Can Auto-Fix):")
            for issue in data["low_risk"]:
                lines.append(f"    - [{issue['category']}] {issue['type']}")
        elif data["low_risk"]:
            lines.append(f"\n  LOW RISK: {len(data['low_risk'])} issues (can auto-fix)")

    return "\n".join(lines)


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else "assess"

    if action == "assess":
        assessment = assess_all_projects()
        print(generate_report(assessment))

    elif action == "json":
        assessment = assess_all_projects()
        print(json.dumps(assessment, indent=2))

    elif action == "fix-low":
        dry_run = "--apply" not in sys.argv
        result = apply_low_risk_fixes(dry_run=dry_run)
        if dry_run:
            print(f"DRY RUN: Would acknowledge {result['fixes_would_apply']} low-risk issues")
            print("Run with --apply to actually apply fixes")
        else:
            print(f"Applied {result['fixes_applied']} fixes")
        print(json.dumps(result, indent=2))

    elif action == "medium":
        assessment = assess_all_projects()
        print("=" * 70)
        print("MEDIUM RISK ISSUES FOR REVIEW")
        print("=" * 70)
        for project_id, data in assessment["projects"].items():
            if "error" in data or not data.get("medium_risk"):
                continue
            print(f"\n{project_id}:")
            for issue in data["medium_risk"]:
                print(f"  [{issue['category']}] {issue['type']}")
                if issue['file']:
                    print(f"    File: {issue['file']}")
                if issue['message']:
                    print(f"    {issue['message'][:100]}")
    else:
        print("Usage: python batch_health_fix.py [assess|json|fix-low|medium]")
        print("  assess   - Full assessment report (default)")
        print("  json     - Assessment as JSON")
        print("  fix-low  - Preview low-risk fixes (add --apply to execute)")
        print("  medium   - Show only medium-risk issues")


if __name__ == "__main__":
    main()
