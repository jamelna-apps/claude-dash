---
name: error-diagnosis
description: When user encounters "error", "exception", "failed", "stack trace", "crashed", or needs error categorization. Provides structured root cause analysis and prevention strategies.
---

# Error Diagnosis Framework

## When This Activates

This skill activates when:
- User shares an error message or stack trace
- Something failed unexpectedly
- Debugging session errors
- Need to categorize and prevent errors

## Error Categories

### 1. Prompt Errors (User → Claude)
| Subcategory | Description | Prevention |
|-------------|-------------|------------|
| `ambiguous_instruction` | Could be interpreted multiple ways | Be specific about expected output |
| `missing_constraints` | Didn't specify what NOT to do | State exclusions explicitly |
| `too_verbose` | Key requirements buried in text | Put critical info first |
| `implicit_expectations` | Requirements in head, not prompt | Write everything down |
| `wrong_abstraction` | Too high/low level for task | Match detail to task complexity |

### 2. Context Errors (Session State)
| Subcategory | Description | Prevention |
|-------------|-------------|------------|
| `context_rot` | Conversation too long | Clear context periodically |
| `stale_context` | Old info polluting responses | Start fresh for new topics |
| `missing_context` | Assumed Claude remembered | Re-state critical context |
| `wrong_context` | Irrelevant info drowning signal | Provide focused context |

### 3. Harness Errors (Agent System)
| Subcategory | Description | Prevention |
|-------------|-------------|------------|
| `subagent_context_loss` | Info didn't reach subagents | Pass explicit context |
| `wrong_agent_type` | Used wrong specialized agent | Match agent to task |
| `no_guardrails` | Didn't constrain behavior | Set clear boundaries |
| `missing_validation` | No check that output correct | Verify results |

### 4. Tool Errors (Execution)
| Subcategory | Description | Prevention |
|-------------|-------------|------------|
| `wrong_command` | Incorrect command/syntax | Verify syntax before running |
| `missing_dependency` | Package not installed | Check deps first |
| `permission_error` | Insufficient permissions | Check access rights |
| `path_error` | File/directory not found | Verify paths exist |
| `syntax_error` | Code syntax issue | Lint before running |

## Diagnosis Workflow

### Step 1: Categorize
```
Error received → Identify category → Identify subcategory
```

### Step 2: Extract Details
```json
{
  "category": "tool",
  "subcategory": "path_error",
  "summary": "File not found when trying to read config",
  "root_cause": "Path was relative but CWD was different",
  "prevention": "Use absolute paths or verify CWD"
}
```

### Step 3: Generate Fix
Based on category, apply targeted fix strategy.

### Step 4: Record Learning
Add to ReasoningBank for future reference.

## Common Error Patterns

### "Module not found"
```
Category: tool/missing_dependency
Check: Is the package installed? Right version? Correct import path?
Fix: npm install / pip install / check import statement
```

### "Permission denied"
```
Category: tool/permission_error
Check: File permissions? Running as correct user? Sudo needed?
Fix: chmod, chown, or run with appropriate privileges
```

### "Undefined is not a function"
```
Category: tool/syntax_error (or context/stale_context)
Check: Is object initialized? Correct method name? Async/await issue?
Fix: Add null checks, verify object shape, await promises
```

### "CORS error"
```
Category: tool/wrong_command (or infrastructure)
Check: Server CORS config? Proxy setup? Credentials mode?
Fix: Configure CORS headers, use proxy in dev
```

### "Claude did the wrong thing"
```
Category: prompt/* (most likely)
Check: Was instruction ambiguous? Missing constraints? Too much context?
Fix: Rewrite prompt with specific details
```

## Error Response Template

When diagnosing an error, respond with:

```markdown
## Error Analysis

**Category:** [category/subcategory]
**Root Cause:** [what actually went wrong]

## Fix
[specific steps to resolve]

## Prevention
[how to avoid this in the future]

## Similar Past Issues
[if any relevant observations exist]
```

## MCP Tools for Diagnosis

```
# Check past similar errors
memory_sessions category=bugfix query="similar error"

# Get reasoning bank solutions
reasoning_query context="error description"

# Check if this was a known gotcha
memory_sessions category=gotcha query="topic"
```

## Learning Integration

Errors feed into:
- ReasoningBank trajectories
- Observation extractor (bugfix category)
- Confidence calibration (track error rates by domain)
