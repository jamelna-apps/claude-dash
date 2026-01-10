# Claude-Dash

Persistent memory and local AI tools for Claude Code.

## What It Does

Claude-Dash gives Claude Code persistent memory across sessions. It indexes your projects, tracks functions and file summaries, and provides local AI tools that answer questions about your codebase without using API tokens.

When you ask Claude Code "where is the login screen?" or "how does authentication work?", Claude-Dash can answer from its indexed memory instead of scanning your entire codebase each time.

## Quick Start

1. Clone this repository:
   ```bash
   git clone https://github.com/YOUR_USERNAME/claude-dash.git ~/.claude-dash
   ```

2. Set up configuration:
   ```bash
   cd ~/.claude-dash
   cp config.example.json config.json
   cp global/preferences.example.json global/preferences.json
   ```

3. Edit `config.json` and add your projects (see Configuration section below).

4. Install the file watcher:
   ```bash
   cd watcher && npm install
   ```

5. Add the MCP server to your Claude Code settings (see MCP Setup section below).

6. Start the watcher:
   ```bash
   ./watcher/start-watcher.sh start
   ```

## Features

**Project Indexing**
- Tracks files, functions, and generates summaries for each file
- Automatically re-indexes when files change
- Extracts database schemas from Firestore/MongoDB code

**MCP Integration**
- Memory tools available as native Claude tools
- Claude can query memory directly without scanning files
- Works with Claude Code's existing workflow

**Semantic Search**
- Find files by meaning, not just keywords
- Uses embeddings for conceptual matching
- "Find files related to user authentication" works even without the word "auth" in filenames

**Local AI Tools (Apple Silicon)**
- MLX-powered queries run locally at zero API cost
- Ask questions about your codebase from the command line
- Generate commit messages, PR descriptions, and code reviews locally

**Code Health Analysis**
- Detects dead code, duplicates, and complexity issues
- Tracks health metrics over time
- Provides actionable suggestions

**Session Memory**
- Logs decisions and patterns from conversations
- Search past sessions: "what did we decide about X?"
- Preserves institutional knowledge

**Web Dashboard**
- Visual interface for browsing memory
- Project health overview
- Session and observation browser

## Requirements

- macOS (Apple Silicon recommended for MLX tools)
- Node.js 18+
- Python 3.10+
- Claude Code CLI
- Ollama (optional, for local AI queries)

## Configuration

Edit `config.json` to register your projects:

```json
{
  "version": "1.0",
  "projectsRoot": "/path/to/your/projects",
  "watcher": {
    "enabled": true,
    "ignorePatterns": ["node_modules", ".git", "dist", "build"],
    "scanIntervalMs": 5000
  },
  "projects": [
    {
      "id": "my-app",
      "displayName": "My Application",
      "path": "/path/to/your/projects/my-app",
      "memoryPath": "projects/my-app"
    }
  ]
}
```

Each project needs:
- `id`: Short identifier used in commands (e.g., `mlx q my-app "query"`)
- `displayName`: Human-readable name shown in dashboard
- `path`: Absolute path to the project root
- `memoryPath`: Where to store memory files (relative to `~/.claude-dash/`)

## MCP Setup

Add Claude-Dash to your Claude Code MCP configuration.

**Location:** `~/.claude/settings.json` or project-level `.claude/settings.json`

```json
{
  "mcpServers": {
    "claude-dash": {
      "command": "node",
      "args": ["/Users/YOUR_USERNAME/.claude-dash/mcp-server/server.js"]
    }
  }
}
```

After adding, restart Claude Code. You should see new tools available:
- `memory_query` - Natural language queries
- `memory_search` - Semantic search
- `memory_similar` - Find related files
- `memory_functions` - Look up function definitions
- `memory_health` - Code health status
- `memory_sessions` - Search past sessions
- `memory_wireframe` - App navigation info

## File Watcher

The watcher monitors your projects for changes and updates the index.

```bash
# Start the watcher
./watcher/start-watcher.sh start

# Check status
./watcher/start-watcher.sh status

# View logs
./watcher/start-watcher.sh logs

# Stop
./watcher/start-watcher.sh stop
```

The watcher runs in the background and logs to `watcher/watcher.log`.

## Local AI Tools (MLX)

If you have Apple Silicon and want local AI features:

1. Set up the Python environment:
   ```bash
   python3 -m venv ~/.claude-dash/mlx-env
   source ~/.claude-dash/mlx-env/bin/activate
   pip install mlx-lm sentence-transformers
   ```

2. Install Ollama (optional, for better quality):
   ```bash
   brew install ollama
   ollama pull qwen2.5:7b
   ```

3. Add MLX to your PATH:
   ```bash
   echo 'export PATH="$HOME/.claude-dash/mlx-tools:$PATH"' >> ~/.zshrc
   source ~/.zshrc
   ```

4. Use MLX commands:
   ```bash
   # Quick query
   mlx q my-app "where is the login screen?"

   # RAG-powered Q&A (requires Ollama)
   mlx rag my-app "how does authentication work?"

   # Find similar files
   mlx similar my-app src/components/Button.js

   # Code health check
   mlx health my-app

   # Generate commit message
   mlx commit

   # Full command list
   mlx help
   ```

## Dashboard

The web dashboard provides a visual interface for browsing memory.

```bash
cd ~/.claude-dash/dashboard
npm install
./start.sh
```

Opens at `http://localhost:3847`.

## Directory Structure

```
~/.claude-dash/
├── config.json              # Project registry
├── global/
│   └── preferences.json     # Cross-project preferences
├── projects/
│   └── {project}/
│       ├── index.json       # File structure
│       ├── functions.json   # Function index
│       ├── summaries.json   # File summaries
│       ├── schema.json      # Database schema
│       ├── graph.json       # Navigation graph
│       └── health.json      # Code health metrics
├── sessions/
│   └── observations.json    # Decisions, patterns, learnings
├── mcp-server/
│   └── server.js            # MCP protocol server
├── watcher/
│   └── watcher.js           # File change monitor
├── mlx-tools/
│   └── mlx                  # Local AI tools
└── dashboard/
    └── server.js            # Web dashboard
```

## How It Works

1. **Watcher** monitors your projects for file changes
2. When files change, **extractors** parse them for functions, imports, and structure
3. Summaries and embeddings are generated (locally or via API)
4. Data is stored in JSON files under `projects/{id}/`
5. **MCP server** exposes this data to Claude Code as tools
6. Claude can query memory instead of scanning files

## Troubleshooting

**MCP tools not appearing in Claude Code**
- Check that the path in `settings.json` is correct
- Restart Claude Code after changing settings
- Run `node ~/.claude-dash/mcp-server/server.js` manually to check for errors

**Watcher not detecting changes**
- Check `./watcher/start-watcher.sh status`
- Review logs in `watcher/watcher.log`
- Verify project paths in `config.json` are correct

**MLX commands not found**
- Ensure `~/.claude-dash/mlx-tools` is in your PATH
- Check that the Python venv is activated

**Empty search results**
- Run `mlx build-embeddings {project}` to build the search index
- Check that the watcher has indexed the project

## License

MIT
