#!/usr/bin/env python3
"""
MLX PR Helper - Generate PR descriptions from branch changes
"""

import sys
import json
import subprocess
import urllib.request
from pathlib import Path

try:
    from config import OLLAMA_URL, OLLAMA_CHAT_MODEL as MODEL, MEMORY_ROOT
except ImportError:
    MEMORY_ROOT = Path.home() / '.claude-dash'
    OLLAMA_URL = 'http://localhost:11434'
    MODEL = 'llama3.2:3b'


def run_git(args):
    """Run git command and return output"""
    try:
        return subprocess.check_output(
            ['git'] + args,
            stderr=subprocess.DEVNULL
        ).decode().strip()
    except:
        return ""


def get_project_context():
    """Get current project"""
    git_root = run_git(['rev-parse', '--show-toplevel'])
    if not git_root:
        return None

    config_path = MEMORY_ROOT / 'config.json'
    if config_path.exists():
        config = json.loads(config_path.read_text())
        for project in config.get('projects', []):
            if project['path'] == git_root:
                return project['id']
    return None


def get_branch_info(base='main'):
    """Get branch commits and changes"""
    current = run_git(['branch', '--show-current'])
    commits = run_git(['log', f'{base}..HEAD', '--oneline'])
    diff_stat = run_git(['diff', f'{base}...HEAD', '--stat'])
    files_changed = run_git(['diff', f'{base}...HEAD', '--name-only'])

    return {
        'branch': current,
        'base': base,
        'commits': commits,
        'diff_stat': diff_stat,
        'files': files_changed.split('\n') if files_changed else []
    }


def get_file_summaries(project_id, files):
    """Get summaries for changed files"""
    if not project_id:
        return ""

    summaries_path = MEMORY_ROOT / 'projects' / project_id / 'summaries.json'
    if not summaries_path.exists():
        return ""

    summaries = json.loads(summaries_path.read_text())
    file_summaries = summaries.get('files', {})

    relevant = []
    for f in files[:10]:
        for key, data in file_summaries.items():
            if f in key:
                relevant.append(f"{f}: {data.get('summary', '')[:80]}")
                break

    return "\n".join(relevant) if relevant else ""


def generate_pr_description(branch_info, file_context):
    """Generate PR description using Ollama"""
    prompt = f"""Generate a GitHub Pull Request description.

Branch: {branch_info['branch']} → {branch_info['base']}

Commits:
{branch_info['commits']}

Files changed:
{branch_info['diff_stat']}

{f"File context:{chr(10)}{file_context}" if file_context else ""}

Generate a PR with this format:

## Summary
(2-3 bullet points summarizing the changes)

## Changes
(Detailed list of what changed)

## Testing
- [ ] (Checklist of things to test)

## Screenshots
(If UI changes, mention to add screenshots)

Be concise but thorough. Focus on the "why" not just the "what"."""

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
    base = sys.argv[1] if len(sys.argv) > 1 else 'main'

    branch_info = get_branch_info(base)
    if not branch_info['commits']:
        print(f"No commits ahead of {base}")
        sys.exit(1)

    project_id = get_project_context()
    file_context = get_file_summaries(project_id, branch_info['files'])

    print(f"Branch: {branch_info['branch']} → {base}")
    print(f"Commits: {len(branch_info['commits'].splitlines())}")
    print(f"Files changed: {len(branch_info['files'])}")
    if project_id:
        print(f"Project: {project_id}")
    print("---")
    print("Generating PR description...")
    print("")

    description = generate_pr_description(branch_info, file_context)
    print(description)

    # Offer to create PR
    print("\n---")
    choice = input("Create PR with this description? [y/n]: ").strip().lower()

    if choice == 'y':
        title = input("PR Title: ").strip()
        if title:
            # Write description to temp file for gh
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
                f.write(description)
                tmp_path = f.name

            subprocess.run([
                'gh', 'pr', 'create',
                '--title', title,
                '--body-file', tmp_path,
                '--base', base
            ])

            Path(tmp_path).unlink()


if __name__ == '__main__':
    main()
