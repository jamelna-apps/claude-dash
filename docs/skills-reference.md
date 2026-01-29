# Claude-Dash Skills Reference

> Auto-generated on 2026-01-29 (updated)
> Source: `~/.claude-dash/skills/registry.json`

## Summary

**Global Skills:** 26
**Project-Specific Skills:** 0
**Total:** 26

### By Category

| Category | Count |
|----------|-------|
| core | 22 |
| marketing | 4 |

---

## Core Skills

### api-design

**Description:** API design patterns

**Triggers:** `API, endpoint, REST, GraphQL, API route, request, response`

**Path:** `~/.claude-dash/skills/core/api-design/SKILL.md`

---

### app-store-submission

**Description:** App Store Connect submission and privacy declarations

**Triggers:** `app store, app store connect, privacy declaration, data tracking, app submission, iOS submission, app review, privacy labels`

**Path:** `~/.claude-dash/skills/core/app-store-submission/SKILL.md`

---

### claude-dash-admin

**Description:** Self-maintenance and system administration guidance

**Triggers:** `system health, system cleanup, optimize claude-dash, memory system, indexes, watcher`

**Path:** `~/.claude-dash/skills/core/claude-dash-admin/SKILL.md`

---

### code-health-remediation

**Description:** Act on health scan results - safe code cleanup guidance

**Triggers:** `dead code, duplicates, code cleanup, tech debt, health scan, remediation, unused`

**Path:** `~/.claude-dash/skills/core/code-health-remediation/SKILL.md`

---

### code-review

**Description:** Code review guidelines

**Triggers:** `review, PR, pull request, code review, check my code, feedback`

**Path:** `~/.claude-dash/skills/core/code-review/SKILL.md`

---

### confidence-calibration

**Description:** Domain-aware self-assessment and calibrated uncertainty

**Triggers:** `confidence, accuracy, how sure, uncertain, reliable, track record, calibration`

**Path:** `~/.claude-dash/skills/core/confidence-calibration/SKILL.md`

---

### correction-learning

**Description:** Real-time learning from user corrections

**Triggers:** `no I meant, that's wrong, actually, I prefer, always use, don't suggest, not X but Y, use X instead`

**Path:** `~/.claude-dash/skills/core/correction-learning/SKILL.md`

---

### cost-tracking

**Description:** API cost awareness and optimization guidance

**Triggers:** `spending, usage, tokens, API cost, budget, expensive, cost`

**Path:** `~/.claude-dash/skills/core/cost-tracking/SKILL.md`

---

### debug-strategy

**Description:** Systematic debugging approaches

**Triggers:** `bug, error, not working, broken, crash, fails, issue, problem`

**Path:** `~/.claude-dash/skills/core/debug-strategy/SKILL.md`

---

### error-diagnosis

**Description:** Structured error categorization and prevention strategies

**Triggers:** `exception, stack trace, crashed, categorize error, root cause, failed`

**Path:** `~/.claude-dash/skills/core/error-diagnosis/SKILL.md`

---

### git-workflow

**Description:** Session continuity via git awareness and commit guidance

**Triggers:** `commit, branch, merge, git history, what changed, since last session, git context`

**Path:** `~/.claude-dash/skills/core/git-workflow/SKILL.md`

---

### index-freshness

**Description:** Index maintenance and freshness detection

**Triggers:** `stale, outdated, reindex, sync, refresh index, embeddings outdated`

**Path:** `~/.claude-dash/skills/core/index-freshness/SKILL.md`

---

### knowledge-consolidation

**Description:** RETRIEVE→JUDGE→DISTILL→CONSOLIDATE learning cycle

**Triggers:** `remember this, pattern, decision, gotcha, bug fix, next time, learned, consolidate`

**Path:** `~/.claude-dash/skills/core/knowledge-consolidation/SKILL.md`

---

### mode-awareness

**Description:** Mode-specific approach guidance for detected work patterns

**Triggers:** `switch mode, debugging mode, exploration mode, feature mode, refactor mode, infrastructure mode`

**Path:** `~/.claude-dash/skills/core/mode-awareness/SKILL.md`

---

### performance-audit

**Description:** Performance analysis framework

**Triggers:** `slow, performance, optimize, speed, lag, loading, memory, CPU`

**Path:** `~/.claude-dash/skills/core/performance-audit/SKILL.md`

---

### portfolio-intelligence

**Description:** Cross-project strategic guidance and PR generation

**Triggers:** `portfolio, across projects, compare projects, project health, PR description, cross-project`

**Path:** `~/.claude-dash/skills/core/portfolio-intelligence/SKILL.md`

---

### rag-enhancement

**Description:** Auto-enhance explanations with retrieved decision history

**Triggers:** `explain, how does, understand, background on, context for, why does`

**Path:** `~/.claude-dash/skills/core/rag-enhancement/SKILL.md`

---

### refactor-guide

**Description:** Safe refactoring practices

**Triggers:** `refactor, clean up, technical debt, restructure, reorganize`

**Path:** `~/.claude-dash/skills/core/refactor-guide/SKILL.md`

---

### self-healing *(NEW)*

**Description:** Auto-detect and fix broken dependencies when resources are removed

**Triggers:** `remove model, deprecate, cleanup, broken dependency, self-heal, impact analysis`

**Path:** `~/.claude-dash/skills/core/self-healing/SKILL.md`

---

### session-handoff

**Description:** Session continuity and structured context handoff

**Triggers:** `continue, pick up, last time, previous session, what were we doing, left off`

**Path:** `~/.claude-dash/skills/core/session-handoff/SKILL.md`

---

### smart-routing

**Description:** Local vs Claude routing decisions for cost optimization

**Triggers:** `model routing, which model, complex task, multi-file, architectural, deep debugging, local vs claude, cost savings`

**Path:** `~/.claude-dash/skills/core/smart-routing/SKILL.md`

---

### testing-strategy

**Description:** Testing approaches

**Triggers:** `test, testing, unit test, integration, e2e, coverage, TDD, mock`

**Path:** `~/.claude-dash/skills/core/testing-strategy/SKILL.md`

---

## Marketing Skills

### free-tool-strategy

**Description:** Engineering-as-marketing tools

**Triggers:** `free tool, engineering as marketing, lead magnet, calculator, generator`

**Path:** `~/.claude-dash/skills/marketing/free-tool-strategy/SKILL.md`

---

### launch-strategy

**Description:** Product launch planning

**Triggers:** `launch, release, announcement, go-to-market, GTM`

**Path:** `~/.claude-dash/skills/marketing/launch-strategy/SKILL.md`

---

### page-cro

**Description:** Page conversion optimization

**Triggers:** `conversion, CRO, landing page, not converting, bounce rate, optimize page`

**Path:** `~/.claude-dash/skills/marketing/page-cro/SKILL.md`

---

### pricing-strategy

**Description:** Pricing and monetization strategies

**Triggers:** `pricing, price, monetization, subscription, tiers, freemium`

**Path:** `~/.claude-dash/skills/marketing/pricing-strategy/SKILL.md`

---

## Usage Notes

### Auto-Injection

Skills are automatically injected when prompt keywords match triggers:
- Top 2 skills (by match count) are injected per prompt
- Content appears in `<activated-skill>` tags
- Both global and project-specific skills are checked

### Manual Invocation

Skills can also be invoked explicitly via `/skill <skill-name>` commands.