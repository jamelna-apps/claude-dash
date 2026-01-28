---
name: rag-enhancement
description: When user asks "explain", "how does", "understand", "background on", "context for", or needs deep explanations with retrieved history. Auto-enhances answers with decision history and patterns.
---

# RAG Enhancement Framework

## When This Activates

This skill activates for explanation/understanding requests:
- "How does X work?"
- "Explain the Y system"
- "Give me background on Z"
- "What's the context for this?"
- Understanding complex codebases

## Hybrid Search (BM25 + Semantic)

The system uses Reciprocal Rank Fusion (RRF) to combine:

### BM25 (Keyword)
- Catches exact matches (function names, acronyms)
- Fast, works without embeddings
- Good for specific terms

### Semantic (Embeddings)
- Catches conceptually similar content
- Works for paraphrased queries
- Understands intent

**RRF Formula:**
```
RRF(d) = Σ(1 / (k + rank(d)))
```
Where k=60 works well empirically.

## Context Building

For explanations, the system retrieves:

### 1. Relevant Files
Based on query similarity:
```
memory_query "how does authentication work"
→ Returns top files with summaries
```

### 2. Database Schema (if data-related)
Keywords: database, collection, store, save, user, data, schema
```
Collections and their fields
```

### 3. Function Definitions (if code-related)
Keywords: function, method, how does, implement, call
```
Function name, file, line number
```

### 4. Architectural Decisions (if why-related)
Keywords: decision, why, chose, architecture, pattern
```
Past decisions with context
```

### 5. Past Observations (if problem-related)
Keywords: bug, fix, issue, pattern, learned, gotcha
```
Category, description, resolution
```

### 6. Project Conventions (if style-related)
Keywords: convention, rule, preference, style, standard
```
Name and rule description
```

## Recency Weighting

Recently modified files get boosted:
- Files modified today: +20% score boost
- Linear decay over 30 days to +0%

This helps surface actively developed code.

## RAG Workflow

1. **Receive question** about the codebase
2. **Hybrid search** for relevant files
3. **Keyword detect** for additional context types
4. **Build context** with all relevant information
5. **Generate answer** using retrieved context only
6. **Reference file paths** in the response

## MCP Tools for RAG

```
# Hybrid search
memory_query "how does X work"

# Semantic search
memory_search query="authentication flow"

# Function lookup
memory_functions name="handleLogin"

# Similar files
memory_similar file="src/auth/login.ts"

# Session observations
memory_sessions category=decision query="auth"
```

## Explanation Format

When explaining code:

```markdown
## How [X] Works

### Overview
Brief description of the system/feature.

### Key Files
- `path/to/file.ts:123` - Main implementation
- `path/to/other.ts:45` - Helper functions

### Data Flow
1. User triggers [action]
2. [Component] handles request
3. [Service] processes data
4. Result returned to [destination]

### Relevant Decisions
- Decision 1 (why this approach)
- Decision 2 (trade-offs made)

### Gotchas
- Known issue or quirk to watch for
```

## Local RAG (Free)

For simple explanations, route to local:
```
local_ask question="where is login handled?" mode=rag
```

Uses Ollama with project context, $0 cost.
