# Claude Memory Dashboard - Conductor Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Integrate Conductor AI capabilities into the claude-memory dashboard for web search fallback, proactive alerts, knowledge base, and weekly reports.

**Architecture:** Add Conductor API proxy to existing Node.js server, extend Ollama chat with confidence scoring and web fallback, add new UI sections for alerts/reports/knowledge base.

**Tech Stack:** Node.js (server.js), Vanilla JS (app.js), HTML/CSS, Conductor API (Tavily + Claude)

---

## Phase 1: Conductor Proxy & Configuration

### Task 1: Create integrations config file

**Files:**
- Create: `~/.claude-memory/global/integrations.json`

**Step 1: Create the integrations config structure**

```json
{
  "conductor": {
    "url": "",
    "sessionToken": "",
    "connected": false,
    "connectedAt": null
  },
  "lastUpdated": null
}
```

**Step 2: Create file manually or via dashboard setup**

Run:
```bash
mkdir -p ~/.claude-memory/global
echo '{"conductor":{"url":"","sessionToken":"","connected":false,"connectedAt":null},"lastUpdated":null}' > ~/.claude-memory/global/integrations.json
```

**Step 3: Verify file exists**

Run: `cat ~/.claude-memory/global/integrations.json`
Expected: JSON content displayed

---

### Task 2: Add integrations API endpoints to server

**Files:**
- Modify: `~/.claude-memory/dashboard/server.js`

**Step 1: Add integrations config helpers after keychain helpers (around line 232)**

```javascript
// ========== INTEGRATIONS CONFIG ==========
const INTEGRATIONS_PATH = path.join(MEMORY_ROOT, 'global', 'integrations.json');

function getIntegrations() {
  try {
    if (fs.existsSync(INTEGRATIONS_PATH)) {
      return JSON.parse(fs.readFileSync(INTEGRATIONS_PATH, 'utf8'));
    }
  } catch (e) {
    console.error('Failed to read integrations:', e.message);
  }
  return { conductor: { url: '', sessionToken: '', connected: false, connectedAt: null } };
}

function saveIntegrations(integrations) {
  const dir = path.dirname(INTEGRATIONS_PATH);
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
  integrations.lastUpdated = new Date().toISOString();
  fs.writeFileSync(INTEGRATIONS_PATH, JSON.stringify(integrations, null, 2));
}
// ========== END INTEGRATIONS CONFIG ==========
```

**Step 2: Add GET /api/integrations endpoint in handleAPI function**

Find the API endpoints section and add:

```javascript
    // GET /api/integrations - get all integrations config
    if (parts[1] === 'integrations' && !parts[2]) {
      const integrations = getIntegrations();
      // Don't expose session token
      const safe = {
        conductor: {
          url: integrations.conductor?.url || '',
          connected: integrations.conductor?.connected || false,
          connectedAt: integrations.conductor?.connectedAt
        }
      };
      res.end(JSON.stringify(safe));
      return;
    }
```

**Step 3: Add POST /api/integrations/conductor/connect endpoint**

```javascript
    // POST /api/integrations/conductor/connect - connect to Conductor
    if (req.method === 'POST' && parts[1] === 'integrations' && parts[2] === 'conductor' && parts[3] === 'connect') {
      let body = '';
      req.on('data', chunk => body += chunk);
      req.on('end', async () => {
        try {
          const { url, sessionToken } = JSON.parse(body);

          if (!url || !sessionToken) {
            res.statusCode = 400;
            res.end(JSON.stringify({ error: 'url and sessionToken are required' }));
            return;
          }

          // Test connection by fetching profile
          const testUrl = `${url}/api/jobs/profile`;
          const testRes = await fetch(testUrl, {
            headers: { 'Authorization': `Bearer ${sessionToken}` }
          });

          if (!testRes.ok) {
            res.statusCode = 401;
            res.end(JSON.stringify({ error: 'Invalid credentials or URL' }));
            return;
          }

          // Save to integrations
          const integrations = getIntegrations();
          integrations.conductor = {
            url,
            sessionToken,
            connected: true,
            connectedAt: new Date().toISOString()
          };
          saveIntegrations(integrations);

          res.end(JSON.stringify({ success: true, connected: true }));
        } catch (e) {
          res.statusCode = 500;
          res.end(JSON.stringify({ error: e.message }));
        }
      });
      return;
    }
```

**Step 4: Add DELETE /api/integrations/conductor/disconnect endpoint**

```javascript
    // DELETE /api/integrations/conductor/disconnect
    if (req.method === 'DELETE' && parts[1] === 'integrations' && parts[2] === 'conductor' && parts[3] === 'disconnect') {
      const integrations = getIntegrations();
      integrations.conductor = {
        url: '',
        sessionToken: '',
        connected: false,
        connectedAt: null
      };
      saveIntegrations(integrations);
      res.end(JSON.stringify({ success: true }));
      return;
    }
```

**Step 5: Test the endpoints**

Run: `curl http://localhost:3333/api/integrations`
Expected: `{"conductor":{"url":"","connected":false,"connectedAt":null}}`

---

### Task 3: Add Conductor web search proxy endpoint

**Files:**
- Modify: `~/.claude-memory/dashboard/server.js`

**Step 1: Add POST /api/conductor/web-search endpoint**

```javascript
    // POST /api/conductor/web-search - proxy web search to Conductor
    if (req.method === 'POST' && parts[1] === 'conductor' && parts[2] === 'web-search') {
      let body = '';
      req.on('data', chunk => body += chunk);
      req.on('end', async () => {
        try {
          const { query, workspaceId } = JSON.parse(body);
          const integrations = getIntegrations();

          if (!integrations.conductor?.connected) {
            res.statusCode = 400;
            res.end(JSON.stringify({ error: 'Conductor not connected' }));
            return;
          }

          // Use the chat endpoint with web search
          const chatUrl = `${integrations.conductor.url}/api/chat`;
          const chatRes = await fetch(chatUrl, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'Authorization': `Bearer ${integrations.conductor.sessionToken}`
            },
            body: JSON.stringify({
              workspaceId: workspaceId || 'default',
              message: query,
              useWebSearch: true
            })
          });

          if (!chatRes.ok) {
            const error = await chatRes.text();
            res.statusCode = chatRes.status;
            res.end(JSON.stringify({ error }));
            return;
          }

          const data = await chatRes.json();
          res.end(JSON.stringify({
            answer: data.response || data.answer,
            sources: data.webSearchResults || [],
            suggestWebSearch: false
          }));
        } catch (e) {
          res.statusCode = 500;
          res.end(JSON.stringify({ error: e.message }));
        }
      });
      return;
    }
```

**Step 2: Verify endpoint exists**

Run: `curl -X POST http://localhost:3333/api/conductor/web-search -H "Content-Type: application/json" -d '{"query":"test"}'`
Expected: `{"error":"Conductor not connected"}` (expected when not connected)

---

## Phase 2: Confidence Scoring & Web Fallback UI

### Task 4: Add confidence scoring to Ollama responses

**Files:**
- Modify: `~/.claude-memory/dashboard/server.js`

**Step 1: Create confidence scoring function after integrations helpers**

```javascript
// ========== CONFIDENCE SCORING ==========
function scoreConfidence(response, question) {
  let score = 0.7; // Default medium-high confidence

  const uncertainPhrases = [
    "i'm not sure", "i don't know", "i don't have", "i cannot",
    "you should check", "might be", "could be", "possibly",
    "i'm uncertain", "hard to say", "difficult to determine",
    "i don't have access", "outside my knowledge", "beyond my"
  ];

  const responseLower = response.toLowerCase();

  // Check for uncertainty phrases
  for (const phrase of uncertainPhrases) {
    if (responseLower.includes(phrase)) {
      score -= 0.2;
    }
  }

  // Very short responses often indicate uncertainty
  if (response.length < 100) {
    score -= 0.15;
  }

  // Questions about external topics likely need web search
  const externalTopics = [
    'latest', 'current version', 'documentation', 'how to install',
    'error:', 'exception', 'npm', 'library', 'package', 'api'
  ];
  const questionLower = question.toLowerCase();
  for (const topic of externalTopics) {
    if (questionLower.includes(topic)) {
      score -= 0.1;
    }
  }

  // Clamp to 0-1
  return Math.max(0, Math.min(1, score));
}
// ========== END CONFIDENCE SCORING ==========
```

**Step 2: Update the standalone-chat endpoint to include confidence**

Find the `/api/ollama/standalone-chat` endpoint and modify the response section:

After `const parsed = JSON.parse(data);` add:

```javascript
const confidence = scoreConfidence(parsed.response || '', question);
const integrations = getIntegrations();
const suggestWebSearch = confidence < 0.5 && integrations.conductor?.connected;

res.end(JSON.stringify({
  response: parsed.response || 'No response',
  confidence: confidence,
  suggestWebSearch: suggestWebSearch,
  originalQuestion: question
}));
```

**Step 3: Test confidence scoring**

Run the dashboard and ask a question that should trigger low confidence.

---

### Task 5: Add web search fallback UI to chat

**Files:**
- Modify: `~/.claude-memory/dashboard/app.js`

**Step 1: Find the askOllama function and update it to handle web search suggestion**

Locate the function that handles Ollama responses (around the standalone chat handling) and add after receiving response:

```javascript
// Add web search button if suggested
if (data.suggestWebSearch) {
  const webSearchDiv = document.createElement('div');
  webSearchDiv.className = 'web-search-suggestion';
  webSearchDiv.innerHTML = `
    <p class="suggestion-text">I'm not fully confident in this answer.</p>
    <button class="web-search-btn" onclick="searchWeb('${encodeURIComponent(data.originalQuestion || '')}')">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">
        <circle cx="11" cy="11" r="8"></circle>
        <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
      </svg>
      Search the web
    </button>
  `;
  messagesEl.appendChild(webSearchDiv);
}
```

**Step 2: Add searchWeb function**

```javascript
async function searchWeb(query) {
  const messagesEl = document.getElementById('ollama-messages');

  // Add loading message
  const loadingDiv = document.createElement('div');
  loadingDiv.className = 'chat-message assistant loading';
  loadingDiv.textContent = 'Searching the web...';
  messagesEl.appendChild(loadingDiv);
  messagesEl.scrollTop = messagesEl.scrollHeight;

  try {
    const res = await fetch('/api/conductor/web-search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: decodeURIComponent(query) })
    });

    loadingDiv.remove();

    if (!res.ok) {
      const error = await res.json();
      throw new Error(error.error || 'Web search failed');
    }

    const data = await res.json();

    // Display web search results
    const resultDiv = document.createElement('div');
    resultDiv.className = 'chat-message assistant web-result';

    let sourcesHtml = '';
    if (data.sources && data.sources.length > 0) {
      sourcesHtml = `
        <div class="web-sources">
          <h5>Sources:</h5>
          ${data.sources.slice(0, 3).map(s => `
            <a href="${s.url}" target="_blank" class="web-source-link">
              ${s.title || s.url}
            </a>
          `).join('')}
        </div>
      `;
    }

    resultDiv.innerHTML = `
      <div class="web-answer">${data.answer || 'No results found'}</div>
      ${sourcesHtml}
    `;
    messagesEl.appendChild(resultDiv);
  } catch (e) {
    loadingDiv.remove();
    const errorDiv = document.createElement('div');
    errorDiv.className = 'chat-message assistant error';
    errorDiv.textContent = 'Web search failed: ' + e.message;
    messagesEl.appendChild(errorDiv);
  }

  messagesEl.scrollTop = messagesEl.scrollHeight;
}
```

**Step 3: Add CSS styles for web search UI**

**Files:**
- Modify: `~/.claude-memory/dashboard/styles.css`

Add at the end:

```css
/* Web Search Styles */
.web-search-suggestion {
  padding: 12px;
  margin: 8px 0;
  background: rgba(0, 168, 255, 0.1);
  border: 1px solid rgba(0, 168, 255, 0.3);
  border-radius: 8px;
}

.web-search-suggestion .suggestion-text {
  font-size: 13px;
  color: #888;
  margin-bottom: 8px;
}

.web-search-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  background: #00a8ff;
  color: white;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
}

.web-search-btn:hover {
  background: #0090dd;
}

.web-result {
  background: rgba(64, 224, 208, 0.1);
  border-left: 3px solid #40E0D0;
}

.web-sources {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid rgba(255,255,255,0.1);
}

.web-sources h5 {
  font-size: 12px;
  color: #888;
  margin-bottom: 8px;
}

.web-source-link {
  display: block;
  padding: 4px 0;
  color: #00a8ff;
  text-decoration: none;
  font-size: 13px;
}

.web-source-link:hover {
  text-decoration: underline;
}
```

---

## Phase 3: Proactive Alerts

### Task 6: Create alerts storage and generation

**Files:**
- Create: `~/.claude-memory/dashboard/alerts.js`

**Step 1: Create the alerts module**

```javascript
// alerts.js - Proactive health alerts generation
const fs = require('fs');
const path = require('path');

const MEMORY_ROOT = process.env.MEMORY_ROOT || path.join(require('os').homedir(), '.claude-memory');

function generateAlerts() {
  const configPath = path.join(MEMORY_ROOT, 'config.json');
  if (!fs.existsSync(configPath)) return [];

  const config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
  const alerts = [];

  for (const project of config.projects) {
    const projectDir = path.join(MEMORY_ROOT, 'projects', project.id);
    const healthPath = path.join(projectDir, 'health.json');
    const historyPath = path.join(projectDir, 'health_history.json');
    const alertsPath = path.join(projectDir, 'alerts.json');

    // Load existing dismissed alerts
    let dismissed = [];
    if (fs.existsSync(alertsPath)) {
      try {
        const existing = JSON.parse(fs.readFileSync(alertsPath, 'utf8'));
        dismissed = existing.alerts?.filter(a => a.dismissedAt).map(a => a.id) || [];
      } catch (e) {}
    }

    // Check health
    if (fs.existsSync(healthPath)) {
      try {
        const health = JSON.parse(fs.readFileSync(healthPath, 'utf8'));

        // Critical health
        if (health.score !== null && health.score < 40) {
          const alertId = `critical-${project.id}`;
          if (!dismissed.includes(alertId)) {
            alerts.push({
              id: alertId,
              type: 'critical_issue',
              priority: 'urgent',
              title: `${project.displayName} health is critical (${health.score}/100)`,
              details: 'Health score is below 40. Immediate attention recommended.',
              projectId: project.id,
              createdAt: new Date().toISOString()
            });
          }
        }

        // Check for degradation
        if (fs.existsSync(historyPath)) {
          const history = JSON.parse(fs.readFileSync(historyPath, 'utf8'));
          if (history.length >= 2) {
            const recent = history[history.length - 1];
            const previous = history[history.length - 2];
            const drop = previous.score - recent.score;

            if (drop >= 10) {
              const alertId = `degradation-${project.id}-${recent.timestamp}`;
              if (!dismissed.includes(alertId)) {
                alerts.push({
                  id: alertId,
                  type: 'health_degradation',
                  priority: 'high',
                  title: `${project.displayName} health dropped ${drop} points`,
                  details: `Score went from ${previous.score} to ${recent.score}`,
                  projectId: project.id,
                  createdAt: new Date().toISOString()
                });
              }
            }
          }
        }

        // Stale scan
        if (health.timestamp) {
          const scanDate = new Date(health.timestamp);
          const daysSinceScan = (Date.now() - scanDate.getTime()) / (1000 * 60 * 60 * 24);

          if (daysSinceScan > 7) {
            const alertId = `stale-${project.id}`;
            if (!dismissed.includes(alertId)) {
              alerts.push({
                id: alertId,
                type: 'stale_scan',
                priority: 'medium',
                title: `${project.displayName} hasn't been scanned in ${Math.floor(daysSinceScan)} days`,
                details: 'Run a health scan to get current status.',
                projectId: project.id,
                createdAt: new Date().toISOString()
              });
            }
          }
        }
      } catch (e) {
        console.error(`Error checking health for ${project.id}:`, e.message);
      }
    }
  }

  return alerts;
}

function dismissAlert(projectId, alertId) {
  const alertsPath = path.join(MEMORY_ROOT, 'projects', projectId, 'alerts.json');

  let data = { alerts: [] };
  if (fs.existsSync(alertsPath)) {
    data = JSON.parse(fs.readFileSync(alertsPath, 'utf8'));
  }

  // Find or create alert entry
  let alert = data.alerts.find(a => a.id === alertId);
  if (!alert) {
    alert = { id: alertId, dismissedAt: new Date().toISOString() };
    data.alerts.push(alert);
  } else {
    alert.dismissedAt = new Date().toISOString();
  }

  fs.writeFileSync(alertsPath, JSON.stringify(data, null, 2));
  return true;
}

module.exports = { generateAlerts, dismissAlert };
```

**Step 2: Verify file created**

Run: `ls ~/.claude-memory/dashboard/alerts.js`

---

### Task 7: Add alerts API endpoints

**Files:**
- Modify: `~/.claude-memory/dashboard/server.js`

**Step 1: Import alerts module at top of server.js**

After other requires:
```javascript
const { generateAlerts, dismissAlert } = require('./alerts.js');
```

**Step 2: Add GET /api/alerts endpoint**

```javascript
    // GET /api/alerts - get all active alerts
    if (parts[1] === 'alerts' && !parts[2]) {
      try {
        const alerts = generateAlerts();
        res.end(JSON.stringify({ alerts }));
      } catch (e) {
        res.statusCode = 500;
        res.end(JSON.stringify({ error: e.message }));
      }
      return;
    }
```

**Step 3: Add POST /api/alerts/:id/dismiss endpoint**

```javascript
    // POST /api/alerts/:id/dismiss - dismiss an alert
    if (req.method === 'POST' && parts[1] === 'alerts' && parts[2] && parts[3] === 'dismiss') {
      let body = '';
      req.on('data', chunk => body += chunk);
      req.on('end', () => {
        try {
          const { projectId } = JSON.parse(body);
          const alertId = parts[2];

          if (!projectId) {
            res.statusCode = 400;
            res.end(JSON.stringify({ error: 'projectId is required' }));
            return;
          }

          dismissAlert(projectId, alertId);
          res.end(JSON.stringify({ success: true }));
        } catch (e) {
          res.statusCode = 500;
          res.end(JSON.stringify({ error: e.message }));
        }
      });
      return;
    }
```

**Step 4: Test alerts endpoint**

Run: `curl http://localhost:3333/api/alerts`
Expected: `{"alerts":[...]}` (array of any current alerts)

---

### Task 8: Add alerts banner to portal UI

**Files:**
- Modify: `~/.claude-memory/dashboard/index.html`

**Step 1: Add alerts banner before portal-header**

```html
    <!-- Alerts Banner -->
    <div id="alerts-banner" class="alerts-banner hidden">
      <div class="alerts-container" id="alerts-container">
        <!-- Alerts will be rendered here -->
      </div>
    </div>
```

**Step 2: Add alerts JavaScript to app.js**

```javascript
// ========== ALERTS ==========
async function loadAlerts() {
  try {
    const res = await fetch('/api/alerts');
    const data = await res.json();
    renderAlerts(data.alerts || []);
  } catch (e) {
    console.error('Failed to load alerts:', e);
  }
}

function renderAlerts(alerts) {
  const banner = document.getElementById('alerts-banner');
  const container = document.getElementById('alerts-container');

  if (!alerts || alerts.length === 0) {
    banner.classList.add('hidden');
    return;
  }

  banner.classList.remove('hidden');

  // Sort by priority
  const priorityOrder = { urgent: 0, high: 1, medium: 2, low: 3 };
  alerts.sort((a, b) => priorityOrder[a.priority] - priorityOrder[b.priority]);

  container.innerHTML = alerts.map(alert => `
    <div class="alert-item priority-${alert.priority}">
      <div class="alert-icon">${alert.priority === 'urgent' ? '🚨' : alert.priority === 'high' ? '⚠️' : 'ℹ️'}</div>
      <div class="alert-content">
        <div class="alert-title">${alert.title}</div>
        <div class="alert-details">${alert.details}</div>
      </div>
      <div class="alert-actions">
        <button class="alert-action-btn" onclick="navigateToProject('${alert.projectId}')">View</button>
        <button class="alert-dismiss-btn" onclick="dismissAlert('${alert.id}', '${alert.projectId}')">&times;</button>
      </div>
    </div>
  `).join('');
}

async function dismissAlert(alertId, projectId) {
  try {
    await fetch(`/api/alerts/${alertId}/dismiss`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ projectId })
    });
    loadAlerts(); // Refresh
  } catch (e) {
    console.error('Failed to dismiss alert:', e);
  }
}
```

**Step 3: Call loadAlerts on startup**

In the init function or DOMContentLoaded, add:
```javascript
loadAlerts();
```

**Step 4: Add CSS for alerts banner**

```css
/* Alerts Banner */
.alerts-banner {
  background: #1a1a1d;
  border-bottom: 1px solid #333;
  padding: 8px 20px;
}

.alerts-banner.hidden {
  display: none;
}

.alerts-container {
  max-width: 1400px;
  margin: 0 auto;
}

.alert-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  margin-bottom: 6px;
  border-radius: 8px;
  background: rgba(255,255,255,0.05);
}

.alert-item.priority-urgent {
  background: rgba(220, 38, 38, 0.15);
  border-left: 3px solid #dc2626;
}

.alert-item.priority-high {
  background: rgba(245, 158, 11, 0.15);
  border-left: 3px solid #f59e0b;
}

.alert-item.priority-medium {
  background: rgba(59, 130, 246, 0.15);
  border-left: 3px solid #3b82f6;
}

.alert-icon {
  font-size: 20px;
}

.alert-content {
  flex: 1;
}

.alert-title {
  font-weight: 500;
  color: #fff;
}

.alert-details {
  font-size: 12px;
  color: #888;
}

.alert-actions {
  display: flex;
  gap: 8px;
}

.alert-action-btn {
  padding: 6px 12px;
  background: rgba(255,255,255,0.1);
  border: none;
  border-radius: 4px;
  color: #fff;
  cursor: pointer;
  font-size: 12px;
}

.alert-action-btn:hover {
  background: rgba(255,255,255,0.2);
}

.alert-dismiss-btn {
  padding: 6px 10px;
  background: transparent;
  border: none;
  color: #666;
  cursor: pointer;
  font-size: 16px;
}

.alert-dismiss-btn:hover {
  color: #fff;
}
```

---

## Phase 4: Knowledge Base

### Task 9: Create knowledge base storage and API

**Files:**
- Modify: `~/.claude-memory/dashboard/server.js`

**Step 1: Add knowledge base helpers**

```javascript
// ========== KNOWLEDGE BASE ==========
const KB_PATH = path.join(MEMORY_ROOT, 'global', 'knowledge-base.json');

function getKnowledgeBase() {
  try {
    if (fs.existsSync(KB_PATH)) {
      return JSON.parse(fs.readFileSync(KB_PATH, 'utf8'));
    }
  } catch (e) {}
  return { sources: [], lastUpdated: null };
}

function saveKnowledgeBase(kb) {
  const dir = path.dirname(KB_PATH);
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
  kb.lastUpdated = new Date().toISOString();
  fs.writeFileSync(KB_PATH, JSON.stringify(kb, null, 2));
}
// ========== END KNOWLEDGE BASE ==========
```

**Step 2: Add GET /api/knowledge-base endpoint**

```javascript
    // GET /api/knowledge-base - get all sources
    if (parts[1] === 'knowledge-base' && !parts[2]) {
      const kb = getKnowledgeBase();
      res.end(JSON.stringify(kb));
      return;
    }
```

**Step 3: Add POST /api/knowledge-base endpoint (add URL)**

```javascript
    // POST /api/knowledge-base - add a URL
    if (req.method === 'POST' && parts[1] === 'knowledge-base' && !parts[2]) {
      let body = '';
      req.on('data', chunk => body += chunk);
      req.on('end', async () => {
        try {
          const { url } = JSON.parse(body);

          if (!url) {
            res.statusCode = 400;
            res.end(JSON.stringify({ error: 'url is required' }));
            return;
          }

          // Check Conductor connection
          const integrations = getIntegrations();
          let content = '';
          let title = url;

          if (integrations.conductor?.connected) {
            // Use Conductor to fetch and extract content
            try {
              const extractUrl = `${integrations.conductor.url}/api/web-sources`;
              const extractRes = await fetch(extractUrl, {
                method: 'POST',
                headers: {
                  'Content-Type': 'application/json',
                  'Authorization': `Bearer ${integrations.conductor.sessionToken}`
                },
                body: JSON.stringify({ url, fromManual: true })
              });

              if (extractRes.ok) {
                const data = await extractRes.json();
                content = data.content || '';
                title = data.title || url;
              }
            } catch (e) {
              console.error('Conductor fetch failed:', e.message);
            }
          }

          // Add to knowledge base
          const kb = getKnowledgeBase();
          const id = 'kb-' + Date.now();
          kb.sources.push({
            id,
            title,
            url,
            content,
            fetchedAt: new Date().toISOString(),
            tags: []
          });
          saveKnowledgeBase(kb);

          res.end(JSON.stringify({ id, title, url }));
        } catch (e) {
          res.statusCode = 500;
          res.end(JSON.stringify({ error: e.message }));
        }
      });
      return;
    }
```

**Step 4: Add DELETE /api/knowledge-base/:id endpoint**

```javascript
    // DELETE /api/knowledge-base/:id - remove a source
    if (req.method === 'DELETE' && parts[1] === 'knowledge-base' && parts[2]) {
      const sourceId = parts[2];
      const kb = getKnowledgeBase();
      kb.sources = kb.sources.filter(s => s.id !== sourceId);
      saveKnowledgeBase(kb);
      res.end(JSON.stringify({ success: true }));
      return;
    }
```

---

### Task 10: Add Knowledge Base tab to portal UI

**Files:**
- Modify: `~/.claude-memory/dashboard/index.html`
- Modify: `~/.claude-memory/dashboard/app.js`

**Step 1: Add Knowledge Base tab in portal-header**

```html
    <div class="portal-header">
      <h2>Your Projects</h2>
      <div class="portal-tabs">
        <button class="portal-tab active" onclick="showPortalTab('projects')">Projects</button>
        <button class="portal-tab" onclick="showPortalTab('knowledge-base')">Knowledge Base</button>
        <button class="portal-tab" onclick="showPortalTab('reports')">Reports</button>
      </div>
    </div>
```

**Step 2: Add knowledge base section after portal-grid**

```html
    <div id="knowledge-base-view" class="knowledge-base-view hidden">
      <div class="kb-header">
        <h3>Documentation Knowledge Base</h3>
        <p>Save frequently referenced documentation for quick access via chat.</p>
      </div>
      <div class="kb-add-form">
        <input type="url" id="kb-url-input" placeholder="https://docs.example.com/..." class="search-box" style="flex:1;">
        <button onclick="addKnowledgeBaseUrl()" class="zoom-btn">Add URL</button>
      </div>
      <div id="kb-sources-list" class="kb-sources-list">
        <div class="loading">Loading...</div>
      </div>
    </div>
```

**Step 3: Add JavaScript for knowledge base**

```javascript
// ========== KNOWLEDGE BASE UI ==========
async function loadKnowledgeBase() {
  try {
    const res = await fetch('/api/knowledge-base');
    const data = await res.json();
    renderKnowledgeBase(data.sources || []);
  } catch (e) {
    console.error('Failed to load knowledge base:', e);
  }
}

function renderKnowledgeBase(sources) {
  const container = document.getElementById('kb-sources-list');

  if (!sources || sources.length === 0) {
    container.innerHTML = '<div class="kb-empty">No sources added yet. Add documentation URLs above.</div>';
    return;
  }

  container.innerHTML = sources.map(s => `
    <div class="kb-source-item">
      <div class="kb-source-info">
        <div class="kb-source-title">${s.title}</div>
        <a href="${s.url}" target="_blank" class="kb-source-url">${s.url}</a>
        <div class="kb-source-meta">Added ${formatRelativeTime(s.fetchedAt)}</div>
      </div>
      <button class="kb-delete-btn" onclick="deleteKnowledgeBaseSource('${s.id}')">&times;</button>
    </div>
  `).join('');
}

async function addKnowledgeBaseUrl() {
  const input = document.getElementById('kb-url-input');
  const url = input.value.trim();

  if (!url) return;

  try {
    const res = await fetch('/api/knowledge-base', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url })
    });

    if (!res.ok) {
      const error = await res.json();
      alert('Failed to add: ' + error.error);
      return;
    }

    input.value = '';
    loadKnowledgeBase();
  } catch (e) {
    alert('Failed to add URL: ' + e.message);
  }
}

async function deleteKnowledgeBaseSource(id) {
  try {
    await fetch(`/api/knowledge-base/${id}`, { method: 'DELETE' });
    loadKnowledgeBase();
  } catch (e) {
    console.error('Failed to delete source:', e);
  }
}

function showPortalTab(tab) {
  // Update tab buttons
  document.querySelectorAll('.portal-tab').forEach(t => t.classList.remove('active'));
  event.target.classList.add('active');

  // Hide all tab content
  document.getElementById('portal-grid').classList.add('hidden');
  document.getElementById('knowledge-base-view')?.classList.add('hidden');
  document.getElementById('reports-view')?.classList.add('hidden');
  document.getElementById('ollama-quick-access')?.classList.add('hidden');

  // Show selected tab
  if (tab === 'projects') {
    document.getElementById('portal-grid').classList.remove('hidden');
    document.getElementById('ollama-quick-access')?.classList.remove('hidden');
  } else if (tab === 'knowledge-base') {
    document.getElementById('knowledge-base-view')?.classList.remove('hidden');
    loadKnowledgeBase();
  } else if (tab === 'reports') {
    document.getElementById('reports-view')?.classList.remove('hidden');
    loadReports();
  }
}
```

**Step 4: Add CSS for knowledge base**

```css
/* Knowledge Base */
.knowledge-base-view {
  padding: 20px;
  max-width: 800px;
  margin: 0 auto;
}

.kb-header {
  margin-bottom: 20px;
}

.kb-header h3 {
  color: #fff;
  margin-bottom: 4px;
}

.kb-header p {
  color: #888;
  font-size: 14px;
}

.kb-add-form {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
}

.kb-sources-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.kb-source-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px;
  background: rgba(255,255,255,0.05);
  border-radius: 8px;
}

.kb-source-title {
  font-weight: 500;
  color: #fff;
}

.kb-source-url {
  font-size: 12px;
  color: #00a8ff;
  text-decoration: none;
}

.kb-source-url:hover {
  text-decoration: underline;
}

.kb-source-meta {
  font-size: 11px;
  color: #666;
  margin-top: 4px;
}

.kb-delete-btn {
  background: transparent;
  border: none;
  color: #666;
  cursor: pointer;
  font-size: 18px;
  padding: 8px;
}

.kb-delete-btn:hover {
  color: #f87171;
}

.kb-empty {
  text-align: center;
  padding: 40px;
  color: #666;
}

.portal-tabs {
  display: flex;
  gap: 8px;
  margin-top: 12px;
}

.portal-tab {
  padding: 8px 16px;
  background: transparent;
  border: 1px solid #333;
  border-radius: 6px;
  color: #888;
  cursor: pointer;
  font-size: 13px;
}

.portal-tab:hover {
  border-color: #555;
  color: #fff;
}

.portal-tab.active {
  background: rgba(0, 168, 255, 0.2);
  border-color: #00a8ff;
  color: #00a8ff;
}
```

---

## Phase 5: Weekly Reports

### Task 11: Add reports generation API

**Files:**
- Modify: `~/.claude-memory/dashboard/server.js`

**Step 1: Add reports helpers**

```javascript
// ========== REPORTS ==========
const REPORTS_DIR = path.join(MEMORY_ROOT, 'reports');

function getReports() {
  if (!fs.existsSync(REPORTS_DIR)) return [];

  return fs.readdirSync(REPORTS_DIR)
    .filter(f => f.endsWith('.json'))
    .map(f => {
      try {
        return JSON.parse(fs.readFileSync(path.join(REPORTS_DIR, f), 'utf8'));
      } catch (e) {
        return null;
      }
    })
    .filter(Boolean)
    .sort((a, b) => new Date(b.generatedAt) - new Date(a.generatedAt));
}

function saveReport(report) {
  if (!fs.existsSync(REPORTS_DIR)) {
    fs.mkdirSync(REPORTS_DIR, { recursive: true });
  }
  const filename = `${report.weekOf}.json`;
  fs.writeFileSync(path.join(REPORTS_DIR, filename), JSON.stringify(report, null, 2));
}
// ========== END REPORTS ==========
```

**Step 2: Add GET /api/reports endpoint**

```javascript
    // GET /api/reports - get all weekly reports
    if (parts[1] === 'reports' && !parts[2]) {
      const reports = getReports();
      res.end(JSON.stringify({ reports }));
      return;
    }
```

**Step 3: Add POST /api/reports/generate endpoint**

```javascript
    // POST /api/reports/generate - generate weekly report
    if (req.method === 'POST' && parts[1] === 'reports' && parts[2] === 'generate') {
      const integrations = getIntegrations();

      if (!integrations.conductor?.connected) {
        res.statusCode = 400;
        res.end(JSON.stringify({ error: 'Conductor not connected (needed for AI synthesis)' }));
        return;
      }

      try {
        const configPath = path.join(MEMORY_ROOT, 'config.json');
        const config = JSON.parse(fs.readFileSync(configPath, 'utf8'));

        // Gather data from all projects
        const projectData = [];
        for (const project of config.projects) {
          const projectDir = path.join(MEMORY_ROOT, 'projects', project.id);
          const data = { id: project.id, name: project.displayName };

          // Health
          const healthPath = path.join(projectDir, 'health.json');
          if (fs.existsSync(healthPath)) {
            data.health = JSON.parse(fs.readFileSync(healthPath, 'utf8'));
          }

          // Decisions
          const decisionsPath = path.join(projectDir, 'decisions.json');
          if (fs.existsSync(decisionsPath)) {
            const dec = JSON.parse(fs.readFileSync(decisionsPath, 'utf8'));
            data.decisions = Array.isArray(dec) ? dec.slice(-5) : (dec.decisions || []).slice(-5);
          }

          // Observations
          const obsPath = path.join(projectDir, 'observations.json');
          if (fs.existsSync(obsPath)) {
            const obs = JSON.parse(fs.readFileSync(obsPath, 'utf8'));
            data.observations = Array.isArray(obs) ? obs.slice(-10) : (obs.observations || []).slice(-10);
          }

          projectData.push(data);
        }

        // Use Claude via Conductor to synthesize
        const prompt = `Generate a weekly development report based on this data:

${JSON.stringify(projectData, null, 2)}

Format as:
## Projects Worked On
[list projects with activity]

## Key Decisions Made
[bullet points]

## Patterns Identified
[common themes]

## Health Trends
[score changes]

## Upcoming Concerns
[things to watch]

Be concise and actionable.`;

        const chatRes = await fetch(`${integrations.conductor.url}/api/chat`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${integrations.conductor.sessionToken}`
          },
          body: JSON.stringify({
            workspaceId: 'default',
            message: prompt
          })
        });

        if (!chatRes.ok) {
          throw new Error('Failed to generate report via Claude');
        }

        const chatData = await chatRes.json();

        // Get week start date
        const now = new Date();
        const weekStart = new Date(now);
        weekStart.setDate(weekStart.getDate() - weekStart.getDay());
        const weekOf = weekStart.toISOString().split('T')[0];

        const report = {
          weekOf,
          generatedAt: new Date().toISOString(),
          content: chatData.response || chatData.answer,
          rawData: projectData
        };

        saveReport(report);
        res.end(JSON.stringify(report));
      } catch (e) {
        res.statusCode = 500;
        res.end(JSON.stringify({ error: e.message }));
      }
      return;
    }
```

---

### Task 12: Add reports tab UI

**Files:**
- Modify: `~/.claude-memory/dashboard/index.html`
- Modify: `~/.claude-memory/dashboard/app.js`

**Step 1: Add reports view section**

```html
    <div id="reports-view" class="reports-view hidden">
      <div class="reports-header">
        <h3>Weekly Reports</h3>
        <button onclick="generateReport()" class="zoom-btn">Generate This Week's Report</button>
      </div>
      <div id="reports-list" class="reports-list">
        <div class="loading">Loading...</div>
      </div>
    </div>
```

**Step 2: Add JavaScript for reports**

```javascript
// ========== REPORTS UI ==========
async function loadReports() {
  try {
    const res = await fetch('/api/reports');
    const data = await res.json();
    renderReports(data.reports || []);
  } catch (e) {
    console.error('Failed to load reports:', e);
  }
}

function renderReports(reports) {
  const container = document.getElementById('reports-list');

  if (!reports || reports.length === 0) {
    container.innerHTML = '<div class="reports-empty">No reports yet. Generate your first weekly report.</div>';
    return;
  }

  container.innerHTML = reports.map(r => `
    <div class="report-item">
      <div class="report-header">
        <h4>Week of ${r.weekOf}</h4>
        <span class="report-date">Generated ${formatRelativeTime(r.generatedAt)}</span>
      </div>
      <div class="report-content">${marked ? marked.parse(r.content) : r.content}</div>
    </div>
  `).join('');
}

async function generateReport() {
  const container = document.getElementById('reports-list');
  container.innerHTML = '<div class="loading">Generating report with Claude AI...</div>';

  try {
    const res = await fetch('/api/reports/generate', { method: 'POST' });

    if (!res.ok) {
      const error = await res.json();
      throw new Error(error.error);
    }

    loadReports();
  } catch (e) {
    container.innerHTML = `<div class="reports-error">Failed to generate report: ${e.message}</div>`;
  }
}
```

**Step 3: Add CSS for reports**

```css
/* Reports */
.reports-view {
  padding: 20px;
  max-width: 900px;
  margin: 0 auto;
}

.reports-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.reports-header h3 {
  color: #fff;
}

.reports-list {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.report-item {
  background: rgba(255,255,255,0.05);
  border-radius: 12px;
  padding: 20px;
}

.report-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid #333;
}

.report-header h4 {
  color: #fff;
  margin: 0;
}

.report-date {
  font-size: 12px;
  color: #666;
}

.report-content {
  color: #ccc;
  line-height: 1.6;
}

.report-content h2 {
  color: #00a8ff;
  font-size: 16px;
  margin: 20px 0 8px 0;
}

.report-content ul {
  margin: 8px 0;
  padding-left: 20px;
}

.reports-empty, .reports-error {
  text-align: center;
  padding: 40px;
  color: #666;
}

.reports-error {
  color: #f87171;
}
```

---

## Phase 6: Settings & Integration UI

### Task 13: Add Settings tab with Conductor connection

**Files:**
- Modify: `~/.claude-memory/dashboard/index.html`
- Modify: `~/.claude-memory/dashboard/app.js`

**Step 1: Add Settings tab button**

In portal-tabs:
```html
<button class="portal-tab" onclick="showPortalTab('settings')">Settings</button>
```

**Step 2: Add settings view section**

```html
    <div id="settings-view" class="settings-view hidden">
      <h3>Settings</h3>

      <div class="settings-section">
        <h4>Conductor Integration</h4>
        <p class="settings-desc">Connect to Conductor for web search, AI reports, and knowledge base features.</p>

        <div id="conductor-status" class="conductor-status">
          <span class="status-dot disconnected"></span>
          <span>Not connected</span>
        </div>

        <div id="conductor-connect-form" class="conductor-form">
          <input type="url" id="conductor-url" placeholder="https://conductor.jamelna.com" class="search-box">
          <input type="password" id="conductor-token" placeholder="Session token" class="search-box">
          <button onclick="connectConductor()" class="zoom-btn">Connect</button>
        </div>

        <div id="conductor-disconnect-form" class="conductor-form hidden">
          <button onclick="disconnectConductor()" class="zoom-btn danger">Disconnect</button>
        </div>
      </div>
    </div>
```

**Step 3: Add JavaScript for settings**

```javascript
// ========== SETTINGS UI ==========
async function loadSettings() {
  try {
    const res = await fetch('/api/integrations');
    const data = await res.json();
    renderConductorStatus(data.conductor);
  } catch (e) {
    console.error('Failed to load settings:', e);
  }
}

function renderConductorStatus(conductor) {
  const statusEl = document.getElementById('conductor-status');
  const connectForm = document.getElementById('conductor-connect-form');
  const disconnectForm = document.getElementById('conductor-disconnect-form');

  if (conductor?.connected) {
    statusEl.innerHTML = `
      <span class="status-dot connected"></span>
      <span>Connected to ${conductor.url}</span>
    `;
    connectForm.classList.add('hidden');
    disconnectForm.classList.remove('hidden');
  } else {
    statusEl.innerHTML = `
      <span class="status-dot disconnected"></span>
      <span>Not connected</span>
    `;
    connectForm.classList.remove('hidden');
    disconnectForm.classList.add('hidden');
  }
}

async function connectConductor() {
  const url = document.getElementById('conductor-url').value.trim();
  const sessionToken = document.getElementById('conductor-token').value.trim();

  if (!url || !sessionToken) {
    alert('Please enter both URL and session token');
    return;
  }

  try {
    const res = await fetch('/api/integrations/conductor/connect', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url, sessionToken })
    });

    if (!res.ok) {
      const error = await res.json();
      throw new Error(error.error);
    }

    loadSettings();
    alert('Connected to Conductor successfully!');
  } catch (e) {
    alert('Failed to connect: ' + e.message);
  }
}

async function disconnectConductor() {
  try {
    await fetch('/api/integrations/conductor/disconnect', { method: 'DELETE' });
    loadSettings();
  } catch (e) {
    console.error('Failed to disconnect:', e);
  }
}
```

**Step 4: Update showPortalTab for settings**

```javascript
} else if (tab === 'settings') {
  document.getElementById('settings-view')?.classList.remove('hidden');
  loadSettings();
}
```

**Step 5: Add CSS for settings**

```css
/* Settings */
.settings-view {
  padding: 20px;
  max-width: 600px;
  margin: 0 auto;
}

.settings-view h3 {
  color: #fff;
  margin-bottom: 24px;
}

.settings-section {
  background: rgba(255,255,255,0.05);
  border-radius: 12px;
  padding: 20px;
  margin-bottom: 20px;
}

.settings-section h4 {
  color: #fff;
  margin: 0 0 8px 0;
}

.settings-desc {
  color: #888;
  font-size: 13px;
  margin-bottom: 16px;
}

.conductor-status {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px;
  background: rgba(0,0,0,0.2);
  border-radius: 6px;
  margin-bottom: 16px;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.status-dot.connected {
  background: #10b981;
}

.status-dot.disconnected {
  background: #666;
}

.conductor-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.conductor-form.hidden {
  display: none;
}

.zoom-btn.danger {
  background: rgba(220, 38, 38, 0.2);
  border-color: #dc2626;
  color: #f87171;
}

.zoom-btn.danger:hover {
  background: rgba(220, 38, 38, 0.3);
}
```

---

## Verification Checklist

After completing all tasks, verify:

1. [ ] `curl http://localhost:3333/api/integrations` returns JSON
2. [ ] Conductor connect/disconnect works in Settings
3. [ ] `curl http://localhost:3333/api/alerts` returns alerts array
4. [ ] Alerts banner shows on portal when alerts exist
5. [ ] Knowledge Base tab shows and allows adding URLs
6. [ ] Reports tab shows and generates reports (when Conductor connected)
7. [ ] Chat shows "Search the web" button on uncertain answers
8. [ ] Web search returns results (when Conductor connected)

---

## Commit Strategy

After each phase, commit:
```bash
git add -A
git commit -m "feat(dashboard): add [phase description]"
```

Final commit message:
```
feat(dashboard): integrate Conductor for web search, alerts, KB, and reports

- Add Conductor API proxy with connect/disconnect
- Add confidence scoring with web search fallback
- Add proactive health alerts with banner UI
- Add knowledge base for documentation
- Add weekly reports generation
- Add Settings tab for integration management
```
