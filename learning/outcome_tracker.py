#!/usr/bin/env python3
"""
Outcome Tracker

Tracks the outcomes of Claude's code changes and suggestions.
Associates approaches with success/failure for learning.

Usage:
  # Record an outcome
  python outcome_tracker.py --record --approach "used async/await" --outcome success --domain "javascript"

  # Check build/test after changes
  python outcome_tracker.py --check-build --project-path /path/to/project

  # Get success rate for a domain
  python outcome_tracker.py --stats --domain "docker"
"""

import json
import subprocess
import sys
import os
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict

MEMORY_ROOT = Path.home() / ".claude-dash"
OUTCOMES_FILE = MEMORY_ROOT / "learning" / "outcomes.json"


def load_outcomes():
    """Load outcomes database."""
    if not OUTCOMES_FILE.exists():
        return {
            "outcomes": [],
            "domain_stats": {},
            "approach_stats": {}
        }

    try:
        return json.loads(OUTCOMES_FILE.read_text())
    except:
        return {"outcomes": [], "domain_stats": {}, "approach_stats": {}}


def save_outcomes(data):
    """Save outcomes database."""
    OUTCOMES_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTCOMES_FILE.write_text(json.dumps(data, indent=2))


def detect_project_type(project_path):
    """Detect project type for appropriate build/test commands."""
    path = Path(project_path)

    if (path / "package.json").exists():
        pkg = json.loads((path / "package.json").read_text())
        scripts = pkg.get("scripts", {})

        if "expo" in str(pkg.get("dependencies", {})):
            return "expo"
        elif "next" in str(pkg.get("dependencies", {})):
            return "nextjs"
        elif "react-native" in str(pkg.get("dependencies", {})):
            return "react-native"
        else:
            return "node"

    elif (path / "requirements.txt").exists() or (path / "pyproject.toml").exists():
        return "python"

    elif (path / "Cargo.toml").exists():
        return "rust"

    elif (path / "go.mod").exists():
        return "go"

    elif (path / "build.gradle").exists() or (path / "build.gradle.kts").exists():
        return "android"

    return "unknown"


def get_build_commands(project_type):
    """Get build/test commands for project type."""
    commands = {
        "node": {
            "build": "npm run build",
            "test": "npm test",
            "lint": "npm run lint"
        },
        "nextjs": {
            "build": "npm run build",
            "test": "npm test",
            "lint": "npm run lint"
        },
        "expo": {
            "build": "npx expo export --platform web",
            "test": "npm test",
            "lint": "npm run lint"
        },
        "react-native": {
            "build": "npx react-native bundle --entry-file index.js --platform ios --dev false --bundle-output /tmp/bundle.js",
            "test": "npm test",
            "lint": "npm run lint"
        },
        "python": {
            "build": "python -m py_compile *.py",
            "test": "pytest",
            "lint": "ruff check ."
        },
        "rust": {
            "build": "cargo build",
            "test": "cargo test",
            "lint": "cargo clippy"
        },
        "go": {
            "build": "go build ./...",
            "test": "go test ./...",
            "lint": "go vet ./..."
        },
        "android": {
            "build": "./gradlew assembleDebug",
            "test": "./gradlew test",
            "lint": "./gradlew lint"
        }
    }

    return commands.get(project_type, {"build": None, "test": None, "lint": None})


def run_check(command, project_path, timeout=120):
    """Run a build/test command and return result."""
    if not command:
        return {"success": None, "skipped": True, "reason": "no command"}

    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=timeout
        )

        return {
            "success": result.returncode == 0,
            "exit_code": result.returncode,
            "stdout": result.stdout[-1000:] if result.stdout else "",
            "stderr": result.stderr[-1000:] if result.stderr else ""
        }

    except subprocess.TimeoutExpired:
        return {"success": False, "error": "timeout"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def check_build(project_path, checks=None):
    """Run build/test checks on a project."""
    project_type = detect_project_type(project_path)
    commands = get_build_commands(project_type)

    if checks is None:
        checks = ["lint", "build"]  # Default to lint and build (tests can be slow)

    results = {
        "project_type": project_type,
        "project_path": str(project_path),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": {}
    }

    overall_success = True

    for check in checks:
        if check in commands and commands[check]:
            result = run_check(commands[check], project_path)
            results["checks"][check] = result
            if result.get("success") is False:
                overall_success = False

    results["overall_success"] = overall_success
    return results


def record_outcome(approach, outcome, domain=None, context=None, project_id=None, files_changed=None):
    """Record an outcome for learning."""
    data = load_outcomes()

    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "approach": approach,
        "outcome": outcome,  # "success", "failure", "partial"
        "domain": domain,
        "context": context[:200] if context else None,
        "project_id": project_id,
        "files_changed": files_changed[:10] if files_changed else None
    }

    data["outcomes"].append(record)

    # Update domain stats
    if domain:
        if domain not in data["domain_stats"]:
            data["domain_stats"][domain] = {"success": 0, "failure": 0, "partial": 0}
        if outcome in data["domain_stats"][domain]:
            data["domain_stats"][domain][outcome] += 1

    # Update approach stats
    approach_key = approach[:50] if approach else "unknown"
    if approach_key not in data["approach_stats"]:
        data["approach_stats"][approach_key] = {"success": 0, "failure": 0, "partial": 0}
    if outcome in data["approach_stats"][approach_key]:
        data["approach_stats"][approach_key][outcome] += 1

    # Keep last 500 outcomes
    data["outcomes"] = data["outcomes"][-500:]

    save_outcomes(data)
    return record


def get_domain_stats(domain=None):
    """Get success statistics for a domain."""
    data = load_outcomes()
    stats = data.get("domain_stats", {})

    if domain:
        if domain in stats:
            s = stats[domain]
            total = s["success"] + s["failure"] + s["partial"]
            success_rate = s["success"] / total if total > 0 else 0
            return {
                "domain": domain,
                "total": total,
                "success": s["success"],
                "failure": s["failure"],
                "partial": s["partial"],
                "success_rate": success_rate
            }
        return None

    # Return all domain stats
    result = {}
    for d, s in stats.items():
        total = s["success"] + s["failure"] + s["partial"]
        result[d] = {
            "total": total,
            "success_rate": s["success"] / total if total > 0 else 0
        }
    return result


def get_approach_history(approach_pattern, limit=5):
    """Get history of similar approaches."""
    data = load_outcomes()
    outcomes = data.get("outcomes", [])

    pattern_lower = approach_pattern.lower()
    relevant = []

    for outcome in reversed(outcomes):
        approach = outcome.get("approach", "").lower()
        if pattern_lower in approach or approach in pattern_lower:
            relevant.append(outcome)
            if len(relevant) >= limit:
                break

    return relevant


def format_stats_for_injection(stats):
    """Format stats for context injection."""
    if not stats:
        return None

    lines = ["[OUTCOME HISTORY - Confidence calibration]"]

    for domain, s in sorted(stats.items(), key=lambda x: x[1]["total"], reverse=True)[:5]:
        rate = s["success_rate"] * 100
        emoji = "+" if rate >= 70 else "~" if rate >= 50 else "!"
        lines.append(f"  {emoji} {domain}: {rate:.0f}% success ({s['total']} attempts)")

    return "\n".join(lines)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Outcome tracker")
    parser.add_argument("--record", action="store_true", help="Record an outcome")
    parser.add_argument("--check-build", action="store_true", help="Run build checks")
    parser.add_argument("--stats", action="store_true", help="Get statistics")
    parser.add_argument("--approach", help="Approach description")
    parser.add_argument("--outcome", choices=["success", "failure", "partial"], help="Outcome")
    parser.add_argument("--domain", help="Domain/topic")
    parser.add_argument("--context", help="Context description")
    parser.add_argument("--project", help="Project ID")
    parser.add_argument("--project-path", help="Project path for build checks")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    if args.record:
        if not args.approach or not args.outcome:
            print("Error: --approach and --outcome required for recording")
            sys.exit(1)

        record = record_outcome(
            approach=args.approach,
            outcome=args.outcome,
            domain=args.domain,
            context=args.context,
            project_id=args.project
        )

        if args.json:
            print(json.dumps(record, indent=2))
        else:
            print(f"Recorded: {args.outcome} for '{args.approach[:50]}'")

    elif args.check_build:
        if not args.project_path:
            print("Error: --project-path required")
            sys.exit(1)

        results = check_build(args.project_path)

        if args.json:
            print(json.dumps(results, indent=2))
        else:
            status = "PASS" if results["overall_success"] else "FAIL"
            print(f"Build check: {status} ({results['project_type']})")
            for check, result in results["checks"].items():
                s = "OK" if result.get("success") else "FAIL"
                print(f"  {check}: {s}")

    elif args.stats:
        stats = get_domain_stats(args.domain)

        if args.json:
            print(json.dumps(stats, indent=2))
        else:
            if args.domain and stats:
                print(f"{args.domain}: {stats['success_rate']*100:.0f}% success ({stats['total']} attempts)")
            elif stats:
                formatted = format_stats_for_injection(stats)
                print(formatted or "No stats yet")
            else:
                print("No stats available")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
