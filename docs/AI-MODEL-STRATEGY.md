# AI Model Selection Strategy

**Last Updated:** 2026-01-26
**Hardware:** Mac Mini M2, 16GB RAM
**Goal:** Quality over cost - use the right model for the job

---

## The Quality-First Approach

```
Task Criticality:    Low ←――――――――――――――→ High
                      │         │        │
Tools Used:        Local  ← Haiku → Sonnet → Opus
Token Cost:         $0      $      $$     $$$$
Quality:           Low    Good   Great  Excellent
```

**IMPORTANT:** Local LLM is NOT for critical development work.

---

## Tier 1: Haiku - $ (Fast Exploration)

### Use Haiku For:

**Quick, straightforward tasks:**
- File/code exploration: "Show me all API routes"
- Simple lookups: "Find files that use Firebase"
- Code formatting/style fixes
- Adding debug logging
- Simple translations/conversions
- Documentation updates

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

## Tier 2: Sonnet - $$ (Default for Development)

### Use Sonnet For:

**THE DEFAULT for all development work:**
- ALL implementation work (even from Opus plans)
- Bug fixes requiring context understanding
- Feature additions to existing code
- Test writing
- Most day-to-day coding tasks
- Refactoring with clear approach

**Planning (75% of cases):**
- Feature implementations following existing patterns
- Well-understood problems
- Most day-to-day planning

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

## Tier 3: Opus - $$$$ (Complex Architecture)

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

## Tier 4: Local Ollama - $0 (Non-Critical Only)

### IMPORTANT: NOT for Critical Development Work

Local LLM (Ollama) is NOT appropriate for development tasks. Use ONLY for:

**Acceptable Uses:**
- Enchanted/mobile app queries (API access)
- Commit message generation (`mlx commit`)
- PR description drafts (`mlx pr`)
- Personal tinkering and experimentation

**DO NOT Use Local For:**
- ❌ Code generation or modification
- ❌ Bug debugging or investigation
- ❌ Feature implementation
- ❌ Code review for critical changes
- ❌ Any task where quality matters

### Manual MLX Commands (Terminal)

```bash
# Git operations only
mlx commit                              # Generate commit message
mlx pr [base]                           # Generate PR description
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
Is it a simple exploration/lookup?
    ├─ YES → Use HAIKU (fast, cheap)
    │
    └─ NO → Is it trivial (commit msg, personal experiment)?
            ├─ YES → Local OK
            └─ NO → Use SONNET
```

---

## Quick Reference Card

**Model Selection:**

| Task Type | Model | Why |
|-----------|-------|-----|
| Complex architecture | **Opus** | High-stakes decisions |
| Standard planning | **Sonnet** | 75% of planning tasks |
| Implementation | **Sonnet** | Always |
| Exploration/lookup | **Haiku** | Fast and cheap |
| Commit messages | Local | Non-critical |

**Remember:** Quality over cost. Use Claude for critical work, Local only for trivial non-development tasks.
