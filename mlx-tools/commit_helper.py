#!/usr/bin/env python3
"""
MLX Commit Helper - Generate context-aware commit messages
Uses project conventions and past commits for style matching
"""

import sys
import json
import subprocess
import urllib.request
from pathlib import Path

MEMORY_ROOT = Path.home() / '.claude-dash'
OLLAMA_URL = 'http://localhost:11434'
MODEL = 'llama3.2:3b'


def get_project_context():
    """Get current project from git root"""
    try:
        git_root = subprocess.check_output(
            ['git', 'rev-parse', '--show-toplevel'],
            stderr=subprocess.DEVNULL
        ).decode().strip()

        # Find project in config
        config_path = MEMORY_ROOT / 'config.json'
        if config_path.exists():
            config = json.loads(config_path.read_text())
            for project in config.get('projects', []):
                if project['path'] == git_root:
                    return project['id'], git_root

        return None, git_root
    except:
        return None, None


def get_recent_commits(limit=5):
    """Get recent commit messages for style reference"""
    try:
        result = subprocess.check_output(
            ['git', 'log', f'-{limit}', '--oneline'],
            stderr=subprocess.DEVNULL
        ).decode().strip()
        return result
    except:
        return ""


def get_staged_diff():
    """Get staged changes"""
    try:
        return subprocess.check_output(
            ['git', 'diff', '--staged'],
            stderr=subprocess.DEVNULL
        ).decode()
    except:
        return ""


def get_project_conventions(project_id):
    """Load project conventions if available"""
    if not project_id:
        return ""

    prefs_path = MEMORY_ROOT / 'projects' / project_id / 'preferences.json'
    if prefs_path.exists():
        prefs = json.loads(prefs_path.read_text())
        conventions = prefs.get('conventions', [])
        if conventions:
            return "Project conventions:\n" + "\n".join(f"- {c}" for c in conventions)
    return ""


def generate_message(diff, recent_commits, conventions):
    """Generate commit message using Ollama"""
    prompt = f"""Generate a git commit message for this diff.

Requirements:
- Use conventional commit format (feat/fix/refactor/docs/chore/test)
- First line max 72 characters
- Be specific about what changed
- Match the style of recent commits

{conventions}

Recent commits for style reference:
{recent_commits}

Diff:
{diff[:4000]}

Output only the commit message, nothing else."""

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
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())
            return result.get('response', '').strip()
    except Exception as e:
        print(f"Error: {e}")
        return None


def main():
    diff = get_staged_diff()
    if not diff:
        print("No staged changes. Use 'git add' first.")
        sys.exit(1)

    project_id, git_root = get_project_context()
    recent_commits = get_recent_commits()
    conventions = get_project_conventions(project_id)

    if project_id:
        print(f"Project: {project_id}")

    print("Generating commit message...")
    message = generate_message(diff, recent_commits, conventions)

    if not message:
        print("Failed to generate message.")
        sys.exit(1)

    print(f"\n{message}\n")

    choice = input("Use this message? [y/n/e(dit)]: ").strip().lower()

    if choice == 'y':
        subprocess.run(['git', 'commit', '-m', message])
    elif choice == 'e':
        subprocess.run(['git', 'commit', '-e', '-m', message])
    else:
        print("Commit cancelled.")


if __name__ == '__main__':
    main()
