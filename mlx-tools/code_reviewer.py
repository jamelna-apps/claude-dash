#!/usr/bin/env python3
"""
MLX Code Reviewer - AI-powered code review
Can be used standalone or as a pre-commit hook
"""

import sys
import json
import subprocess
import urllib.request
from pathlib import Path

# Use centralized config
try:
    from config import OLLAMA_URL, OLLAMA_CHAT_MODEL as MODEL, MEMORY_ROOT, MAX_CODE_LENGTH
except ImportError:
    MEMORY_ROOT = Path.home() / '.claude-dash'
    OLLAMA_URL = 'http://localhost:11434'
    MODEL = 'qwen2.5:7b'
    MAX_CODE_LENGTH = 6000


def get_project_context():
    """Get current project from git root"""
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

        return None, git_root
    except:
        return None, None


def get_staged_diff():
    """Get staged changes"""
    try:
        return subprocess.check_output(
            ['git', 'diff', '--staged'],
            stderr=subprocess.DEVNULL
        ).decode()
    except:
        return ""


def read_file(filepath):
    """Read a file"""
    try:
        return Path(filepath).read_text()
    except:
        return ""


def review_code(code, context=""):
    """Review code using Ollama"""
    prompt = f"""Review this code for:

1. **Bugs** - Logic errors, null/undefined issues, off-by-one errors
2. **Security** - Injection, XSS, exposed secrets, unsafe operations
3. **Performance** - N+1 queries, unnecessary loops, memory leaks
4. **Best Practices** - Error handling, edge cases, code clarity

{context}

Code to review:
```
{code[:6000]}
```

Format your response as:
## Issues Found
(list issues with severity: HIGH/MEDIUM/LOW)

## Suggestions
(optional improvements)

If no issues found, say "No issues found - code looks good!"
"""

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
    args = sys.argv[1:]

    # Determine what to review
    if '--staged' in args or not args:
        # Review staged changes
        code = get_staged_diff()
        if not code:
            print("No staged changes to review.")
            sys.exit(0)
        source = "staged changes"
    elif '--hook' in args:
        # Pre-commit hook mode - exit non-zero on HIGH severity issues
        code = get_staged_diff()
        if not code:
            sys.exit(0)
        source = "pre-commit"
    else:
        # Review specific file
        filepath = args[0]
        code = read_file(filepath)
        if not code:
            print(f"Could not read: {filepath}")
            sys.exit(1)
        source = filepath

    project_id, _ = get_project_context()

    # Get project context
    context = ""
    if project_id:
        prefs_path = MEMORY_ROOT / 'projects' / project_id / 'preferences.json'
        if prefs_path.exists():
            prefs = json.loads(prefs_path.read_text())
            avoid = prefs.get('avoid', [])
            if avoid:
                context = f"Project rules - avoid: {', '.join(avoid)}"

    print(f"Reviewing: {source}")
    if project_id:
        print(f"Project: {project_id}")
    print("---")

    review = review_code(code, context)
    print(review)

    # In hook mode, block on HIGH severity issues
    if '--hook' in args and 'HIGH' in review:
        print("\n⛔ HIGH severity issues found. Fix before committing.")
        print("To bypass: git commit --no-verify")
        sys.exit(1)


if __name__ == '__main__':
    main()
