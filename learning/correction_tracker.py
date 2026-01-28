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
    correction = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user_message": message[:500],
        "previous_context": previous_context[:500] if previous_context else None,
    }

    msg_lower = message.lower()

    # Pattern 1: "use X not Y" or "use X instead of Y"
    use_not_match = re.search(r"use\s+([^\s,]+(?:\s+[^\s,]+)?)\s+(?:not|instead\s+of)\s+([^\s,]+)", msg_lower)
    if use_not_match:
        correction["correct"] = use_not_match.group(1)
        correction["wrong"] = use_not_match.group(2)
        return correction

    # Pattern 2: "no, I meant X" or "I meant X not Y"
    meant_match = re.search(r"(?:no[,.]?\s+)?i\s+meant\s+(?:use\s+)?([^\s,]+(?:\.[^\s,]+)?)", msg_lower)
    if meant_match:
        correction["correct"] = meant_match.group(1)
        return correction

    # Pattern 3: "should be X not Y"
    should_be_match = re.search(r"should\s+be\s+([^\s,]+)\s+not\s+([^\s,]+)", msg_lower)
    if should_be_match:
        correction["correct"] = should_be_match.group(1)
        correction["wrong"] = should_be_match.group(2)
        return correction

    # Pattern 4: "it's X not Y" (capturing multi-part identifiers)
    its_not_match = re.search(r"it'?s\s+([^\s,]+(?:\.[^\s,]+)?)\s+not\s+([^\s,]+)", msg_lower)
    if its_not_match:
        correction["correct"] = its_not_match.group(1)
        correction["wrong"] = its_not_match.group(2)
        return correction

    # Pattern 5: "prefer X over Y"
    prefer_over_match = re.search(r"prefer\s+([^\s,]+)\s+over\s+([^\s,]+)", msg_lower)
    if prefer_over_match:
        correction["correct"] = prefer_over_match.group(1)
        correction["wrong"] = prefer_over_match.group(2)
        return correction

    # Pattern 6: "always use X"
    always_match = re.search(r"always\s+use\s+([^\s,]+(?:[\s-]+\w+)?)", msg_lower)
    if always_match:
        correction["correct"] = always_match.group(1)
        return correction

    # Pattern 7: "don't use X" or "never use X" or "stop using X"
    dont_match = re.search(r"(?:don'?t|never|stop)\s+(?:use|using)\s+([^\s,]+(?:\s+\w+)?)", msg_lower)
    if dont_match:
        correction["wrong"] = dont_match.group(1)
        return correction

    # Pattern 8: "do not add/do/make X"
    donot_match = re.search(r"do\s+not\s+(?:add|do|make|create|put)\s+([^\s,]+(?:\s+[^\s,]+)?)", msg_lower)
    if donot_match:
        correction["wrong"] = donot_match.group(1)
        return correction

    # Pattern 9: "uses X instead" or "have X now"
    have_now_match = re.search(r"(?:have|using?)\s+([^\s,]+)\s+(?:now|instead)", msg_lower)
    if have_now_match:
        correction["correct"] = have_now_match.group(1)
        return correction

    return correction


def is_quality_correction(message):
    """Filter out false positive corrections (build output, errors, instructions)."""
    msg = message.lower()

    # Skip if message looks like build/error output (common false positives)
    build_output_patterns = [
        r'^\s*›',                    # Expo/npm progress lines
        r'^\s*\d+\.\d+\.\d+',        # Version numbers at start
        r'error\s*\(exit\s*\d+\)',   # Exit codes
        r'npm\s+(run|install|start|test)',  # npm commands
        r'compiling\s+\w+\s+pods',   # iOS compilation
        r'shell\s+cwd\s+was\s+reset', # Shell resets
        r'http://\d+\.\d+\.\d+\.\d+:\d+',  # IP:port URLs
        r'waiting\s+for\s+watchman',  # Watchman output
        r'^\s*at\s+\w+\s+\(',        # Stack traces
        r'npx\s+expo',               # Expo commands
        r'eas\s+build',              # EAS commands
    ]

    for pattern in build_output_patterns:
        if re.search(pattern, msg):
            return False

    # Skip if message is too long (likely pasted output, not a correction)
    if len(message) > 500:
        return False

    # Skip if message has too many newlines (likely pasted output)
    if message.count('\n') > 3:
        return False

    # Must have a clear correction signal (not just matching a vague pattern)
    clear_signals = [
        r'\bno[,.]?\s+i\s+meant\b',
        r'\bno[,.]?\s+use\b',
        r'\bactually[,.]?\s+i\s+(want|meant|need)\b',
        r'\buse\s+\w+\s+not\s+\w+\b',
        r'\buse\s+\w+\s+instead\b',
        r"\bi\s+prefer\b",
        r"\balways\s+use\b",
        r"\bnever\s+use\b",
    ]

    has_clear_signal = any(re.search(p, msg) for p in clear_signals)

    return has_clear_signal


def record_correction(message, previous_context=None, topic=None, project_id=None):
    """Record a correction for future learning."""
    # Quality filter - skip false positives
    if not is_quality_correction(message):
        return None

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
    # Only record to ReasoningBank if we extracted a meaningful correction
    # Don't pollute with garbage solutions
    if correction.get("correct") or correction.get("wrong"):
        try:
            from reasoning_bank import record_trajectory
            # Build meaningful solution string
            solution_parts = []
            if correction.get("correct"):
                solution_parts.append(f"Use: {correction['correct']}")
            if correction.get("wrong"):
                solution_parts.append(f"Avoid: {correction['wrong']}")
            solution = "; ".join(solution_parts)

            record_trajectory(
                context=previous_context or message[:200],  # Use message as context fallback
                problem=message[:200],
                solution=solution,
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
