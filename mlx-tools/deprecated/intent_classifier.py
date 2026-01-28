#!/usr/bin/env python3
"""
MLX Intent Classifier for Claude Memory System

Classifies user queries and suggests which memory files to read first.
Helps route queries to the right information without scanning everything.

Usage:
  source ~/.claude-dash/mlx-env/bin/activate
  python intent_classifier.py "where is the login screen?"
  python intent_classifier.py "what collections store user data?"
  python intent_classifier.py "how does navigation work?"
"""

import json
import sys
import argparse
from pathlib import Path

try:
    from mlx_lm import load, generate
except ImportError:
    print("Error: mlx-lm not installed. Run: pip install mlx-lm")
    sys.exit(1)

MEMORY_ROOT = Path.home() / ".claude-dash"
DEFAULT_MODEL = "mlx-community/Llama-3.2-3B-Instruct-4bit"

INTENTS = {
    "find_file": {
        "description": "Find a specific file, screen, or component",
        "memory_files": ["summaries.json", "functions.json"],
        "keywords": ["where", "find", "locate", "which file", "screen", "component"]
    },
    "understand_schema": {
        "description": "Understand database schema, collections, or data structure",
        "memory_files": ["schema.json"],
        "keywords": ["collection", "database", "firestore", "field", "data", "store", "schema"]
    },
    "understand_navigation": {
        "description": "Understand screen navigation or app flow",
        "memory_files": ["graph.json"],
        "keywords": ["navigation", "navigate", "flow", "screen", "route", "go to"]
    },
    "find_function": {
        "description": "Find a specific function or method",
        "memory_files": ["functions.json"],
        "keywords": ["function", "method", "handler", "callback", "how does", "implement"]
    },
    "understand_dependencies": {
        "description": "Understand file imports or dependencies",
        "memory_files": ["graph.json", "summaries.json"],
        "keywords": ["import", "depend", "use", "require", "relationship"]
    },
    "understand_feature": {
        "description": "Understand how a feature works",
        "memory_files": ["features.json", "summaries.json", "graph.json"],
        "keywords": ["feature", "how does", "works", "implement", "functionality"]
    },
    "find_preference": {
        "description": "Check coding preferences or conventions",
        "memory_files": ["preferences.json", "decisions.json"],
        "keywords": ["prefer", "convention", "style", "should I", "always", "never"]
    }
}

def classify_with_keywords(query):
    """Simple keyword-based classification."""
    query_lower = query.lower()
    scores = {}

    for intent, data in INTENTS.items():
        score = sum(1 for kw in data["keywords"] if kw in query_lower)
        if score > 0:
            scores[intent] = score

    if scores:
        return max(scores.items(), key=lambda x: x[1])[0]
    return None

def classify_with_llm(model, tokenizer, query):
    """Use LLM for more nuanced classification."""
    intent_descriptions = "\n".join(
        f"- {name}: {data['description']}"
        for name, data in INTENTS.items()
    )

    prompt = f"""Classify this user query into one of these intents:

{intent_descriptions}

Query: "{query}"

Respond with ONLY the intent name (e.g., "find_file"). If unsure, respond with the most likely intent."""

    response = generate(
        model,
        tokenizer,
        prompt=prompt,
        max_tokens=50,
        temp=0.1
    )

    # Extract intent from response
    response_lower = response.lower().strip()
    for intent in INTENTS.keys():
        if intent in response_lower:
            return intent

    # Fallback to keyword matching
    return classify_with_keywords(query)

def get_recommendations(intent, query):
    """Get memory file recommendations for an intent."""
    if intent not in INTENTS:
        return {
            "intent": "unknown",
            "description": "Could not classify query",
            "read_first": ["summaries.json"],
            "also_check": ["functions.json", "graph.json"]
        }

    data = INTENTS[intent]
    return {
        "intent": intent,
        "description": data["description"],
        "read_first": data["memory_files"],
        "also_check": [f for f in ["summaries.json", "functions.json", "schema.json", "graph.json"]
                       if f not in data["memory_files"]][:2]
    }

def main():
    parser = argparse.ArgumentParser(description="MLX Intent Classifier")
    parser.add_argument("query", help="User query to classify")
    parser.add_argument("--llm", action="store_true", help="Use LLM for classification")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="MLX model")
    args = parser.parse_args()

    # Try keyword classification first
    keyword_intent = classify_with_keywords(args.query)

    if args.llm or not keyword_intent:
        print(f"Loading model: {args.model}")
        model, tokenizer = load(args.model)
        intent = classify_with_llm(model, tokenizer, args.query)
    else:
        intent = keyword_intent

    recommendations = get_recommendations(intent, args.query)

    print(f"\nQuery: \"{args.query}\"")
    print(f"\nIntent: {recommendations['intent']}")
    print(f"Description: {recommendations['description']}")
    print(f"\nRead these memory files first:")
    for f in recommendations['read_first']:
        print(f"  - ~/.claude-dash/projects/{{project}}/{f}")
    print(f"\nAlso check if needed:")
    for f in recommendations['also_check']:
        print(f"  - ~/.claude-dash/projects/{{project}}/{f}")

    # Output as JSON for programmatic use
    print(f"\n--- JSON ---")
    print(json.dumps(recommendations, indent=2))

if __name__ == "__main__":
    main()
