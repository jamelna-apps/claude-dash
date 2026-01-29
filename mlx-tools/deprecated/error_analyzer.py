#!/usr/bin/env python3
"""
MLX Error Analyzer - Analyze stack traces and error logs
"""

import sys
import json
import urllib.request
from pathlib import Path

try:
    from config import OLLAMA_URL, OLLAMA_CHAT_MODEL as MODEL, MEMORY_ROOT
except ImportError:
    MEMORY_ROOT = Path.home() / '.claude-dash'
    OLLAMA_URL = 'http://localhost:11434'
    MODEL = 'gemma3:4b-it-qat'


def get_project_context():
    """Get current project context"""
    import subprocess
    try:
        git_root = subprocess.check_output(
            ['git', 'rev-parse', '--show-toplevel'],
            stderr=subprocess.DEVNULL
        ).decode().strip()

        config_path = MEMORY_ROOT / 'config.json'
        if config_path.exists():
            config = json.loads(config_path.read_text())
            for project in config.get('projects', []):
                if project['path'] == git_root:
                    return project['id'], git_root
    except:
        pass
    return None, None


def get_relevant_files(project_id, error_text):
    """Find files mentioned in the error"""
    if not project_id:
        return []

    summaries_path = MEMORY_ROOT / 'projects' / project_id / 'summaries.json'
    if not summaries_path.exists():
        return []

    summaries = json.loads(summaries_path.read_text())
    files = list(summaries.get('files', {}).keys())

    # Find files mentioned in error
    relevant = []
    for f in files:
        filename = Path(f).name
        if filename in error_text:
            summary = summaries['files'][f].get('summary', '')
            relevant.append(f"{f}: {summary[:100]}")

    return relevant[:5]


def analyze_error(error_text, context=""):
    """Analyze error using Ollama"""
    prompt = f"""Analyze this error/stack trace and provide:

## What Went Wrong
(Brief explanation of the error)

## Root Cause
(The likely underlying cause)

## How to Fix
(Step-by-step fix instructions)

## Prevention
(How to prevent this in the future)

{context}

Error:
```
{error_text[:4000]}
```

Be concise and practical. Focus on actionable solutions."""

    data = json.dumps({
        'model': MODEL,
        'prompt': prompt,
        'stream': False
    }).encode()

    req = urllib.request.Request(
        f'{OLLAMA_URL}/api/generate',
        data=data,
        headers={'Content-Type': 'application/json'}
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode())
            return result.get('response', '').strip()
    except Exception as e:
        return f"Error: {e}"


def main():
    # Read error from file, argument, or stdin
    if len(sys.argv) > 1 and sys.argv[1] != '-':
        filepath = sys.argv[1]
        try:
            error_text = Path(filepath).read_text()
        except:
            # Maybe it's the error itself
            error_text = ' '.join(sys.argv[1:])
    else:
        print("Paste error/stack trace (Ctrl+D when done):")
        error_text = sys.stdin.read()

    if not error_text.strip():
        print("No error text provided.")
        sys.exit(1)

    project_id, _ = get_project_context()
    relevant_files = get_relevant_files(project_id, error_text)

    context = ""
    if relevant_files:
        context = f"Possibly relevant files:\n" + "\n".join(relevant_files)

    print("Analyzing error...")
    if project_id:
        print(f"Project: {project_id}")
    print("---")

    analysis = analyze_error(error_text, context)
    print(analysis)


if __name__ == '__main__':
    main()
