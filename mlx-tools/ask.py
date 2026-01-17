#!/usr/bin/env python3
"""
MLX Ask - Natural Language Q&A using Ollama

Ask questions about your codebase in plain English.
Uses local Ollama for inference + memory files for context.

Usage:
  python ask.py <project> "your question"
  python ask.py gyst "how does authentication work?"
  python ask.py gyst "what files handle user login?"
"""

import json
import sys
import argparse
from pathlib import Path

MEMORY_ROOT = Path.home() / ".claude-dash"

# Import ollama client
sys.path.insert(0, str(MEMORY_ROOT / "mlx-tools"))
from ollama_client import OllamaClient
from query import query as keyword_query, extract_search_terms


def load_context(project_id: str, question: str) -> str:
    """Load relevant context from memory files based on question."""
    project_dir = MEMORY_ROOT / "projects" / project_id

    context_parts = []

    # Get keyword search results first
    search_result = keyword_query(project_id, question)

    # Add file matches
    if "files" in search_result.get("results", {}):
        files = search_result["results"]["files"][:5]
        if files:
            context_parts.append("## Relevant Files")
            for f in files:
                context_parts.append(f"- **{f['file']}**: {f.get('summary', f.get('purpose', ''))[:200]}")

    # Add function matches
    if "functions" in search_result.get("results", {}):
        funcs = search_result["results"]["functions"][:5]
        if funcs:
            context_parts.append("\n## Relevant Functions")
            for f in funcs:
                context_parts.append(f"- `{f['function']}()` in {f['file']}:{f['line']}")

    # Add schema info if question mentions data/database
    terms = extract_search_terms(question)
    data_keywords = {"data", "database", "store", "save", "collection", "field", "schema", "firestore"}
    if any(t in data_keywords for t in terms):
        schema_path = project_dir / "schema.json"
        if schema_path.exists():
            schema = json.loads(schema_path.read_text())
            collections = list(schema.get("collections", {}).keys())[:10]
            if collections:
                context_parts.append(f"\n## Database Collections: {', '.join(collections)}")

    # Add navigation info if question mentions screens/navigation
    nav_keywords = {"screen", "navigate", "page", "route", "flow", "go"}
    if any(t in nav_keywords for t in terms):
        graph_path = project_dir / "graph.json"
        if graph_path.exists():
            graph = json.loads(graph_path.read_text())
            screens = list(graph.get("screenNavigation", {}).keys())[:10]
            if screens:
                context_parts.append(f"\n## Screens: {', '.join(screens)}")

    return "\n".join(context_parts) if context_parts else "No specific context found."


def ask(project_id: str, question: str, client: OllamaClient) -> str:
    """Ask a question about the project."""

    # Load project info
    config = json.loads((MEMORY_ROOT / "config.json").read_text())
    project = next((p for p in config["projects"] if p["id"] == project_id), None)

    if not project:
        return f"Project not found: {project_id}"

    # Get relevant context
    context = load_context(project_id, question)

    # Build prompt
    system_prompt = f"""You are a helpful assistant that answers questions about the {project['displayName']} codebase.
Use the provided context to answer questions accurately. If the context doesn't contain enough information, say so.
Be concise but complete. Reference specific files and functions when relevant."""

    user_prompt = f"""## Context from {project['displayName']}
{context}

## Question
{question}

## Answer"""

    # Generate response
    response = client.generate(user_prompt, system=system_prompt)

    if response:
        return response
    else:
        return "Error: Could not generate response. Is Ollama running?"


def interactive_mode(project_id: str, client: OllamaClient):
    """Interactive chat mode."""
    config = json.loads((MEMORY_ROOT / "config.json").read_text())
    project = next((p for p in config["projects"] if p["id"] == project_id), None)

    if not project:
        print(f"Project not found: {project_id}")
        return

    print(f"\n=== Chat with {project['displayName']} ===")
    print("Type 'quit' or 'exit' to end, 'clear' to reset context\n")

    while True:
        try:
            question = input("You: ").strip()

            if not question:
                continue
            if question.lower() in ['quit', 'exit', 'q']:
                print("Goodbye!")
                break
            if question.lower() == 'clear':
                print("Context cleared.\n")
                continue

            print("\nThinking...", end="\r")
            response = ask(project_id, question, client)
            print(f"AI: {response}\n")

        except KeyboardInterrupt:
            print("\nGoodbye!")
            break
        except EOFError:
            break


def main():
    parser = argparse.ArgumentParser(description="Ask questions about your codebase")
    parser.add_argument("project", help="Project ID")
    parser.add_argument("question", nargs="?", help="Question to ask (omit for interactive mode)")
    parser.add_argument("--chat", "-c", action="store_true", help="Interactive chat mode")
    parser.add_argument("--model", "-m", help="Ollama model to use (overrides task-based routing)")
    args = parser.parse_args()

    # Initialize Ollama client with task-based routing
    # If explicit model provided, use it; otherwise use task='ask' for automatic selection
    if args.model:
        client = OllamaClient(model=args.model)
    else:
        client = OllamaClient(task='ask')

    if not client.available:
        print("Error: Ollama is not running.")
        print("Start it with: ollama serve")
        sys.exit(1)

    # Interactive or single question mode
    if args.chat or not args.question:
        interactive_mode(args.project, client)
    else:
        response = ask(args.project, args.question, client)
        print(response)


if __name__ == "__main__":
    main()
