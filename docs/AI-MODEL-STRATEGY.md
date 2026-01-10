# AI Model Selection Strategy

**Last Updated:** 2026-01-10
**Hardware:** Mac Mini M2, 16GB RAM
**Goal:** Minimize token costs while maintaining quality

---

## The Gradient Approach

```
Question Complexity:     Low ←――――――――――――――→ High
                         │         │        │
Tools Used:          Local MLX  → Sonnet → Opus
Token Cost:          $0        → $$     → $$$$
Response Time:       2-3s      → 10-20s → 15-30s
```

---

## Tier 1: Local First (qwen2.5:7b via MLX) - $0

### Automatic MLX Routing (Claude does this)

When asking Claude questions, these patterns trigger automatic MLX usage:

| Question Pattern | MLX Command | Example |
|-----------------|-------------|---------|
| "Where is X?" | `mlx q <project> "query"` | "Where is the login screen?" |
| "Find files that..." | `mlx db-search <query>` | "Find files that use Firebase" |
| "How does X work?" (exploring) | `mlx rag <project> "query"` | "How does authentication work?" |
| "What files use X?" | `mlx q <project> "query"` | "What files use AuthContext?" |
| Function lookups | `mlx db-functions <name>` | "Find handleSubmit function" |

**Context Awareness:**
- **Exploring phase** (first messages, no files read) → Use MLX
- **Mid-implementation** (files loaded, actively coding) → Skip MLX, use loaded context

### Manual MLX Usage (Terminal/Direct)

Commands to run yourself to save tokens:

```bash
# Before asking Claude
mlx q <project> "where is X?"           # Find files/features
mlx rag <project> "how does X work?"    # Understand systems
mlx db-functions "functionName"         # Find function locations
mlx similar <project> <file>            # Find related files

# Git operations
mlx commit                              # Generate commit message
mlx pr [base]                           # Generate PR description

# Code quality
mlx code-review [file]                  # Review for issues
mlx test <file>                         # Generate test scaffolds
mlx error                               # Analyze error messages
```

### Current Local Model

**Installed:** `llama3.2:3b` (2GB)
**Recommended Upgrade:** `qwen2.5:7b` (4.7GB)

**Why upgrade?**
- 2-3x better at `mlx rag` (understanding complex questions)
- Significantly better code review (catches logic issues, not just syntax)
- Better intent classification
- Still fast on M2 (2-3 seconds)
- Fits comfortably in 16GB RAM (~5-6GB usage)

**To upgrade:**
```bash
ollama pull qwen2.5:7b
```

---

## Tier 2: Sonnet - $$

### Use Sonnet For:

**Planning (75% of cases):**
- ✅ Feature implementations following existing patterns
- ✅ Refactoring with clear approach
- ✅ Well-understood problems
- ✅ Most day-to-day planning

**Examples:**
- "Add user profile edit screen" (follow existing patterns)
- "Implement pagination for product list" (known pattern)
- "Refactor auth to use context" (clear path)
- "Add dark mode support" (established approach)

**Implementation (100% of cases):**
- ✅ ALL implementation work (even from Opus plans)
- ✅ Bug fixes requiring context understanding
- ✅ Feature additions to existing code
- ✅ Test writing
- ✅ Most day-to-day coding tasks

### Agent Usage with Sonnet

```javascript
// Planning agent
Task({
  subagent_type: "Plan",
  model: "sonnet",  // Use sonnet for standard planning
  prompt: "Plan implementation of user profile editing"
})

// Implementation agent
Task({
  subagent_type: "coder",
  model: "sonnet",  // Always sonnet for implementation
  prompt: "Implement the approved plan"
})
```

---

## Tier 3: Opus - $$$$

### Use Opus ONLY For:

**Complex Planning (25% of cases):**
- ✅ Greenfield architecture decisions
- ✅ Multiple valid approaches with non-obvious trade-offs
- ✅ High cost to reverse if wrong choice
- ✅ Cross-cutting technical decisions (security, scalability, performance)

**Examples:**
- "Design real-time sync system for offline-first app"
- "Architect multi-tenant data isolation strategy"
- "Evaluate: monorepo vs microservices for new platform"
- "Design migration path from Firebase to self-hosted"

### NEVER Use Opus For:

- ❌ Implementation (always use Sonnet)
- ❌ Exploration (use MLX or Sonnet)
- ❌ Simple/standard planning (use Sonnet)
- ❌ Bug fixes (use Sonnet)
- ❌ Following established patterns (use Sonnet)

### Agent Usage with Opus

```javascript
// Only for genuinely complex planning
Task({
  subagent_type: "Plan",
  model: "opus",  // Reserve for complex architecture
  prompt: "Design data sync architecture for offline-first mobile app with conflict resolution"
})
```

---

## Tier 4: Haiku - $

### Use Haiku For:

**Quick, straightforward tasks:**
- ✅ File/code exploration: "Show me all API routes"
- ✅ Simple refactors: "Rename variable X to Y"
- ✅ Code formatting/style fixes
- ✅ Adding debug logging
- ✅ Simple translations/conversions
- ✅ Documentation updates

### Agent Usage with Haiku

```javascript
// Exploration agent
Task({
  subagent_type: "Explore",
  model: "haiku",  // Fast exploration
  prompt: "Find all files that define React components"
})
```

---

## Decision Tree

### For Planning Tasks

```
New task arrives
    ↓
Is this genuinely complex architecture?
  • Multiple approaches with non-obvious trade-offs?
  • Greenfield design with high cost to reverse?
  • Cross-cutting concerns (security, performance, scale)?
    ├─ YES → Use OPUS for planning
    │         Then SONNET for implementation
    │
    └─ NO → Use SONNET for planning
            Then SONNET for implementation
```

### For Quick Tasks

```
New task arrives
    ↓
Need to find/explore first?
    ├─ YES → Use MLX (local, $0)
    │        mlx q / mlx rag / mlx db-search
    │
    └─ NO → Is it straightforward?
            ├─ YES → HAIKU
            └─ NO → SONNET
```

---

## Token Savings Estimate

**Before optimization:**
- Exploration: Claude Sonnet ($$)
- Planning: Opus by default ($$$$)
- Implementation: Sonnet ($$)

**After optimization:**
- Exploration: MLX local ($0) ← **Saves 100%**
- Planning: Sonnet for 75% of cases ($$) ← **Saves ~40%**
- Implementation: Sonnet ($$) ← **No change**

**Overall estimated savings: ~50-60% of total token usage**

---

## Implementation Checklist

- [ ] Upgrade Ollama: `ollama pull qwen2.5:7b`
- [ ] Test MLX with new model: `mlx rag gyst "how does authentication work?"`
- [ ] Update global preferences with new model selection rules
- [ ] Create shell function for terminal usage (optional)
- [ ] Practice using MLX before asking Claude
- [ ] Default to Sonnet for planning, reserve Opus for complex cases

---

## Quick Reference Card

**Before asking Claude:**

| Question Type | Try First | Command |
|--------------|-----------|---------|
| Where is X? | MLX | `mlx q <project> "query"` |
| How does X work? | MLX | `mlx rag <project> "query"` |
| Find function X | MLX | `mlx db-functions "name"` |
| Commit message | MLX | `mlx commit` |
| PR description | MLX | `mlx pr` |

**When using agents:**

| Task Type | Model | Why |
|-----------|-------|-----|
| Complex planning | Opus | Genuinely hard problems |
| Standard planning | Sonnet | 75% of planning tasks |
| Implementation | Sonnet | Always |
| Exploration | Haiku | Fast and cheap |

**Remember:** If in doubt, ask yourself: "Could I use MLX for this?" → Try it first!
