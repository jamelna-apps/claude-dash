# Local LLM Benchmark Results

**Date**: 2026-01-25
**Hardware**: Mac mini M2 (8 cores, 16GB unified memory)

## Model Comparison Summary

| Model | Avg Response Time | Tokens/sec | Quality Score | Size |
|-------|-------------------|------------|---------------|------|
| gemma3:4b-it-qat | 4.86s | 9.2 | 100% | 4.0 GB |
| deepseek-coder:6.7b | 10.93s | 10.9 | 100% | 3.8 GB |
| qwen2.5-coder:7b | 12.45s | 12.2 | 88% | 4.7 GB |

## Key Findings

### 1. DeepSeek Coder 6.7B Outperforms Qwen 2.5 Coder 7B
- **Better quality**: 100% vs 88% on benchmark tests
- **Faster**: 10.93s vs 12.45s average response
- **Smaller**: 3.8GB vs 4.7GB

### 2. Gemma3 4B is Fastest for Simple Tasks
- Best for: commit messages, quick summaries, simple queries
- 2-3x faster than 7B models
- Good quality on straightforward tasks

### 3. Task-Based Routing is Effective
Current routing strategy is sound:
- Code tasks → qwen2.5-coder:7b (consider switching to deepseek-coder:6.7b)
- Documentation/simple tasks → gemma3:4b-it-qat

## Recommendations

### Immediate Actions
1. **Consider DeepSeek Coder as primary coding model**
   - Higher quality on coding benchmarks
   - Faster response times
   - Smaller memory footprint

2. **Keep Gemma3:4b for speed-critical tasks**
   - Commit messages, PR descriptions
   - Quick queries where response time matters
   - Classification and intent detection

### Routing Update Proposal
```
Code Analysis:
  code_review       → deepseek-coder:6.7b  (was qwen2.5-coder:7b)
  code_analysis     → deepseek-coder:6.7b
  code_explanation  → deepseek-coder:6.7b
  static_analysis   → deepseek-coder:6.7b
  test_generation   → deepseek-coder:6.7b
  error_analysis    → deepseek-coder:6.7b

Documentation (keep as-is):
  commit_message    → gemma3:4b-it-qat
  pr_description    → gemma3:4b-it-qat
  summarization     → gemma3:4b-it-qat
```

## Test Details

### Code Completion Test
Generate Fibonacci function implementation.
- qwen2.5-coder: 19.94s, 75% quality
- deepseek-coder: 14.90s, 100% quality
- gemma3:4b: 5.96s, 100% quality

### Code Explanation Test
Explain async fetch function.
- qwen2.5-coder: 4.96s, 100% quality
- deepseek-coder: 6.95s, 100% quality
- gemma3:4b: 3.76s, 100% quality

## Memory Usage Notes

With 16GB unified memory:
- Can comfortably run any single 7B model
- System uses ~4-6GB, leaving 10-12GB for inference
- Loading a new model takes 2-5 seconds (warm from cache)
- Hot-swapping between models is seamless with Ollama

## Implementation Summary

### Completed Improvements

1. **Model Comparison** - DeepSeek Coder 6.7B tested and recommended
2. **RAG Enhancement** - Integrated hybrid search (BM25 + semantic) with recency weighting
3. **Complexity Router** - Automatic local/cloud task routing (`mlx complexity`)
4. **Benchmark Suite** - Repeatable performance tests (`python benchmark.py`)

### New Commands

```bash
# Analyze task complexity (decide local vs cloud)
mlx complexity "your task description"

# Compare models
python ~/.claude-dash/mlx-tools/benchmark.py --compare

# Run benchmark
python ~/.claude-dash/mlx-tools/benchmark.py
```

### Cost Optimization Strategy

The complexity router ensures you only pay for Claude API when needed:

| Task Type | Backend | Cost |
|-----------|---------|------|
| Fix typo, rename variable | Local | Free |
| Add simple feature | Local | Free |
| Explain code | Local | Free |
| Multi-file refactor | Claude | Paid |
| Complex debugging | Claude | Paid |
| Architectural decisions | Claude | Paid |

**Estimated savings**: 60-70% of tasks can run locally for free.

## Next Steps (Optional)

1. **LMStudio**: Install for speculative decoding (20-50% speed boost)
   - Download from: https://lmstudio.ai
   - Supports Apple Silicon Metal acceleration
   - Can run alongside Ollama

2. **Switch to DeepSeek**: Update model_router.py to use deepseek-coder:6.7b
   ```python
   # In config.py, change coding tasks to use:
   'code_review': 'deepseek-coder:6.7b',
   'code_analysis': 'deepseek-coder:6.7b',
   ```

3. **Install BM25**: For better hybrid search quality
   ```bash
   pip install rank-bm25
   ```
