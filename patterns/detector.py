#!/usr/bin/env python3
"""
Pattern Detector

Detects conversation mode from user messages using signal matching.
Optionally enhances with Ollama for ambiguous cases.

Usage:
  python detector.py "user message" [--no-ollama] [--context] [--json]
"""

import json
import re
import sys
import urllib.request
from pathlib import Path

MEMORY_ROOT = Path.home() / ".claude-dash"
PATTERNS_FILE = MEMORY_ROOT / "patterns" / "patterns.json"
OLLAMA_URL = "http://localhost:11434"
OLLAMA_MODEL = "qwen2.5:7b"


def load_patterns():
    """Load pattern definitions."""
    if not PATTERNS_FILE.exists():
        return {"modes": {}, "learned_patterns": []}

    try:
        return json.loads(PATTERNS_FILE.read_text())
    except:
        return {"modes": {}, "learned_patterns": []}


def detect_mode_fast(message, patterns):
    """Fast regex-based mode detection."""
    message_lower = message.lower()
    scores = {}

    for mode, config in patterns.get("modes", {}).items():
        signals = config.get("signals", [])
        matched = []

        for signal in signals:
            if re.search(r'\b' + re.escape(signal) + r'\b', message_lower):
                matched.append(signal)

        if matched:
            scores[mode] = {
                "score": len(matched),
                "matched_signals": matched,
                "confidence": min(len(matched) / 3, 1.0)
            }

    return scores


def detect_mode_ollama(message, patterns):
    """Use Ollama for more nuanced detection."""
    modes = list(patterns.get("modes", {}).keys())

    if not modes:
        return None

    prompt = f"""Classify this message into ONE of these categories: {', '.join(modes)}

Message: "{message}"

Respond with ONLY the category name, nothing else."""

    try:
        data = json.dumps({
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0, "num_predict": 20}
        }).encode('utf-8')

        req = urllib.request.Request(
            f"{OLLAMA_URL}/api/generate",
            data=data,
            headers={"Content-Type": "application/json"}
        )

        with urllib.request.urlopen(req, timeout=10) as response:
            result = json.loads(response.read().decode('utf-8'))
            detected = result.get("response", "").strip().lower()

            if detected in modes:
                return {"mode": detected, "confidence": 0.8, "method": "ollama"}

    except Exception as e:
        pass

    return None


def detect_mode(message, use_ollama=True):
    """Main detection function."""
    patterns = load_patterns()
    fast_scores = detect_mode_fast(message, patterns)

    if not fast_scores:
        if use_ollama:
            ollama_result = detect_mode_ollama(message, patterns)
            if ollama_result:
                return {
                    "primary_mode": ollama_result["mode"],
                    "secondary_modes": [],
                    "confidence": ollama_result["confidence"],
                    "matched_signals": [],
                    "all_scores": {},
                    "method": "ollama"
                }
        return {
            "primary_mode": None,
            "secondary_modes": [],
            "confidence": 0,
            "matched_signals": [],
            "all_scores": {},
            "method": "none"
        }

    # Sort by score
    sorted_modes = sorted(fast_scores.items(), key=lambda x: x[1]["score"], reverse=True)

    primary = sorted_modes[0]
    secondary = [m[0] for m in sorted_modes[1:] if m[1]["score"] > 0]

    result = {
        "primary_mode": primary[0],
        "secondary_modes": secondary,
        "confidence": primary[1]["confidence"],
        "matched_signals": primary[1]["matched_signals"],
        "all_scores": fast_scores,
        "method": "fast"
    }

    # If low confidence and Ollama enabled, try Ollama
    if use_ollama and result["confidence"] < 0.5:
        ollama_result = detect_mode_ollama(message, patterns)
        if ollama_result and ollama_result["confidence"] > result["confidence"]:
            result["primary_mode"] = ollama_result["mode"]
            result["confidence"] = ollama_result["confidence"]
            result["method"] = "ollama_enhanced"

    return result


def get_mode_context(mode, patterns):
    """Get context guidance for a mode."""
    mode_config = patterns.get("modes", {}).get(mode, {})
    context = mode_config.get("context", {})

    return {
        "mode": mode,
        "description": context.get("description", ""),
        "suggested_actions": context.get("actions", []),
        "recommended_tools": context.get("tools", []),
        "things_to_avoid": context.get("avoid", []),
        "preferences": []
    }


def format_context_text(context):
    """Format context for injection."""
    lines = [f"[DETECTED MODE: {context['mode'].upper()}]"]
    lines.append(f"Context: {context['description']}")

    if context["suggested_actions"]:
        lines.append("Suggested approach:")
        for action in context["suggested_actions"]:
            lines.append(f"  - {action}")

    if context["things_to_avoid"]:
        lines.append("Avoid:")
        for avoid in context["things_to_avoid"]:
            lines.append(f"  - {avoid}")

    return "\n".join(lines)


def track_user_phrase(phrase, mode, outcome=True):
    """Track a user phrase and its mode for pattern learning."""
    patterns = load_patterns()

    learned = patterns.get("learned_patterns", [])
    learned.append({
        "phrase": phrase[:100],
        "mode": mode,
        "outcome": outcome
    })

    # Keep last 100
    patterns["learned_patterns"] = learned[-100:]

    try:
        PATTERNS_FILE.write_text(json.dumps(patterns, indent=2))
    except:
        pass


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Detect conversation mode")
    parser.add_argument("message", help="User message to analyze")
    parser.add_argument("--no-ollama", action="store_true", help="Skip Ollama enhancement")
    parser.add_argument("--context", action="store_true", help="Include context guidance")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    result = detect_mode(args.message, use_ollama=not args.no_ollama)

    if args.context and result["primary_mode"]:
        patterns = load_patterns()
        context = get_mode_context(result["primary_mode"], patterns)
        result["context"] = context
        result["context_text"] = format_context_text(context)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        if result["primary_mode"]:
            print(f"Mode: {result['primary_mode']} ({result['confidence']:.0%})")
            if result["matched_signals"]:
                print(f"Signals: {', '.join(result['matched_signals'])}")
            if args.context:
                print()
                print(result.get("context_text", ""))
        else:
            print("No mode detected")


if __name__ == "__main__":
    main()
