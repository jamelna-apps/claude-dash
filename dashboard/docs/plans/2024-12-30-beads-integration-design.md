# Beads + Claude Memory Integration Design

## Overview

Integrate Beads (git-backed task tracker for AI agents) with the claude-memory system to create a unified project memory that combines task tracking, session continuity, and code intelligence.

## Goals

1. **Task Tracking** - Track tasks, blockers, and dependencies per project
2. **Session Continuity** - Pick up where previous sessions left off
3. **Multi-Agent Collaboration** - Sequential handoffs between agents with full context

## Architecture

### Two-Layer System

**Per-Project Layer (`.beads/` in each repo):**
- Tasks, issues, and dependencies (Beads' JSONL format)
- Git-tracked, travels with the code
- Uses Beads CLI (`bd`) for task operations

**Global Layer (`~/.claude-memory/`):**
- Project registry, code intelligence (existing)
- Cross-project index of active tasks
- Session history linking to Beads tasks

### Data Flow

**Session Startup:**
1. Load Beads context - Read `.beads/` for active tasks, recent decisions, blockers
2. Load claude-memory context - Read `functions.json`, `schema.json`, `graph.json`
3. Merge into unified context - Present combined view

**Task Lifecycle:**
```
Create task → .beads/tasks (git-tracked)
      ↓
Work on task → Session logs reference task ID
      ↓
Complete task → Mark done in .beads/, update global index
      ↓
Git commit → Task history travels with code
```

**Agent Handoff:**
When Agent B picks up from Agent A:
1. Reads `.beads/` - sees task state, what was attempted
2. Reads git log - sees what changed
3. Gets full context without Agent A being present

## Integration Points

### CLI Commands (Unified Interface)

```bash
# Task management (wraps Beads)
claude-memory task create "Fix login validation"
claude-memory task list                    # Active tasks across all projects
claude-memory task list --project gyst     # Project-specific
claude-memory task done <id>

# Existing commands enhanced with task context
claude-memory query gyst "where is login?"
claude-memory session start gyst           # Loads tasks + code intel
```

### Dashboard Integration

- Project cards show **active task count** alongside health score
- Project view gets new **Tasks tab** showing Beads tasks
- Tasks link to relevant files (via function index)

### Session Hook Enhancement

Existing `SessionStart` hook expands:
```
Current: Load summaries.json, schema.json, graph.json
New:     + Load .beads/ for active tasks
         + Show "Continuing task #42: Fix login validation"
```

### Beads Native Commands

```bash
cd WardrobeApp
bd create "Add dark mode"    # Creates in .beads/
bd ready                     # Shows unblocked tasks
bd show <id>                 # Task details
```

Both interfaces write to the same `.beads/` files.

## Beads Reference

**Installation:**
```bash
npm install -g @beads/bd
# or
brew install steveyegge/beads/bd
```

**Key Commands:**
| Command | Purpose |
|---------|---------|
| `bd init` | Initialize Beads in a repository |
| `bd ready` | Display tasks without open blockers |
| `bd create "Title"` | Create a task |
| `bd dep add <child> <parent>` | Establish task dependencies |
| `bd show <id>` | View task details and history |

**File Format:**
- JSONL files in `.beads/` directory
- Hash-based IDs (e.g., `bd-a1b2`)
- Hierarchical subtasks (`bd-a3f8.1`, `bd-a3f8.1.1`)

## Implementation Phases

### Phase 1: Beads Setup
- Install Beads CLI globally
- Initialize `.beads/` in each registered project
- Verify git tracking works

### Phase 2: Claude-Memory Integration
- Add task loading to session startup hook
- Create global tasks index at `~/.claude-memory/tasks-index.json`
- Sync logic: on task create/complete, update global index

### Phase 3: CLI Commands
- Add `task` subcommand to mlx-tools
- Commands: `create`, `list`, `done`, `show`
- Delegates to Beads for storage, adds cross-project awareness

### Phase 4: Dashboard Enhancement
- Add task count to project cards (portal view)
- Add Tasks tab to project view
- New endpoint: `/api/projects/{id}/tasks`

## Migration

**For each registered project:**
1. `bd init` in project root
2. `.beads/` added to git
3. First commit establishes task history

**Edge Cases:**
| Scenario | Behavior |
|----------|----------|
| Project has no `.beads/` | Session loads without tasks, suggests init |
| Global index out of sync | Rebuild from scanning `.beads/` directories |
| Task references deleted file | Mark task as stale, surface in dashboard |

## What We're NOT Building

- Custom JSONL parser (use Beads' format as-is)
- Real-time sync (git push/pull is explicit)
- Complex dependency graphs (start simple)
- Breaking changes to existing claude-memory workflow

## Git Workflow

```bash
# Before session
git pull                    # Get latest tasks

# During session
bd create "Fix bug"         # Local .beads/ updated
git add .beads/ && git commit

# After session
git push                    # Share task state
```
