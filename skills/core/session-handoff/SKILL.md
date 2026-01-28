---
name: session-handoff
description: When user says "continue", "pick up where we left off", "last time", "previous session", "what were we doing", or wants explicit session continuity. Provides structured context handoff between sessions.
---

# Session Handoff Framework

## When This Activates

This skill activates when:
- Starting a new session with continuity expectations
- User explicitly asks about previous work
- Context from last session is needed

## Session Continuity Data

The system automatically tracks:

### Last Session Summary
```
<session-continuity>
[LAST SESSION] Description of what was worked on
Files: list of key files
</session-continuity>
```

### Recent Decisions
Important choices made recently that affect current work.

### Learned Patterns
- Gotchas discovered
- Decisions recorded
- Patterns established

## Handoff Protocol

### 1. Acknowledge State (What we know)
```
"Continuing from the last session where we worked on [X]...

Current state:
- Last worked on: [from session-continuity]
- Pending items: [from PENDING WORK]
- Blockers: [from BLOCKERS if any]"
```

### 2. Address Blockers First (If any)
```
"I see there's a blocker we need to address first:
  [blocker description]

Let me investigate this before continuing..."
```

### 3. Propose Next Actions
```
"Based on our pending work, I suggest we:
1. [Most important/blocked item first]
2. [Next priority item]
3. [Continue from where we left off]

Which would you like to tackle?"
```

### 4. Check for External Changes
```
"Let me check what changed since then..."
→ Use git_awareness for code changes
→ Check for new errors or issues
```

## MCP Tools for Continuity

```
# Get session context
memory_sessions list_sessions=true

# Get recent decisions
memory_sessions category=decision limit=5

# Check what changed
memory_query "recent changes to [area]"
```

## Session Recovery Scenarios

### "What were we working on?"
1. Check `<session-continuity>` injection
2. Query recent session observations
3. Summarize last activities

### "Continue from last time"
1. Recall last session context
2. Check git for any external changes
3. Resume with state awareness

### "Pick up [specific task]"
1. Search session history for task
2. Load relevant context
3. Resume from last known state

## State Persistence

Sessions are persisted in:
```
~/.claude-dash/sessions/
├── {project}/
│   └── session-{timestamp}.json
├── observations.json (cross-session learnings)
├── summaries/ (per-project summaries)
└── transcripts/ (compressed conversation logs)
```

## Best Practices

1. **End sessions cleanly** - Summarize what was done
2. **Note blocking issues** - Record what couldn't be resolved
3. **Mark next steps** - Clarify intended continuation
4. **Save decisions** - Record important choices with context

## Actionable Handoff Checklist

At session start:
- [ ] Read `<session-continuity>` injection
- [ ] Check for `[PENDING WORK]` items
- [ ] Check for `[BLOCKERS]` - address these first
- [ ] Acknowledge state to user
- [ ] Propose next actions based on priorities

At session end:
- [ ] Summarize what was completed
- [ ] Note any new blockers discovered
- [ ] Update roadmap if tasks completed
- [ ] Record any important decisions made

## Continuity Phrases

Use these to acknowledge context:
- "Picking up from where we left off..."
- "Based on our last session where we..."
- "Continuing the work on [X]..."
- "As we discussed previously..."

## Handling Missing Context

If session context isn't available:
```
"I don't have specific context from our last session.
Could you remind me what we were working on, or should
I check the recent git history and project state?"
```
