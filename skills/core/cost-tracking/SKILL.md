---
name: cost-tracking
description: When user mentions "spending", "usage", "tokens", "API cost", "budget", "expensive", or wants to understand Claude API costs. Provides cost awareness and optimization guidance.
---

# Cost Tracking Framework

## When This Activates

This skill activates when:
- User asks about API costs or spending
- Concerns about expensive operations
- Need to optimize token usage

## Token Cost Reference

### Claude Pricing (Approximate)
| Model | Input (per 1M tokens) | Output (per 1M tokens) |
|-------|----------------------|------------------------|
| Opus | ~$15 | ~$75 |
| Sonnet | ~$3 | ~$15 |
| Haiku | ~$0.25 | ~$1.25 |

### Typical Operation Costs

| Operation | Tokens | Approximate Cost |
|-----------|--------|------------------|
| Simple question | 500-2K | $0.01-0.05 |
| File read + analysis | 2-10K | $0.05-0.25 |
| Code generation | 5-20K | $0.15-0.50 |
| Multi-file refactor | 20-100K | $0.50-2.50 |
| Long conversation | 50-200K | $1.00-5.00 |

## Cost Optimization Strategies

### 1. Route to Local LLM (FREE)
Use `local_ask` for simple tasks:
```
# FREE - no API cost
local_ask question="where is the login function?"
local_ask question="explain this error" mode=explain
local_review file="src/auth.ts" focus=bugs
```

**Good for local:**
- Simple lookups ("where is X?")
- Code explanations
- Commit message generation
- Quick code reviews

### 2. Use Memory Tools First
Pre-indexed memory is instant and free:
```
# Instant, no API cost
memory_query "authentication flow"
memory_functions name="handleLogin"
smart_read path="src/auth.ts" detail=summary
```

### 3. Reduce Context Size
- Use `smart_read` with `detail=summary` before `detail=full`
- Truncate large files to relevant sections
- Clear conversation when changing topics

### 4. Batch Related Questions
Instead of 5 separate messages, combine:
```
"Can you: 1) explain the auth flow, 2) find the login
component, 3) check for security issues, and 4) suggest
improvements?"
```

## Gateway Metrics

Check current efficiency:
```
gateway_metrics format=summary
```

Returns:
- Cache hit rate
- Token savings
- Routing breakdown (local vs API)

## Cost Estimation

Before expensive operations:
```
This refactor will touch ~20 files.
Estimated cost: $0.50-1.00
Proceed? [Y/n]
```

## Budget Awareness

### Daily Patterns
- Morning: Fresh context, lower cost
- Long sessions: Context grows, higher cost
- After compaction: Reset context, lower cost

### High-Cost Triggers
- "Analyze entire codebase"
- "Review all files in directory"
- "Generate comprehensive documentation"
- Very long conversations (>50 turns)

## Saving Tips

1. **Start fresh for new topics** - Don't carry irrelevant context
2. **Use subagents** - They have focused context
3. **Check memory first** - Summaries save full file reads
4. **Compress transcripts** - Archived sessions are compressed
5. **Local for simple tasks** - Ollama is free

## Monitoring Commands

```bash
# Check gateway efficiency
python3 ~/.claude-dash/learning/efficiency_tracker.py --report

# View session sizes
du -sh ~/.claude-dash/sessions/*
```
