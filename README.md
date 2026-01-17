# Claude-Dash

Persistent memory, learning systems, and local AI tools for Claude Code.

## What It Does

Claude-Dash gives Claude Code persistent memory across sessions. It indexes your projects, learns from corrections, tracks your preferences, and provides intelligent context injection that makes Claude smarter over time.

**Key capabilities:**
- **Session Continuity** - Remembers what you worked on last session
- **Learning from Corrections** - "No, I meant X" gets recorded and recalled
- **Git Awareness** - Shows what changed since your last session
- **Preference Inference** - Learns your coding style from your edits
- **Confidence Calibration** - Tracks accuracy by domain to know when to be more careful
- **Semantic Memory** - Auto-fetches relevant context when you mention topics like "docker" or "auth"

## Quick Start

### One-Line Install

```bash
curl -fsSL https://raw.githubusercontent.com/jamelna-apps/claude-dash/main/install.sh | bash
```

### Manual Installation

1. Clone this repository:
   ```bash
   git clone https://github.com/jamelna-apps/claude-dash.git ~/.claude-dash
   ```

2. Run the installer:
   ```bash
   ~/.claude-dash/install.sh
   ```

### Manual Setup (Advanced)

1. Clone this repository:
   ```bash
   git clone https://github.com/jamelna-apps/claude-dash.git ~/.claude-dash
   ```

2. Set up configuration:
   ```bash
   cd ~/.claude-dash
   cp config.example.json config.json
   cp global/preferences.example.json global/preferences.json
   ```

3. Edit `config.json` and add your projects.

4. Install dependencies:
   ```bash
   cd watcher && npm install
   ```

5. Install Ollama (required for learning features):
   ```bash
   brew install ollama
   # Task-optimized models for M2 16GB
   ollama pull deepseek-coder:6.7b    # Code review & analysis
   ollama pull gemma3:4b              # RAG queries (128K context!)
   ollama pull phi3:mini              # Quick tasks (commit messages)
   ollama pull qwen3-vl:8b            # UI/screenshot analysis
   ollama pull nomic-embed-text       # Embeddings for semantic search
   ```

6. Set up Claude Code hooks:
   ```bash
   mkdir -p ~/.claude/hooks
   cp ~/.claude-dash/hooks/*.sh ~/.claude/hooks/
   chmod +x ~/.claude/hooks/*.sh
   ```

7. Add hooks to Claude Code settings (`~/.claude/settings.json`):
   ```json
   {
     "hooks": {
       "UserPromptSubmit": [{
         "matcher": "",
         "hooks": [{"type": "command", "command": "~/.claude/hooks/inject-context.sh"}]
       }],
       "Stop": [{
         "matcher": "",
         "hooks": [{"type": "command", "command": "~/.claude/hooks/save-session.sh"}]
       }]
     }
   }
   ```

8. Add the MCP server to Claude Code (see MCP Setup section).

9. Start the watcher:
   ```bash
   ./watcher/start-watcher.sh start
   ```

## Features

### Memory System

**Session Continuity**
- Automatically loads context from your last session
- Shows recent decisions and learned patterns
- Provides "what we were working on" context

**Semantic Triggers**
- Mention "docker" → retrieves docker-related decisions
- Mention "auth" → fetches authentication patterns
- Topics: docker, database, auth, performance, api, testing, deployment

**Pattern Detection**
- Detects conversation mode (debugging, performance, feature, etc.)
- Injects relevant guidance based on detected mode
- Learns from your phrasing patterns

### Learning Systems

**Correction Tracking** (`learning/correction_tracker.py`)
- Detects "no, I meant...", "that's wrong", "actually..."
- Records corrections with context
- Surfaces relevant past mistakes when similar context arises

**Outcome Tracking** (`learning/outcome_tracker.py`)
- Records success/failure of approaches
- Associates outcomes with domains and approaches
- Tracks what works and what doesn't

**Git Awareness** (`learning/git_awareness.py`)
- Shows commits made since last Claude session
- Highlights files changed by you (vs. by Claude)
- Alerts to uncommitted changes

**Preference Learner** (`learning/preference_learner.py`)
- Infers preferences from your edits to Claude's code
- Detects: const vs let, arrow vs function, quotes, semicolons
- Builds confidence as patterns repeat

**Confidence Calibration** (`learning/confidence_calibration.py`)
- Tracks accuracy by domain (docker, react, python, etc.)
- Suggests when to caveat responses
- Identifies weak areas needing more caution

### Health & Maintenance

**Health Check** (`memory/health_check.py`)
- Runs at session start (first message only)
- Auto-fixes common issues (missing directories, Ollama not running)
- Reports issues that need manual intervention

**Transcript Compaction** (`memory/transcript_compactor.py`)
- Compresses old session transcripts by 99%
- Preserves: synthesis, files changed, commands, key responses
- Runs weekly automatically

### Hybrid Search System

**BM25 + Semantic Search** (v2.0)
- Combines keyword matching (BM25) with semantic embeddings
- Uses Reciprocal Rank Fusion (RRF) for optimal results
- SQLite with FTS5 for fast full-text search
- HNSW indexes for O(log n) approximate nearest neighbor
- Falls back gracefully: Ollama → sentence-transformers → TF-IDF

**Data Storage**
- `memory.db` - SQLite database with indexed queries
- `embeddings_v2.json` - File embeddings for semantic search
- JSON files remain source of truth, SQLite for fast queries

### Project Indexing

- Tracks files, functions, and generates summaries
- Automatically re-indexes when files change
- Extracts database schemas from Firestore/MongoDB code
- Semantic search using embeddings
- Incremental sync keeps SQLite in sync with JSON

### MCP Integration

Tools available to Claude:
- `memory_query` - Natural language queries
- `memory_search` - Semantic search
- `memory_similar` - Find related files
- `memory_functions` - Look up function definitions
- `memory_health` - Code health status
- `memory_sessions` - Search past sessions
- `memory_wireframe` - App navigation info

### Local AI Tools (Task-Optimized)

Claude-Dash uses **task-based model routing** for optimal performance on M2 16GB:
- Code tasks → `deepseek-coder:6.7b` (best code quality)
- RAG queries → `gemma3:4b` (128K context window!)
- Quick tasks → `phi3:mini` (60-80 tok/s, ultra-fast)
- UI analysis → `qwen3-vl:8b` (vision specialist)

```bash
# Quick query (uses gemma3:4b)
mlx q my-app "where is the login screen?"

# RAG-powered Q&A (uses gemma3:4b with 128K context)
mlx rag my-app "how does authentication work?"

# Find similar files (semantic search)
mlx similar my-app src/components/Button.js

# Code review (uses deepseek-coder:6.7b)
mlx review src/NewFeature.js

# UI/screenshot analysis (uses qwen3-vl:8b)
mlx ui screenshot.png
mlx ui screenshot.png --mode accessibility

# Model management
mlx models list      # Show task routing
mlx models status    # Show model status
mlx hardware         # M2-specific recommendations
```

**See also:**
- `mlx-tools/ARCHITECTURE_OVERVIEW.md` - Complete system design
- `mlx-tools/FINAL_SETUP_M2_16GB.md` - Optimal M2 16GB configuration
- `mlx-tools/ROLE_HIERARCHY.md` - Claude as senior developer, local models as assistants

### Web Dashboard

```bash
cd ~/.claude-dash/dashboard && ./start.sh
```

Opens at `http://localhost:3847`.

## Requirements

- macOS (Apple Silicon recommended, optimized for M2 16GB)
- Node.js 18+
- Python 3.10+
- Claude Code CLI
- Ollama with task-optimized models (see installation above)

## Directory Structure

```
~/.claude-dash/
├── config.json                 # Project registry
├── global/
│   ├── preferences.json        # Cross-project preferences
│   └── infrastructure.json     # Infrastructure decisions
├── projects/
│   └── {project}/
│       ├── index.json          # File structure
│       ├── functions.json      # Function index
│       ├── summaries.json      # File summaries
│       ├── schema.json         # Database schema
│       └── decisions.json      # Project decisions
├── sessions/
│   ├── observations.json       # Patterns, gotchas, learnings
│   ├── summaries/              # Session summaries by project
│   ├── digests/                # Compacted old transcripts
│   └── transcripts/            # Recent full transcripts
├── learning/
│   ├── correction_tracker.py   # Learns from corrections
│   ├── outcome_tracker.py      # Tracks approach outcomes
│   ├── git_awareness.py        # Git change detection
│   ├── preference_learner.py   # Infers coding preferences
│   └── confidence_calibration.py # Accuracy tracking
├── memory/
│   ├── session_context.py      # Loads session continuity
│   ├── semantic_triggers.py    # Topic-based memory fetch
│   ├── summarizer.py           # Session summarization
│   ├── transcript_compactor.py # Storage optimization
│   └── health_check.py         # System health checks
├── patterns/
│   ├── patterns.json           # Mode definitions
│   └── detector.py             # Conversation mode detection
├── gateway/
│   ├── server.js               # Unified MCP server
│   ├── cache.js                # Query caching
│   └── metrics.json            # Performance tracking
├── watcher/
│   └── watcher.js              # File change monitor
├── mlx-tools/
│   ├── mlx                     # Local AI CLI
│   ├── memory_db.py            # SQLite database
│   ├── hybrid_search.py        # BM25 + semantic search
│   ├── embeddings.py           # Unified embedding provider
│   └── indexing_daemon.py      # Background auto-indexer
└── dashboard/
    └── server.js               # Web dashboard
```

## How Context Injection Works

**On first message of session:**
```
<session-continuity>    Last session summary, recent decisions
<git-changes>           Your commits since last session
<learned-preferences>   Inferred style preferences
<confidence-calibration> Weak areas to be careful about
```

**On every message:**
```
<past-corrections>      If correcting, shows similar past mistakes
<semantic-memory>       Topic-triggered relevant memory
<pattern-context>       Detected conversation mode guidance
```

## Manual Commands

```bash
# Check system health
python3 ~/.claude-dash/memory/health_check.py

# Run transcript compaction manually
python3 ~/.claude-dash/memory/transcript_compactor.py --compact-all --keep 10

# View confidence calibration
python3 ~/.claude-dash/learning/confidence_calibration.py --calibration

# Record an outcome manually
python3 ~/.claude-dash/learning/outcome_tracker.py \
  --record --domain "docker" --approach "used bridge" --actual success

# View inferred preferences
python3 ~/.claude-dash/learning/preference_learner.py --get-preferences

# Check git changes since last session
python3 ~/.claude-dash/learning/git_awareness.py /path/to/project

# Backup database
~/.claude-dash/backup.sh

# Restore database
~/.claude-dash/restore.sh
```

## Performance

- Hook execution: ~500ms first message, ~300ms subsequent
- Storage: ~150MB typical (with compaction)
- Compaction ratio: 99% (20MB transcript → 5KB digest)

## Troubleshooting

**Hooks not running**
- Check `~/.claude/settings.json` has correct paths
- Verify hooks are executable: `chmod +x ~/.claude/hooks/*.sh`

**Ollama errors**
- Run `ollama serve` to start Ollama
- Check model is installed: `ollama list`

**Health check failing**
- Run manually: `python3 ~/.claude-dash/memory/health_check.py`
- Check logs: `~/.claude-dash/logs/`

**Storage growing large**
- Run compaction: `python3 ~/.claude-dash/memory/transcript_compactor.py --compact-all`
- Clear logs: `rm ~/.claude-dash/logs/*.log`

## Uninstalling

To remove Claude-Dash:

```bash
~/.claude-dash/uninstall.sh
```

The uninstaller will optionally preserve your project data and learning history.

## License

MIT
