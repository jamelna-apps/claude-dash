---
name: knowledge-consolidation
description: When user says "remember this", "pattern", "decision", "gotcha", "bug fix", "next time", "learned", or wants to capture session learnings. Uses RETRIEVE→JUDGE→DISTILL→CONSOLIDATE cycle.
---

# Knowledge Consolidation Framework

## When This Activates

This skill activates when:
- User wants to remember something for future sessions
- A significant decision or pattern emerges
- A bug fix reveals a gotcha
- Session learnings should be captured

## The RETRIEVE→JUDGE→DISTILL→CONSOLIDATE Cycle

### 1. RETRIEVE
Find similar past situations from corrections/decisions:
```
memory_sessions category=decision "authentication pattern"
reasoning_query context="login flow architecture"
```

### 2. JUDGE
Assess if past solution applies to current context:
- Domain match? (same tech area)
- Context similarity > 30%?
- Confidence threshold met?

### 3. DISTILL
Extract generalizable patterns from specific instances:
- Find common trigger terms across examples
- Identify shared solution approaches
- Require 2+ examples before creating pattern

### 4. CONSOLIDATE
Update long-term memory with new patterns:
- Merge similar trajectories
- Update confidence scores
- Prune outdated patterns

## Observation Categories

When capturing learnings, categorize them:

| Category | When to Use | Example |
|----------|-------------|---------|
| `decision` | Technical choices made | "Chose native Ollama over Docker for Metal GPU" |
| `pattern` | Patterns discovered/applied | "Use host.docker.internal for Docker→host" |
| `bugfix` | Bugs found and fixed | "Fixed Firebase error by mounting key" |
| `gotcha` | Tricky/unexpected things | "Docker can't use Metal GPU on Mac" |
| `feature` | Features implemented | "Added doc_query tool to gateway" |
| `implementation` | How something was built | "Integrated AnythingLLM via REST" |

## Recording Workflow

When the user says "remember this" or similar:

### 1. Identify the Learning Type
```
"Remember: Docker containers can't use Metal GPU"
→ Category: gotcha
→ Domain: docker
```

### 2. Structure the Observation
```json
{
  "category": "gotcha",
  "observation": "Docker containers on macOS cannot use Metal GPU - must use native services",
  "context": "Trying to run Ollama in Docker for GPU acceleration",
  "files": [],
  "project_id": "claude-dash"
}
```

### 3. Check for Related Past Learnings
```
reasoning_query context="Docker GPU Metal macOS"
```

### 4. Confirm and Store
"Recorded as a gotcha. This will surface next time Docker GPU topics come up."

## Pattern Extraction

After multiple similar observations, patterns emerge:

```
Observations:
1. "Docker can't use Metal GPU"
2. "Ollama must run native for GPU"
3. "MLX requires native execution"

Distilled Pattern:
{
  "id": "docker_metal_gpu",
  "domain": "docker",
  "trigger_terms": ["docker", "metal", "gpu", "macos"],
  "solution_terms": ["native", "host", "not container"],
  "description": "When [docker, metal, gpu], try [native, host execution]",
  "confidence": 0.8
}
```

## Proactive Injection

The system auto-injects relevant memories via:
- `<semantic-memory>` tags on prompt submission
- `<past-corrections>` when similar topics arise
- Pattern matching on trigger terms

## Manual Queries

Check what's been learned:
```
memory_sessions category=decision limit=5
memory_sessions category=gotcha query="docker"
reasoning_query context="current problem description"
```

## Consolidation Triggers

Consolidation runs:
- After 10+ new trajectories
- When explicitly requested
- During background worker runs

Output: Merged patterns, updated confidence scores, pruned stale entries.
