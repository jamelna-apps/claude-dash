---
name: correction-learning
description: When user corrects Claude with "no I meant", "that's wrong", "actually", "I prefer", "always use", "don't suggest", "not X but Y", or similar correction phrases. Enables real-time learning from feedback.
---

# Correction Learning Framework

## When This Activates

This skill activates when you detect the user is correcting your output:
- Explicit disagreement
- Preference expressions
- Style corrections
- Terminology corrections

## Correction Detection Patterns

**Explicit Corrections:**
- "no, I meant..."
- "that's wrong/incorrect/not right"
- "actually, I want/need/meant..."
- "I said X not Y"
- "no, not X"

**Imperative Corrections:**
- "no, use X"
- "use X not Y"
- "use X instead"
- "should be X not Y"
- "it's X not Y"

**Action Corrections:**
- "don't do/use/add/make X"
- "remove that/this"
- "undo/revert"
- "go back to"
- "change it back to"

**Preference Expressions:**
- "prefer X over Y"
- "always use X"
- "never use X"
- "stop using X"

## Response Protocol

When you detect a correction:

### 1. Acknowledge Without Defensiveness
```
"Got it - using [correct approach] instead."
```

### 2. Extract the Learning
Identify:
- **What was wrong:** Your original approach
- **What is correct:** User's preferred approach
- **Category:** naming, syntax, patterns, style, terminology

### 3. Apply Immediately
Make the change in the current response.

### 4. Record for Future
The system auto-records corrections to `~/.claude-dash/learning/corrections.json`

## Common Correction Categories

### Naming Preferences
```
User: "No, use camelCase not snake_case"
Learn: {category: "naming", prefers: "camelCase", over: "snake_case"}
```

### Syntax Preferences
```
User: "Always use arrow functions"
Learn: {category: "syntax", key: "function_style", prefers: "arrow"}
```

### Framework Patterns
```
User: "Use useQuery not fetch for API calls"
Learn: {category: "patterns", prefers: "useQuery", over: "fetch"}
```

### Style Preferences
```
User: "Single quotes, not double"
Learn: {category: "style", key: "quotes", prefers: "single"}
```

## EWC Protection (Don't Flip-Flop)

The system uses Elastic Weight Consolidation to prevent:
- A few corrections overriding established patterns
- Flip-flopping between preferences

**How it works:**
- New preference: requires 60% ratio + 3 observations
- Reinforcing existing: requires 50% ratio + 2 observations
- Changing established: requires 80% ratio + 8 observations

## Self-Awareness Phrases

When you notice patterns:
- "I notice I've been corrected on [X] before - using [Y] instead"
- "Based on your previous feedback about [X], I'm using [Y]"
- "Following your preference for [X]..."

## What Gets Recorded

```json
{
  "timestamp": "...",
  "user_message": "no, use useState not useRef",
  "correct": "useState",
  "wrong": "useRef",
  "topic": "react-hooks",
  "project_id": "gyst"
}
```

This feeds into the ReasoningBank for future context retrieval.
