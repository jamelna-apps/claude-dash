#!/usr/bin/env python3
"""
Generate skills documentation from registry.json

Usage:
    python3 ~/.claude-dash/scripts/generate-skills-docs.py

Outputs skills-reference.md to ~/.claude-dash/docs/
"""

import json
from pathlib import Path
from datetime import datetime

CLAUDE_DASH = Path.home() / ".claude-dash"
REGISTRY_PATH = CLAUDE_DASH / "skills" / "registry.json"
OUTPUT_PATH = CLAUDE_DASH / "docs" / "skills-reference.md"


def load_registry():
    """Load the skills registry."""
    with open(REGISTRY_PATH) as f:
        return json.load(f)


def generate_markdown(registry: dict) -> str:
    """Generate markdown documentation from registry."""
    lines = [
        "# Claude-Dash Skills Reference",
        "",
        f"> Auto-generated on {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "> Source: `~/.claude-dash/skills/registry.json`",
        "",
    ]

    # Skills are organized as: skills.category -> [skill_objects]
    skills_by_category = registry.get("skills", {})
    project_skills = registry.get("project_skills", {})

    # Count totals
    category_counts = {cat: len(skills) for cat, skills in skills_by_category.items()}
    project_counts = {proj: len(skills) for proj, skills in project_skills.items()}
    total_skills = sum(category_counts.values())
    total_project_skills = sum(project_counts.values())

    lines.extend([
        "## Summary",
        "",
        f"**Global Skills:** {total_skills}",
        f"**Project-Specific Skills:** {total_project_skills}",
        f"**Total:** {total_skills + total_project_skills}",
        "",
        "### By Category",
        "",
        "| Category | Count |",
        "|----------|-------|",
    ])

    for cat, count in sorted(category_counts.items()):
        lines.append(f"| {cat} | {count} |")

    if project_counts:
        lines.extend([
            "",
            "### Project-Specific",
            "",
            "| Project | Count |",
            "|---------|-------|",
        ])
        for proj, count in sorted(project_counts.items()):
            lines.append(f"| {proj} | {count} |")

    lines.extend(["", "---", ""])

    # Generate detailed skill documentation
    for category, skills in sorted(skills_by_category.items()):
        lines.extend([
            f"## {category.title()} Skills",
            "",
        ])

        for skill in sorted(skills, key=lambda x: x.get("name", "")):
            name = skill.get("name", "unknown")
            description = skill.get("description", "No description")
            triggers = skill.get("triggers", [])
            path = skill.get("path", "")

            lines.extend([
                f"### {name}",
                "",
                f"**Description:** {description}",
                "",
            ])

            if triggers:
                lines.append(f"**Triggers:** `{', '.join(triggers)}`")
                lines.append("")

            if path:
                lines.append(f"**Path:** `~/.claude-dash/skills/{path}`")
                lines.append("")

            lines.append("---")
            lines.append("")

    # Project-specific skills
    if project_skills:
        lines.extend([
            "## Project-Specific Skills",
            "",
        ])

        for project, skills in sorted(project_skills.items()):
            lines.extend([
                f"### {project}",
                "",
            ])

            for skill in sorted(skills, key=lambda x: x.get("name", "")):
                name = skill.get("name", "unknown")
                description = skill.get("description", "No description")
                triggers = skill.get("triggers", [])
                path = skill.get("path", "")

                lines.extend([
                    f"#### {name}",
                    "",
                    f"**Description:** {description}",
                    "",
                ])

                if triggers:
                    lines.append(f"**Triggers:** `{', '.join(triggers)}`")
                    lines.append("")

                if path:
                    lines.append(f"**Path:** `~/.claude-dash/{path}`")
                    lines.append("")

            lines.append("---")
            lines.append("")

    # Note about auto-injection
    lines.extend([
        "## Usage Notes",
        "",
        "### Auto-Injection",
        "",
        "Skills are automatically injected when prompt keywords match triggers:",
        "- Top 2 skills (by match count) are injected per prompt",
        "- Content appears in `<activated-skill>` tags",
        "- Both global and project-specific skills are checked",
        "",
        "### Manual Invocation",
        "",
        "Skills can also be invoked explicitly via `/skill <skill-name>` commands.",
    ])

    return "\n".join(lines)


def main():
    print(f"Loading registry from {REGISTRY_PATH}")
    registry = load_registry()

    print("Generating documentation...")
    markdown = generate_markdown(registry)

    # Ensure output directory exists
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    print(f"Writing to {OUTPUT_PATH}")
    with open(OUTPUT_PATH, "w") as f:
        f.write(markdown)

    # Count for summary
    skills = registry.get("skills", {})
    project_skills = registry.get("project_skills", {})
    total = sum(len(s) for s in skills.values()) + sum(len(s) for s in project_skills.values())
    print(f"Done! Documented {total} skills.")


if __name__ == "__main__":
    main()
