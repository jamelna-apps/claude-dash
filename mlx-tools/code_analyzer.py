#!/usr/bin/env python3
"""
Code Analyzer - Using Ollama for code analysis

Uses gemma3:4b-it-qat for local code understanding.
Note: For critical code work, prefer Claude (Sonnet/Opus).

Usage:
  python code_analyzer.py <project> analyze <file>   # Analyze a file
  python code_analyzer.py <project> explain <file>   # Explain code
  python code_analyzer.py <project> review <file>    # Code review
"""

import json
import sys
import argparse
import re
from pathlib import Path

MEMORY_ROOT = Path.home() / ".claude-dash"

# Import config for model routing
try:
    from config import get_model_for_task, call_ollama_generate
except ImportError:
    import os
    import urllib.request

    OLLAMA_URL = os.environ.get('OLLAMA_URL', 'http://localhost:11434')
    CODE_MODEL = os.environ.get('OLLAMA_CODE_MODEL', 'gemma3:4b-it-qat')

    def get_model_for_task(task: str, fallback_to_default: bool = True) -> str:
        return CODE_MODEL

    def call_ollama_generate(prompt: str, model: str = None, timeout: int = 60) -> str:
        model = model or CODE_MODEL
        data = json.dumps({
            'model': model,
            'prompt': prompt,
            'stream': False
        }).encode('utf-8')

        req = urllib.request.Request(
            f"{OLLAMA_URL}/api/generate",
            data=data,
            headers={'Content-Type': 'application/json'}
        )

        with urllib.request.urlopen(req, timeout=timeout) as response:
            result = json.loads(response.read().decode('utf-8'))
            return result.get('response', '')


def analyze_file(file_path: str, project_path: str) -> dict:
    """Analyze a code file."""
    full_path = Path(project_path) / file_path
    if not full_path.exists():
        return {"error": f"File not found: {full_path}"}

    content = full_path.read_text()
    if len(content) > 10000:
        content = content[:10000] + "\n... [truncated]"

    prompt = f"""Analyze this code file and provide:
1. Main purpose (1 sentence)
2. Key functions and what they do
3. Dependencies and imports used
4. Potential issues or improvements

```
{content}
```

Respond in this JSON format:
{{"purpose": "...", "functions": [{{"name": "...", "does": "..."}}], "dependencies": [...], "issues": [...]}}"""

    model = get_model_for_task('code_analysis')
    response = call_ollama_generate(prompt, model=model, timeout=120)

    try:
        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            return json.loads(json_match.group())
    except:
        pass

    return {"raw": response}


def explain_code(file_path: str, project_path: str) -> str:
    """Explain what code does in plain English."""
    full_path = Path(project_path) / file_path
    content = full_path.read_text()[:8000]

    prompt = f"""Explain this code in simple terms. What does it do? How does it work?

```
{content}
```

Explain in 3-5 sentences:"""

    model = get_model_for_task('code_explanation')
    return call_ollama_generate(prompt, model=model, timeout=90)


def review_code(file_path: str, project_path: str) -> str:
    """Review code for issues and improvements."""
    full_path = Path(project_path) / file_path
    content = full_path.read_text()[:8000]

    prompt = f"""Review this code. Look for:
- Bugs or potential issues
- Performance problems
- Security concerns
- Code quality issues
- Suggestions for improvement

```
{content}
```

List the issues found (or say "No major issues" if clean):"""

    model = get_model_for_task('code_review')
    return call_ollama_generate(prompt, model=model, timeout=120)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("project", help="Project ID")
    parser.add_argument("command", choices=["analyze", "explain", "review"])
    parser.add_argument("file", help="File path relative to project")
    args = parser.parse_args()

    # Get project path
    config = json.loads((MEMORY_ROOT / "config.json").read_text())
    project = next((p for p in config["projects"] if p["id"] == args.project), None)
    if not project:
        print(f"Project not found: {args.project}")
        sys.exit(1)

    if args.command == "analyze":
        result = analyze_file(args.file, project["path"])
        print(json.dumps(result, indent=2))

    elif args.command == "explain":
        result = explain_code(args.file, project["path"])
        print(result)

    elif args.command == "review":
        result = review_code(args.file, project["path"])
        print(result)


if __name__ == "__main__":
    main()
