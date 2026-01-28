---
name: code-health-remediation
description: When user mentions "dead code", "duplicates", "cleanup", "tech debt", "health scan", "remediation", "unused", or wants to act on health scan results. Guides safe code cleanup.
---

# Code Health Remediation Framework

## When This Activates

This skill activates when:
- Health scan shows issues to fix
- User wants to clean up codebase
- Removing dead code or duplicates
- Addressing tech debt

## Health Score Interpretation

| Score | Rating | Action |
|-------|--------|--------|
| 90-100 | Excellent | Maintain current practices |
| 75-89 | Good | Address minor issues opportunistically |
| 60-74 | Fair | Schedule cleanup sprint |
| 40-59 | Poor | Prioritize remediation |
| 0-39 | Critical | Immediate attention required |

## Issue Categories

### 1. Dead Code
**Types:**
- `unused_export` - Exported but never imported elsewhere
- `orphan_file` - File not imported by any other file
- `unused_function` - Function defined but never called

**Confidence Levels:**
- **High** - Static analysis confirms no references
- **Medium** - May have dynamic references
- **Low** - Could be used via string import or reflection

### 2. Duplicates
**Types:**
- Exact duplicates (identical code blocks)
- Near duplicates (similar logic, different variables)
- Pattern duplicates (same structure, different implementations)

### 3. Security Issues
**Types:**
- Hardcoded secrets
- Unsafe eval/exec usage
- SQL injection vulnerabilities
- XSS vulnerabilities

### 4. Performance Issues
**Types:**
- N+1 queries
- Missing indexes
- Unbounded loops
- Memory leaks

## Safe Remediation Workflow

### Before Removing Dead Code

1. **Verify with search**
   ```
   # Check for string references
   grep -r "functionName" .

   # Check for dynamic imports
   grep -r "import(" .
   ```

2. **Check test coverage**
   - Is the code tested directly?
   - Is it a test helper?

3. **Check for side effects**
   - Does it register listeners?
   - Does it modify global state?

4. **Review git history**
   - Why was it added?
   - Was it recently used?

### Removal Strategy

**High confidence dead code:**
```
1. Remove the code
2. Run tests
3. If tests pass, commit
```

**Medium confidence:**
```
1. Add deprecation comment
2. Log usage if called
3. Remove after verification period
```

**Low confidence:**
```
1. Don't remove automatically
2. Flag for manual review
3. Ask original author if available
```

## Duplicate Consolidation

### Steps
1. **Identify the canonical location**
2. **Create shared utility if needed**
3. **Update all callers to use shared version**
4. **Remove duplicates**
5. **Run tests**

### Example
```typescript
// Before: duplicated in 3 files
const formatDate = (d) => d.toISOString().split('T')[0];

// After: single location
// utils/dates.ts
export const formatDate = (d: Date) => d.toISOString().split('T')[0];
```

## Health Config (Ignore Rules)

Projects can configure ignore rules in `health_config.json`:

```json
{
  "ignore": {
    "dead_code": [
      {"file": "types.ts", "reason": "Type exports used via declaration merging"},
      {"pattern": "*.stories.tsx", "reason": "Storybook files"}
    ],
    "duplicates": [
      {"pattern": "*.test.ts", "reason": "Test setup can be duplicated"}
    ]
  },
  "exclude_dirs": ["__mocks__", "fixtures"]
}
```

## MCP Tools for Health

```
# Get current health status
memory_health action=status project=gyst

# Trigger a new scan
memory_health action=scan project=gyst

# Search for specific issues
memory_query "unused exports in auth"
```

## Prioritization Matrix

| Issue Type | Impact | Effort | Priority |
|------------|--------|--------|----------|
| Security (hardcoded secrets) | Critical | Low | P0 |
| Large orphan files | Medium | Low | P1 |
| Duplicate logic | Medium | Medium | P2 |
| Unused exports | Low | Low | P3 |
| Minor duplicates | Low | Low | P4 |

## Remediation Report Template

```markdown
## Health Remediation Report

**Project:** [name]
**Score Before:** [X]/100
**Score After:** [Y]/100

### Removed
- [list of removed items]

### Consolidated
- [list of deduplicated code]

### Flagged for Review
- [items needing manual review]

### Skipped (Configured Ignores)
- [items skipped per config]
```
