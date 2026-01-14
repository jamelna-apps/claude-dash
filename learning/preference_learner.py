#!/usr/bin/env python3
"""
Preference Learner

Infers coding preferences from user modifications to Claude's suggestions.
Tracks patterns when user edits Claude's output.

Usage:
  # Record a preference observation
  python preference_learner.py --observe --original "const x" --modified "let x" --category "variables"

  # Analyze git history for preference patterns
  python preference_learner.py --analyze-history /path/to/project

  # Get inferred preferences
  python preference_learner.py --get-preferences
"""

import json
import subprocess
import sys
import re
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict

MEMORY_ROOT = Path.home() / ".claude-dash"
PREFERENCES_FILE = MEMORY_ROOT / "learning" / "inferred_preferences.json"


def load_preferences():
    """Load inferred preferences."""
    if not PREFERENCES_FILE.exists():
        return {
            "observations": [],
            "inferred": {
                "naming": {},
                "syntax": {},
                "patterns": {},
                "style": {}
            },
            "confidence": {}
        }

    try:
        return json.loads(PREFERENCES_FILE.read_text())
    except:
        return {"observations": [], "inferred": {}, "confidence": {}}


def save_preferences(data):
    """Save preferences."""
    PREFERENCES_FILE.parent.mkdir(parents=True, exist_ok=True)
    PREFERENCES_FILE.write_text(json.dumps(data, indent=2))


def record_observation(original, modified, category=None, file_type=None, context=None):
    """Record when user modifies Claude's output."""
    data = load_preferences()

    observation = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "original": original[:200],
        "modified": modified[:200],
        "category": category,
        "file_type": file_type,
        "context": context[:100] if context else None
    }

    # Try to infer the preference
    inference = infer_preference(original, modified)
    if inference:
        observation["inference"] = inference
        update_inferred_preferences(data, inference)

    data["observations"].append(observation)

    # Keep last 300 observations
    data["observations"] = data["observations"][-300:]

    save_preferences(data)
    return observation


def infer_preference(original, modified):
    """Infer what preference the change indicates."""
    inferences = []

    orig = original.strip()
    mod = modified.strip()

    # Variable declarations
    if "const " in orig and "let " in mod:
        inferences.append({"category": "syntax", "key": "variable_declaration", "prefers": "let", "over": "const"})
    elif "let " in orig and "const " in mod:
        inferences.append({"category": "syntax", "key": "variable_declaration", "prefers": "const", "over": "let"})

    # Arrow vs function
    if "function " in orig and "=>" in mod:
        inferences.append({"category": "syntax", "key": "function_style", "prefers": "arrow", "over": "function"})
    elif "=>" in orig and "function " in mod:
        inferences.append({"category": "syntax", "key": "function_style", "prefers": "function", "over": "arrow"})

    # Single vs double quotes
    if '"' in orig and "'" in mod and orig.replace('"', "'") == mod:
        inferences.append({"category": "style", "key": "quotes", "prefers": "single", "over": "double"})
    elif "'" in orig and '"' in mod and orig.replace("'", '"') == mod:
        inferences.append({"category": "style", "key": "quotes", "prefers": "double", "over": "single"})

    # Semicolons
    if orig.endswith(";") and not mod.endswith(";"):
        inferences.append({"category": "style", "key": "semicolons", "prefers": "no", "over": "yes"})
    elif not orig.endswith(";") and mod.endswith(";"):
        inferences.append({"category": "style", "key": "semicolons", "prefers": "yes", "over": "no"})

    # Trailing commas
    if ",\n" in orig and not ",\n" in mod:
        inferences.append({"category": "style", "key": "trailing_commas", "prefers": "no", "over": "yes"})

    # Comments removed
    if "//" in orig and "//" not in mod:
        inferences.append({"category": "style", "key": "inline_comments", "prefers": "minimal", "over": "verbose"})
    if "/*" in orig and "/*" not in mod:
        inferences.append({"category": "style", "key": "block_comments", "prefers": "minimal", "over": "verbose"})

    # Naming: camelCase vs snake_case
    camel_pattern = r'\b[a-z]+[A-Z][a-zA-Z]*\b'
    snake_pattern = r'\b[a-z]+_[a-z_]+\b'

    orig_camels = re.findall(camel_pattern, orig)
    mod_snakes = re.findall(snake_pattern, mod)

    if orig_camels and mod_snakes:
        inferences.append({"category": "naming", "key": "case_style", "prefers": "snake_case", "over": "camelCase"})

    # Explicit types vs inference
    if ": string" in orig or ": number" in orig or ": boolean" in orig:
        if ": string" not in mod and ": number" not in mod and ": boolean" not in mod:
            inferences.append({"category": "syntax", "key": "type_annotations", "prefers": "inferred", "over": "explicit"})

    # Spread vs Object.assign
    if "Object.assign" in orig and "..." in mod:
        inferences.append({"category": "patterns", "key": "object_merge", "prefers": "spread", "over": "Object.assign"})

    # Template literals vs concatenation
    if "+" in orig and "`" in mod and "${" in mod:
        inferences.append({"category": "syntax", "key": "string_interpolation", "prefers": "template_literals", "over": "concatenation"})

    return inferences if inferences else None


def update_inferred_preferences(data, inferences):
    """Update inferred preferences based on observations."""
    for inf in inferences:
        category = inf["category"]
        key = inf["key"]
        prefers = inf["prefers"]

        if category not in data["inferred"]:
            data["inferred"][category] = {}

        if key not in data["inferred"][category]:
            data["inferred"][category][key] = {"counts": {}, "preferred": None}

        pref_data = data["inferred"][category][key]

        if prefers not in pref_data["counts"]:
            pref_data["counts"][prefers] = 0
        pref_data["counts"][prefers] += 1

        # Update preferred based on counts
        if pref_data["counts"]:
            max_pref = max(pref_data["counts"], key=pref_data["counts"].get)
            max_count = pref_data["counts"][max_pref]
            total = sum(pref_data["counts"].values())

            if max_count >= 3 and max_count / total >= 0.6:
                pref_data["preferred"] = max_pref

                # Update confidence
                conf_key = f"{category}.{key}"
                data["confidence"][conf_key] = max_count / total


def analyze_git_diffs(project_path, limit=50):
    """Analyze recent git diffs to find user edits to Claude-generated code."""
    # This is a simplified version - would need access to Claude's change history
    # to properly identify which changes were to Claude's output

    # For now, look for patterns in recent commits
    cmd = f'git log -p -{limit} --pretty=format:"COMMIT:%h" -- "*.ts" "*.tsx" "*.js" "*.jsx"'

    try:
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=60
        )

        if result.returncode != 0:
            return []

        # Parse diffs for style patterns
        patterns_found = defaultdict(int)

        # Look for consistent patterns
        content = result.stdout

        # Quote style
        single_quotes = len(re.findall(r"^\+.*'[^']*'", content, re.MULTILINE))
        double_quotes = len(re.findall(r'^\+.*"[^"]*"', content, re.MULTILINE))

        if single_quotes > double_quotes * 1.5:
            patterns_found["quotes:single"] = single_quotes
        elif double_quotes > single_quotes * 1.5:
            patterns_found["quotes:double"] = double_quotes

        # Semicolons
        with_semi = len(re.findall(r"^\+.*;\s*$", content, re.MULTILINE))
        without_semi = len(re.findall(r"^\+.*[^;{]\s*$", content, re.MULTILINE))

        if with_semi > without_semi * 2:
            patterns_found["semicolons:yes"] = with_semi
        elif without_semi > with_semi * 2:
            patterns_found["semicolons:no"] = without_semi

        # Arrow functions vs function keyword
        arrows = len(re.findall(r"^\+.*=>", content, re.MULTILINE))
        functions = len(re.findall(r"^\+.*\bfunction\b", content, re.MULTILINE))

        if arrows > functions * 2:
            patterns_found["functions:arrow"] = arrows
        elif functions > arrows:
            patterns_found["functions:keyword"] = functions

        return dict(patterns_found)

    except Exception as e:
        return {"error": str(e)}


def get_preferences_for_injection():
    """Get high-confidence preferences for context injection."""
    data = load_preferences()

    inferred = data.get("inferred", {})
    confidence = data.get("confidence", {})

    high_confidence = []

    for category, prefs in inferred.items():
        for key, pref_data in prefs.items():
            if pref_data.get("preferred"):
                conf_key = f"{category}.{key}"
                conf = confidence.get(conf_key, 0)

                if conf >= 0.6:
                    high_confidence.append({
                        "category": category,
                        "preference": f"{key}: {pref_data['preferred']}",
                        "confidence": conf
                    })

    return high_confidence


def format_preferences_for_injection(preferences):
    """Format preferences for context injection."""
    if not preferences:
        return None

    lines = ["[LEARNED STYLE PREFERENCES]"]

    for p in preferences:
        conf_pct = int(p["confidence"] * 100)
        lines.append(f"  - {p['preference']} ({conf_pct}% confidence)")

    return "\n".join(lines)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Preference learner")
    parser.add_argument("--observe", action="store_true", help="Record an observation")
    parser.add_argument("--original", help="Original code")
    parser.add_argument("--modified", help="Modified code")
    parser.add_argument("--category", help="Category")
    parser.add_argument("--analyze-history", help="Analyze git history at path")
    parser.add_argument("--get-preferences", action="store_true", help="Get inferred preferences")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    if args.observe:
        if not args.original or not args.modified:
            print("Error: --original and --modified required")
            sys.exit(1)

        obs = record_observation(
            args.original,
            args.modified,
            category=args.category
        )

        if args.json:
            print(json.dumps(obs, indent=2))
        else:
            inf = obs.get("inference", [])
            if inf:
                for i in inf:
                    print(f"Inferred: prefers {i['prefers']} over {i['over']} for {i['key']}")
            else:
                print("Observation recorded, no preference inferred")

    elif args.analyze_history:
        patterns = analyze_git_diffs(args.analyze_history)

        if args.json:
            print(json.dumps(patterns, indent=2))
        else:
            for pattern, count in patterns.items():
                print(f"{pattern}: {count} occurrences")

    elif args.get_preferences:
        prefs = get_preferences_for_injection()

        if args.json:
            print(json.dumps(prefs, indent=2))
        else:
            formatted = format_preferences_for_injection(prefs)
            if formatted:
                print(formatted)
            else:
                print("No high-confidence preferences yet")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
