---
name: git-workflow
description: When user mentions "commit", "branch", "merge", "git history", "what changed", "since last session", "PR", or needs git context. Provides session continuity via git awareness.
---

# Git Workflow Framework

## When This Activates

This skill activates for:
- Commit message generation
- Understanding what changed since last session
- Branch strategy decisions
- PR creation and descriptions
- Git context for debugging

## Session Continuity via Git

### What Changed Since Last Session?

The system tracks:
```
Last session: 2024-01-15 14:30
Commits since: 5
Files changed: 12
Authors: jmelendez (4), dependabot (1)
```

### Key Questions to Answer

1. **What was worked on outside Claude sessions?**
2. **Are there uncommitted changes?**
3. **Is the branch up to date with remote?**
4. **Any merge conflicts pending?**

## Commit Message Generation

### Format
```
<type>(<scope>): <subject>

<body>

<footer>
```

### Types
| Type | When to Use |
|------|-------------|
| `feat` | New feature |
| `fix` | Bug fix |
| `docs` | Documentation only |
| `style` | Formatting, no code change |
| `refactor` | Code restructure, no behavior change |
| `perf` | Performance improvement |
| `test` | Adding tests |
| `chore` | Build, deps, config |

### Good Commit Messages
```
feat(auth): add biometric login support

- Add FaceID/TouchID integration
- Store biometric preference in SecureStore
- Add fallback to PIN entry

Closes #123
```

### Bad Commit Messages
```
fix stuff
update code
WIP
```

## Branch Strategy

### Naming Convention
```
feature/  - New features
fix/      - Bug fixes
refactor/ - Code improvements
docs/     - Documentation
chore/    - Maintenance
```

### Example
```
feature/biometric-auth
fix/login-crash-ios17
refactor/auth-service-cleanup
```

## PR Description Framework

When creating PRs, include:

```markdown
## Summary
- 2-3 bullet points of what changed

## Changes
- Detailed list of modifications

## Testing
- [ ] Tested locally
- [ ] Unit tests pass
- [ ] E2E tests pass (if applicable)

## Screenshots
(If UI changes)
```

## Git Context for Debugging

When debugging, check:

1. **Recent commits** - What changed that might have broken it?
   ```
   git log --oneline -10
   ```

2. **Uncommitted changes** - Is it a local modification?
   ```
   git status
   ```

3. **Diff from working state** - What's different from last known good?
   ```
   git diff HEAD~5
   ```

4. **Blame** - Who changed this line and when?
   ```
   git blame <file>
   ```

## MCP Integration

The system provides git context via:
- `<session-continuity>` - Last session info
- Memory files track project work history
- Observation extractor logs git activity

## Workflow Examples

### Starting a Session
```
"What changed since I was last here?"
→ Check git log since last session timestamp
→ Summarize commits and changes
→ Note any uncommitted work
```

### Preparing a Commit
```
"Help me commit these changes"
→ Review staged changes
→ Detect change type
→ Generate conventional commit message
→ Offer to commit
```

### Creating a PR
```
"Create a PR for this branch"
→ Get branch info and commits
→ Get file summaries from memory
→ Generate PR description
→ Offer to create via gh CLI
```

## Safety Protocols

**NEVER:**
- Force push without explicit request
- Reset --hard without warning
- Delete branches without confirmation
- Skip pre-commit hooks unless asked

**ALWAYS:**
- Show what will be committed before committing
- Confirm destructive operations
- Preserve uncommitted work
