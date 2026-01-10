# Beads + Claude Memory Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Integrate Beads git-backed task tracking with claude-memory for unified project context

**Architecture:** Two-layer system - per-project `.beads/` directories (git-tracked) + global index at `~/.claude-memory/tasks-index.json`. Session startup loads both Beads tasks and code intelligence.

**Tech Stack:** Beads CLI (`bd`), Node.js, existing claude-memory infrastructure

---

## Task 1: Install Beads CLI

**Files:**
- None (CLI installation)

**Step 1: Install Beads globally**

Run:
```bash
npm install -g @beads/bd
```

**Step 2: Verify installation**

Run:
```bash
bd --version
```
Expected: Version number displayed

**Step 3: Document installation in claude-memory**

No commit needed - this is environment setup.

---

## Task 2: Initialize Beads in GYST Project

**Files:**
- Create: `/Users/jmelendez/Documents/Projects/WardrobeApp/.beads/` (directory)

**Step 1: Initialize Beads**

Run:
```bash
cd /Users/jmelendez/Documents/Projects/WardrobeApp
bd init
```
Expected: `.beads/` directory created

**Step 2: Verify initialization**

Run:
```bash
ls -la .beads/
```
Expected: Beads files present

**Step 3: Add to git**

Run:
```bash
cd /Users/jmelendez/Documents/Projects/WardrobeApp
git add .beads/
git commit -m "chore: initialize Beads task tracking"
```

---

## Task 3: Initialize Beads in Other Projects

**Files:**
- Create: `.beads/` in each project

**Step 1: Initialize in CodeTale**

Run:
```bash
cd /Users/jmelendez/Documents/Projects/codetale
bd init
git add .beads/ && git commit -m "chore: initialize Beads task tracking"
```

**Step 2: Initialize in remaining projects**

Run for each:
```bash
cd /Users/jmelendez/Documents/Projects/gyst-seller-portal
bd init
git add .beads/ && git commit -m "chore: initialize Beads task tracking"

cd /Users/jmelendez/Documents/Projects/jamelna
bd init
git add .beads/ && git commit -m "chore: initialize Beads task tracking"

cd /Users/jmelendez/Documents/Projects/smartiegoals
bd init
git add .beads/ && git commit -m "chore: initialize Beads task tracking"

cd /Users/jmelendez/Documents/Projects/spread-your-ashes
bd init
git add .beads/ && git commit -m "chore: initialize Beads task tracking"
```

---

## Task 4: Create Global Tasks Index Structure

**Files:**
- Create: `~/.claude-memory/tasks-index.json`

**Step 1: Create initial index structure**

Create file `~/.claude-memory/tasks-index.json`:
```json
{
  "version": 1,
  "lastUpdated": null,
  "projects": {}
}
```

**Step 2: Verify file created**

Run:
```bash
cat ~/.claude-memory/tasks-index.json
```
Expected: JSON structure displayed

---

## Task 5: Add Task Loading to MLX Tools

**Files:**
- Modify: `~/.claude-memory/mlx-tools/mlx`

**Step 1: Read current mlx script**

Read the file to understand current structure.

**Step 2: Add `tasks` subcommand**

Add to the mlx script a new subcommand handler:

```bash
# In the case statement, add:
tasks)
    shift
    project="$1"
    if [ -z "$project" ]; then
        echo "Usage: mlx tasks <project>"
        exit 1
    fi

    # Get project path from config
    project_path=$(jq -r ".projects[] | select(.id == \"$project\") | .path" ~/.claude-memory/config.json)

    if [ -z "$project_path" ] || [ "$project_path" = "null" ]; then
        echo "Project not found: $project"
        exit 1
    fi

    beads_dir="$project_path/.beads"

    if [ ! -d "$beads_dir" ]; then
        echo "Beads not initialized in $project. Run: cd $project_path && bd init"
        exit 1
    fi

    echo "=== Active Tasks for $project ==="
    cd "$project_path" && bd ready
    ;;
```

**Step 3: Test the command**

Run:
```bash
~/.claude-memory/mlx-tools/mlx tasks gyst
```
Expected: Shows active tasks or "no tasks" message

**Step 4: Commit**

```bash
cd ~/.claude-memory
git add mlx-tools/mlx
git commit -m "feat: add tasks subcommand to mlx"
```

---

## Task 6: Create Task Sync Script

**Files:**
- Create: `~/.claude-memory/mlx-tools/sync-tasks.js`

**Step 1: Write the sync script**

Create file `~/.claude-memory/mlx-tools/sync-tasks.js`:
```javascript
#!/usr/bin/env node

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const CONFIG_PATH = path.join(process.env.HOME, '.claude-memory/config.json');
const INDEX_PATH = path.join(process.env.HOME, '.claude-memory/tasks-index.json');

function loadConfig() {
    return JSON.parse(fs.readFileSync(CONFIG_PATH, 'utf8'));
}

function loadIndex() {
    if (!fs.existsSync(INDEX_PATH)) {
        return { version: 1, lastUpdated: null, projects: {} };
    }
    return JSON.parse(fs.readFileSync(INDEX_PATH, 'utf8'));
}

function saveIndex(index) {
    index.lastUpdated = new Date().toISOString();
    fs.writeFileSync(INDEX_PATH, JSON.stringify(index, null, 2));
}

function getProjectTasks(projectPath) {
    const beadsDir = path.join(projectPath, '.beads');
    if (!fs.existsSync(beadsDir)) {
        return null;
    }

    try {
        const output = execSync('bd ready --json 2>/dev/null || echo "[]"', {
            cwd: projectPath,
            encoding: 'utf8'
        });
        return JSON.parse(output);
    } catch (e) {
        // bd ready without --json, parse text output
        try {
            const output = execSync('bd ready 2>/dev/null || echo ""', {
                cwd: projectPath,
                encoding: 'utf8'
            });
            // Return count from text output
            const lines = output.trim().split('\n').filter(l => l.startsWith('bd-'));
            return { count: lines.length, initialized: true };
        } catch (e2) {
            return { count: 0, initialized: true };
        }
    }
}

function syncAllProjects() {
    const config = loadConfig();
    const index = loadIndex();

    console.log('Syncing tasks from all projects...\n');

    for (const project of config.projects || []) {
        const tasks = getProjectTasks(project.path);

        if (tasks === null) {
            console.log(`${project.id}: Beads not initialized`);
            index.projects[project.id] = { initialized: false };
        } else {
            const count = tasks.count || (Array.isArray(tasks) ? tasks.length : 0);
            console.log(`${project.id}: ${count} active task(s)`);
            index.projects[project.id] = {
                initialized: true,
                activeCount: count,
                lastSync: new Date().toISOString()
            };
        }
    }

    saveIndex(index);
    console.log('\nIndex updated:', INDEX_PATH);
}

syncAllProjects();
```

**Step 2: Make executable**

Run:
```bash
chmod +x ~/.claude-memory/mlx-tools/sync-tasks.js
```

**Step 3: Test the script**

Run:
```bash
node ~/.claude-memory/mlx-tools/sync-tasks.js
```
Expected: Lists projects with task counts, updates index

**Step 4: Commit**

```bash
cd ~/.claude-memory
git add mlx-tools/sync-tasks.js tasks-index.json
git commit -m "feat: add task sync script for global index"
```

---

## Task 7: Update Session Startup Hook

**Files:**
- Modify: `~/.claude/hooks/load-memory.sh` (or equivalent session hook)

**Step 1: Read current hook**

Read the session startup hook to understand current behavior.

**Step 2: Add task loading**

Add to the hook after existing memory loading:

```bash
# Load Beads tasks if available
if [ -n "$PROJECT_ID" ]; then
    project_path=$(jq -r ".projects[] | select(.id == \"$PROJECT_ID\") | .path" ~/.claude-memory/config.json)
    if [ -d "$project_path/.beads" ]; then
        echo ""
        echo "=== Active Tasks ==="
        cd "$project_path" && bd ready 2>/dev/null || echo "No active tasks"
    fi
fi
```

**Step 3: Test the hook**

Start a new session and verify tasks are displayed.

**Step 4: Commit**

```bash
cd ~/.claude
git add hooks/load-memory.sh
git commit -m "feat: add Beads task loading to session startup"
```

---

## Task 8: Add Tasks Endpoint to Dashboard Server

**Files:**
- Modify: `~/.claude-memory/dashboard/server.js`

**Step 1: Read current server.js**

Read the file to find where to add the endpoint.

**Step 2: Add /api/projects/:id/tasks endpoint**

Add after existing endpoints:

```javascript
// Get tasks for a specific project
app.get('/api/projects/:projectId/tasks', async (req, res) => {
    try {
        const { projectId } = req.params;
        const config = JSON.parse(fs.readFileSync(
            path.join(MEMORY_BASE, 'config.json'), 'utf8'
        ));

        const project = config.projects?.find(p => p.id === projectId);
        if (!project) {
            return res.status(404).json({ error: 'Project not found' });
        }

        const beadsDir = path.join(project.path, '.beads');
        if (!fs.existsSync(beadsDir)) {
            return res.json({
                initialized: false,
                tasks: [],
                message: 'Beads not initialized'
            });
        }

        // Get tasks using bd command
        try {
            const output = execSync('bd ready 2>/dev/null || echo ""', {
                cwd: project.path,
                encoding: 'utf8',
                timeout: 5000
            });

            const lines = output.trim().split('\n').filter(l => l.trim());
            const tasks = lines.map(line => {
                // Parse bd ready output format: "bd-xxxx: Title"
                const match = line.match(/^(bd-[\w.]+):\s*(.+)$/);
                if (match) {
                    return { id: match[1], title: match[2] };
                }
                return { id: 'unknown', title: line };
            }).filter(t => t.id.startsWith('bd-'));

            res.json({
                initialized: true,
                tasks: tasks,
                count: tasks.length
            });
        } catch (e) {
            res.json({
                initialized: true,
                tasks: [],
                count: 0
            });
        }
    } catch (error) {
        console.error('Error fetching tasks:', error);
        res.status(500).json({ error: error.message });
    }
});
```

**Step 3: Add execSync import if needed**

At top of file, ensure:
```javascript
const { execSync } = require('child_process');
```

**Step 4: Test the endpoint**

Run:
```bash
curl http://localhost:3333/api/projects/gyst/tasks
```
Expected: JSON with tasks array

**Step 5: Commit**

```bash
cd ~/.claude-memory/dashboard
git add server.js
git commit -m "feat: add /api/projects/:id/tasks endpoint"
```

---

## Task 9: Add Task Count to Portal Cards

**Files:**
- Modify: `~/.claude-memory/dashboard/app.js`

**Step 1: Read current portal rendering**

Find the `renderPortal()` function.

**Step 2: Update project summary fetch to include tasks**

In the `/api/projects/summary` response handling or card rendering, add task count:

```javascript
// In createProjectCard or similar function
async function getTaskCount(projectId) {
    try {
        const response = await fetch(`/api/projects/${projectId}/tasks`);
        const data = await response.json();
        return data.count || 0;
    } catch (e) {
        return 0;
    }
}

// In card HTML, add task count display
<div class="card-tasks">${taskCount} task${taskCount !== 1 ? 's' : ''}</div>
```

**Step 3: Add CSS for task count**

In styles.css:
```css
.card-tasks {
    font-size: 0.85rem;
    color: var(--text-secondary);
    margin-top: 0.25rem;
}

.card-tasks:not(:empty)::before {
    content: "📋 ";
}
```

**Step 4: Test portal**

Open dashboard, verify task counts appear on cards.

**Step 5: Commit**

```bash
cd ~/.claude-memory/dashboard
git add app.js styles.css
git commit -m "feat: display task count on portal project cards"
```

---

## Task 10: Add Tasks Tab to Project View

**Files:**
- Modify: `~/.claude-memory/dashboard/index.html`
- Modify: `~/.claude-memory/dashboard/app.js`
- Modify: `~/.claude-memory/dashboard/styles.css`

**Step 1: Add Tasks tab button**

In index.html, add to tabs section:
```html
<button class="tab-btn" data-tab="tasks">Tasks</button>
```

**Step 2: Add Tasks tab content container**

In index.html:
```html
<div id="tasks-tab" class="tab-content hidden">
    <div class="tasks-header">
        <h2>Active Tasks</h2>
        <button id="refresh-tasks" class="btn btn-secondary">Refresh</button>
    </div>
    <div id="tasks-list" class="tasks-list">
        <div class="loading">Loading tasks...</div>
    </div>
</div>
```

**Step 3: Add task rendering logic**

In app.js, add:
```javascript
async function loadTasks() {
    const container = document.getElementById('tasks-list');
    container.innerHTML = '<div class="loading">Loading tasks...</div>';

    try {
        const response = await fetch(`/api/projects/${selectedProject}/tasks`);
        const data = await response.json();

        if (!data.initialized) {
            container.innerHTML = `
                <div class="empty-state">
                    <p>Beads not initialized in this project.</p>
                    <code>cd ${selectedProject} && bd init</code>
                </div>
            `;
            return;
        }

        if (data.tasks.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <p>No active tasks.</p>
                    <code>bd create "Your task title"</code>
                </div>
            `;
            return;
        }

        container.innerHTML = data.tasks.map(task => `
            <div class="task-item">
                <span class="task-id">${task.id}</span>
                <span class="task-title">${task.title}</span>
            </div>
        `).join('');
    } catch (error) {
        container.innerHTML = `<div class="error">Error loading tasks: ${error.message}</div>`;
    }
}

// Add to tab switching logic
if (tab === 'tasks') {
    loadTasks();
}
```

**Step 4: Add CSS for tasks tab**

In styles.css:
```css
.tasks-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 1rem;
}

.tasks-list {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
}

.task-item {
    display: flex;
    gap: 1rem;
    padding: 0.75rem 1rem;
    background: var(--bg-secondary);
    border-radius: 6px;
    border: 1px solid var(--border);
}

.task-id {
    font-family: monospace;
    color: var(--accent);
    font-size: 0.9rem;
}

.task-title {
    flex: 1;
}
```

**Step 5: Test Tasks tab**

Open dashboard, navigate to project, click Tasks tab.

**Step 6: Commit**

```bash
cd ~/.claude-memory/dashboard
git add index.html app.js styles.css
git commit -m "feat: add Tasks tab to project view"
```

---

## Task 11: Final Testing

**Step 1: Test full workflow**

1. Open dashboard at http://localhost:3333
2. Verify portal shows task counts on cards
3. Click into a project
4. Click Tasks tab, verify tasks load
5. Create a task: `cd WardrobeApp && bd create "Test task"`
6. Refresh Tasks tab, verify new task appears

**Step 2: Test session startup**

Start a new Claude session in a project directory, verify tasks are displayed.

**Step 3: Test sync script**

Run:
```bash
node ~/.claude-memory/mlx-tools/sync-tasks.js
cat ~/.claude-memory/tasks-index.json
```
Verify all projects are indexed.

---

## Summary

| Task | Description | Key Files |
|------|-------------|-----------|
| 1 | Install Beads CLI | (environment) |
| 2 | Init Beads in GYST | WardrobeApp/.beads/ |
| 3 | Init Beads in other projects | */.beads/ |
| 4 | Create global index | tasks-index.json |
| 5 | Add mlx tasks command | mlx-tools/mlx |
| 6 | Create sync script | mlx-tools/sync-tasks.js |
| 7 | Update session hook | hooks/load-memory.sh |
| 8 | Add tasks API endpoint | dashboard/server.js |
| 9 | Add task count to portal | dashboard/app.js |
| 10 | Add Tasks tab | dashboard/*.* |
| 11 | Final testing | (verification) |
