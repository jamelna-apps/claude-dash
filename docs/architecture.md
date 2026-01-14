# Claude Code Architecture: Hooks, MCPs, Agents, and .md Files

## Session Lifecycle

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           SESSION START                                      │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  1. CLAUDE.md FILES LOADED (Static Context)                                 │
│                                                                             │
│  Searched in order (all matching files merged):                             │
│  • ~/.claude/CLAUDE.md              (global preferences)                    │
│  • ~/Documents/Projects/CLAUDE.md   (workspace-level)                       │
│  • ./CLAUDE.md                      (project-level)                         │
│  • ./.claude/CLAUDE.md              (project hidden)                        │
│                                                                             │
│  Purpose: Static instructions, project context, coding conventions          │
│  When: Once at session start, becomes part of system prompt                 │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  2. MCP SERVERS CONNECTED                                                   │
│                                                                             │
│  Configured in: ~/Library/Application Support/Claude/claude_desktop_config  │
│  Or for CLI: ~/.claude.json                                                 │
│                                                                             │
│  Your active MCP servers:                                                   │
│  • claude-dash (gateway)  → memory_query, memory_search, doc_query, etc.   │
│  • MCP_DOCKER             → browser tools, mcp-find, mcp-add               │
│                                                                             │
│  Purpose: Provide additional tools beyond built-in ones                     │
│  When: Connected at session start, tools available throughout              │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         CONVERSATION LOOP                                    │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
         ┌──────────────────────────┼──────────────────────────┐
         │                          │                          │
         ▼                          ▼                          ▼
┌─────────────────┐    ┌─────────────────────┐    ┌─────────────────────┐
│ USER SENDS      │    │ 3. UserPromptSubmit │    │                     │
│ MESSAGE         │───▶│    HOOK RUNS        │───▶│ CLAUDE RECEIVES     │
│                 │    │                     │    │ MESSAGE + CONTEXT   │
└─────────────────┘    │ inject-context.sh:  │    └─────────────────────┘
                       │ • Pattern detection │              │
                       │ • Mode context      │              │
                       │ • Project memory    │              ▼
                       │ • Preferences       │    ┌─────────────────────┐
                       └─────────────────────┘    │ CLAUDE PROCESSES    │
                                                  │                     │
                                                  │ Has access to:      │
                                                  │ • CLAUDE.md context │
                                                  │ • Hook-injected ctx │
                                                  │ • MCP tools         │
                                                  │ • Built-in tools    │
                                                  └─────────────────────┘
                                                            │
                       ┌────────────────────────────────────┼────────────────┐
                       │                                    │                │
                       ▼                                    ▼                ▼
            ┌─────────────────────┐            ┌─────────────────┐  ┌────────────────┐
            │ TOOL CALLS          │            │ MCP TOOL CALLS  │  │ SPAWN AGENTS   │
            │                     │            │                 │  │                │
            │ Built-in:           │            │ memory_query    │  │ Task tool with │
            │ • Read, Write, Edit │            │ memory_search   │  │ subagent_type: │
            │ • Bash, Glob, Grep  │            │ doc_query       │  │ • Explore      │
            │ • WebSearch, etc.   │            │ browser_*       │  │ • Plan         │
            └─────────────────────┘            └─────────────────┘  │ • coder        │
                       │                                │           │ • planner      │
                       │                                │           └────────────────┘
                       │                                │                    │
                       ▼                                ▼                    ▼
            ┌─────────────────────────────────────────────────────────────────────┐
            │  4. PreToolUse / PostToolUse HOOKS (if configured)                  │
            │                                                                     │
            │  Can intercept tool calls for:                                      │
            │  • Logging                                                          │
            │  • Approval gates                                                   │
            │  • Capturing results                                                │
            └─────────────────────────────────────────────────────────────────────┘
                                                  │
                                                  ▼
                                    ┌─────────────────────┐
                                    │ CLAUDE RESPONDS     │
                                    │                     │
                                    │ Response informed   │
                                    │ by all above        │
                                    └─────────────────────┘
                                                  │
                                                  ▼
                                          (Loop continues)
                                                  │
                                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           SESSION END                                        │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  5. Stop HOOK RUNS                                                          │
│                                                                             │
│  save-session.sh:                                                           │
│  • Archives transcript                                                      │
│  • Runs observation_extractor.py (background)                               │
│    └─▶ Uses Ollama to extract decisions, patterns, bugfixes                │
│    └─▶ Saves to observations.json                                          │
│    └─▶ Learns patterns from user phrases                                   │
│    └─▶ Updates patterns.json with learned associations                     │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Component Details

### 1. CLAUDE.md Files (Static Context)

**What they do:** Provide instructions that become part of my system prompt

**Location hierarchy:**
```
~/.claude/CLAUDE.md                    # Your global preferences (rare)
~/Documents/Projects/CLAUDE.md         # Workspace-wide rules ← YOU HAVE THIS
./CLAUDE.md                            # Per-project rules
./.claude/CLAUDE.md                    # Hidden per-project
```

**Your CLAUDE.md contains:**
- Project memory system documentation
- Registered projects list
- Memory file structure
- Token-saving strategies
- Trigger phrases for preferences

**When loaded:** Session start, read-only, merged into context

---

### 2. MCP Servers (Dynamic Tools)

**What they do:** Extend my capabilities with custom tools

**Your MCP servers:**

| Server | Tools Provided | Purpose |
|--------|----------------|---------|
| claude-dash | memory_query, memory_search, memory_functions, memory_similar, memory_sessions, doc_query | Project memory + document RAG |
| MCP_DOCKER | browser_*, mcp-find, mcp-add | Browser automation, MCP catalog |

**Config location:** `~/Library/Application Support/Claude/claude_desktop_config.json`

**When active:** Throughout session, I call these tools like built-in ones

---

### 3. Hooks (Lifecycle Events)

**What they do:** Run shell commands at specific points

**Your configured hooks:**

| Hook | When | Script | Purpose |
|------|------|--------|---------|
| UserPromptSubmit | Before I see your message | inject-context.sh | Pattern detection, context injection |
| Stop | Session ends | save-session.sh | Extract observations, learn patterns |

**Hook data flow:**
```
Hook receives JSON → Processes → Outputs text → I see the output
```

---

### 4. Agents (Specialized Subprocesses)

**What they do:** Handle complex tasks autonomously

**When I spawn them:** Via the Task tool with subagent_type

| Agent Type | Purpose | Has Access To |
|------------|---------|---------------|
| Explore | Find files/code quickly | Glob, Grep, Read |
| Plan | Design implementation | All tools |
| coder | Write code | Read, Write, Edit, Bash, memory tools |
| planner | Architectural decisions | Read, Grep, memory tools |

**Agent lifecycle:**
```
I call Task → Agent spawns → Works autonomously → Returns result → I summarize
```

---

## Data Flow Example

**You type:** "this docker setup is slow, can we optimize?"

```
1. UserPromptSubmit hook runs
   │
   ├─▶ Pattern detector sees "slow" + "optimize"
   │   └─▶ Detects: PERFORMANCE mode (66% confidence)
   │
   ├─▶ Injects context:
   │   <pattern-context mode="performance">
   │   Suggested: Measure before changing, profile first
   │   Avoid: Premature optimization
   │   </pattern-context>
   │
   └─▶ Also injects: project preferences, infrastructure.json

2. I receive your message + injected context
   │
   ├─▶ CLAUDE.md tells me: "prefer native for GPU workloads"
   ├─▶ Pattern context tells me: "measure before changing"
   └─▶ I know to: check current performance → identify bottleneck → suggest fix

3. I call tools
   │
   ├─▶ memory_query("docker performance") → check past decisions
   ├─▶ Bash("docker stats") → measure current state
   └─▶ Based on findings, suggest optimization

4. Session ends
   │
   └─▶ Stop hook runs
       └─▶ Observation extractor:
           - Records: "Migrated Ollama to native for 40x speedup"
           - Learns: "docker...slow...optimize" → infrastructure mode
           - Updates: patterns.json with your phrase patterns
```

---

## File Locations Summary

```
~/.claude/
├── settings.json              # Hook configuration
├── CLAUDE.md                  # Global instructions (optional)
└── hooks/
    ├── inject-context.sh      # UserPromptSubmit hook
    └── save-session.sh        # Stop hook

~/.claude-dash/
├── config.json                # Project registry
├── global/
│   ├── preferences.json       # Your preferences (use/avoid)
│   └── infrastructure.json    # System decisions
├── patterns/
│   ├── patterns.json          # Mode definitions + learned patterns
│   └── detector.py            # Pattern detection logic
├── mlx-tools/
│   └── observation_extractor.py  # Session learning
├── gateway/
│   └── server.js              # MCP server (memory + doc_query)
├── projects/
│   └── {project}/             # Per-project memory
└── sessions/
    └── observations.json      # Extracted observations

~/Documents/Projects/
└── CLAUDE.md                  # Your workspace instructions
```
