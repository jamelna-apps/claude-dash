---
name: code-review
description: When the user mentions "review", "PR", "pull request", "code review", "check my code", "feedback on", or asks for code quality assessment.
---

# Code Review Guide

## Review Priorities (In Order)

1. **Correctness** - Does it work? Does it handle edge cases?
2. **Security** - Vulnerabilities, data exposure, injection risks
3. **Performance** - Obvious inefficiencies, scaling concerns
4. **Maintainability** - Readability, complexity, documentation
5. **Style** - Formatting, naming (lowest priority if linter exists)

## What to Look For

### Correctness
- [ ] Logic handles all cases (including edge cases)
- [ ] Error handling is appropriate
- [ ] Async operations handled correctly
- [ ] State mutations are intentional
- [ ] Tests cover the changes

### Security Checklist
- [ ] No hardcoded secrets
- [ ] Input is validated/sanitized
- [ ] SQL queries are parameterized
- [ ] User input isn't rendered as HTML
- [ ] Auth checks are in place
- [ ] Sensitive data isn't logged
- [ ] CORS is configured correctly

### Performance Red Flags
- [ ] N+1 queries
- [ ] Missing pagination
- [ ] Large data in memory
- [ ] Unnecessary re-renders
- [ ] Missing indexes for queries
- [ ] Synchronous operations that could be async

### Maintainability
- [ ] Functions do one thing
- [ ] Clear naming
- [ ] No magic numbers/strings
- [ ] Comments explain "why", not "what"
- [ ] Error messages are helpful
- [ ] Code is testable

## How to Give Feedback

### Good Feedback
```
This might cause an issue when `items` is empty -
the `reduce()` on line 45 will throw without an
initial value. Consider: `items.reduce((a, b) => a + b, 0)`
```

### Bad Feedback
```
This is wrong.
```

### Framework

**Blocking issues:** "This needs to change because [reason]"
**Suggestions:** "Consider [alternative] because [benefit]"
**Questions:** "What happens when [edge case]?"
**Praise:** "Nice use of [pattern] here"

## Review Size Guidelines

| Lines Changed | Review Time | Risk |
|---------------|-------------|------|
| < 50 | Quick | Low |
| 50-200 | Normal | Medium |
| 200-500 | Careful | High |
| > 500 | Split if possible | Very High |

## Common Patterns to Flag

### Over-engineering
- Abstractions for single-use code
- Premature optimization
- Unnecessary design patterns

### Under-engineering
- Copy-pasted code (3+ occurrences)
- Missing error handling
- No input validation

### Anti-patterns
- God objects/functions
- Deep nesting (> 3 levels)
- Boolean blindness
- Stringly-typed code

## Questions to Ask

1. "What happens if this fails?"
2. "How does this behave under load?"
3. "Can this be tested easily?"
4. "Will this be obvious in 6 months?"
5. "What could a malicious user do here?"

## Approval Criteria

Approve when:
- Passes all automated checks
- No blocking issues
- Tests exist and pass
- You understand what it does

Request changes when:
- Security vulnerabilities
- Clear bugs
- Missing critical tests
- Breaking changes without migration
