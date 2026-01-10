# Portal Redesign Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Transform the dashboard into a project portal with cards landing page and breadcrumb navigation.

**Architecture:** Add a `currentView` state ('portal' | 'project') that controls whether to render the portal grid or the project tabs view. Portal loads lightweight summary data; full project data loads on project selection.

**Tech Stack:** Vanilla JS, CSS, Node.js server

---

## Task 1: Add Portal State and URL Routing

**Files:**
- Modify: `app.js:1-20` (state section)
- Modify: `app.js:63-88` (loadProjects function)

**Step 1: Add new state variables**

Add after line 18 in app.js:

```javascript
// Portal state
let currentView = 'portal'; // 'portal' | 'project'
let allProjectsSummary = []; // Cached summary for portal cards
```

**Step 2: Add URL routing functions**

Add after the new state variables:

```javascript
// ==========================================
// URL ROUTING
// ==========================================
function initRouter() {
  // Handle initial URL
  const hash = window.location.hash.slice(1) || '/';
  handleRoute(hash);

  // Handle back/forward navigation
  window.addEventListener('popstate', () => {
    const hash = window.location.hash.slice(1) || '/';
    handleRoute(hash);
  });
}

function handleRoute(path) {
  if (path === '/' || path === '') {
    showPortal();
  } else if (path.startsWith('/project/')) {
    const parts = path.split('/');
    const projectId = parts[2];
    const tab = parts[3] || 'graph';
    showProject(projectId, tab);
  } else {
    showPortal();
  }
}

function updateURL(path) {
  const newHash = '#' + path;
  if (window.location.hash !== newHash) {
    window.history.pushState(null, '', newHash);
  }
}
```

**Step 3: Run to verify no syntax errors**

Run: `node --check /Users/jmelendez/.claude-memory/dashboard/app.js`
Expected: No output (success)

**Step 4: Commit**

```bash
cd /Users/jmelendez/.claude-memory
git add dashboard/app.js
git commit -m "feat(portal): add view state and URL routing"
```

---

## Task 2: Add Server Endpoint for Project Summaries

**Files:**
- Modify: `server.js:102-143` (after stats endpoint)

**Step 1: Add projects summary endpoint**

Add after the `/api/stats` endpoint (around line 143):

```javascript
    // GET /api/projects/summary - get summary data for all projects (portal cards)
    if (parts[1] === 'projects' && parts[2] === 'summary' && !parts[3]) {
      const configPath = path.join(MEMORY_ROOT, 'config.json');
      const config = JSON.parse(fs.readFileSync(configPath, 'utf8'));

      const projectSummaries = [];

      for (const project of config.projects) {
        const summary = {
          id: project.id,
          displayName: project.displayName,
          path: project.path,
          type: 'Unknown',
          health: { score: null, lastScan: null },
          stats: { files: 0, functions: 0 },
          lastActivity: null
        };

        // Detect project type
        const packagePath = path.join(project.path, 'package.json');
        if (fs.existsSync(packagePath)) {
          try {
            const pkg = JSON.parse(fs.readFileSync(packagePath, 'utf8'));
            if (pkg.dependencies?.['react-native'] || pkg.dependencies?.['expo']) {
              summary.type = 'React Native';
            } else if (pkg.dependencies?.next) {
              summary.type = 'Next.js';
            } else if (pkg.dependencies?.react) {
              summary.type = 'React';
            } else if (pkg.dependencies?.express) {
              summary.type = 'Express';
            } else {
              summary.type = 'Node.js';
            }
          } catch (e) {}
        }

        // Get health score
        const healthPath = path.join(MEMORY_ROOT, 'projects', project.id, 'health.json');
        if (fs.existsSync(healthPath)) {
          try {
            const health = JSON.parse(fs.readFileSync(healthPath, 'utf8'));
            summary.health.score = health.score;
            summary.health.lastScan = health.timestamp;
          } catch (e) {}
        }

        // Get stats
        const summariesPath = path.join(MEMORY_ROOT, 'projects', project.id, 'summaries.json');
        if (fs.existsSync(summariesPath)) {
          try {
            const summaries = JSON.parse(fs.readFileSync(summariesPath, 'utf8'));
            summary.stats.files = Object.keys(summaries.files || {}).length;
            summary.lastActivity = summaries.lastUpdated;
          } catch (e) {}
        }

        const functionsPath = path.join(MEMORY_ROOT, 'projects', project.id, 'functions.json');
        if (fs.existsSync(functionsPath)) {
          try {
            const functions = JSON.parse(fs.readFileSync(functionsPath, 'utf8'));
            summary.stats.functions = functions.totalFunctions || 0;
          } catch (e) {}
        }

        projectSummaries.push(summary);
      }

      res.end(JSON.stringify({ projects: projectSummaries }));
      return;
    }
```

**Step 2: Test the endpoint**

Run: `curl -s http://localhost:3333/api/projects/summary | head -c 500`
Expected: JSON with projects array

**Step 3: Commit**

```bash
cd /Users/jmelendez/.claude-memory
git add dashboard/server.js
git commit -m "feat(portal): add /api/projects/summary endpoint"
```

---

## Task 3: Add Portal HTML Structure

**Files:**
- Modify: `index.html:14-36` (header and container)

**Step 1: Update header with breadcrumb support**

Replace lines 14-23 with:

```html
  <!-- Header -->
  <div class="header">
    <div class="header-left">
      <h1 id="header-title">
        <a href="#/" class="header-home-link">
          <svg class="logo-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2z"/>
            <path d="M12 6v6l4 2"/>
          </svg>
          Claude Memory
        </a>
        <span id="breadcrumb-separator" class="breadcrumb-separator hidden"> › </span>
        <span id="breadcrumb-project" class="breadcrumb-project hidden"></span>
      </h1>
    </div>
    <div class="stats" id="stats">Loading...</div>
  </div>
```

**Step 2: Add portal container after header, before main container**

Add after line 23 (after header closing div):

```html
  <!-- Portal View -->
  <div id="portal-view" class="portal-container">
    <div class="portal-header">
      <h2>Your Projects</h2>
      <p>Select a project to explore its codebase</p>
    </div>
    <div id="portal-grid" class="portal-grid">
      <div class="loading">Loading projects...</div>
    </div>
  </div>
```

**Step 3: Add hidden class to main container**

Change the container div (around line 26) to:

```html
  <!-- Main Container (Project View) -->
  <div class="container hidden" id="project-view">
```

**Step 4: Remove sidebar from container**

Delete the entire sidebar div (lines 28-36 approximately):

```html
    <!-- Sidebar - DELETE THIS ENTIRE BLOCK -->
    <div class="sidebar">
      <h3>Projects</h3>
      <div id="projects">Loading...</div>
      <button class="sidebar-toggle" id="sidebar-toggle" title="Toggle Sidebar">
        ...
      </button>
    </div>
```

**Step 5: Verify HTML syntax**

Open in browser and check console for errors.

**Step 6: Commit**

```bash
cd /Users/jmelendez/.claude-memory
git add dashboard/index.html
git commit -m "feat(portal): add portal HTML structure and breadcrumb"
```

---

## Task 4: Add Portal CSS Styles

**Files:**
- Modify: `styles.css` (add at end of file)

**Step 1: Add portal and breadcrumb styles**

Add at end of styles.css:

```css
/* ==========================================
   PORTAL VIEW
   ========================================== */
.portal-container {
  padding: var(--spacing-xl);
  max-width: 1400px;
  margin: 0 auto;
}

.portal-header {
  text-align: center;
  margin-bottom: var(--spacing-xl);
}

.portal-header h2 {
  font-size: 28px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: var(--spacing-sm);
}

.portal-header p {
  color: var(--text-muted);
  font-size: 16px;
}

.portal-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: var(--spacing-lg);
}

/* Project Card */
.project-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-xl);
  padding: var(--spacing-lg);
  cursor: pointer;
  transition: all var(--transition-normal);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.project-card:hover {
  border-color: var(--accent-blue);
  transform: translateY(-4px);
  box-shadow: var(--shadow-lg);
}

.project-card-header {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-md);
}

.project-card-health {
  width: 56px;
  height: 56px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  font-weight: 700;
  flex-shrink: 0;
  border: 3px solid;
}

.project-card-health.good {
  background: rgba(63, 185, 80, 0.15);
  border-color: var(--accent-green);
  color: var(--accent-green);
}

.project-card-health.warning {
  background: rgba(210, 153, 34, 0.15);
  border-color: var(--warning);
  color: var(--warning);
}

.project-card-health.critical {
  background: rgba(248, 81, 73, 0.15);
  border-color: var(--error);
  color: var(--error);
}

.project-card-health.unknown {
  background: var(--bg-tertiary);
  border-color: var(--border-default);
  color: var(--text-muted);
  font-size: 14px;
}

.project-card-info {
  flex: 1;
  min-width: 0;
}

.project-card-name {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: var(--spacing-xs);
}

.project-card-type {
  display: inline-block;
  padding: 2px 8px;
  background: var(--bg-tertiary);
  border-radius: var(--radius-sm);
  font-size: 12px;
  color: var(--accent-cyan);
  font-weight: 500;
}

.project-card-stats {
  display: flex;
  gap: var(--spacing-lg);
  color: var(--text-muted);
  font-size: 13px;
}

.project-card-stats span {
  color: var(--text-secondary);
  font-weight: 500;
}

.project-card-activity {
  font-size: 12px;
  color: var(--text-subtle);
  padding-top: var(--spacing-sm);
  border-top: 1px solid var(--border-muted);
}

/* Breadcrumb Navigation */
.header-left {
  display: flex;
  align-items: center;
}

.header-home-link {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  color: var(--text-primary);
  text-decoration: none;
  transition: color var(--transition-fast);
}

.header-home-link:hover {
  color: var(--accent-blue);
}

.breadcrumb-separator {
  color: var(--text-muted);
  margin: 0 var(--spacing-xs);
}

.breadcrumb-project {
  color: var(--text-secondary);
  font-weight: 500;
}

/* Adjust main for full width (no sidebar) */
#project-view .main {
  width: 100%;
}

/* Responsive Portal */
@media (max-width: 767px) {
  .portal-container {
    padding: var(--spacing-md);
  }

  .portal-grid {
    grid-template-columns: 1fr;
  }

  .project-card-header {
    flex-direction: column;
    align-items: center;
    text-align: center;
  }

  .project-card-stats {
    justify-content: center;
  }
}
```

**Step 2: Remove sidebar CSS variables**

In :root (around line 63), remove:
```css
  /* Sidebar - REMOVE THESE LINES */
  --sidebar-width: 240px;
  --sidebar-collapsed-width: 60px;
```

**Step 3: Verify styles render correctly**

Open in browser and check portal layout.

**Step 4: Commit**

```bash
cd /Users/jmelendez/.claude-memory
git add dashboard/styles.css
git commit -m "feat(portal): add portal grid and card styles"
```

---

## Task 5: Implement Portal Rendering Logic

**Files:**
- Modify: `app.js` (replace loadProjects, add showPortal/showProject)

**Step 1: Replace loadProjects function**

Replace the existing `loadProjects` function (around line 63-88) with:

```javascript
async function loadProjectsSummary() {
  try {
    const res = await fetch('/api/projects/summary');
    const data = await res.json();
    allProjectsSummary = data.projects || [];
    return allProjectsSummary;
  } catch (e) {
    console.error('Failed to load projects summary:', e);
    return [];
  }
}

function renderPortalGrid(projects) {
  const grid = document.getElementById('portal-grid');

  if (!projects || projects.length === 0) {
    grid.innerHTML = '<div class="loading">No projects found</div>';
    return;
  }

  grid.innerHTML = projects.map(p => {
    const healthClass = p.health.score === null ? 'unknown' :
      p.health.score >= 80 ? 'good' :
      p.health.score >= 60 ? 'warning' : 'critical';
    const healthDisplay = p.health.score === null ? '?' : p.health.score;
    const lastActivity = p.lastActivity ? formatRelativeTime(p.lastActivity) : 'Never';

    return `
      <div class="project-card" data-id="${p.id}" onclick="navigateToProject('${p.id}')">
        <div class="project-card-header">
          <div class="project-card-health ${healthClass}">${healthDisplay}</div>
          <div class="project-card-info">
            <div class="project-card-name">${p.displayName}</div>
            <span class="project-card-type">${p.type}</span>
          </div>
        </div>
        <div class="project-card-stats">
          <div><span>${p.stats.files}</span> files</div>
          <div><span>${p.stats.functions.toLocaleString()}</span> functions</div>
        </div>
        <div class="project-card-activity">Last active: ${lastActivity}</div>
      </div>
    `;
  }).join('');
}

function formatRelativeTime(dateString) {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now - date;
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffDays === 0) return 'Today';
  if (diffDays === 1) return 'Yesterday';
  if (diffDays < 7) return `${diffDays} days ago`;
  if (diffDays < 30) return `${Math.floor(diffDays / 7)} weeks ago`;
  return date.toLocaleDateString();
}

function navigateToProject(projectId) {
  updateURL(`/project/${projectId}`);
  showProject(projectId);
}
```

**Step 2: Add showPortal and showProject functions**

Add after navigateToProject:

```javascript
async function showPortal() {
  currentView = 'portal';
  currentProject = null;

  // Update UI visibility
  document.getElementById('portal-view').classList.remove('hidden');
  document.getElementById('project-view').classList.add('hidden');

  // Update breadcrumb
  document.getElementById('breadcrumb-separator').classList.add('hidden');
  document.getElementById('breadcrumb-project').classList.add('hidden');

  // Load and render projects if not cached
  if (allProjectsSummary.length === 0) {
    await loadProjectsSummary();
  }
  renderPortalGrid(allProjectsSummary);

  updateURL('/');
}

async function showProject(projectId, tab = 'graph') {
  currentView = 'project';
  currentProject = projectId;

  // Update UI visibility
  document.getElementById('portal-view').classList.add('hidden');
  document.getElementById('project-view').classList.remove('hidden');

  // Update breadcrumb
  const project = allProjectsSummary.find(p => p.id === projectId);
  const projectName = project?.displayName || projectId;
  document.getElementById('breadcrumb-separator').classList.remove('hidden');
  document.getElementById('breadcrumb-project').classList.remove('hidden');
  document.getElementById('breadcrumb-project').textContent = projectName;

  // Update context-aware tabs
  updateTabsForProject(projectId);

  // Load project data
  projectData = {};

  try {
    const [graph, summaries, functions, schema] = await Promise.all([
      fetch(`/api/projects/${projectId}/graph`).then(r => r.json()).catch(() => null),
      fetch(`/api/projects/${projectId}/summaries`).then(r => r.json()).catch(() => null),
      fetch(`/api/projects/${projectId}/functions`).then(r => r.json()).catch(() => null),
      fetch(`/api/projects/${projectId}/schema`).then(r => r.json()).catch(() => null)
    ]);

    projectData = { graph, summaries, functions, schema };

    // Activate requested tab
    const tabButton = document.querySelector(`.tab[data-tab="${tab}"]`);
    if (tabButton && !tabButton.classList.contains('hidden')) {
      tabButton.click();
    } else {
      document.querySelector('.tab[data-tab="graph"]').click();
    }
  } catch (e) {
    console.error('Error loading project data:', e);
  }

  updateURL(`/project/${projectId}`);
}

function updateTabsForProject(projectId) {
  const pixelArtTab = document.querySelector('.tab[data-tab="pixelart"]');
  if (pixelArtTab) {
    // Only show Pixel Art tab for CodeTale project
    if (projectId === 'codetale') {
      pixelArtTab.classList.remove('hidden');
    } else {
      pixelArtTab.classList.add('hidden');
    }
  }
}
```

**Step 3: Verify no syntax errors**

Run: `node --check /Users/jmelendez/.claude-memory/dashboard/app.js`
Expected: No output (success)

**Step 4: Commit**

```bash
cd /Users/jmelendez/.claude-memory
git add dashboard/app.js
git commit -m "feat(portal): implement portal rendering and navigation"
```

---

## Task 6: Update Initialization

**Files:**
- Modify: `app.js` (init section at bottom)

**Step 1: Find and update the DOMContentLoaded handler**

Find the initialization code (usually at the end) and update it:

```javascript
// ==========================================
// INITIALIZATION
// ==========================================
document.addEventListener('DOMContentLoaded', async () => {
  // Load stats for header
  loadStats();

  // Initialize tabs
  initTabs();

  // Load project summaries for portal
  await loadProjectsSummary();

  // Initialize router (handles showing portal or project based on URL)
  initRouter();
});
```

**Step 2: Remove old sidebar and selectProject initialization**

Find and remove these lines if they exist in init:
- `initSidebar();`
- `loadProjects();`
- Any call to `selectProject()`

**Step 3: Test the full flow**

1. Open http://localhost:3333 - should show portal
2. Click a project card - should navigate to project view
3. Click "Claude Memory" in breadcrumb - should return to portal
4. Browser back button should work

**Step 4: Commit**

```bash
cd /Users/jmelendez/.claude-memory
git add dashboard/app.js
git commit -m "feat(portal): update initialization for portal-first flow"
```

---

## Task 7: Clean Up Removed Sidebar Code

**Files:**
- Modify: `app.js` (remove sidebar functions)
- Modify: `styles.css` (remove sidebar styles)

**Step 1: Remove initSidebar function from app.js**

Delete the entire initSidebar function (lines 27-44 approximately):

```javascript
// DELETE THIS FUNCTION
function initSidebar() {
  const sidebar = document.querySelector('.sidebar');
  const toggle = document.getElementById('sidebar-toggle');
  // ...
}
```

**Step 2: Remove sidebar styles from styles.css**

Delete lines 131-265 (the entire SIDEBAR section):

```css
/* ==========================================
   SIDEBAR - DELETE THIS ENTIRE SECTION
   ========================================== */
.sidebar {
  ...
}
// ... all the way through .sidebar.collapsed rules
```

**Step 3: Verify no JavaScript errors**

Open browser console, check for errors.

**Step 4: Commit**

```bash
cd /Users/jmelendez/.claude-memory
git add dashboard/app.js dashboard/styles.css
git commit -m "chore(portal): remove sidebar code"
```

---

## Task 8: Final Testing and Polish

**Files:**
- All modified files

**Step 1: Test portal view**

1. Navigate to http://localhost:3333
2. Verify project cards display with:
   - Health score (or ? for unknown)
   - Project name and type badge
   - File/function counts
   - Last activity

**Step 2: Test project view**

1. Click a project card
2. Verify breadcrumb shows "Claude Memory > [Project Name]"
3. Verify all tabs work
4. Verify Pixel Art tab only shows for CodeTale

**Step 3: Test navigation**

1. Click "Claude Memory" in breadcrumb - returns to portal
2. Browser back button - returns to portal
3. Direct URL http://localhost:3333/#/project/gyst - opens GYST

**Step 4: Test responsive design**

1. Resize browser to mobile width
2. Verify portal cards stack vertically
3. Verify project view tabs scroll horizontally

**Step 5: Final commit**

```bash
cd /Users/jmelendez/.claude-memory
git add -A
git commit -m "feat(portal): complete portal redesign implementation"
```

---

## Summary of Changes

| File | Changes |
|------|---------|
| `index.html` | Added portal container, breadcrumb header, removed sidebar |
| `app.js` | Added view state, URL routing, portal rendering, context-aware tabs |
| `styles.css` | Added portal/card styles, removed sidebar styles |
| `server.js` | Added `/api/projects/summary` endpoint |

## Rollback

If issues occur, revert with:
```bash
git revert HEAD~8..HEAD
```
