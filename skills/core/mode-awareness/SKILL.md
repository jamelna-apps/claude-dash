---
name: mode-awareness
description: When explicitly switching modes or when mode detection shows low confidence. Provides guidance on optimal approach for each detected mode (debugging, performance, feature, refactor, exploration, infrastructure).
---

# Mode Awareness Framework

## When This Activates

This skill activates when:
- Mode detection shows in `<pattern-context>` with low confidence
- User explicitly asks to "switch to X mode"
- Approach guidance is needed for a task type

## Detected Modes

The system auto-detects these modes from your messages:

### 1. Debugging Mode
**Signals:** fix, broken, error, bug, issue, wrong, not working, fails, crash, exception

**Approach:**
- Check recent changes first
- Review error logs
- Identify root cause BEFORE fixing
- Don't change code until you understand the issue

**Avoid:**
- Making changes without understanding
- Multiple fixes at once (hard to isolate)

**Tools:** Error logs, git diff, debugger

---

### 2. Performance Mode
**Signals:** slow, fast, optimize, performance, speed, memory, cpu, latency, efficient

**Approach:**
- Measure before changing
- Profile to identify bottleneck
- Document baseline metrics
- Change one thing at a time

**Avoid:**
- Premature optimization
- Changing without measuring first
- Optimizing non-bottlenecks

**Tools:** Profiler, time command, resource monitors

---

### 3. Feature Mode
**Signals:** add, create, implement, build, new, feature, want, need to

**Approach:**
- Understand requirements fully
- Check existing patterns in codebase
- Plan before coding
- Consider edge cases

**Avoid:**
- Over-engineering
- Skipping tests
- Not checking for similar features

**Tools:** memory_query for similar features, project patterns

---

### 4. Refactor Mode
**Signals:** refactor, clean, reorganize, restructure, improve, simplify

**Approach:**
- Ensure tests exist first
- Make small incremental changes
- Verify behavior unchanged after each step
- Commit frequently

**Avoid:**
- Changing behavior during refactor
- Large changes without tests
- Refactoring untested code

**Tools:** Test suite, git diff, code review

---

### 5. Exploration Mode
**Signals:** how, what, where, why, explain, understand, find, show, look

**Approach:**
- Use memory query first (instant)
- Check existing documentation
- Explore systematically
- Build mental model before acting

**Avoid:**
- Modifying code while exploring
- Making assumptions

**Tools:** memory_query, memory_search, Grep, Read

---

### 6. Infrastructure Mode
**Signals:** docker, deploy, server, database, config, setup, install, environment

**Approach:**
- Check current state first
- Document all changes
- Test in isolation before applying
- Have rollback plan

**Avoid:**
- Making production changes without testing
- Undocumented configuration
- Assuming environment matches local

**Tools:** Docker, config files, environment variables

---

## Mode Confidence

When mode is detected with low confidence (<0.5):

```
<pattern-context mode="exploration" confidence="0.33">
```

This means:
- Multiple modes match equally
- Signals are ambiguous
- May need clarification

**Response:** Ask which approach the user wants:
"I could approach this as exploration (understanding the code) or as a feature (implementing something). Which would you prefer?"

## Mode Switching

Users can explicitly switch:
- "Let's switch to debugging mode"
- "I want to explore first"
- "Time to refactor this"

When switching, acknowledge and adjust:
"Switching to debugging mode. Let me check what changed recently and look at the error logs."

## Multi-Mode Tasks

Some tasks span modes:
1. **Explore** → understand the issue
2. **Debug** → find root cause
3. **Feature** → implement fix
4. **Refactor** → clean up after

It's okay to move through modes naturally. The key is being intentional about which mode you're in.

## Mode-Specific Memory Queries

Each mode benefits from different queries:

| Mode | Useful Queries |
|------|---------------|
| Debugging | `memory_sessions category=bugfix query="topic"` |
| Performance | `memory_sessions category=pattern query="optimization"` |
| Feature | `memory_query "similar feature implementation"` |
| Refactor | `memory_similar file="file-being-refactored"` |
| Exploration | `memory_query "how does X work"` |
| Infrastructure | `memory_sessions category=gotcha query="docker"` |
