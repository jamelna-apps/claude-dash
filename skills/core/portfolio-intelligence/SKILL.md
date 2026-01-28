---
name: portfolio-intelligence
description: When user asks about "portfolio", "across projects", "compare projects", "project health", "PR description", or wants cross-project insights. Provides strategic guidance across the codebase ecosystem.
---

# Portfolio Intelligence Framework

## When This Activates

This skill activates for cross-project strategic questions:
- Comparing approaches across projects
- Finding where patterns exist
- Assessing overall health
- Generating PR descriptions with context

## Available Intelligence

### Project Overview
```
pm_portfolio detail=summary
```
Returns: Total projects, health scores, function counts, feature counts

### Health Comparison
Compare code quality across all projects:
- Security issues
- Performance problems
- Dead code
- Duplicates

**Health Score Guide:**
| Score | Rating | Meaning |
|-------|--------|---------|
| 90-100 | Excellent | Clean, well-maintained |
| 75-89 | Good | Minor issues |
| 60-74 | Fair | Needs attention |
| 40-59 | Poor | Significant tech debt |
| 0-39 | Critical | Major refactoring needed |

### Tech Stack Analysis
Detect technologies across projects:
- React, React Native, Next.js
- TypeScript vs JavaScript
- Firebase/Firestore usage
- Framework patterns

### Feature Catalog
Find which projects have which features:
- Shared features (appear in multiple projects)
- Feature dependencies
- Implementation status

### Session History
Track work patterns:
- Recent sessions by project
- Observation categories (decisions, bugfixes, gotchas)
- Patterns learned

## Cross-Project Search

Find code/patterns across all projects:
```
memory_search_all query="authentication" type=files
memory_search_all query="useAuth" type=functions
```

## Registered Projects

| ID | Name | Type |
|----|------|------|
| gyst | GYST Mobile | React Native |
| gyst-web | GYST Website | Next.js |
| jamelna | Jamelna.com | Next.js |
| smartiegoals | Smartie Goals | Next.js |
| spread-your-ashes | Spread Your Ashes | Next.js |
| codetale | CodeTale | Next.js |
| android-gyst | Android GYST | Android/Kotlin |
| playbook | PlayBook | Next.js |

## PR Description Generation

When creating PRs, the system can:

1. **Detect project context** from git root
2. **Analyze branch changes** (commits, files, diff)
3. **Get file summaries** from memory
4. **Generate description** with:
   - Summary (2-3 bullet points)
   - Detailed changes
   - Testing checklist
   - Screenshot prompts (if UI)

### PR Format
```markdown
## Summary
- Bullet point 1
- Bullet point 2

## Changes
- Detailed change list

## Testing
- [ ] Test case 1
- [ ] Test case 2

## Screenshots
(Add if UI changes)
```

## Strategic Questions

Use portfolio intelligence for:

**"Which project has the best auth implementation?"**
→ Search auth patterns across projects, compare approaches

**"Where should I implement feature X?"**
→ Check existing features, identify reuse opportunities

**"What tech debt should I prioritize?"**
→ Compare health scores, identify common issues

**"How do other projects handle Y?"**
→ Cross-project search for implementations

## MCP Tools

- `pm_portfolio` - Get portfolio overview
- `pm_ask` - Ask about priorities and projects
- `memory_search_all` - Search across all projects
- `memory_roadmap` - Project task tracking
