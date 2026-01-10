#!/usr/bin/env python3
"""
MLX Local Summarizer for Claude Memory System

Re-summarizes files locally using MLX models - zero API token cost.
Processes files marked with needsResummarization: true in summaries.json.

Usage:
  source ~/.claude-dash/mlx-env/bin/activate
  python summarizer.py <project-id> [--limit N] [--model MODEL]
"""

import json
import os
import sys
import argparse
from pathlib import Path

# MLX imports
try:
    from mlx_lm import load, generate
except ImportError:
    print("Error: mlx-lm not installed. Run: pip install mlx-lm")
    sys.exit(1)

MEMORY_ROOT = Path.home() / ".claude-dash"
DEFAULT_MODEL = "mlx-community/Llama-3.2-3B-Instruct-4bit"

def load_summaries(project_id):
    """Load summaries.json for a project."""
    path = MEMORY_ROOT / "projects" / project_id / "summaries.json"
    if not path.exists():
        raise FileNotFoundError(f"Summaries not found: {path}")
    return json.loads(path.read_text())

def save_summaries(project_id, summaries):
    """Save updated summaries.json."""
    path = MEMORY_ROOT / "projects" / project_id / "summaries.json"
    path.write_text(json.dumps(summaries, indent=2))

def get_files_needing_summarization(summaries):
    """Find files marked as needing re-summarization."""
    return [
        (path, data) for path, data in summaries.get("files", {}).items()
        if data.get("needsResummarization", False)
    ]

def generate_prompt(file_path, content, structural_data):
    """Generate a summarization prompt."""
    truncated = content[:12000] + "\n... [truncated]" if len(content) > 12000 else content

    return f"""Analyze this code file and provide a brief summary.

FILE: {file_path}

STRUCTURE:
- Component: {structural_data.get('componentName', 'No')}
- Functions: {', '.join(f['name'] for f in structural_data.get('functions', [])) or 'None'}
- Hooks: {', '.join(structural_data.get('hooks', [])) or 'None'}
- State: {', '.join(structural_data.get('stateVariables', [])) or 'None'}

CODE:
```
{truncated}
```

Respond with ONLY a JSON object:
{{"summary": "1-2 sentence summary", "purpose": "main purpose", "keyLogic": "most important function/logic", "complexity": "low|medium|high"}}"""

def summarize_file(model, tokenizer, project_path, file_path, structural_data):
    """Summarize a single file using MLX."""
    full_path = Path(project_path) / file_path

    if not full_path.exists():
        return {"error": "File not found"}

    try:
        content = full_path.read_text()
    except Exception as e:
        return {"error": str(e)}

    # Skip very large files
    if len(content) > 50000:
        return {
            "summary": "Large file - manual review recommended",
            "purpose": "Unknown (file too large)",
            "keyLogic": None,
            "complexity": "high",
            "skipped": True
        }

    prompt = generate_prompt(file_path, content, structural_data)

    # Generate with MLX
    response = generate(
        model,
        tokenizer,
        prompt=prompt,
        max_tokens=300,
        temp=0.1
    )

    # Parse JSON from response
    try:
        # Find JSON in response
        import re
        json_match = re.search(r'\{[^{}]*\}', response)
        if json_match:
            return json.loads(json_match.group())
        raise ValueError("No JSON found")
    except Exception as e:
        return {
            "summary": response[:200] if response else "Failed to generate",
            "purpose": None,
            "keyLogic": None,
            "complexity": "unknown",
            "parseError": str(e)
        }

def main():
    parser = argparse.ArgumentParser(description="MLX Local Summarizer")
    parser.add_argument("project_id", help="Project ID (e.g., 'gyst')")
    parser.add_argument("--limit", type=int, default=10, help="Max files to process")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="MLX model to use")
    parser.add_argument("--all", action="store_true", help="Process all files, not just marked ones")
    args = parser.parse_args()

    # Load config to get project path
    config_path = MEMORY_ROOT / "config.json"
    config = json.loads(config_path.read_text())

    project = next((p for p in config["projects"] if p["id"] == args.project_id), None)
    if not project:
        print(f"Project not found: {args.project_id}")
        sys.exit(1)

    project_path = project["path"]

    print(f"Loading model: {args.model}")
    model, tokenizer = load(args.model)

    print(f"Loading summaries for {args.project_id}...")
    summaries = load_summaries(args.project_id)

    if args.all:
        files_to_process = [(p, d) for p, d in summaries.get("files", {}).items()]
    else:
        files_to_process = get_files_needing_summarization(summaries)

    files_to_process = files_to_process[:args.limit]

    print(f"Processing {len(files_to_process)} files...")

    processed = 0
    errors = 0

    for file_path, data in files_to_process:
        print(f"  {file_path}")

        result = summarize_file(model, tokenizer, project_path, file_path, data)

        # Update summaries
        summaries["files"][file_path].update(result)
        summaries["files"][file_path]["needsResummarization"] = False
        summaries["files"][file_path]["summarizedBy"] = "mlx-local"

        if result.get("error"):
            errors += 1
        else:
            processed += 1

    # Save
    summaries["lastUpdated"] = __import__("datetime").datetime.now().isoformat()
    save_summaries(args.project_id, summaries)

    print(f"\nDone! Processed: {processed}, Errors: {errors}")

if __name__ == "__main__":
    main()
