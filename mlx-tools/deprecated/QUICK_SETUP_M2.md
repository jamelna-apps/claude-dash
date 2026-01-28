# Quick Setup Guide for M2 16GB

## Your Current Setup ✅

```
qwen2.5:7b (4.7GB)              → Default for all tasks
nomic-embed-text (274MB)         → Embeddings
claude-dash-assistant (4.7GB)    → Installed but not in use
```

## Option 1: Minimal Setup (Recommended to Start)

**Keep what you have, use qwen2.5:7b for everything**

✅ Pros:
- Already working
- One model to manage
- Fast switching (no model loading delays)
- Good quality for most tasks

❌ Cons:
- No visual analysis capability (can't analyze screenshots)
- Not specialized for code

**Do this:**
```bash
# Nothing! You're already set up.
# Test it out:
mlx models status
mlx ask gyst "how does authentication work?"
mlx review path/to/file.js
```

## Option 2: Add Visual Analysis (When You Need It)

**Add llava:7b for UI/screenshot analysis**

```bash
# Install llava
ollama pull llava:7b  # ~4.7GB download

# Configure it
export OLLAMA_VLM_MODEL="llava:7b"
# Add to ~/.zshrc to make permanent

# Test it
mlx models test ui_analysis
```

**Models after this:**
```
qwen2.5:7b → All text tasks
llava:7b → UI analysis, screenshots
nomic-embed-text → Embeddings
```

**RAM impact**: Still only ~5GB at a time (Ollama swaps models automatically)

## Option 3: Specialized Code Model (Optional)

**If you want better code review, add deepseek-coder:6.7b**

```bash
# Install
ollama pull deepseek-coder:6.7b  # ~4GB

# Update config
# Edit ~/.claude-dash/mlx-tools/config.py
# Change: 'code_review': 'deepseek-coder:6.7b'

# Test
mlx models test code_review
```

## What About claude-dash-assistant?

You have it installed but it's not configured in the routing system. You can:

**Option A**: Use it for specific tasks
```bash
# Edit config.py to use it
TASK_MODEL_MAP = {
    'ask': 'claude-dash-assistant:latest',
    'rag': 'claude-dash-assistant:latest',
    # ... rest use qwen2.5:7b
}
```

**Option B**: Remove it to free disk space
```bash
ollama rm claude-dash-assistant
```

**Option C**: Keep it for manual testing
```bash
# Use it directly when needed
OLLAMA_MODEL="claude-dash-assistant" mlx ask gyst "question"
```

## My Recommendation

**Phase 1 (Now)**: Use qwen2.5:7b for everything
- Test all the tools (ask, review, rag, commit)
- See if quality is good enough
- Decide if claude-dash-assistant is worth keeping

**Phase 2 (When you need UI analysis)**: Add llava:7b
```bash
ollama pull llava:7b
export OLLAMA_VLM_MODEL="llava:7b"
```

**Phase 3 (Only if needed)**: Specialize further
- Better code review? → deepseek-coder:6.7b
- Faster simple tasks? → qwen2.5:3b or llama3.2:3b

## Quick Comparison for Your Hardware

| Model | Size | Speed on M2 | Best For | Should You Install? |
|-------|------|-------------|----------|-------------------|
| qwen2.5:7b | 4.7GB | ⚡⚡⚡ Fast | General tasks | ✅ Already have |
| llava:7b | 4.7GB | ⚡⚡ Good | UI analysis | 👍 Yes, when needed |
| deepseek-coder:6.7b | 4GB | ⚡⚡⚡ Fast | Code review | 🤔 Maybe, if quality lacking |
| qwen2.5:3b | 2GB | ⚡⚡⚡⚡ Very fast | Simple tasks | 🤷 Optional |
| llava:13b | 8GB | ⚡ Slow | Better vision | ❌ Too tight for 16GB |
| deepseek-coder:33b | 20GB | 🐌 Won't work | - | ❌ Too large |

## Performance Check

Test your current setup:

```bash
# Check routing
mlx models status
mlx models list

# Test speed
time mlx ask gyst "what screens are in this app?"

# Test quality
mlx review src/some-file.js
mlx rag gyst "how does user authentication work?"
```

If it feels good → stick with qwen2.5:7b!
If you need UI analysis → add llava:7b
If code review quality is lacking → try deepseek-coder:6.7b

## Disk Space Note

Your models:
- qwen2.5:7b: 4.7GB
- claude-dash-assistant: 4.7GB
- nomic-embed-text: 274MB
- **Total: ~9.7GB**

If you add llava:7b: ~14.4GB total
If you remove claude-dash-assistant: ~5GB total

Choose based on your available disk space.
