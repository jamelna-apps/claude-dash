# MLX Tools for Claude Memory System

Local AI tools using Apple MLX - zero API token cost.

## Setup

```bash
# Create and activate virtual environment (already done)
cd ~/.claude-dash
python3 -m venv mlx-env
source mlx-env/bin/activate
pip install mlx-lm

# Add mlx command to PATH (optional)
echo 'export PATH="$HOME/.claude-memory/mlx-tools:$PATH"' >> ~/.zshrc
```

## Available Tools

### 1. Summarizer (`mlx summarize`)
Re-summarize files locally when they change. Zero API tokens.

```bash
mlx summarize gyst --limit 5    # Summarize 5 pending files
mlx summarize gyst --all        # Re-summarize all files
```

### 2. Semantic Search (`mlx search`, `mlx similar`)
Find files by meaning, not just keywords.

```bash
# Build embeddings first (one-time)
mlx build-embeddings gyst

# Search for files
mlx search gyst "user authentication login"
mlx search gyst "firestore data persistence"

# Find similar files
mlx similar gyst src/features/auth/screens/LoginScreen.js
```

### 3. Intent Classifier (`mlx classify`)
Classify user queries to find the right memory files.

```bash
mlx classify "where is the login screen?"
# -> Intent: find_file, Read: summaries.json, functions.json

mlx classify "what collections store user data?"
# -> Intent: understand_schema, Read: schema.json

mlx classify "how does navigation work?"
# -> Intent: understand_navigation, Read: graph.json
```

### 4. Pending Processor (`mlx pending`, `mlx process`)
Check and process files marked for re-summarization.

```bash
mlx pending              # Show status
mlx process gyst         # Process one project
mlx process --all        # Process all projects
```

## Integration with Watcher

The file watcher (`~/.claude-dash/watcher/watcher.js`) marks changed files with
`needsResummarization: true`. Run `mlx process --all` periodically to update summaries.

### Automatic Processing (cron)

```bash
# Add to crontab (runs every hour)
0 * * * * cd ~/.claude-dash && source mlx-env/bin/activate && python mlx-tools/process_pending.py --all-projects --limit 20
```

## Models

Default: `mlx-community/Llama-3.2-3B-Instruct-4bit`

Available models in `~/.cache/huggingface/hub/`:
- mlx-community/Llama-3.2-3B-Instruct-4bit
- mlx-community/Mistral-7B-Instruct-v0.3-4bit

Use `--model` to specify a different model:
```bash
mlx summarize gyst --model mlx-community/Mistral-7B-Instruct-v0.3-4bit
```

## Token Savings

| Task | With Claude API | With MLX Local |
|------|-----------------|----------------|
| Summarize 100 files | ~500K tokens | 0 tokens |
| Re-summarize on change | ~5K tokens/file | 0 tokens |
| Semantic search | N/A | 0 tokens |
| Intent classification | ~1K tokens | 0 tokens |

**Estimated monthly savings**: 1-5M tokens for active development.
