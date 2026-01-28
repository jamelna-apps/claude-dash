#!/usr/bin/env python3
"""
Skills Loader for Claude-Dash
Loads and activates skills based on keyword triggers in user prompts.

UPDATED: Now primarily uses triggers from registry.json for consistency.
Fallback to description parsing when registry entry not found.
"""

import os
import re
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

SKILLS_ROOT = Path(__file__).parent
MEMORY_ROOT = Path.home() / ".claude-dash"
REGISTRY_PATH = SKILLS_ROOT / "registry.json"

# Cache for registry to avoid repeated file reads
_registry_cache = None
_registry_triggers_cache = None


def load_registry() -> Dict:
    """Load skills registry JSON with caching."""
    global _registry_cache
    if _registry_cache is not None:
        return _registry_cache

    if not REGISTRY_PATH.exists():
        _registry_cache = {'skills': {}, 'project_skills': {}}
        return _registry_cache

    try:
        _registry_cache = json.loads(REGISTRY_PATH.read_text())
        return _registry_cache
    except (json.JSONDecodeError, IOError):
        _registry_cache = {'skills': {}, 'project_skills': {}}
        return _registry_cache


def get_registry_triggers() -> Dict[str, List[str]]:
    """Build skill name → triggers mapping from registry."""
    global _registry_triggers_cache
    if _registry_triggers_cache is not None:
        return _registry_triggers_cache

    registry = load_registry()
    triggers_map = {}

    # Process core and marketing skills
    for category_name, skills_list in registry.get('skills', {}).items():
        if isinstance(skills_list, list):
            for skill in skills_list:
                name = skill.get('name', '')
                triggers = skill.get('triggers', [])
                if name and triggers:
                    triggers_map[name] = triggers

    # Process project-specific skills
    for project_id, skills_list in registry.get('project_skills', {}).items():
        if isinstance(skills_list, list):
            for skill in skills_list:
                name = skill.get('name', '')
                triggers = skill.get('triggers', [])
                if name and triggers:
                    triggers_map[name] = triggers

    _registry_triggers_cache = triggers_map
    return triggers_map


def parse_skill_file(skill_path: Path) -> Optional[Dict]:
    """Parse a SKILL.md file and extract frontmatter + content."""
    if not skill_path.exists():
        return None

    content = skill_path.read_text()

    # Extract YAML frontmatter
    frontmatter_match = re.match(r'^---\n(.*?)\n---\n(.*)$', content, re.DOTALL)
    if not frontmatter_match:
        # Try without frontmatter - use filename as name
        return {
            'name': skill_path.parent.name,
            'description': '',
            'triggers': [],
            'content': content.strip()
        }

    frontmatter_text = frontmatter_match.group(1)
    skill_content = frontmatter_match.group(2).strip()

    # Parse simple YAML frontmatter
    metadata = {}
    for line in frontmatter_text.split('\n'):
        if ':' in line:
            key, value = line.split(':', 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            metadata[key] = value

    skill_name = metadata.get('name', skill_path.parent.name)

    # PRIMARY: Get triggers from registry
    registry_triggers = get_registry_triggers()
    triggers = registry_triggers.get(skill_name, [])

    # FALLBACK: Extract from description if not in registry
    if not triggers:
        triggers = extract_triggers_from_description(metadata.get('description', ''))

    return {
        'name': skill_name,
        'description': metadata.get('description', ''),
        'triggers': triggers,
        'content': skill_content,
        'path': str(skill_path)
    }


def extract_triggers_from_description(description: str) -> List[str]:
    """Fallback: Extract trigger keywords from skill description."""
    triggers = []
    desc_lower = description.lower()

    # Extract quoted triggers (e.g., "bug", "error")
    quoted = re.findall(r'["\']([^"\']+)["\']', description)
    triggers.extend([q.lower() for q in quoted])

    # Extract common terms that appear in description
    common_terms = [
        'conversion', 'optimize', 'cro', 'landing page', 'pricing',
        'seo', 'audit', 'launch', 'referral', 'email', 'sequence',
        'copywriting', 'copy', 'social', 'ads', 'analytics',
        'debug', 'bug', 'error', 'performance', 'slow', 'refactor',
        'api', 'endpoint', 'auth', 'login', 'database', 'schema',
        'test', 'commit', 'branch', 'git', 'deploy', 'docker'
    ]

    for term in common_terms:
        if term in desc_lower:
            triggers.append(term)

    return list(set(triggers))


def discover_skills(skills_dir: Path) -> List[Dict]:
    """Discover all skills in a directory."""
    skills = []

    if not skills_dir.exists():
        return skills

    for skill_dir in skills_dir.iterdir():
        if skill_dir.is_dir():
            skill_file = skill_dir / "SKILL.md"
            if skill_file.exists():
                skill = parse_skill_file(skill_file)
                if skill:
                    skills.append(skill)

    return skills


def match_skills(prompt: str, skills: List[Dict], max_skills: int = 2) -> List[Dict]:
    """Match skills based on prompt keywords."""
    prompt_lower = prompt.lower()
    matches = []

    for skill in skills:
        score = 0

        # Check triggers (primary matching mechanism)
        for trigger in skill.get('triggers', []):
            trigger_lower = trigger.lower()
            # Exact word boundary match for short triggers
            if len(trigger_lower) <= 4:
                if re.search(r'\b' + re.escape(trigger_lower) + r'\b', prompt_lower):
                    score += 3
            # Substring match for longer triggers
            elif trigger_lower in prompt_lower:
                score += 2

        # Check skill name
        skill_name_words = skill['name'].replace('-', ' ').lower()
        if skill_name_words in prompt_lower:
            score += 4

        # Minor boost for description keyword overlap
        desc_words = set(skill.get('description', '').lower().split())
        prompt_words = set(prompt_lower.split())
        common = len(desc_words & prompt_words)
        score += common * 0.3

        if score > 0:
            matches.append((skill, score))

    # Sort by score and return top matches
    matches.sort(key=lambda x: x[1], reverse=True)
    return [m[0] for m in matches[:max_skills]]


def format_skill_injection(skill: Dict, max_lines: int = 100) -> str:
    """Format skill content for injection."""
    content = skill.get('content', '')
    lines = content.split('\n')

    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines.append(f"\n... [Skill truncated - {len(content.split(chr(10))) - max_lines} more lines]")

    return '\n'.join(lines)


def load_all_skills(project_id: Optional[str] = None) -> List[Dict]:
    """Load all available skills (core, marketing, project-specific)."""
    all_skills = []

    # Core development skills
    core_dir = SKILLS_ROOT / "core"
    all_skills.extend(discover_skills(core_dir))

    # Marketing skills
    marketing_dir = SKILLS_ROOT / "marketing"
    all_skills.extend(discover_skills(marketing_dir))

    # Project-specific skills
    if project_id:
        project_skills_dir = MEMORY_ROOT / "projects" / project_id / "skills"
        all_skills.extend(discover_skills(project_skills_dir))

    return all_skills


def find_matching_skills(prompt: str, project_id: Optional[str] = None) -> List[Dict]:
    """Main entry point: find skills matching a prompt."""
    all_skills = load_all_skills(project_id)
    return match_skills(prompt, all_skills)


def inject_skills(prompt: str, project_id: Optional[str] = None) -> str:
    """Generate skill injection XML for a prompt."""
    matches = find_matching_skills(prompt, project_id)

    if not matches:
        return ""

    output_parts = []
    for skill in matches:
        content = format_skill_injection(skill)
        triggers_preview = ",".join(skill.get("triggers", [])[:5])
        output_parts.append(
            f'<activated-skill name="{skill["name"]}">\n'
            f'{content}\n'
            f'</activated-skill>'
        )

    return '\n'.join(output_parts)


def list_all_skills() -> str:
    """List all available skills with their triggers (for debugging)."""
    all_skills = load_all_skills()
    lines = ["Available Skills:", "=" * 50]

    for skill in sorted(all_skills, key=lambda x: x['name']):
        triggers = skill.get('triggers', [])[:5]
        lines.append(f"\n{skill['name']}")
        lines.append(f"  Triggers: {', '.join(triggers) if triggers else '(none)'}")
        if skill.get('description'):
            lines.append(f"  Desc: {skill['description'][:60]}...")

    return '\n'.join(lines)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: skills_loader.py <prompt> [project_id]", file=sys.stderr)
        print("       skills_loader.py --list", file=sys.stderr)
        sys.exit(1)

    if sys.argv[1] == "--list":
        print(list_all_skills())
    else:
        prompt = sys.argv[1]
        project_id = sys.argv[2] if len(sys.argv) > 2 else None

        output = inject_skills(prompt, project_id)
        if output:
            print(output)
