#!/usr/bin/env python3
"""
Semantic Triggers for Claude Memory

Detects topic keywords in user messages and auto-fetches relevant memory.
When user mentions "docker", automatically retrieves docker-related decisions.

Usage:
  python semantic_triggers.py "user message" --project gyst
"""

import json
import sys
import re
from pathlib import Path
from collections import defaultdict

MEMORY_ROOT = Path.home() / ".claude-dash"

# Topic keywords and their related search terms
TOPIC_TRIGGERS = {
    "docker": {
        "keywords": ["docker", "container", "dockerfile", "compose", "image"],
        "search_terms": ["docker", "container", "compose"],
        "memory_types": ["decisions", "observations", "infrastructure"]
    },
    "ollama": {
        "keywords": ["ollama", "llm", "local ai", "metal gpu", "inference"],
        "search_terms": ["ollama", "llm", "model", "inference"],
        "memory_types": ["decisions", "infrastructure"]
    },
    "database": {
        "keywords": ["database", "postgres", "sql", "firestore", "mongodb", "db"],
        "search_terms": ["database", "postgres", "sql", "db", "query"],
        "memory_types": ["decisions", "schema"]
    },
    "auth": {
        "keywords": ["auth", "login", "authentication", "password", "token", "session"],
        "search_terms": ["auth", "login", "token", "session"],
        "memory_types": ["decisions", "observations"]
    },
    "performance": {
        "keywords": ["slow", "fast", "optimize", "performance", "speed", "memory", "cpu"],
        "search_terms": ["performance", "optimize", "speed", "slow"],
        "memory_types": ["decisions", "observations"]
    },
    "api": {
        "keywords": ["api", "endpoint", "rest", "graphql", "request", "response"],
        "search_terms": ["api", "endpoint", "request"],
        "memory_types": ["decisions", "observations"]
    },
    "testing": {
        "keywords": ["test", "testing", "jest", "pytest", "spec", "coverage"],
        "search_terms": ["test", "testing", "spec"],
        "memory_types": ["decisions", "patterns"]
    },
    "deployment": {
        "keywords": ["deploy", "production", "staging", "ci", "cd", "pipeline"],
        "search_terms": ["deploy", "production", "pipeline"],
        "memory_types": ["decisions", "infrastructure"]
    }
}


def detect_topics(message):
    """Detect which topics are mentioned in the message."""
    message_lower = message.lower()
    detected = []

    for topic, config in TOPIC_TRIGGERS.items():
        for keyword in config["keywords"]:
            if re.search(r'\b' + re.escape(keyword) + r'\b', message_lower):
                detected.append(topic)
                break  # Only count topic once

    return detected


def search_decisions(search_terms, project_id=None):
    """Search decisions for matching terms."""
    results = []

    # Search project decisions
    if project_id:
        decisions_path = MEMORY_ROOT / "projects" / project_id / "decisions.json"
        if decisions_path.exists():
            try:
                data = json.loads(decisions_path.read_text())
                for d in data.get("decisions", []):
                    decision_text = d.get("decision", "") if isinstance(d, dict) else str(d)
                    for term in search_terms:
                        if term.lower() in decision_text.lower():
                            results.append({"type": "decision", "text": decision_text, "project": project_id})
                            break
            except (json.JSONDecodeError, IOError, KeyError) as e:
                pass  # File unreadable or malformed

    # Search global infrastructure
    infra_path = MEMORY_ROOT / "global" / "infrastructure.json"
    if infra_path.exists():
        try:
            data = json.loads(infra_path.read_text())
            for d in data.get("decisions", []):
                decision_text = d.get("decision", "") if isinstance(d, dict) else str(d)
                for term in search_terms:
                    if term.lower() in decision_text.lower():
                        results.append({"type": "infrastructure", "text": decision_text})
                        break
        except (json.JSONDecodeError, IOError, KeyError) as e:
            pass  # File unreadable or malformed

    return results[:5]  # Limit results


def search_observations(search_terms, project_id=None):
    """Search observations for matching terms."""
    results = []

    obs_path = MEMORY_ROOT / "sessions" / "observations.json"
    if obs_path.exists():
        try:
            data = json.loads(obs_path.read_text())
            for o in data.get("observations", []):
                if project_id and o.get("projectId") != project_id:
                    continue

                obs_text = o.get("observation", "")
                category = o.get("category", "")

                for term in search_terms:
                    if term.lower() in obs_text.lower():
                        results.append({
                            "type": "observation",
                            "category": category,
                            "text": obs_text
                        })
                        break
        except (json.JSONDecodeError, IOError, KeyError) as e:
            pass  # File unreadable or malformed

    return results[:5]


def search_patterns(search_terms):
    """Search learned patterns."""
    results = []

    patterns_path = MEMORY_ROOT / "patterns" / "patterns.json"
    if patterns_path.exists():
        try:
            data = json.loads(patterns_path.read_text())
            for p in data.get("learned_patterns", []):
                phrase = p.get("phrase", "")
                mode = p.get("mode", "")

                for term in search_terms:
                    if term.lower() in phrase.lower():
                        results.append({
                            "type": "pattern",
                            "phrase": phrase,
                            "mode": mode
                        })
                        break
        except (json.JSONDecodeError, IOError, KeyError) as e:
            pass  # File unreadable or malformed

    return results[:3]


def search_correction_patterns(search_terms):
    """Search learned correction patterns from transcript analysis."""
    results = []

    corrections_path = MEMORY_ROOT / "learning" / "corrections.json"
    if corrections_path.exists():
        try:
            data = json.loads(corrections_path.read_text())
            patterns = data.get("patterns", {})

            for key, pattern_data in patterns.items():
                if key in ["extracted_from_transcripts", "recurring_errors"]:
                    continue

                pattern_text = pattern_data.get("pattern", "")
                projects = pattern_data.get("projects", [])
                priority = pattern_data.get("priority", "normal")

                for term in search_terms:
                    if term.lower() in pattern_text.lower() or term.lower() in key.lower():
                        results.append({
                            "type": "correction_pattern",
                            "key": key,
                            "pattern": pattern_text,
                            "projects": projects,
                            "priority": priority
                        })
                        break

            # Also check recurring errors
            recurring = patterns.get("recurring_errors", {})
            for error_key, error_data in recurring.items():
                error_text = error_data.get("error", "")
                fix = error_data.get("fix", error_data.get("possible_cause", ""))

                for term in search_terms:
                    if term.lower() in error_text.lower() or term.lower() in error_key.lower():
                        results.append({
                            "type": "recurring_error",
                            "error": error_text,
                            "fix": fix
                        })
                        break

        except (json.JSONDecodeError, IOError, KeyError) as e:
            pass

    return results[:3]


def get_topic_memory(topics, project_id=None):
    """Get all relevant memory for detected topics."""
    all_results = defaultdict(list)

    for topic in topics:
        config = TOPIC_TRIGGERS.get(topic, {})
        search_terms = config.get("search_terms", [topic])
        memory_types = config.get("memory_types", ["decisions"])

        if "decisions" in memory_types or "infrastructure" in memory_types:
            decisions = search_decisions(search_terms, project_id)
            all_results["decisions"].extend(decisions)

        if "observations" in memory_types:
            observations = search_observations(search_terms, project_id)
            all_results["observations"].extend(observations)

        if "patterns" in memory_types:
            patterns = search_patterns(search_terms)
            all_results["patterns"].extend(patterns)

        # Always check correction patterns for relevant topics
        correction_patterns = search_correction_patterns(search_terms)
        all_results["correction_patterns"].extend(correction_patterns)

    return dict(all_results)


def format_memory_context(topics, memory):
    """Format memory for injection."""
    if not memory or not any(memory.values()):
        return None

    lines = [f"[RELEVANT MEMORY for: {', '.join(topics)}]"]

    # Decisions first (most important)
    decisions = memory.get("decisions", [])
    if decisions:
        lines.append("\nPast decisions:")
        seen = set()
        for d in decisions[:4]:
            text = d.get("text", "")[:100]
            if text not in seen:
                seen.add(text)
                lines.append(f"  • {text}")

    # Correction patterns (learned from past corrections)
    correction_patterns = memory.get("correction_patterns", [])
    if correction_patterns:
        lines.append("\nLearned from corrections:")
        seen = set()
        for cp in correction_patterns[:3]:
            if cp.get("type") == "correction_pattern":
                text = cp.get("pattern", "")[:100]
                priority = cp.get("priority", "")
                if text not in seen:
                    seen.add(text)
                    prefix = "⚠️ " if priority == "high" else "• "
                    lines.append(f"  {prefix}{text}")
            elif cp.get("type") == "recurring_error":
                error = cp.get("error", "")[:60]
                fix = cp.get("fix", "")[:60]
                if error not in seen:
                    seen.add(error)
                    lines.append(f"  • Error: {error}")
                    if fix:
                        lines.append(f"    Fix: {fix}")

    # Observations
    observations = memory.get("observations", [])
    if observations:
        lines.append("\nLearned:")
        seen = set()
        for o in observations[:3]:
            text = o.get("text", "")[:80]
            if text not in seen:
                seen.add(text)
                lines.append(f"  • [{o.get('category', '')}] {text}")

    return "\n".join(lines)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Semantic memory triggers")
    parser.add_argument("message", help="User message to analyze")
    parser.add_argument("--project", help="Project ID")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    # Detect topics
    topics = detect_topics(args.message)

    if not topics:
        # No topics detected
        sys.exit(0)

    # Get relevant memory
    memory = get_topic_memory(topics, args.project)

    if args.json:
        print(json.dumps({
            "topics": topics,
            "memory": memory
        }, indent=2))
    else:
        context = format_memory_context(topics, memory)
        if context:
            print(context)


if __name__ == "__main__":
    main()
