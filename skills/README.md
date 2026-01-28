# Claude-Dash Skills Framework

Domain expertise modules that automatically activate based on keywords in your prompts.

## How It Works

1. When you submit a prompt, the skills loader scans for trigger keywords
2. Matching skills are injected into the context as `<activated-skills>` blocks
3. Skills provide structured expertise for specific domains

## Directory Structure

```
~/.claude-dash/skills/
├── skills_loader.py      # Main loader script
├── registry.json         # Skills registry
├── README.md
├── core/                 # Development skills (always available)
│   ├── debug-strategy/
│   ├── performance-audit/
│   ├── refactor-guide/
│   ├── api-design/
│   ├── code-review/
│   └── testing-strategy/
└── marketing/            # Marketing skills
    ├── pricing-strategy/
    ├── launch-strategy/
    ├── free-tool-strategy/
    └── page-cro/

~/.claude-dash/projects/{project}/skills/  # Project-specific skills
└── {skill-name}/
    └── SKILL.md
```

## Skill File Format

Each skill is a SKILL.md file with YAML frontmatter:

```markdown
---
name: skill-name
description: When to activate this skill. Mention trigger keywords here.
---

# Skill Title

[Structured expertise content here]
```

## Available Skills

### Core Development Skills

| Skill | Triggers | Purpose |
|-------|----------|---------|
| debug-strategy | bug, error, not working, broken | Systematic debugging |
| performance-audit | slow, performance, optimize | Performance analysis |
| refactor-guide | refactor, clean up, technical debt | Safe refactoring |
| api-design | API, endpoint, REST, GraphQL | API design patterns |
| code-review | review, PR, pull request | Code review guidelines |
| testing-strategy | test, unit test, e2e, coverage | Testing approaches |

### Marketing Skills

| Skill | Triggers | Purpose |
|-------|----------|---------|
| pricing-strategy | pricing, monetization, subscription | Pricing models |
| launch-strategy | launch, release, GTM | Product launches |
| free-tool-strategy | free tool, lead magnet | Engineering as marketing |
| page-cro | conversion, CRO, landing page | Page optimization |

### Project-Specific Skills

**GYST:**
- `gyst-auth` - Firebase authentication patterns
- `gyst-firestore` - Firestore data patterns
- `react-native-expo` - Expo build and navigation

**GYST Seller Portal:**
- `nextjs-patterns` - Next.js App Router patterns
- `seller-features` - Marketplace features

## Creating New Skills

1. Create directory: `~/.claude-dash/skills/core/{skill-name}/`
2. Create SKILL.md with frontmatter
3. Include trigger keywords in description
4. Add structured content

Example:
```bash
mkdir -p ~/.claude-dash/skills/core/my-skill
cat > ~/.claude-dash/skills/core/my-skill/SKILL.md << 'EOF'
---
name: my-skill
description: Triggers on "keyword1", "keyword2". Use for specific domain.
---

# My Skill Guide

## Section 1
Content here...
EOF
```

## Creating Project-Specific Skills

```bash
mkdir -p ~/.claude-dash/projects/{project-id}/skills/{skill-name}
# Create SKILL.md as above
```

## Testing Skills

```bash
# Test skill activation
python3 ~/.claude-dash/skills/skills_loader.py "your test prompt" project-id

# Check activation logs
tail ~/.claude-dash/logs/skills-activation.log
```

## Integration

Skills are automatically loaded by `inject-context.sh` hook on every prompt.
Skill injection happens after semantic triggers but before pattern detection.

## Inspired By

This framework was inspired by [marketingskills](https://github.com/coreyhaines31/marketingskills)
by Corey Haines - a collection of marketing skills for Claude Code.
