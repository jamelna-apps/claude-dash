# Claude Memory Dashboard - Conductor Integration Design

**Date:** 2025-01-06
**Status:** Draft

## Overview

Enhance the claude-memory dashboard by integrating Conductor's AI capabilities, creating a more powerful local development assistant with web search fallback, proactive alerts, and documentation access.

## Current State

The dashboard currently has:
- **Ollama AI Chat** - Local LLM for project questions (portfolio, coding, general modes)
- **Project Health Scanning** - Code quality metrics via `code_health.py`
- **File/Function Browsing** - Navigate codebase structure
- **Graph Visualization** - Dependency and navigation graphs
- **Session Observations** - Track decisions and notes
- **Claude Code Handoff** - Send fix requests to Claude Code

## Integration Features

### 1. Hybrid Search Fallback (Ollama + Tavily)

**Problem:** Ollama answers based only on local memory files. Questions about external topics (library docs, error messages, best practices) get hallucinated or "I don't know" responses.

**Solution:** Add confidence scoring + Tavily web search fallback.

**Workflow:**
1. User asks question in chat
2. Ollama generates response
3. Dashboard evaluates response confidence:
   - Pattern match for uncertainty phrases ("I'm not sure", "I don't have", "you should check")
   - Response length analysis (very short = uncertain)
   - Question type detection (external topic = likely needs web)
4. If low confidence → offer "Search the web?" button
5. User clicks → Tavily search via Conductor API
6. Display web results alongside Ollama answer

**API Extension:**
```javascript
// POST /api/ollama/chat (extended response)
{
  response: "...",
  confidence: "high" | "medium" | "low",
  suggestWebSearch: boolean,
  originalQuestion: "..."
}

// POST /api/conductor/web-search
{
  query: "React useEffect cleanup pattern",
  context: "coding" // helps format results
}
→ { results: [{ title, url, snippet }], summary: "..." }
```

**UI Change:**
- Add "Search Web" button below uncertain responses
- Web results appear in collapsible section
- "Save to Knowledge Base" button for useful results

---

### 2. Proactive Health Alerts

**Problem:** Health issues exist but user must remember to check. No visibility into worsening trends.

**Solution:** Generate proactive insights based on health data patterns.

**Alert Types:**

| Type | Trigger | Priority |
|------|---------|----------|
| `health_degradation` | Score dropped 10+ points since last scan | high |
| `critical_issue` | Health score below 40 | urgent |
| `stale_scan` | No scan in 7+ days | medium |
| `new_complexity_issue` | New high-complexity file detected | medium |
| `dead_code_growth` | Dead code increased by 5+ files | low |

**Generation:**
- Run on dashboard startup
- Compare current health.json to health_history.json
- Store alerts in `~/.claude-memory/projects/{id}/alerts.json`
- Dismiss persists (don't regenerate same alert)

**Data Model:**
```javascript
// alerts.json
{
  alerts: [{
    id: "alert-123",
    type: "health_degradation",
    priority: "high",
    title: "GYST health dropped from 78 to 65",
    details: "Main causes: 3 new high-complexity files",
    projectId: "gyst",
    dismissedAt: null,
    createdAt: "2025-01-06T10:00:00Z"
  }]
}
```

**UI:**
- Alert banner at top of portal (across all projects)
- Per-project alert badge on project cards
- Alert detail panel with "Dismiss" and "Fix with Claude" actions

---

### 3. Documentation Knowledge Base

**Problem:** Developers frequently reference the same docs (React Native, Expo, Firebase). Re-searching wastes time.

**Solution:** Curated documentation sources stored locally, searchable via chat.

**Data Model:**
```javascript
// ~/.claude-memory/global/knowledge-base.json
{
  sources: [{
    id: "kb-123",
    title: "React Native Navigation",
    url: "https://reactnavigation.org/docs/getting-started",
    content: "...", // Fetched and cached
    fetchedAt: "2025-01-06T10:00:00Z",
    tags: ["react-native", "navigation"]
  }],
  lastUpdated: "2025-01-06T10:00:00Z"
}
```

**Workflow:**
1. User adds URL to knowledge base (Settings → Knowledge Base)
2. Dashboard fetches content via Conductor's Tavily extract
3. Content stored locally
4. Chat searches knowledge base before/alongside Ollama

**API:**
```javascript
// POST /api/knowledge-base/add
{ url: "https://docs.expo.dev/..." }
→ { id, title, content, tags }

// GET /api/knowledge-base
→ { sources: [...] }

// DELETE /api/knowledge-base/:id
```

**Chat Integration:**
- New context mode: `contextMode: 'with-knowledge-base'`
- Searches knowledge base for relevant snippets
- Includes in Ollama prompt alongside project context

---

### 4. Weekly Development Reports

**Problem:** Session observations accumulate but aren't synthesized. Hard to see patterns across sessions.

**Solution:** Generate weekly summaries from session observations.

**Report Sections:**
- **Projects Worked On** - Which projects had activity
- **Key Decisions Made** - Extracted from decisions.json
- **Patterns Identified** - Common themes across sessions
- **Health Trends** - Score changes week-over-week
- **Upcoming Concerns** - Based on observations flagged as "todo" or "investigate"

**Generation:**
- Manual trigger: "Generate Weekly Report" button
- Or automated via cron (if dashboard runs as service)
- Uses Claude API (via Conductor) for synthesis

**Storage:**
```javascript
// ~/.claude-memory/reports/2025-W01.json
{
  weekOf: "2025-01-06",
  generatedAt: "2025-01-06T20:00:00Z",
  sections: {
    projectsWorkedOn: ["gyst", "conductor"],
    decisions: [{...}],
    patterns: ["Frequent Firebase auth debugging", "..."],
    healthTrends: { gyst: { before: 78, after: 72 }, ... },
    concerns: ["Performance regression in GYST feed"]
  }
}
```

**UI:**
- Reports tab in portal view
- Week-by-week history
- Export to Markdown

---

### 5. Enhanced Chat with Context Modes

**Problem:** Current chat has 3 modes (portfolio, coding, general) but no way to focus on specific project deeply.

**Solution:** Add project-deep mode with full codebase context.

**Context Modes:**
| Mode | Context Loaded | Use Case |
|------|---------------|----------|
| `general` | None | General questions |
| `portfolio` | All projects (summary) | Cross-project questions |
| `coding` | None (system prompt) | Generic coding help |
| `project-deep` | Single project (full) | Deep codebase questions |
| `with-knowledge-base` | KB + portfolio | Questions needing docs |

**Project-Deep Mode:**
- Load all of: summaries.json, functions.json, schema.json, graph.json
- Chunk if needed (large projects)
- Enable questions like "What files import AuthContext?"

**API Extension:**
```javascript
// POST /api/ollama/standalone-chat
{
  question: "...",
  contextMode: "project-deep",
  projectId: "gyst",  // Required for project-deep
  history: [...]
}
```

---

### 6. Conductor API Proxy

**Problem:** Dashboard currently only uses Ollama. Adding Conductor features requires API access.

**Solution:** Add Conductor API proxy endpoints to dashboard server.

**Implementation:**
- Store Conductor URL in config: `~/.claude-memory/global/integrations.json`
- Dashboard server proxies requests to Conductor
- Auth via stored session token (keychain)

**Endpoints:**
```javascript
// GET /api/integrations/conductor/status
// POST /api/integrations/conductor/connect (store token)
// POST /api/conductor/web-search
// POST /api/conductor/generate-report
// GET /api/conductor/workspaces
```

**Config:**
```javascript
// ~/.claude-memory/global/integrations.json
{
  conductor: {
    url: "https://conductor.jamelna.com",
    connected: true,
    connectedAt: "2025-01-06T10:00:00Z"
  }
}
```

---

## UI Layout Changes

### Portal View
```
┌─────────────────────────────────────────────────────────────┐
│ [Alerts Banner - urgent/high alerts across all projects]    │
├─────────────────────────────────────────────────────────────┤
│ Projects    Reports    Knowledge Base    Settings           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Project Cards (existing)                                   │
│  + Alert badge on cards with issues                         │
│                                                             │
│                                           ┌───────────────┐ │
│                                           │  Dash AI Chat │ │
│                                           │  + Web search │ │
│                                           │  + KB search  │ │
│                                           └───────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### New Tabs
- **Reports** - Weekly report history + generate
- **Knowledge Base** - Manage saved documentation sources

### Settings Additions
- Conductor Integration section
- Alert preferences (which alerts to show)
- Knowledge base management

---

## Implementation Phases

### Phase 1: Conductor Proxy & Web Search
- Add integrations.json config
- Implement Conductor proxy endpoints
- Add web search fallback to chat UI
- Confidence scoring for Ollama responses

### Phase 2: Knowledge Base
- Knowledge base storage and API
- Tavily content extraction via Conductor
- Chat integration with KB context mode

### Phase 3: Proactive Alerts
- Alert generation logic
- Alert storage and dismissal
- Alert banner UI

### Phase 4: Weekly Reports
- Report generation via Claude API
- Report storage and history
- Reports tab UI

### Phase 5: Enhanced Chat
- Project-deep context mode
- Context mode selector in chat UI

---

## Dependencies

- **Conductor API** - For web search (Tavily) and Claude API access
- **Existing Dashboard** - server.js, app.js, index.html
- **Existing Memory Files** - health.json, observations.json, etc.

## Notes

- All new features are additive (don't break existing functionality)
- Conductor integration is optional (dashboard works without it, just with reduced features)
- Local-first approach (knowledge base stored locally, not in Conductor)
