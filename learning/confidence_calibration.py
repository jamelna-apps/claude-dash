#!/usr/bin/env python3
"""
Confidence Calibration

Tracks Claude's accuracy by domain to calibrate confidence levels.
Learns when to be more or less certain based on past performance.

Usage:
  # Record a prediction outcome
  python confidence_calibration.py --record --domain "docker" --predicted "use bridge network" --actual "success"

  # Get calibration for a domain
  python confidence_calibration.py --calibration --domain "react-native"

  # Get all calibrations
  python confidence_calibration.py --calibration
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict

MEMORY_ROOT = Path.home() / ".claude-dash"
CALIBRATION_FILE = MEMORY_ROOT / "learning" / "confidence_calibration.json"

# Domain categories
DOMAINS = [
    "docker", "kubernetes", "infrastructure",
    "react", "react-native", "expo", "nextjs",
    "typescript", "javascript", "python",
    "firebase", "firestore", "authentication",
    "testing", "git", "database", "api",
    "performance", "security", "css", "styling",
    "state-management", "navigation", "forms",
    "file-system", "networking", "caching"
]


def load_calibration():
    """Load calibration data."""
    if not CALIBRATION_FILE.exists():
        return {
            "predictions": [],
            "domain_stats": {},
            "topic_stats": {},
            "overall": {"correct": 0, "incorrect": 0, "partial": 0}
        }

    try:
        return json.loads(CALIBRATION_FILE.read_text())
    except:
        return {"predictions": [], "domain_stats": {}, "topic_stats": {}, "overall": {}}


def save_calibration(data):
    """Save calibration data."""
    CALIBRATION_FILE.parent.mkdir(parents=True, exist_ok=True)
    CALIBRATION_FILE.write_text(json.dumps(data, indent=2))


def detect_domain(text):
    """Detect domain from text content."""
    text_lower = text.lower()

    domain_keywords = {
        "docker": ["docker", "container", "dockerfile", "compose", "image"],
        "kubernetes": ["kubernetes", "k8s", "kubectl", "pod", "deployment"],
        "infrastructure": ["server", "deploy", "ci/cd", "pipeline", "nginx"],
        "react": ["react", "component", "jsx", "hooks", "usestate", "useeffect"],
        "react-native": ["react native", "expo", "metro", "native module"],
        "nextjs": ["next.js", "nextjs", "getserversideprops", "app router"],
        "typescript": ["typescript", "type", "interface", "generic"],
        "javascript": ["javascript", "js", "async", "promise", "callback"],
        "python": ["python", "pip", "django", "flask", "pytest"],
        "firebase": ["firebase", "firestore", "realtime database"],
        "firestore": ["firestore", "collection", "document", "query"],
        "authentication": ["auth", "login", "token", "jwt", "session", "oauth"],
        "testing": ["test", "jest", "pytest", "spec", "mock", "coverage"],
        "git": ["git", "commit", "branch", "merge", "rebase"],
        "database": ["database", "sql", "postgres", "mongodb", "query"],
        "api": ["api", "endpoint", "rest", "graphql", "fetch"],
        "performance": ["performance", "optimize", "slow", "memory", "profil"],
        "security": ["security", "vulnerability", "xss", "injection", "sanitize"],
        "css": ["css", "style", "flexbox", "grid", "animation"],
        "styling": ["tailwind", "styled-components", "sass", "scss"],
        "state-management": ["redux", "zustand", "context", "state management"],
        "navigation": ["navigation", "router", "route", "navigate", "screen"],
        "forms": ["form", "input", "validation", "submit"],
        "file-system": ["file", "fs", "read", "write", "path"],
        "networking": ["http", "fetch", "axios", "request", "socket"],
        "caching": ["cache", "redis", "memoize", "storage"]
    }

    detected = []
    for domain, keywords in domain_keywords.items():
        for keyword in keywords:
            if keyword in text_lower:
                detected.append(domain)
                break

    return detected[0] if detected else "general"


def record_prediction(domain, prediction, outcome, context=None, confidence_given=None):
    """Record a prediction and its outcome."""
    data = load_calibration()

    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "domain": domain,
        "prediction": prediction[:200],
        "outcome": outcome,  # "correct", "incorrect", "partial"
        "context": context[:200] if context else None,
        "confidence_given": confidence_given
    }

    data["predictions"].append(record)

    # Update domain stats
    if domain not in data["domain_stats"]:
        data["domain_stats"][domain] = {"correct": 0, "incorrect": 0, "partial": 0, "total": 0}

    stats = data["domain_stats"][domain]
    stats["total"] += 1
    if outcome in stats:
        stats[outcome] += 1

    # Update overall stats
    if outcome in data["overall"]:
        data["overall"][outcome] += 1

    # Keep last 500 predictions
    data["predictions"] = data["predictions"][-500:]

    save_calibration(data)
    return record


def get_calibration(domain=None):
    """Get calibration data for domain(s)."""
    data = load_calibration()
    stats = data.get("domain_stats", {})

    if domain:
        if domain in stats:
            s = stats[domain]
            total = s["total"]
            if total == 0:
                return None

            accuracy = s["correct"] / total
            partial_rate = s["partial"] / total

            # Determine recommended confidence level
            if accuracy >= 0.85:
                confidence_rec = "high"
            elif accuracy >= 0.65:
                confidence_rec = "moderate"
            elif accuracy >= 0.45:
                confidence_rec = "low - caveat heavily"
            else:
                confidence_rec = "very low - ask questions first"

            return {
                "domain": domain,
                "total_predictions": total,
                "accuracy": accuracy,
                "partial_rate": partial_rate,
                "recommended_confidence": confidence_rec,
                "suggestion": get_confidence_suggestion(accuracy)
            }
        return None

    # Return all domains
    result = {}
    for d, s in stats.items():
        if s["total"] > 0:
            result[d] = {
                "accuracy": s["correct"] / s["total"],
                "total": s["total"]
            }

    return result


def get_confidence_suggestion(accuracy):
    """Get suggestion based on accuracy."""
    if accuracy >= 0.85:
        return "Track record is strong. Can be confident in this domain."
    elif accuracy >= 0.65:
        return "Generally reliable, but verify important details."
    elif accuracy >= 0.45:
        return "Mixed results. Recommend caveating with 'I think' or 'likely'."
    else:
        return "High error rate. Ask clarifying questions before suggesting."


def get_domain_calibration_for_context(domains):
    """Get calibration info for multiple domains for context injection."""
    calibrations = []

    for domain in domains:
        cal = get_calibration(domain)
        if cal:
            calibrations.append(cal)

    return calibrations


def format_calibration_for_injection(calibrations):
    """Format calibration for context injection."""
    if not calibrations:
        return None

    lines = ["[CONFIDENCE CALIBRATION]"]

    for cal in calibrations:
        domain = cal["domain"]
        acc = cal["accuracy"] * 100
        rec = cal["recommended_confidence"]

        if acc >= 70:
            indicator = "+"
        elif acc >= 50:
            indicator = "~"
        else:
            indicator = "!"

        lines.append(f"  {indicator} {domain}: {acc:.0f}% accuracy → {rec}")

    return "\n".join(lines)


def analyze_weak_areas():
    """Identify domains where accuracy is low."""
    data = load_calibration()
    stats = data.get("domain_stats", {})

    weak = []
    for domain, s in stats.items():
        if s["total"] >= 3:  # Need at least 3 predictions
            accuracy = s["correct"] / s["total"]
            if accuracy < 0.6:
                weak.append({
                    "domain": domain,
                    "accuracy": accuracy,
                    "total": s["total"]
                })

    return sorted(weak, key=lambda x: x["accuracy"])


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Confidence calibration")
    parser.add_argument("--record", action="store_true", help="Record a prediction outcome")
    parser.add_argument("--domain", help="Domain/topic")
    parser.add_argument("--predicted", help="What was predicted")
    parser.add_argument("--actual", choices=["correct", "incorrect", "partial"], help="Outcome")
    parser.add_argument("--calibration", action="store_true", help="Get calibration")
    parser.add_argument("--weak-areas", action="store_true", help="Show weak areas")
    parser.add_argument("--context", help="Context")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    if args.record:
        if not args.domain or not args.predicted or not args.actual:
            print("Error: --domain, --predicted, and --actual required")
            sys.exit(1)

        record = record_prediction(
            domain=args.domain,
            prediction=args.predicted,
            outcome=args.actual,
            context=args.context
        )

        if args.json:
            print(json.dumps(record, indent=2))
        else:
            print(f"Recorded: {args.actual} for {args.domain}")

    elif args.calibration:
        cal = get_calibration(args.domain)

        if args.json:
            print(json.dumps(cal, indent=2))
        else:
            if args.domain and cal:
                print(f"{cal['domain']}: {cal['accuracy']*100:.0f}% accuracy ({cal['total_predictions']} predictions)")
                print(f"  Recommendation: {cal['recommended_confidence']}")
                print(f"  {cal['suggestion']}")
            elif cal:
                for domain, stats in sorted(cal.items(), key=lambda x: x[1]["accuracy"]):
                    acc = stats["accuracy"] * 100
                    print(f"  {domain}: {acc:.0f}% ({stats['total']} predictions)")
            else:
                print("No calibration data yet")

    elif args.weak_areas:
        weak = analyze_weak_areas()

        if args.json:
            print(json.dumps(weak, indent=2))
        else:
            if weak:
                print("Weak areas (< 60% accuracy):")
                for w in weak:
                    print(f"  ! {w['domain']}: {w['accuracy']*100:.0f}% ({w['total']} predictions)")
            else:
                print("No weak areas identified (need 3+ predictions per domain)")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
