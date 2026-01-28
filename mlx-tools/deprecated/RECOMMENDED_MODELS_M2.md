# Recommended Models for Mac Mini M2 (16GB)

Based on your hardware, here are realistic model recommendations that will run smoothly.

## Hardware Constraints

- **RAM**: 16GB total
- **Available for models**: ~12-14GB (after OS overhead)
- **Model size guideline**: Stay under 8-10GB per model for good performance

## Model Size Reference

```
3B models  → ~2GB RAM   (Fast, great for quick tasks)
7B models  → ~4-5GB RAM (Good balance, handles most tasks well)
13B models → ~8-9GB RAM (Slower, only if you need quality boost)
33B+ models → Won't fit comfortably
```

## Recommended Setup

### Current: qwen2.5:7b (4.7GB)
✅ **Keep this** - Good all-rounder, runs well on M2

### For Code Tasks
```bash
# OPTION 1: Keep qwen2.5:7b for everything (simplest)
# Already installed, works well

# OPTION 2: Add a specialized code model (if you want better code review)
ollama pull deepseek-coder:6.7b  # ~4GB, good for code
ollama pull codegemma:7b         # ~5GB, Google's code model
```

**Recommendation**: Stick with qwen2.5:7b unless you find code review quality lacking.

### For Visual Tasks (UI Analysis)
```bash
# RECOMMENDED: LLaVA 7B
ollama pull llava:7b             # ~4.7GB - BEST for your hardware

# Alternative (lighter)
ollama pull llava:latest         # Usually points to 7B version

# DON'T USE (too big for comfortable use)
# llava:13b → ~8GB, will slow down your system
# llava:34b → Won't fit
```

**Recommendation**: `llava:7b` - Perfect for M2 16GB, handles screenshots/UI well.

### For Fast/Simple Tasks
```bash
# If you want a lighter model for quick tasks
ollama pull qwen2.5:3b           # ~2GB, faster responses
ollama pull llama3.2:3b          # ~2GB, good for simple queries
```

**Recommendation**: Optional - only if qwen2.5:7b feels slow for simple tasks.

## Realistic Task Routing Configuration

Here's what will work well on your M2:

```python
# Edit ~/.claude-dash/mlx-tools/config.py

TASK_MODEL_MAP = {
    # All code tasks - use qwen2.5:7b (already installed)
    'code_review': 'qwen2.5:7b',
    'code_analysis': 'qwen2.5:7b',
    'code_explanation': 'qwen2.5:7b',

    # Documentation - use qwen2.5:7b
    'commit_message': 'qwen2.5:7b',
    'pr_description': 'qwen2.5:7b',
    'summarization': 'qwen2.5:7b',

    # Reasoning - use qwen2.5:7b
    'rag': 'qwen2.5:7b',
    'ask': 'qwen2.5:7b',
    'query': 'qwen2.5:7b',

    # Visual tasks - use llava:7b (when you install it)
    'ui_analysis': 'llava:7b',
    'screenshot_review': 'llava:7b',
    'design_assessment': 'llava:7b',
}
```

## What NOT to Install

❌ **Avoid these** - too large for comfortable use:
- `deepseek-coder:33b` (~20GB)
- `llama3:70b` (~40GB)
- `mixtral:8x7b` (~26GB)
- `llava:13b` (possible but tight, will slow things down)
- `llava:34b` (won't fit)

## Optimal Setup for Your Use Case

### Minimal (Current)
```bash
# What you have now
qwen2.5:7b (4.7GB)          → All text tasks
nomic-embed-text (274MB)    → Embeddings
claude-dash-assistant (4.7GB) → Unused, can remove
```

**RAM usage**: ~5GB for one model at a time ✅

### Recommended Addition: Visual Analysis
```bash
# Add when ready for UI analysis
ollama pull llava:7b

# Total models
qwen2.5:7b (4.7GB)          → All text tasks
llava:7b (4.7GB)            → UI/screenshot analysis
nomic-embed-text (274MB)    → Embeddings
```

**RAM usage**: ~5GB for one model at a time ✅ (Ollama unloads inactive models)

### If You Want Code Specialization
```bash
# Optional: Better code review
ollama pull deepseek-coder:6.7b

# Task routing
code_review → deepseek-coder:6.7b (better code understanding)
everything else → qwen2.5:7b
visual → llava:7b
```

**RAM usage**: ~5GB for one model at a time ✅

## Performance Expectations

### qwen2.5:7b on M2
- **Speed**: ~30-50 tokens/sec
- **Quality**: Good for most tasks
- **RAM**: 4-5GB
- **Verdict**: ✅ Perfect fit

### llava:7b on M2
- **Speed**: ~20-30 tokens/sec with images
- **Quality**: Good for UI analysis, screenshots
- **RAM**: 4-5GB
- **Verdict**: ✅ Will work well

### deepseek-coder:6.7b on M2
- **Speed**: ~30-40 tokens/sec
- **Quality**: Better code understanding than qwen
- **RAM**: ~4GB
- **Verdict**: ✅ Good if you need better code review

## My Recommendation for You

**Start simple, add as needed:**

1. **Now**: Keep using `qwen2.5:7b` for everything
   - Test it on real tasks
   - See if quality is good enough

2. **When ready for UI analysis**: Add `llava:7b`
   ```bash
   ollama pull llava:7b
   export OLLAMA_VLM_MODEL="llava:7b"
   ```

3. **If code review quality isn't enough**: Add `deepseek-coder:6.7b`
   ```bash
   ollama pull deepseek-coder:6.7b
   # Edit config.py to use it for code_review task
   ```

## Cleanup Suggestion

You have `claude-dash-assistant:latest` (4.7GB) that's not being used. Consider removing it:

```bash
ollama rm claude-dash-assistant
```

This frees up disk space (not RAM, since Ollama only loads active models).

## Testing Performance

```bash
# Test current model speed
time mlx ask gyst "what is this app about?"

# After adding llava:7b, test visual tasks
mlx models test ui_analysis

# Check RAM usage while model is loaded
# Models auto-unload after ~5 min of inactivity
```

## Bottom Line

**Your M2 16GB can comfortably run:**
- ✅ One 7B model at a time (perfect)
- ✅ Multiple 7B models installed (Ollama swaps as needed)
- ⚠️  One 13B model (possible but slower)
- ❌ 33B+ models (don't bother)

**Recommended strategy**: Stick with 7B models. They're the sweet spot for M2 16GB.
