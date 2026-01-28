---
name: smart-routing
description: When deciding which Claude model (Opus/Sonnet/Haiku) to use, or when "route", "which model", "complex task", "multi-file", "architectural", or "deep debugging" is mentioned. Guides quality-first model selection.
---

# Smart Routing Decision Framework

## When This Activates

Use this framework BEFORE starting complex work to determine the best model:
- Should this use Opus (architecture), Sonnet (default), or Haiku (exploration)?
- Local Ollama is ONLY for non-critical tasks (commit messages, Enchanted API)

## IMPORTANT: Local LLM is NOT for Critical Work

**DO NOT route development tasks to local Ollama.** Local is only appropriate for:
- Commit message generation
- PR description drafts
- Enchanted/mobile API access
- Personal tinkering

## Quick Decision Matrix

| Task Type | Route To | Model |
|-----------|----------|-------|
| "Where is X?" | CLAUDE | **Haiku** (fast exploration) |
| "What does Y do?" | CLAUDE | **Haiku** (simple lookup) |
| "How does Z work?" | CLAUDE | **Sonnet** (reasoning needed) |
| Code review | CLAUDE | **Sonnet** (quality matters) |
| Commit message | Local | (non-critical) |
| **Multi-file refactor** | CLAUDE | **Sonnet** |
| **Debug intermittent bug** | CLAUDE | **Sonnet** |
| **Architecture decision** | CLAUDE | **Opus** |
| **Write new feature** | CLAUDE | **Sonnet** |
| **Fix across codebase** | CLAUDE | **Sonnet** |

## Model Selection Guide

**Use Opus when:**
- Greenfield architecture decisions
- Multiple valid approaches with non-obvious trade-offs
- High cost to reverse if wrong choice
- Cross-cutting concerns (security, scalability, performance)

**Use Sonnet when (DEFAULT):**
- ALL implementation work
- Bug fixes and debugging
- Feature additions
- Refactoring
- Code review
- Most planning tasks (75%)

**Use Haiku when:**
- File/code exploration
- Simple lookups ("where is X?")
- Documentation updates
- Simple formatting

**Use Local ONLY when:**
- Commit messages (`mlx commit`)
- PR descriptions (`mlx pr`)
- Enchanted app queries
- Personal experimentation

## Tool-Need Detection

Any task requiring tools should use Claude (never local):
- `edit`, `modify`, `change`, `update`, `fix` (file operations) → **Sonnet**
- `create file`, `write file`, `new file` → **Sonnet**
- `commit`, `push`, `pull request` → **Sonnet** (local for msg only)
- `run test`, `execute`, `build`, `deploy` → **Sonnet**
- `install`, `npm`, `pip`, `yarn` → **Sonnet**

## Simple Question Patterns

For quick lookups, use Haiku:
- "what is/does/are..." → **Haiku**
- "where is/are/do..." → **Haiku**
- "find", "search", "look for", "locate" → **Haiku**

For reasoning questions, use Sonnet:
- "how does/do/to..." → **Sonnet**
- "why does/is/do..." → **Sonnet**
- "explain", "describe" (complex) → **Sonnet**

## Workflow

1. **Default to Sonnet** for all development work
2. **Use Haiku** only for simple exploration/lookups
3. **Use Opus** only for complex architecture decisions
4. **Use Local** only for commit messages and non-critical tasks

## MCP Tools (All Use Claude)

Memory tools (use with appropriate Claude model):
- `memory_query` - Instant hybrid search (Haiku OK)
- `memory_functions` - Function lookup (Haiku OK)
- `smart_read` - File reading (Sonnet for analysis)
- `smart_edit` - File editing (Sonnet always)

Local tools (non-critical ONLY):
- `local_ask` - ONLY for commit messages, personal queries
- `local_review` - NOT for critical code review

## Quality Over Cost

- **Critical work**: Always use Claude (Sonnet default)
- **Architecture**: Use Opus - worth the cost for high-stakes decisions
- **Exploration**: Haiku is cheap and good enough
- **Trivial**: Local is fine for commit messages only
