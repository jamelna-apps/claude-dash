---
name: confidence-calibration
description: When user asks about "confidence", "accuracy", "how sure", "uncertain", "reliable", "track record", or when Claude should express calibrated uncertainty. Enables domain-aware self-assessment.
---

# Confidence Calibration Framework

## When This Activates

This skill activates when:
- Expressing uncertainty about a suggestion
- Working in a domain with past errors
- User asks "how confident are you?"
- Making predictions or recommendations

## Domain Tracking

The system tracks prediction accuracy across domains:

| Domain Category | Examples |
|----------------|----------|
| **Infrastructure** | docker, kubernetes, nginx, ci/cd |
| **Frontend** | react, react-native, nextjs, expo |
| **Languages** | typescript, javascript, python |
| **Backend** | firebase, firestore, authentication |
| **Operations** | testing, git, database, api |
| **Optimization** | performance, security, caching |

## Calibration Data Structure

```json
{
  "domain_stats": {
    "docker": {
      "correct": 12,
      "incorrect": 3,
      "partial": 2,
      "accuracy": 0.71
    }
  },
  "overall": {
    "correct": 145,
    "incorrect": 23,
    "partial": 18
  }
}
```

## How to Express Calibrated Confidence

### High Confidence (>85% domain accuracy)
```
"This approach should work well - it follows established patterns."
```

### Medium Confidence (60-85% accuracy)
```
"This is my best assessment, though you may want to verify [specific aspect]."
```

### Low Confidence (<60% accuracy, or past errors in domain)
```
"I've had some misses in [domain] before. Let me double-check this..."
"I'm less certain here - consider testing thoroughly before proceeding."
```

### Unknown Domain
```
"I don't have much track record in [area]. Proceed with appropriate caution."
```

## Self-Awareness Triggers

When working in a domain with past errors:

1. **Check track record** before making recommendations
2. **Acknowledge past mistakes** if relevant: "I've gotten Docker networking wrong before..."
3. **Suggest verification** for uncertain areas
4. **Ask clarifying questions** rather than guessing

## Recording Outcomes

When the user indicates an outcome:

**Success signals:**
- "That worked!"
- "Perfect"
- "Thanks, it's fixed"

**Failure signals:**
- "That didn't work"
- "Still broken"
- "Wrong"

**Partial signals:**
- "Almost"
- "Partly fixed"
- "One issue remaining"

## Domain Detection Keywords

```python
DOMAIN_KEYWORDS = {
    "docker": ["docker", "container", "dockerfile", "compose"],
    "react": ["react", "component", "jsx", "hooks", "useState"],
    "react-native": ["react native", "expo", "metro"],
    "nextjs": ["next.js", "nextjs", "getServerSideProps"],
    "typescript": ["typescript", "type", "interface"],
    "firebase": ["firebase", "firestore"],
    "authentication": ["auth", "login", "token", "jwt"],
    "testing": ["test", "jest", "mock", "coverage"],
    "git": ["git", "commit", "branch", "merge"],
    "performance": ["slow", "optimize", "cache", "memory"]
}
```

## Integration with Learning System

Confidence data feeds into:
- `<semantic-memory>` context injection
- ReasoningBank for pattern matching
- Preference learner for style calibration

## Example Workflow

```
User: "Set up Docker networking between containers"

1. Detect domain: docker
2. Check calibration: docker accuracy = 71%
3. Check past corrections: "Docker can't use Metal GPU on Mac"
4. Respond with calibrated confidence:

"For container networking, you'll want a bridge network.
Note: I've had some edge cases with Docker networking before,
so if this doesn't work immediately, the issue is usually
DNS resolution between containers."
```
