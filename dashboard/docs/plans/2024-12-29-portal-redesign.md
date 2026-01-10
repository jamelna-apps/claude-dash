# Claude Memory Portal Redesign

## Overview

Transform the Claude Memory dashboard from a project-context-first view into a **project portal** - a landing page that shows all projects at a glance, with drill-down into individual project views.

## Goals

1. **Portal landing page** - Project cards grid as the home view
2. **Project-specific context** - All project tools grouped when inside a project
3. **Context-aware tabs** - Show/hide tabs based on project (e.g., Pixel Art for CodeTale only)
4. **Cleaner navigation** - Remove sidebar, use breadcrumbs for back navigation

## Design

### Portal Landing Page

When opening the dashboard, users see a project cards grid.

**Layout:**
- Header: "Claude Memory" logo and title
- Main area: Responsive grid of project cards (2-3 columns)
- No sidebar on landing page

**Project Card Contents:**
- Project name (e.g., "GYST", "CodeTale")
- Project type badge (React Native, Next.js)
- Health score - circular indicator with color (green/yellow/red)
- Last activity timestamp
- Quick stats - file count, function count (subtle)

**Interactions:**
- Hover: subtle lift/glow effect
- Click: navigate to full project view

### Project View

Full-screen project context with tabs.

**Header:**
- Breadcrumb: "Claude Memory › GYST"
- "Claude Memory" clickable → returns to portal
- Project stats bar below breadcrumb

**Navigation:**
- Sidebar removed (portal replaces project switching)
- Tabs remain as primary in-project navigation
- Browser back button works (history routing)

**Context-Aware Tabs:**

| Tab | All Projects | CodeTale Only |
|-----|--------------|---------------|
| Graph | ✓ | ✓ |
| Files | ✓ | ✓ |
| Functions | ✓ | ✓ |
| Schema | ✓ | ✓ |
| Health | ✓ | ✓ |
| Ask | ✓ | ✓ |
| Features | ✓ | ✓ |
| Wireframe | ✓ | ✓ |
| Sessions | ✓ | ✓ |
| Keys | ✓ | ✓ |
| Pixel Art | - | ✓ |

## Implementation

### State Management

```javascript
// New state variables
let currentView = 'portal'; // 'portal' | 'project'
let selectedProject = null;

// View switching
function showPortal() {
  currentView = 'portal';
  selectedProject = null;
  renderPortal();
  updateURL('/');
}

function showProject(projectId) {
  currentView = 'project';
  selectedProject = projectId;
  renderProjectView();
  updateURL(`/project/${projectId}`);
}
```

### URL Structure

- `/` → Portal landing
- `/project/{id}` → Project view
- `/project/{id}/{tab}` → Project view with specific tab

### Data Loading

**Portal:**
- Load summary data for all projects
- Health scores from cached/last scan
- Last activity from session data
- Keep lightweight for fast loading

**Project View:**
- Load full project data on entry
- Same behavior as current implementation

### Files to Modify

1. **index.html**
   - Add portal container markup
   - Add project card template
   - Update header for breadcrumb support
   - Remove sidebar markup

2. **app.js**
   - Add portal rendering logic
   - Add view state management
   - Add URL routing (hash-based)
   - Add context-aware tab filtering
   - Add project summary fetching
   - Remove sidebar logic

3. **styles.css**
   - Add portal grid styles
   - Add project card styles
   - Add breadcrumb styles
   - Remove sidebar styles
   - Adjust main content for full width

4. **server.js**
   - Add `/api/projects/summary` endpoint
   - Returns aggregated data for all projects

### What Gets Removed

- Sidebar element and all related styles
- Sidebar toggle button
- Project list in sidebar
- Sidebar state management code

## API Changes

### New Endpoint: GET /api/projects/summary

Returns summary data for all projects:

```json
{
  "projects": [
    {
      "id": "gyst",
      "displayName": "GYST",
      "type": "React Native",
      "health": {
        "score": 85,
        "lastScan": "2024-12-27T20:24:00Z"
      },
      "stats": {
        "files": 244,
        "functions": 1250
      },
      "lastActivity": "2024-12-29T10:43:00Z"
    }
  ]
}
```

## Visual Design

### Project Cards

```
┌─────────────────────────────┐
│  ┌───┐                      │
│  │ 85│  GYST                │
│  └───┘  React Native        │
│                             │
│  244 files · 1.2k functions │
│  Last active: 2 days ago    │
└─────────────────────────────┘
```

### Breadcrumb Navigation

```
┌──────────────────────────────────────────────┐
│ ⏱ Claude Memory › GYST                       │
│ ─────────────────────────────────────────────│
│ [Graph] [Files] [Functions] ...              │
└──────────────────────────────────────────────┘
```

## Migration Notes

- Existing bookmarks to `/#/` will show portal
- Direct project links will still work via URL routing
- No data migration needed - uses existing memory files
