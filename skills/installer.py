#!/usr/bin/env python3
"""
Claude-Dash Skills Installer

Manages skills: list, install, update, publish.
Skills can be local (private) or from GitHub repositories.

Usage:
    skill list                    - List installed skills
    skill info <name>            - Show skill details
    skill install <github-url>   - Install from GitHub
    skill update [name]          - Update skill(s)
    skill remove <name>          - Remove a skill
    skill publish <name>         - Export skill to GitHub format
    skill create <name>          - Create new skill scaffold
"""

import os
import sys
import json
import shutil
import argparse
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse
import re

MEMORY_ROOT = Path.home() / '.claude-dash'
SKILLS_ROOT = MEMORY_ROOT / 'skills'
REGISTRY_PATH = SKILLS_ROOT / 'registry.json'
INSTALLED_PATH = SKILLS_ROOT / 'installed.json'
BIN_DIR = MEMORY_ROOT / 'bin'

# Manifest schema version
MANIFEST_VERSION = '1.0'

def load_registry():
    """Load the skills registry."""
    if not REGISTRY_PATH.exists():
        return {'version': '1.0', 'skills': {'core': [], 'marketing': []}, 'project_skills': {}}
    with open(REGISTRY_PATH) as f:
        return json.load(f)

def save_registry(registry):
    """Save the skills registry."""
    with open(REGISTRY_PATH, 'w') as f:
        json.dump(registry, f, indent=2)

def load_installed():
    """Load installed skills tracking."""
    if not INSTALLED_PATH.exists():
        return {'skills': [], 'installed_at': {}}
    with open(INSTALLED_PATH) as f:
        return json.load(f)

def save_installed(installed):
    """Save installed skills tracking."""
    with open(INSTALLED_PATH, 'w') as f:
        json.dump(installed, f, indent=2)

def list_skills():
    """List all installed skills."""
    registry = load_registry()
    installed = load_installed()

    print("=== Installed Skills ===\n")

    # Core skills
    core_skills = registry.get('skills', {}).get('core', [])
    if core_skills:
        print("Core Skills:")
        for skill in core_skills:
            status = "built-in"
            triggers = ', '.join(skill.get('triggers', [])[:3])
            if len(skill.get('triggers', [])) > 3:
                triggers += '...'
            print(f"  {skill['name']:<25} [{status}] triggers: {triggers}")
        print()

    # Marketing skills
    marketing_skills = registry.get('skills', {}).get('marketing', [])
    if marketing_skills:
        print("Marketing Skills:")
        for skill in marketing_skills:
            status = "built-in"
            triggers = ', '.join(skill.get('triggers', [])[:3])
            print(f"  {skill['name']:<25} [{status}] triggers: {triggers}")
        print()

    # Installed from GitHub
    github_skills = [s for s in installed.get('skills', []) if s.get('source') == 'github']
    if github_skills:
        print("GitHub Skills:")
        for skill in github_skills:
            installed_at = installed.get('installed_at', {}).get(skill['name'], 'unknown')
            print(f"  {skill['name']:<25} [github] from: {skill.get('repo', 'unknown')}")
        print()

    # Project-specific skills
    project_skills = registry.get('project_skills', {})
    if project_skills:
        print("Project Skills:")
        for project, skills in project_skills.items():
            for skill in skills:
                print(f"  {skill['name']:<25} [project: {project}]")
        print()

    total = len(core_skills) + len(marketing_skills) + len(github_skills)
    print(f"Total: {total} skills")

def skill_info(name):
    """Show detailed information about a skill."""
    registry = load_registry()
    installed = load_installed()

    # Search in all categories
    skill = None
    source = None

    for category in ['core', 'marketing']:
        for s in registry.get('skills', {}).get(category, []):
            if s['name'] == name:
                skill = s
                source = f'built-in ({category})'
                break
        if skill:
            break

    if not skill:
        for s in installed.get('skills', []):
            if s['name'] == name:
                skill = s
                source = f"github ({s.get('repo', 'unknown')})"
                break

    if not skill:
        print(f"Skill not found: {name}")
        return False

    skill_path = SKILLS_ROOT / skill.get('path', f'{name}/SKILL.md')

    print(f"=== Skill: {name} ===\n")
    print(f"Source: {source}")
    print(f"Path: {skill_path}")
    print(f"Description: {skill.get('description', 'No description')}")
    print(f"Triggers: {', '.join(skill.get('triggers', []))}")

    # Check for manifest
    manifest_path = skill_path.parent / 'manifest.json'
    if manifest_path.exists():
        with open(manifest_path) as f:
            manifest = json.load(f)
        print(f"\nManifest:")
        print(f"  Version: {manifest.get('version', '1.0')}")
        print(f"  Author: {manifest.get('author', 'Unknown')}")
        print(f"  Dependencies: {', '.join(manifest.get('dependencies', [])) or 'None'}")

    # Show SKILL.md preview
    if skill_path.exists():
        print(f"\n--- SKILL.md Preview ---")
        with open(skill_path) as f:
            content = f.read()
            lines = content.split('\n')[:20]
            for line in lines:
                print(line)
            if len(content.split('\n')) > 20:
                print('...')

    return True

def install_skill(source):
    """Install a skill from GitHub URL or local path."""
    print(f"Installing skill from: {source}")

    # Parse source
    if source.startswith('https://github.com/') or source.startswith('git@github.com:'):
        return install_from_github(source)
    elif Path(source).exists():
        return install_from_local(source)
    else:
        print(f"Invalid source: {source}")
        print("Supported formats:")
        print("  - GitHub URL: https://github.com/user/skill-name")
        print("  - Local path: /path/to/skill-directory")
        return False

def install_from_github(url):
    """Install skill from GitHub repository."""
    # Parse GitHub URL
    parsed = urlparse(url)
    path_parts = parsed.path.strip('/').split('/')

    if len(path_parts) < 2:
        print(f"Invalid GitHub URL: {url}")
        return False

    owner = path_parts[0]
    repo = path_parts[1].replace('.git', '')
    branch = 'main'  # Default branch

    # Check if branch specified
    if len(path_parts) > 3 and path_parts[2] == 'tree':
        branch = path_parts[3]

    print(f"Cloning {owner}/{repo} (branch: {branch})...")

    # Clone to temp directory
    with tempfile.TemporaryDirectory() as tmpdir:
        clone_path = Path(tmpdir) / repo

        try:
            result = subprocess.run(
                ['git', 'clone', '--depth', '1', '--branch', branch, url, str(clone_path)],
                capture_output=True,
                text=True,
                timeout=60
            )

            if result.returncode != 0:
                print(f"Clone failed: {result.stderr}")
                return False
        except subprocess.TimeoutExpired:
            print("Clone timed out")
            return False
        except FileNotFoundError:
            print("Git not found. Please install git.")
            return False

        # Validate skill structure
        if not validate_skill_structure(clone_path):
            return False

        # Read manifest or create default
        manifest_path = clone_path / 'manifest.json'
        if manifest_path.exists():
            with open(manifest_path) as f:
                manifest = json.load(f)
        else:
            manifest = create_default_manifest(repo, clone_path)

        skill_name = manifest.get('name', repo)

        # Check if already installed
        installed = load_installed()
        existing = next((s for s in installed.get('skills', []) if s['name'] == skill_name), None)
        if existing:
            print(f"Skill '{skill_name}' already installed. Use 'skill update {skill_name}' to update.")
            return False

        # Copy to skills directory
        target_path = SKILLS_ROOT / 'installed' / skill_name
        target_path.parent.mkdir(parents=True, exist_ok=True)

        if target_path.exists():
            shutil.rmtree(target_path)

        shutil.copytree(clone_path, target_path, ignore=shutil.ignore_patterns('.git'))

        # Update registry
        registry = load_registry()
        if 'installed' not in registry.get('skills', {}):
            registry.setdefault('skills', {})['installed'] = []

        registry['skills']['installed'].append({
            'name': skill_name,
            'path': f'installed/{skill_name}/SKILL.md',
            'triggers': manifest.get('triggers', []),
            'description': manifest.get('description', f'Skill from {owner}/{repo}')
        })
        save_registry(registry)

        # Update installed tracking
        installed.setdefault('skills', []).append({
            'name': skill_name,
            'source': 'github',
            'repo': f'{owner}/{repo}',
            'branch': branch,
            'url': url
        })
        installed.setdefault('installed_at', {})[skill_name] = datetime.now().isoformat()
        save_installed(installed)

        print(f"Successfully installed: {skill_name}")
        print(f"Location: {target_path}")
        return True

def install_from_local(path):
    """Install skill from local directory."""
    source_path = Path(path).resolve()

    if not validate_skill_structure(source_path):
        return False

    # Read manifest
    manifest_path = source_path / 'manifest.json'
    if manifest_path.exists():
        with open(manifest_path) as f:
            manifest = json.load(f)
    else:
        manifest = create_default_manifest(source_path.name, source_path)

    skill_name = manifest.get('name', source_path.name)

    # Copy to skills directory
    target_path = SKILLS_ROOT / 'installed' / skill_name
    target_path.parent.mkdir(parents=True, exist_ok=True)

    if target_path.exists():
        shutil.rmtree(target_path)

    shutil.copytree(source_path, target_path, ignore=shutil.ignore_patterns('.git'))

    # Update registry
    registry = load_registry()
    if 'installed' not in registry.get('skills', {}):
        registry.setdefault('skills', {})['installed'] = []

    registry['skills']['installed'].append({
        'name': skill_name,
        'path': f'installed/{skill_name}/SKILL.md',
        'triggers': manifest.get('triggers', []),
        'description': manifest.get('description', f'Local skill: {skill_name}')
    })
    save_registry(registry)

    # Update installed tracking
    installed = load_installed()
    installed.setdefault('skills', []).append({
        'name': skill_name,
        'source': 'local',
        'original_path': str(source_path)
    })
    installed.setdefault('installed_at', {})[skill_name] = datetime.now().isoformat()
    save_installed(installed)

    print(f"Successfully installed: {skill_name}")
    return True

def validate_skill_structure(path):
    """Validate skill directory structure."""
    path = Path(path)

    # Must have SKILL.md
    skill_md = path / 'SKILL.md'
    if not skill_md.exists():
        print(f"Missing required file: SKILL.md")
        return False

    # SKILL.md must not be empty
    if skill_md.stat().st_size == 0:
        print("SKILL.md is empty")
        return False

    return True

def create_default_manifest(name, path):
    """Create default manifest from SKILL.md."""
    skill_md = Path(path) / 'SKILL.md'

    # Extract triggers from SKILL.md
    triggers = []
    with open(skill_md) as f:
        content = f.read()
        # Look for triggers in comments or front matter
        trigger_match = re.search(r'triggers?:\s*\[([^\]]+)\]', content, re.IGNORECASE)
        if trigger_match:
            triggers = [t.strip().strip('"\'') for t in trigger_match.group(1).split(',')]

    return {
        'name': name,
        'version': '1.0.0',
        'description': f'Skill: {name}',
        'triggers': triggers,
        'dependencies': [],
        'manifest_version': MANIFEST_VERSION
    }

def update_skill(name=None):
    """Update installed skill(s)."""
    installed = load_installed()

    if name:
        # Update specific skill
        skill = next((s for s in installed.get('skills', []) if s['name'] == name), None)
        if not skill:
            print(f"Skill not found: {name}")
            return False

        if skill.get('source') != 'github':
            print(f"Cannot update non-GitHub skill: {name}")
            return False

        print(f"Updating {name}...")
        remove_skill(name, quiet=True)
        return install_skill(skill.get('url'))
    else:
        # Update all GitHub skills
        github_skills = [s for s in installed.get('skills', []) if s.get('source') == 'github']

        if not github_skills:
            print("No GitHub skills to update")
            return True

        print(f"Updating {len(github_skills)} skill(s)...")
        for skill in github_skills:
            print(f"\n--- {skill['name']} ---")
            remove_skill(skill['name'], quiet=True)
            install_skill(skill.get('url'))

        return True

def remove_skill(name, quiet=False):
    """Remove an installed skill."""
    installed = load_installed()
    registry = load_registry()

    # Find skill
    skill = next((s for s in installed.get('skills', []) if s['name'] == name), None)
    if not skill:
        if not quiet:
            print(f"Skill not found: {name}")
        return False

    # Remove from disk
    skill_path = SKILLS_ROOT / 'installed' / name
    if skill_path.exists():
        shutil.rmtree(skill_path)

    # Remove from installed tracking
    installed['skills'] = [s for s in installed.get('skills', []) if s['name'] != name]
    if name in installed.get('installed_at', {}):
        del installed['installed_at'][name]
    save_installed(installed)

    # Remove from registry
    if 'installed' in registry.get('skills', {}):
        registry['skills']['installed'] = [
            s for s in registry['skills']['installed'] if s['name'] != name
        ]
        save_registry(registry)

    if not quiet:
        print(f"Removed skill: {name}")
    return True

def publish_skill(name):
    """Export skill to GitHub-ready format."""
    registry = load_registry()

    # Find skill
    skill = None
    skill_path = None

    for category in ['core', 'marketing', 'installed']:
        for s in registry.get('skills', {}).get(category, []):
            if s['name'] == name:
                skill = s
                skill_path = SKILLS_ROOT / s.get('path', f'{name}/SKILL.md')
                break
        if skill:
            break

    if not skill:
        print(f"Skill not found: {name}")
        return False

    skill_dir = skill_path.parent

    # Create export directory
    export_dir = MEMORY_ROOT / 'exports' / name
    export_dir.mkdir(parents=True, exist_ok=True)

    # Copy skill files
    if skill_dir.exists():
        for item in skill_dir.iterdir():
            if item.is_file():
                shutil.copy(item, export_dir)

    # Create/update manifest
    manifest = {
        'name': name,
        'version': '1.0.0',
        'description': skill.get('description', f'Skill: {name}'),
        'triggers': skill.get('triggers', []),
        'dependencies': [],
        'manifest_version': MANIFEST_VERSION,
        'author': os.environ.get('USER', 'unknown'),
        'created': datetime.now().isoformat()
    }

    with open(export_dir / 'manifest.json', 'w') as f:
        json.dump(manifest, f, indent=2)

    # Create README
    readme_content = f"""# {name}

{skill.get('description', 'A Claude-Dash skill.')}

## Installation

```bash
~/.claude-dash/bin/skill install https://github.com/YOUR_USERNAME/{name}
```

## Triggers

This skill activates on the following keywords:
{chr(10).join(f'- {t}' for t in skill.get('triggers', []))}

## Usage

Once installed, the skill will automatically activate when you use its trigger keywords in your prompts.

## License

MIT
"""

    with open(export_dir / 'README.md', 'w') as f:
        f.write(readme_content)

    print(f"Exported skill to: {export_dir}")
    print("\nTo publish to GitHub:")
    print(f"  1. cd {export_dir}")
    print(f"  2. git init && git add .")
    print(f"  3. git commit -m 'Initial commit'")
    print(f"  4. gh repo create {name} --public --source=.")
    print(f"  5. git push -u origin main")

    return True

def create_skill(name):
    """Create a new skill scaffold."""
    skill_dir = SKILLS_ROOT / 'installed' / name

    if skill_dir.exists():
        print(f"Skill already exists: {name}")
        return False

    skill_dir.mkdir(parents=True)

    # Create SKILL.md
    skill_md = f"""# {name.replace('-', ' ').title()}

## Overview

[Describe what this skill does]

## When to Use

This skill activates when:
- [Trigger condition 1]
- [Trigger condition 2]

## Guidance

### Step 1: [First Step]

[Instructions for step 1]

### Step 2: [Second Step]

[Instructions for step 2]

## Examples

### Example 1

[Example usage scenario]

## Related Skills

- [Related skill 1]
- [Related skill 2]
"""

    with open(skill_dir / 'SKILL.md', 'w') as f:
        f.write(skill_md)

    # Create manifest
    manifest = {
        'name': name,
        'version': '1.0.0',
        'description': f'Skill: {name}',
        'triggers': [name.split('-')[0]],  # First word as default trigger
        'dependencies': [],
        'manifest_version': MANIFEST_VERSION,
        'author': os.environ.get('USER', 'unknown'),
        'created': datetime.now().isoformat()
    }

    with open(skill_dir / 'manifest.json', 'w') as f:
        json.dump(manifest, f, indent=2)

    # Add to registry
    registry = load_registry()
    if 'installed' not in registry.get('skills', {}):
        registry.setdefault('skills', {})['installed'] = []

    registry['skills']['installed'].append({
        'name': name,
        'path': f'installed/{name}/SKILL.md',
        'triggers': manifest['triggers'],
        'description': manifest['description']
    })
    save_registry(registry)

    print(f"Created new skill: {name}")
    print(f"Location: {skill_dir}")
    print("\nNext steps:")
    print(f"  1. Edit {skill_dir}/SKILL.md with your skill content")
    print(f"  2. Update {skill_dir}/manifest.json with triggers")
    print(f"  3. Test with: skill info {name}")

    return True

def main():
    parser = argparse.ArgumentParser(
        description='Claude-Dash Skills Manager',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  skill list                              # List all installed skills
  skill info debug-strategy               # Show skill details
  skill install https://github.com/u/sk   # Install from GitHub
  skill update                            # Update all GitHub skills
  skill remove my-skill                   # Remove a skill
  skill publish debug-strategy            # Export to GitHub format
  skill create my-new-skill               # Create new skill scaffold
"""
    )

    subparsers = parser.add_subparsers(dest='command', help='Command to run')

    # List command
    subparsers.add_parser('list', help='List installed skills')

    # Info command
    info_parser = subparsers.add_parser('info', help='Show skill details')
    info_parser.add_argument('name', help='Skill name')

    # Install command
    install_parser = subparsers.add_parser('install', help='Install a skill')
    install_parser.add_argument('source', help='GitHub URL or local path')

    # Update command
    update_parser = subparsers.add_parser('update', help='Update skill(s)')
    update_parser.add_argument('name', nargs='?', help='Skill name (optional, updates all if omitted)')

    # Remove command
    remove_parser = subparsers.add_parser('remove', help='Remove a skill')
    remove_parser.add_argument('name', help='Skill name')

    # Publish command
    publish_parser = subparsers.add_parser('publish', help='Export skill to GitHub format')
    publish_parser.add_argument('name', help='Skill name')

    # Create command
    create_parser = subparsers.add_parser('create', help='Create new skill scaffold')
    create_parser.add_argument('name', help='Skill name (use-kebab-case)')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    if args.command == 'list':
        list_skills()
    elif args.command == 'info':
        skill_info(args.name)
    elif args.command == 'install':
        install_skill(args.source)
    elif args.command == 'update':
        update_skill(args.name)
    elif args.command == 'remove':
        remove_skill(args.name)
    elif args.command == 'publish':
        publish_skill(args.name)
    elif args.command == 'create':
        create_skill(args.name)

if __name__ == '__main__':
    main()
