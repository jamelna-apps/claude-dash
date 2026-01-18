#!/usr/bin/env python3
"""
Correction Tracker

Detects when user corrects Claude and learns from mistakes.
Injects relevant past corrections when similar context arises.

Correction signals:
- "no, I meant..."
- "that's wrong..."
- "actually..."
- "not X, Y"
- "I said X not Y"
"""

import json
import re
import sys
from pathlib import Path
from datetime import datetime, timezone

MEMORY_ROOT = Path.home() / ".claude-dash"
CORRECTIONS_FILE = MEMORY_ROOT / "learning" / "corrections.json"

# Patterns that indicate user is correcting Claude
CORRECTION_PATTERNS = [
    # Explicit corrections
    r"\bno[,.]?\s+(i\s+)?(meant|want|need|said)",
    r"\bthat'?s\s+(wrong|incorrect|not\s+right|not\s+what)",
    r"\bactually[,.]?\s+(i\s+)?(want|need|meant)",
    r"\bactually[,.]?\s+(the|it'?s|it\s+is)",
    r"\bi\s+said\s+(\w+)\s+not\s+(\w+)",
    r"\bno[,.]?\s+not\s+",
    r"\bwrong[,.]?\s+",
    r"\bthat'?s\s+not\s+",
    r"\bi\s+didn'?t\s+(mean|want|ask)",

    # Imperative corrections: "no, use X", "use X not Y", "use X instead"
    r"\bno[,.]?\s+use\s+",
    r"\bno[,.]?\s+it\s+should\s+be\s+",
    r"\buse\s+(\w+)\s+not\s+(\w+)",
    r"\buse\s+(\w+)\s+instead(\s+of)?",
    r"\bshould\s+be\s+(\w+)\s+not\s+(\w+)",
    r"\bit'?s\s+(\w+)\s+not\s+(\w+)",

    # "not X, Y" and "not X but Y" patterns (order matters - more specific first)
    r"\bnot\s+['\"]?(\w+)['\"]?\s*,\s*['\"]?(\w+)['\"]?",
    r"\bnot\s+(\w+)[,.]?\s+but\s+(\w+)",

    # Action corrections
    r"\bdon'?t\s+(do|use|add|make|create)\s+",
    r"\bremove\s+(that|this|the|it)",
    r"\bundo\s+",
    r"\brevert\s+",
    r"\bgo\s+back\s+to",
    r"\bchange\s+(it|that|this)\s+(back\s+)?to\s+",

    # Preference expressions
    r"\bprefer\s+(\w+)\s+(over|to|instead)",
    r"\balways\s+use\s+",
    r"\bnever\s+use\s+",
    r"\bstop\s+using\s+",
]


def load_corrections():
    """Load corrections database."""
    if not CORRECTIONS_FILE.exists():
        return {"corrections": [], "patterns": {}}

    try:
        return json.loads(CORRECTIONS_FILE.read_text())
    except:
        return {"corrections": [], "patterns": {}}


def save_corrections(data):
    """Save corrections database."""
    CORRECTIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    CORRECTIONS_FILE.write_text(json.dumps(data, indent=2))


def detect_correction(message):
    """Detect if message contains a correction."""
    message_lower = message.lower()

    for pattern in CORRECTION_PATTERNS:
        match = re.search(pattern, message_lower)
        if match:
            return {
                "is_correction": True,
                "pattern": pattern,
                "matched_text": match.group(0),
                "full_message": message
            }

    return {"is_correction": False}


def extract_correction_context(message, previous_context=None):
    """Extract what was wrong and what's correct."""
    # Simple extraction - can be enhanced with Ollama
    correction = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user_message": message[:500],
        "previous_context": previous_context[:500] if previous_context else None,
    }

    # Try to extract the "not X, but Y" pattern
    not_but_match = re.search(r"not\s+['\"]?(\w+)['\"]?[,.]?\s+(?:but\s+)?['\"]?(\w+)['\"]?", message.lower())
    if not_but_match:
        correction["wrong"] = not_but_match.group(1)
        correction["correct"] = not_but_match.group(2)

    return correction


def record_correction(message, previous_context=None, topic=None, project_id=None):
    """Record a correction for future learning."""
    data = load_corrections()

    correction = extract_correction_context(message, previous_context)
    correction["topic"] = topic
    correction["project_id"] = project_id

    data["corrections"].append(correction)

    # Keep last 200 corrections
    data["corrections"] = data["corrections"][-200:]

    # Update pattern frequency
    if topic:
        if topic not in data["patterns"]:
            data["patterns"][topic] = {"count": 0, "examples": []}
        data["patterns"][topic]["count"] += 1
        data["patterns"][topic]["examples"].append(message[:100])
        data["patterns"][topic]["examples"] = data["patterns"][topic]["examples"][-5:]

    save_corrections(data)

    # === REASONING BANK INTEGRATION ===
    # Also record to ReasoningBank for RETRIEVE→JUDGE→DISTILL cycle
    try:
        from reasoning_bank import record_trajectory
        record_trajectory(
            context=previous_context or "",
            problem=message[:200],
            solution=correction.get("correct", message[:100]),
            domain=topic,
            project_id=project_id
        )
    except ImportError:
        pass  # ReasoningBank not available
    except Exception:
        pass  # Non-critical - don't fail correction recording

    return correction


def find_relevant_corrections(context, topic=None, limit=3):
    """Find past corrections relevant to current context."""
    data = load_corrections()
    corrections = data.get("corrections", [])

    if not corrections:
        return []

    context_lower = context.lower()
    relevant = []

    # Extract key terms from context
    context_terms = set(re.findall(r'\b\w{4,}\b', context_lower))

    for correction in reversed(corrections):  # Most recent first
        score = 0

        # Check topic match
        if topic and correction.get("topic") == topic:
            score += 2

        # Check term overlap
        correction_text = (correction.get("user_message", "") + " " +
                          (correction.get("previous_context") or "")).lower()
        correction_terms = set(re.findall(r'\b\w{4,}\b', correction_text))

        overlap = len(context_terms & correction_terms)
        score += overlap

        if score > 0:
            relevant.append({
                "score": score,
                "correction": correction
            })

    # Sort by score and return top N
    relevant.sort(key=lambda x: x["score"], reverse=True)
    return [r["correction"] for r in relevant[:limit]]


def format_corrections_for_injection(corrections):
    """Format corrections for context injection."""
    if not corrections:
        return None

    lines = ["[PAST CORRECTIONS - Learn from these mistakes]"]

    for c in corrections:
        msg = c.get("user_message", "")[:100]
        if c.get("wrong") and c.get("correct"):
            lines.append(f"  ! Not '{c['wrong']}' but '{c['correct']}'")
        else:
            lines.append(f"  ! {msg}")

    return "\n".join(lines)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Correction tracker")
    parser.add_argument("message", nargs="?", help="Message to analyze")
    parser.add_argument("--detect", action="store_true", help="Detect if correction")
    parser.add_argument("--record", action="store_true", help="Record a correction")
    parser.add_argument("--find", action="store_true", help="Find relevant corrections")
    parser.add_argument("--context", help="Previous context")
    parser.add_argument("--topic", help="Topic/domain")
    parser.add_argument("--project", help="Project ID")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    if args.detect and args.message:
        result = detect_correction(args.message)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print("Correction detected" if result["is_correction"] else "Not a correction")

    elif args.record and args.message:
        correction = record_correction(
            args.message,
            previous_context=args.context,
            topic=args.topic,
            project_id=args.project
        )
        if args.json:
            print(json.dumps(correction, indent=2))
        else:
            print(f"Recorded correction: {correction.get('user_message', '')[:50]}...")

    elif args.find and args.message:
        corrections = find_relevant_corrections(
            args.message,
            topic=args.topic,
            limit=3
        )
        if args.json:
            print(json.dumps(corrections, indent=2))
        else:
            formatted = format_corrections_for_injection(corrections)
            if formatted:
                print(formatted)
            else:
                print("No relevant corrections found")

    else:
        # Default: check if message is a correction
        if args.message:
            result = detect_correction(args.message)
            print(json.dumps(result, indent=2) if args.json else
                  ("Correction detected" if result["is_correction"] else "Not a correction"))
        else:
            parser.print_help()


if __name__ == "__main__":
    main()
