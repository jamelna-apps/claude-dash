#!/usr/bin/env python3
"""
Ollama-based File Summarizer for Claude-Dash

Processes files marked with needsResummarization: true in summaries.json.
Uses local Ollama for zero API cost.

Usage:
  python summarizer.py <project-id> [--limit N]
"""

import json
import sys
import argparse
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime

MEMORY_ROOT = Path.home() / ".claude-dash"
OLLAMA_URL = "http://localhost:11434"
OLLAMA_MODEL = "gemma3:4b-it-qat"  # Fast, good quality


def call_ollama(prompt: str, model: str = OLLAMA_MODEL) -> str:
    """Call local Ollama for summarization."""
    data = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.2,
            "num_predict": 500
        }
    }).encode('utf-8')

    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/generate",
        data=data,
        headers={"Content-Type": "application/json"}
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            result = json.loads(response.read().decode('utf-8'))
            return result.get("response", "")
    except urllib.error.URLError as e:
        print(f"    Ollama error: {e}")
        return ""
    except Exception as e:
        print(f"    Error: {e}")
        return ""


def load_summaries(project_id: str) -> dict:
    """Load summaries.json for a project."""
    path = MEMORY_ROOT / "projects" / project_id / "summaries.json"
    if not path.exists():
        return {"version": "1.0", "project": project_id, "files": {}}
    return json.loads(path.read_text())


def save_summaries(project_id: str, summaries: dict):
    """Save updated summaries.json."""
    path = MEMORY_ROOT / "projects" / project_id / "summaries.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    summaries["lastUpdated"] = datetime.now().isoformat()
    path.write_text(json.dumps(summaries, indent=2))


def get_project_path(project_id: str) -> str:
    """Get project path from config."""
    config_path = MEMORY_ROOT / "config.json"
    if not config_path.exists():
        return None
    config = json.loads(config_path.read_text())
    project = next((p for p in config.get("projects", []) if p["id"] == project_id), None)
    return project.get("path") if project else None


def get_pending_files(summaries: dict) -> list:
    """Find files marked as needing re-summarization."""
    return [
        (path, data) for path, data in summaries.get("files", {}).items()
        if data and data.get("needsResummarization", False)
    ]


def summarize_file(project_path: str, file_path: str, structural_data: dict) -> dict:
    """Summarize a single file using Ollama."""
    full_path = Path(project_path) / file_path

    if not full_path.exists():
        return {"error": "File not found", "summary": None}

    try:
        content = full_path.read_text()
    except Exception as e:
        return {"error": str(e), "summary": None}

    # Skip very large files
    if len(content) > 30000:
        return {
            "summary": "Large file - contains extensive code",
            "purpose": "Complex module (too large for quick summary)",
            "keyLogic": None,
            "skipped": True
        }

    # Skip binary/non-code files
    if file_path.endswith(('.png', '.jpg', '.svg', '.ico', '.woff', '.ttf', '.eot')):
        return {
            "summary": "Binary/asset file",
            "purpose": "Static asset",
            "skipped": True
        }

    # Truncate content for prompt
    truncated = content[:8000]
    if len(content) > 8000:
        truncated += "\n... [truncated]"

    # Build structural context
    struct_info = []
    if structural_data:
        if structural_data.get("componentName"):
            struct_info.append(f"Component: {structural_data['componentName']}")
        if structural_data.get("functions"):
            funcs = [f.get("name", f) if isinstance(f, dict) else f for f in structural_data["functions"][:5]]
            struct_info.append(f"Functions: {', '.join(funcs)}")
        if structural_data.get("hooks"):
            struct_info.append(f"Hooks: {', '.join(structural_data['hooks'][:5])}")

    struct_text = "\n".join(struct_info) if struct_info else "No structural data"

    prompt = f"""Analyze this code file and provide a brief summary.

FILE: {file_path}

STRUCTURE:
{struct_text}

CODE:
```
{truncated}
```

Respond with ONLY a JSON object (no markdown, no explanation):
{{"summary": "1-2 sentence description of what this file does", "purpose": "main purpose in 5 words or less", "keyLogic": "most important function or pattern"}}"""

    response = call_ollama(prompt)

    if not response:
        return {
            "summary": "Failed to generate summary",
            "purpose": None,
            "error": "No response from Ollama"
        }

    # Parse JSON from response
    try:
        import re
        # Try to find JSON object in response
        json_match = re.search(r'\{[^{}]*"summary"[^{}]*\}', response, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())

        # Fallback: try parsing entire response
        return json.loads(response.strip())
    except json.JSONDecodeError:
        # Use response as summary if JSON parsing fails
        clean = response.strip()[:200]
        return {
            "summary": clean if clean else "Summary generation failed",
            "purpose": None,
            "parseError": True
        }


def main():
    parser = argparse.ArgumentParser(description="Ollama File Summarizer")
    parser.add_argument("project_id", help="Project ID (e.g., 'coachdesk')")
    parser.add_argument("--limit", type=int, default=10, help="Max files to process")
    parser.add_argument("--all", action="store_true", help="Process all files, not just marked ones")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be processed")
    args = parser.parse_args()

    # Get project path
    project_path = get_project_path(args.project_id)
    if not project_path:
        print(f"Project not found: {args.project_id}")
        sys.exit(1)

    print(f"Project: {args.project_id} ({project_path})")

    # Load summaries
    summaries = load_summaries(args.project_id)

    # Get files to process
    if args.all:
        files_to_process = [(p, d) for p, d in summaries.get("files", {}).items() if d]
    else:
        files_to_process = get_pending_files(summaries)

    if not files_to_process:
        print("No files pending summarization")
        return

    files_to_process = files_to_process[:args.limit]
    print(f"Files to process: {len(files_to_process)}")

    if args.dry_run:
        for path, _ in files_to_process:
            print(f"  Would process: {path}")
        return

    # Check Ollama is available
    try:
        urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=5)
    except Exception as e:
        print(f"Error: Ollama not available at {OLLAMA_URL}")
        print("Start Ollama with: ollama serve")
        sys.exit(1)

    print(f"Using model: {OLLAMA_MODEL}")
    print()

    processed = 0
    errors = 0

    for file_path, data in files_to_process:
        print(f"  Summarizing: {file_path}")

        result = summarize_file(project_path, file_path, data or {})

        # Update summaries
        if file_path not in summaries["files"]:
            summaries["files"][file_path] = {}

        summaries["files"][file_path].update(result)
        summaries["files"][file_path]["needsResummarization"] = False
        summaries["files"][file_path]["summarizedAt"] = datetime.now().isoformat()
        summaries["files"][file_path]["summarizedBy"] = "ollama"

        if result.get("error") or result.get("skipped"):
            errors += 1
            if result.get("error"):
                print(f"    Error: {result['error']}")
        else:
            processed += 1
            summary = result.get("summary", "")[:60]
            print(f"    ✓ {summary}...")

    # Save
    save_summaries(args.project_id, summaries)

    print(f"\nDone! Processed: {processed}, Skipped/Errors: {errors}")


if __name__ == "__main__":
    main()
