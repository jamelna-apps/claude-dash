---
name: refactor-guide
description: When the user mentions "refactor", "clean up", "technical debt", "restructure", "reorganize", "improve code quality", or wants to improve existing code without changing behavior.
---

# Refactoring Guide

## Refactoring Principles

1. **Tests first** - Never refactor without test coverage
2. **Small steps** - One change at a time, commit frequently
3. **Behavior unchanged** - Refactoring ≠ feature change
4. **Clear purpose** - Know WHY you're refactoring

## When to Refactor

**Good reasons:**
- Adding a feature is harder than it should be
- Bug fixes keep touching the same code
- Code is hard to understand after a break
- Duplicate code across multiple places
- Performance requires structural change

**Bad reasons:**
- "I don't like how it looks"
- "I would have done it differently"
- "Let's modernize everything"

## Code Smells & Fixes

### Structural Smells
| Smell | Symptom | Refactoring |
|-------|---------|-------------|
| Long Function | > 30 lines, multiple responsibilities | Extract Method |
| Large Class | > 300 lines, many concerns | Extract Class |
| Long Parameter List | > 4 params | Introduce Parameter Object |
| Feature Envy | Method uses another class more than its own | Move Method |
| Primitive Obsession | Strings/numbers representing concepts | Value Object |

### Code Duplication
| Type | Fix |
|------|-----|
| Identical code | Extract to shared function |
| Similar code | Extract with parameters |
| Parallel inheritance | Template Method pattern |

### Coupling Issues
| Smell | Fix |
|-------|-----|
| Inappropriate Intimacy | Move methods, introduce interface |
| Message Chains | Hide Delegate |
| Middle Man | Remove unnecessary delegation |

## Safe Refactoring Steps

### Extract Function
```
1. Identify code to extract
2. Create new function with clear name
3. Copy code to new function
4. Replace original with function call
5. Run tests
6. Commit
```

### Rename
```
1. Use IDE rename (not find-replace)
2. Update all references automatically
3. Check for string references manually
4. Run tests
5. Commit
```

### Move Code
```
1. Copy to new location
2. Make old location delegate to new
3. Run tests
4. Update callers to use new location
5. Remove delegation
6. Run tests
7. Commit
```

## Refactoring Strategies

**Strangler Fig Pattern:**
- Build new alongside old
- Route traffic gradually
- Remove old when unused

**Branch by Abstraction:**
- Introduce abstraction layer
- Implement new version behind it
- Switch implementations
- Remove abstraction if desired

**Parallel Change:**
- Add new, don't modify old
- Migrate callers incrementally
- Remove old when unused

## Red Flags During Refactoring

Stop and reassess if:
- Tests are failing
- Scope keeps growing
- You're fixing bugs while refactoring
- Changes cascade unexpectedly
- You can't explain the improvement

## Output Format

When proposing refactoring:
1. **Current Issues** - Specific problems with current code
2. **Proposed Changes** - What will change and why
3. **Migration Path** - Step-by-step safe transition
4. **Risk Assessment** - What could go wrong
5. **Verification** - How to confirm success
