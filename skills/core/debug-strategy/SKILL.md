---
name: debug-strategy
description: When the user mentions "bug", "error", "not working", "broken", "crash", "fails", "issue", "problem", or asks why something doesn't work. Provides systematic debugging approaches.
---

# Systematic Debugging Strategy

## Initial Assessment

Before diving in, gather context:
1. **What changed?** - Recent code changes, deployments, dependencies
2. **When did it start?** - Timeline helps narrow scope
3. **Reproducible?** - Consistent vs intermittent affects approach
4. **Error messages?** - Exact text, stack traces, logs
5. **Environment?** - Dev/staging/prod, OS, versions

## Debugging Hierarchy (Work Through In Order)

### 1. Read the Error Message
- Parse the FULL stack trace
- Note the originating file and line number
- Look for "Caused by" chains
- Search error message verbatim if unclear

### 2. Reproduce Locally
- Create minimal reproduction case
- Isolate variables (data, environment, timing)
- Add logging at key points

### 3. Binary Search the Problem
- Comment out half the code
- Does it still fail? Problem is in remaining half
- Repeat until isolated

### 4. Check the Obvious
- Is it saved? Is it deployed?
- Correct environment variables?
- Dependencies installed/updated?
- Cache cleared?
- Correct branch?

### 5. Trace Data Flow
- Log inputs at entry point
- Log outputs at each transformation
- Find where actual diverges from expected

## Common Bug Patterns

| Symptom | Likely Causes |
|---------|---------------|
| Works locally, fails in prod | Env vars, paths, permissions, CORS |
| Intermittent failure | Race condition, caching, timing |
| Undefined/null error | Missing data, async timing, typo |
| Silent failure | Swallowed exception, wrong error handler |
| Performance degradation | N+1 queries, memory leak, missing index |

## Debug Tools by Domain

**JavaScript/React:**
- Browser DevTools (Console, Network, React DevTools)
- `console.log`, `console.table`, `debugger`
- React Query DevTools, Redux DevTools

**React Native:**
- Flipper, React Native Debugger
- `adb logcat` (Android), Console.app (iOS)
- Remote JS debugging

**Node.js:**
- `--inspect` flag + Chrome DevTools
- `DEBUG=*` environment variable
- `node --trace-warnings`

**Database:**
- Query explain plans
- Slow query logs
- Connection pool monitoring

## Output Format

When reporting findings:
1. **Root Cause** - What actually caused the bug
2. **Fix** - Code change required
3. **Prevention** - How to avoid similar bugs
4. **Testing** - How to verify the fix
