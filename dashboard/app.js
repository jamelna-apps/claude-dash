/**
 * Claude Dash - Dashboard App
 * Frontend JavaScript for the dashboard UI
 */

// State
let projects = [];
let currentProject = null;
let currentProjectData = null;
let ollamaAvailable = false;

// DOM ready
document.addEventListener('DOMContentLoaded', init);

async function init() {
  console.log('Initializing dashboard...');

  // Setup routing
  window.addEventListener('hashchange', handleRoute);

  // Load initial data
  await Promise.all([
    loadProjects(),
    checkOllamaStatus()
  ]);

  // Setup tab handlers
  setupTabHandlers();

  // Handle initial route
  handleRoute();

  // Refresh Ollama status periodically
  setInterval(checkOllamaStatus, 30000);
}

// Tab handling
function setupTabHandlers() {
  document.querySelectorAll('.tab[data-tab]').forEach(tab => {
    tab.addEventListener('click', () => {
      const tabName = tab.dataset.tab;
      showTab(tabName);
    });
  });
}

function showTab(tabName) {
  // Update tab buttons
  document.querySelectorAll('.tab[data-tab]').forEach(t => {
    t.classList.toggle('active', t.dataset.tab === tabName);
  });

  // Update tab content
  document.querySelectorAll('.tab-content').forEach(content => {
    content.classList.add('hidden');
  });

  const tabContent = document.getElementById(`tab-${tabName}`);
  if (tabContent) {
    tabContent.classList.remove('hidden');
    loadTabContent(tabName);
  }
}

async function loadTabContent(tabName) {
  if (!currentProjectData) return;

  switch (tabName) {
    case 'code':
      renderCode();
      break;
    case 'architecture':
      renderArchitecture();
      break;
    case 'schema':
      renderSchema();
      break;
    case 'health':
      renderHealth();
      break;
    case 'ask':
      setupAskTab();
      break;
    case 'features':
      renderFeatures();
      break;
  }
}

// Routing
function handleRoute() {
  const hash = window.location.hash || '#/';
  const match = hash.match(/^#\/project\/(.+)$/);

  if (match) {
    const projectId = match[1];
    showProjectView(projectId);
  } else {
    showPortalView();
  }
}

// Portal View (Home)
function showPortalView() {
  const portal = document.getElementById('portal-view');
  const projectView = document.getElementById('project-view');

  if (portal) portal.classList.remove('hidden');
  if (projectView) projectView.classList.add('hidden');

  updateBreadcrumb(null);
  renderProjectsGrid();
}

function showPortalTab(tab, btn) {
  document.querySelectorAll('.portal-tab').forEach(t => t.classList.remove('active'));
  if (btn) btn.classList.add('active');

  const portalGrid = document.getElementById('portal-grid');
  const kbView = document.getElementById('knowledge-base-view');
  const reportsView = document.getElementById('reports-view');
  const ollamaAccess = document.getElementById('ollama-quick-access');

  [portalGrid, kbView, reportsView].forEach(el => el?.classList.add('hidden'));

  if (tab === 'projects') {
    portalGrid?.classList.remove('hidden');
    ollamaAccess?.classList.remove('hidden');
    renderProjectsGrid();
  } else if (tab === 'knowledge-base') {
    kbView?.classList.remove('hidden');
    ollamaAccess?.classList.add('hidden');
  } else if (tab === 'reports') {
    reportsView?.classList.remove('hidden');
    ollamaAccess?.classList.add('hidden');
    loadEfficiencyData();
  }
}

function renderProjectsGrid() {
  const grid = document.getElementById('portal-grid');
  if (!grid) return;

  if (projects.length === 0) {
    grid.innerHTML = '<div class="loading">No projects found</div>';
    return;
  }

  grid.innerHTML = projects.map(p => `
    <a href="#/project/${p.id}" class="project-card">
      <div class="project-card-header">
        <div class="project-card-health ${getHealthClass(p)}" title="Health Score">
          ${p.healthScore || '--'}
        </div>
        <div class="project-card-info">
          <div class="project-card-name">${escapeHtml(p.displayName)}</div>
          <span class="project-card-type">${getProjectType(p)}</span>
        </div>
      </div>
      <div class="project-card-stats">
        <span>${p.fileCount || 0} files</span>
        <span>${formatDate(p.lastScanned)}</span>
      </div>
      <div class="project-card-activity">
        Last updated ${formatDate(p.lastScanned)}
      </div>
    </a>
  `).join('');
}

function getHealthClass(project) {
  const score = project.healthScore;
  if (!score) return 'unknown';
  if (score >= 80) return 'good';
  if (score >= 60) return 'warning';
  return 'critical';
}

function getProjectType(project) {
  const path = project.path.toLowerCase();
  if (path.includes('android')) return 'Android';
  if (path.includes('wardrobe') || path.includes('gyst')) return 'React Native';
  if (path.includes('seller-portal') || path.includes('next')) return 'Next.js';
  if (path.includes('jamelna') || path.includes('smartie') || path.includes('spread')) return 'Next.js';
  if (path.includes('conductor')) return 'TypeScript';
  if (path.includes('codetale')) return 'Next.js';
  if (path.includes('folio')) return 'Swift';
  return 'Project';
}

// Project View
async function showProjectView(projectId) {
  currentProject = projects.find(p => p.id === projectId);
  if (!currentProject) {
    window.location.hash = '#/';
    return;
  }

  const portal = document.getElementById('portal-view');
  const projectView = document.getElementById('project-view');

  if (portal) portal.classList.add('hidden');
  if (projectView) projectView.classList.remove('hidden');

  updateBreadcrumb(currentProject);

  // Load project data
  try {
    currentProjectData = await fetch(`/api/project?id=${projectId}`).then(r => r.json());
    // Show first tab (code)
    showTab('code');
  } catch (e) {
    console.error('Failed to load project:', e);
  }
}

// Tab content renderers - Combined Code Tab (Files + Functions)
let currentCodeView = 'files';

function renderCode() {
  const codeList = document.getElementById('code-list');
  const codeStats = document.getElementById('code-stats');
  const searchBox = document.getElementById('code-search');

  if (!codeList || !currentProjectData) return;

  // Update stats
  const files = currentProjectData.index?.fileIndex || [];
  const totalFunctions = currentProjectData.functions?.totalFunctions || 0;

  if (codeStats) {
    codeStats.innerHTML = `<span style="color: var(--text-muted); font-size: 13px;">${files.length} files, ${totalFunctions} functions</span>`;
  }

  // Set up search
  if (searchBox && !searchBox.dataset.bound) {
    searchBox.dataset.bound = 'true';
    searchBox.oninput = () => {
      if (currentCodeView === 'files') {
        renderCodeFiles(searchBox.value);
      } else {
        renderCodeFunctions(searchBox.value);
      }
    };
  }

  // Render based on current view
  if (currentCodeView === 'files') {
    renderCodeFiles(searchBox?.value || '');
  } else {
    renderCodeFunctions(searchBox?.value || '');
  }
}

function renderCodeFiles(filter = '') {
  const codeList = document.getElementById('code-list');
  if (!codeList || !currentProjectData) return;

  const files = currentProjectData.index?.fileIndex || [];
  const summaries = currentProjectData.summaries || {};
  const filterLower = filter.toLowerCase();

  const filtered = filter
    ? files.filter(f => (f.path || '').toLowerCase().includes(filterLower))
    : files;

  if (filtered.length === 0) {
    codeList.innerHTML = '<div class="empty-state">No files found</div>';
    return;
  }

  codeList.innerHTML = filtered.slice(0, 200).map(file => {
    const filePath = file.path || file;
    const summary = summaries[filePath];
    return `
      <div class="file-item">
        <div class="path">${escapeHtml(filePath)}</div>
        ${summary?.purpose ? `<div class="summary">${escapeHtml(summary.purpose)}</div>` : ''}
        <div class="meta">${file.type || 'file'}${file.size ? ` · ${formatSize(file.size)}` : ''}</div>
      </div>
    `;
  }).join('');
}

function renderCodeFunctions(filter = '') {
  const codeList = document.getElementById('code-list');
  if (!codeList || !currentProjectData) return;

  // Functions are nested: { functions: { funcName: [{file, line}, ...] } }
  const functionsData = currentProjectData.functions?.functions || {};
  const filterLower = filter.toLowerCase();

  let allFuncs = [];
  for (const [funcName, locations] of Object.entries(functionsData)) {
    if (Array.isArray(locations)) {
      for (const loc of locations) {
        allFuncs.push({ name: funcName, ...loc });
      }
    }
  }

  const filtered = filter
    ? allFuncs.filter(f => f.name?.toLowerCase().includes(filterLower) || f.file?.toLowerCase().includes(filterLower))
    : allFuncs;

  if (filtered.length === 0) {
    codeList.innerHTML = '<div class="empty-state">No functions found</div>';
    return;
  }

  codeList.innerHTML = filtered.slice(0, 300).map(func => `
    <div class="func-item">
      <span class="func-name">${escapeHtml(func.name || 'anonymous')}</span>
      <span class="func-location">${escapeHtml(func.file || '')}${func.line ? `:${func.line}` : ''}</span>
    </div>
  `).join('');
}

window.setCodeView = function(view) {
  currentCodeView = view;
  // Update toggle buttons
  document.querySelectorAll('[data-code-view]').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.codeView === view);
  });
  // Re-render
  const searchBox = document.getElementById('code-search');
  if (view === 'files') {
    renderCodeFiles(searchBox?.value || '');
  } else {
    renderCodeFunctions(searchBox?.value || '');
  }
};

// Combined Architecture Tab (Graph + Screen Map)
let currentArchView = 'graph';

function renderArchitecture() {
  if (currentArchView === 'graph') {
    renderGraph();
  } else {
    renderScreenMap();
  }
}

function renderScreenMap() {
  const content = document.getElementById('architecture-content');
  if (!content || !currentProjectData) return;

  const graph = currentProjectData.graph;
  // screenNavigation is a dict: { screenName: { path, navigatesTo: [...], reachableFrom: [...] } }
  const screenNav = graph?.screenNavigation || {};
  const screenEntries = Object.entries(screenNav);

  if (screenEntries.length === 0) {
    content.innerHTML = `
      <div class="empty-state" style="padding: 40px; text-align: center; color: var(--text-muted);">
        <p>No screen navigation data found</p>
        <p style="font-size: 13px; margin-top: 8px;">Screen data is extracted from React Native navigation</p>
      </div>
    `;
    return;
  }

  content.innerHTML = `
    <div style="display: grid; grid-template-columns: 1fr 280px; gap: 16px; height: 500px;">
      <div id="screen-graph" class="graph-container" style="background: var(--bg-primary); border-radius: 8px;"></div>
      <div style="overflow-y: auto; background: var(--bg-secondary); border-radius: 8px; padding: 16px;">
        <h4 style="margin-bottom: 12px; color: var(--text-primary);">Screens (${screenEntries.length})</h4>
        <div class="file-list" style="max-height: 420px; overflow-y: auto;">
          ${screenEntries.map(([name, info]) => `
            <div class="file-item" onclick="showScreenInfo('${escapeHtml(name)}')" style="cursor: pointer;">
              <div class="path">${escapeHtml(name.replace(/Screen$/, ''))}</div>
              <div class="meta">${info.navigatesTo?.length || 0} outgoing links</div>
            </div>
          `).join('')}
        </div>
      </div>
    </div>
  `;

  // Render screen navigation graph
  if (typeof vis !== 'undefined') {
    // Build nodes from all screen names
    const allScreens = new Set(Object.keys(screenNav));
    // Also add screens that are navigated to
    for (const info of Object.values(screenNav)) {
      if (info.navigatesTo) {
        info.navigatesTo.forEach(s => allScreens.add(s));
      }
    }

    const nodes = new vis.DataSet([...allScreens].map(name => ({
      id: name,
      label: name.replace(/Screen$/, ''),
      color: screenNav[name] ? '#f78166' : '#8b949e',
      shape: 'box',
      font: { color: '#c9d1d9', size: 11 }
    })));

    // Build edges from navigatesTo arrays
    const edgesList = [];
    for (const [from, info] of Object.entries(screenNav)) {
      if (info.navigatesTo) {
        for (const to of info.navigatesTo) {
          edgesList.push({ from, to });
        }
      }
    }

    const edges = new vis.DataSet(edgesList.map(e => ({
      from: e.from,
      to: e.to,
      arrows: 'to',
      color: { color: '#f78166', hover: '#58a6ff' }
    })));

    new vis.Network(document.getElementById('screen-graph'), { nodes, edges }, {
      physics: {
        enabled: true,
        solver: 'forceAtlas2Based',
        forceAtlas2Based: { gravitationalConstant: -30 },
        stabilization: { iterations: 100 }
      },
      interaction: { hover: true, zoomView: true, dragNodes: true }
    });
  }
}

window.setArchView = function(view) {
  currentArchView = view;
  // Update toggle buttons
  document.querySelectorAll('[data-arch-view]').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.archView === view);
  });
  // Update legend visibility
  const legend = document.getElementById('arch-legend');
  if (legend) {
    legend.style.display = view === 'graph' ? '' : 'none';
  }
  // Re-render
  renderArchitecture();
};

window.showScreenInfo = function(screenName) {
  const detailEl = document.getElementById('screen-detail');
  const titleEl = document.getElementById('screen-detail-title');
  const contentEl = document.getElementById('screen-detail-content');

  if (!detailEl || !currentProjectData) return;

  const screenNav = currentProjectData.graph?.screenNavigation || {};
  const screen = screenNav[screenName];

  if (!screen) return;

  if (titleEl) titleEl.textContent = screenName.replace(/Screen$/, '');
  if (contentEl) {
    const navigatesTo = screen.navigatesTo || [];
    const reachableFrom = screen.reachableFrom || [];

    contentEl.innerHTML = `
      <div style="display: grid; gap: 12px; font-size: 14px;">
        <div><strong>Path:</strong> <span style="color: var(--text-muted);">${escapeHtml(screen.path || 'Unknown')}</span></div>
        ${navigatesTo.length ? `
          <div>
            <strong>Navigates to:</strong>
            <div style="margin-top: 4px; display: flex; flex-wrap: wrap; gap: 4px;">
              ${navigatesTo.map(s => `<span style="background: var(--bg-tertiary); padding: 2px 8px; border-radius: 4px; font-size: 12px;">${escapeHtml(s.replace(/Screen$/, ''))}</span>`).join('')}
            </div>
          </div>
        ` : ''}
        ${reachableFrom.length ? `
          <div>
            <strong>Reachable from:</strong>
            <div style="margin-top: 4px; display: flex; flex-wrap: wrap; gap: 4px;">
              ${reachableFrom.map(s => `<span style="background: var(--bg-tertiary); padding: 2px 8px; border-radius: 4px; font-size: 12px;">${escapeHtml(s.replace(/Screen$/, ''))}</span>`).join('')}
            </div>
          </div>
        ` : ''}
      </div>
    `;
  }

  detailEl.style.display = 'block';
};

// Legacy file renderers (kept for compatibility)
function renderFiles() {
  const fileList = document.getElementById('file-list');
  if (!fileList || !currentProjectData) return;

  const files = currentProjectData.index?.fileIndex || [];
  const searchInput = document.getElementById('file-search');

  const renderList = (filter = '') => {
    const filtered = filter
      ? files.filter(f => (f.path || f).toLowerCase().includes(filter.toLowerCase()))
      : files;

    if (filtered.length === 0) {
      fileList.innerHTML = '<div class="empty-state">No files found</div>';
      return;
    }

    fileList.innerHTML = filtered.slice(0, 200).map(f => {
      const filePath = f.path || f;
      const summary = currentProjectData.summaries?.[filePath];
      return `
        <div class="file-item">
          <div class="path">${escapeHtml(filePath)}</div>
          ${summary?.purpose ? `<div class="summary">${escapeHtml(summary.purpose)}</div>` : ''}
          ${summary?.type ? `<div class="meta">${escapeHtml(summary.type)}</div>` : ''}
        </div>
      `;
    }).join('');

    if (filtered.length > 200) {
      fileList.innerHTML += `<div class="more-items">... and ${filtered.length - 200} more files</div>`;
    }
  };

  renderList();

  if (searchInput) {
    searchInput.oninput = (e) => renderList(e.target.value);
  }
}

function renderFunctions() {
  const funcList = document.getElementById('func-list');
  if (!funcList || !currentProjectData) return;

  const functions = currentProjectData.functions || {};
  const entries = Object.entries(functions);
  const searchInput = document.getElementById('func-search');

  const renderList = (filter = '') => {
    const filtered = filter
      ? entries.filter(([name]) => name.toLowerCase().includes(filter.toLowerCase()))
      : entries;

    if (filtered.length === 0) {
      funcList.innerHTML = '<div class="empty-state">No functions found</div>';
      return;
    }

    funcList.innerHTML = filtered.slice(0, 200).map(([name, info]) => `
      <div class="func-item">
        <span class="func-name">${escapeHtml(name)}</span>
        <span class="func-location">${escapeHtml(info.file || '')}${info.line ? ':' + info.line : ''}</span>
      </div>
    `).join('');

    if (filtered.length > 200) {
      funcList.innerHTML += `<div class="more-items">... and ${filtered.length - 200} more functions</div>`;
    }
  };

  renderList();

  if (searchInput) {
    searchInput.oninput = (e) => renderList(e.target.value);
  }
}

function renderSchema() {
  const schemaGrid = document.getElementById('schema-grid');
  if (!schemaGrid || !currentProjectData) return;

  const schema = currentProjectData.schema || {};
  const collections = Object.entries(schema);

  if (collections.length === 0) {
    schemaGrid.innerHTML = '<div class="empty-state">No schema data available</div>';
    return;
  }

  schemaGrid.innerHTML = collections.map(([name, info]) => `
    <div class="collection-card">
      <h4>${escapeHtml(name)}</h4>
      <div class="fields">
        ${(info.fields || []).map(f => escapeHtml(f)).join(', ') || 'No fields documented'}
      </div>
      ${info.referencedIn?.length ? `
        <div class="refs" style="margin-top: 8px; font-size: 11px; color: var(--text-subtle);">
          Used in ${info.referencedIn.length} file${info.referencedIn.length !== 1 ? 's' : ''}
        </div>
      ` : ''}
    </div>
  `).join('');
}

async function renderHealth() {
  const scoreEl = document.getElementById('health-score');
  const timestampEl = document.getElementById('health-timestamp');
  const issuesEl = document.getElementById('health-issues');

  // Summary count elements
  const securityCount = document.getElementById('security-count');
  const performanceCount = document.getElementById('performance-count');
  const duplicatesCount = document.getElementById('duplicates-count');
  const deadcodeCount = document.getElementById('deadcode-count');
  const deadcodeTotalCount = document.getElementById('deadcode-total-count');

  if (!currentProject) return;

  // Try to load cached health data
  try {
    const response = await fetch(`/api/health?project=${currentProject.id}`);
    if (response.ok) {
      const health = await response.json();

      // Update score
      if (scoreEl) scoreEl.textContent = health.score || '--';
      if (timestampEl) {
        timestampEl.textContent = health.timestamp
          ? `Last scan: ${formatDate(health.timestamp)}`
          : 'Never scanned';
      }

      // Update summary counts
      const summary = health.summary || {};
      if (securityCount) securityCount.textContent = summary.security || 0;
      if (performanceCount) performanceCount.textContent = summary.performance || 0;
      if (duplicatesCount) duplicatesCount.textContent = summary.duplicates || 0;
      if (deadcodeCount) deadcodeCount.textContent = summary.dead_code || 0;
      if (deadcodeTotalCount) deadcodeTotalCount.textContent = summary.dead_code || 0;

      // Render issues list
      if (issuesEl) {
        const issues = health.issues || {};
        const allIssues = [];

        // Collect all issues with their category
        for (const [category, items] of Object.entries(issues)) {
          if (Array.isArray(items)) {
            for (const item of items) {
              allIssues.push({ ...item, category });
            }
          }
        }

        if (allIssues.length === 0) {
          issuesEl.innerHTML = '<div class="empty-state" style="padding: 20px; color: var(--text-muted);">No issues found - codebase is healthy!</div>';
        } else {
          // Group by category for display
          let html = '';

          // Security issues
          const securityIssues = issues.security || [];
          if (securityIssues.length > 0) {
            html += renderIssueSection('Security', securityIssues, 'critical');
          }

          // Performance issues
          const perfIssues = issues.performance || [];
          if (perfIssues.length > 0) {
            html += renderIssueSection('Performance', perfIssues, 'warning');
          }

          // Maintenance issues
          const maintIssues = issues.maintenance || [];
          if (maintIssues.length > 0) {
            html += renderIssueSection('Maintenance', maintIssues, 'info');
          }

          // Duplicates (show summary, not all files)
          const duplicates = issues.duplicates || [];
          if (duplicates.length > 0) {
            html += `
              <div class="issue-section">
                <h4 style="color: var(--warning); margin-bottom: 8px;">Duplicates (${duplicates.length} groups)</h4>
                ${duplicates.slice(0, 5).map(dup => `
                  <div class="issue-item" style="padding: 8px; background: var(--bg-secondary); border-radius: 6px; margin-bottom: 6px;">
                    <div style="font-size: 13px; color: var(--text-secondary);">${escapeHtml(dup.description || `${dup.files?.length || 0} duplicate files`)}</div>
                    ${dup.files ? `<div style="font-size: 11px; color: var(--text-muted); margin-top: 4px;">${dup.files.slice(0, 3).map(f => escapeHtml(f)).join(', ')}${dup.files.length > 3 ? ` +${dup.files.length - 3} more` : ''}</div>` : ''}
                  </div>
                `).join('')}
                ${duplicates.length > 5 ? `<div style="color: var(--text-muted); font-size: 12px;">... and ${duplicates.length - 5} more duplicate groups</div>` : ''}
              </div>
            `;
          }

          // Dead code (show count, not all files)
          const deadCode = issues.dead_code || [];
          if (deadCode.length > 0) {
            html += `
              <div class="issue-section">
                <h4 style="color: var(--text-muted); margin-bottom: 8px;">Dead Code (${deadCode.length} files)</h4>
                <div style="font-size: 13px; color: var(--text-secondary);">
                  ${deadCode.slice(0, 10).map(file => `<div style="padding: 4px 0;">${escapeHtml(typeof file === 'string' ? file : file.file || file.path || JSON.stringify(file))}</div>`).join('')}
                  ${deadCode.length > 10 ? `<div style="color: var(--text-muted); margin-top: 8px;">... and ${deadCode.length - 10} more unused files</div>` : ''}
                </div>
              </div>
            `;
          }

          issuesEl.innerHTML = html || '<div class="empty-state">No actionable issues</div>';
        }
      }
    }
  } catch (e) {
    if (scoreEl) scoreEl.textContent = '--';
    if (timestampEl) timestampEl.textContent = 'Click "Run Scan" to analyze';
    if (issuesEl) issuesEl.innerHTML = '<div class="empty-state" style="color: var(--text-muted);">Run a scan to see issues</div>';
  }
}

function renderIssueSection(title, issues, severity) {
  const severityColors = {
    critical: 'var(--error)',
    warning: 'var(--warning)',
    info: 'var(--info)'
  };
  const color = severityColors[severity] || 'var(--text-secondary)';

  return `
    <div class="issue-section" style="margin-bottom: 16px;">
      <h4 style="color: ${color}; margin-bottom: 8px;">${escapeHtml(title)} (${issues.length})</h4>
      ${issues.slice(0, 10).map(issue => `
        <div class="issue-item" style="padding: 8px; background: var(--bg-secondary); border-radius: 6px; margin-bottom: 6px; border-left: 3px solid ${color};">
          <div style="font-size: 13px; color: var(--text-primary);">${escapeHtml(issue.message || issue.description || issue.rule || 'Issue')}</div>
          ${issue.file ? `<div style="font-size: 11px; color: var(--text-muted); margin-top: 4px;">${escapeHtml(issue.file)}${issue.line ? `:${issue.line}` : ''}</div>` : ''}
        </div>
      `).join('')}
      ${issues.length > 10 ? `<div style="color: var(--text-muted); font-size: 12px;">... and ${issues.length - 10} more ${title.toLowerCase()} issues</div>` : ''}
    </div>
  `;
}

function renderGraph() {
  const graphContainer = document.getElementById('graph');
  if (!graphContainer || !currentProjectData) return;

  const graph = currentProjectData.graph;

  // Convert nested object structure to arrays for vis-network
  const nodesList = [];
  const edgesList = [];

  if (graph && graph.nodes && typeof graph.nodes === 'object') {
    // nodes is organized by category: { screens: {...}, components: {...}, ... }
    for (const [category, items] of Object.entries(graph.nodes)) {
      if (items && typeof items === 'object') {
        for (const [id, node] of Object.entries(items)) {
          nodesList.push({
            id: id,
            label: node.name || node.path?.split('/').pop()?.replace(/\.[^.]+$/, '') || id,
            type: category,
            ...node
          });
        }
      }
    }
  }

  if (graph && graph.edges && typeof graph.edges === 'object') {
    // edges is organized by type: { imports: [...], navigates: [...], ... }
    for (const [edgeType, items] of Object.entries(graph.edges)) {
      if (Array.isArray(items)) {
        for (const edge of items) {
          edgesList.push({
            from: edge.from,
            to: edge.to,
            type: edgeType,
            ...edge
          });
        }
      }
    }
  }

  if (nodesList.length === 0) {
    graphContainer.innerHTML = `
      <div class="empty-state" style="display: flex; align-items: center; justify-content: center; height: 300px; color: var(--text-muted);">
        <div style="text-align: center;">
          <p>No graph data available</p>
          <p style="font-size: 13px; margin-top: 8px;">The watcher will generate navigation data when files change</p>
        </div>
      </div>
    `;
    return;
  }

  // Use vis-network if available
  if (typeof vis !== 'undefined') {
    try {
      const nodes = new vis.DataSet(nodesList.slice(0, 150).map(n => ({
        id: n.id,
        label: n.label,
        color: getNodeColor(n.type),
        shape: n.type === 'screens' ? 'box' : 'dot',
        size: n.type === 'screens' ? 25 : 15,
        font: { color: '#c9d1d9', size: 11 }
      })));

      const edges = new vis.DataSet(edgesList.slice(0, 300).map(e => ({
        from: e.from,
        to: e.to,
        arrows: 'to',
        color: { color: getEdgeColor(e.type), hover: '#58a6ff' },
        dashes: e.type === 'uses'
      })));

      new vis.Network(graphContainer, { nodes, edges }, {
        physics: {
          enabled: true,
          solver: 'forceAtlas2Based',
          forceAtlas2Based: { gravitationalConstant: -50 },
          stabilization: { iterations: 100 }
        },
        interaction: { hover: true, zoomView: true, dragNodes: true },
        nodes: { borderWidth: 2 },
        edges: { smooth: { type: 'continuous' } }
      });
    } catch (e) {
      console.error('Graph render error:', e);
      graphContainer.innerHTML = `<div class="empty-state" style="padding: 20px; text-align: center; color: var(--error);">Error rendering graph: ${escapeHtml(e.message)}</div>`;
    }
  } else {
    graphContainer.innerHTML = `
      <div style="padding: 20px; color: var(--text-secondary);">
        <p><strong>${nodesList.length}</strong> nodes, <strong>${edgesList.length}</strong> edges</p>
        <p style="margin-top: 8px; font-size: 13px; color: var(--text-muted);">vis-network library not loaded</p>
      </div>
    `;
  }
}

function getEdgeColor(type) {
  const colors = {
    imports: '#30363d',
    navigates: '#f78166',
    uses: '#58a6ff',
    calls: '#a371f7'
  };
  return colors[type] || '#30363d';
}

function setupAskTab() {
  const input = document.getElementById('ask-input');
  const submit = document.getElementById('ask-submit');

  if (input && submit) {
    submit.onclick = () => submitAsk();
    input.onkeydown = (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        submitAsk();
      }
    };
  }
}

async function submitAsk() {
  const input = document.getElementById('ask-input');
  const results = document.getElementById('ask-results');
  const answer = document.getElementById('ask-answer');
  const answerText = document.getElementById('ask-answer-text');

  const query = input?.value.trim();
  if (!query || !results) return;

  results.innerHTML = '<div class="loading">Searching...</div>';
  if (answer) answer.classList.add('hidden');

  try {
    const response = await fetch('/api/ollama/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt: query, project: currentProject?.id })
    }).then(r => r.json());

    results.innerHTML = '';

    if (answer && answerText) {
      answer.classList.remove('hidden');
      answerText.textContent = response.response || response.error || 'No response';
    }
  } catch (e) {
    results.innerHTML = `<div class="error">Error: ${escapeHtml(e.message)}</div>`;
  }
}

function getNodeColor(type) {
  const colors = {
    screen: '#f78166',
    screens: '#f78166',
    component: '#a371f7',
    components: '#a371f7',
    service: '#58a6ff',
    services: '#58a6ff',
    hook: '#3fb950',
    hooks: '#3fb950',
    util: '#8b949e',
    utils: '#8b949e',
    files: '#8b949e',
    context: '#d2a8ff',
    contexts: '#d2a8ff',
    navigation: '#f0883e',
    collections: '#7ee787'
  };
  return colors[type] || '#8b949e';
}

// Breadcrumb
function updateBreadcrumb(project) {
  const separator = document.getElementById('breadcrumb-separator');
  const projectName = document.getElementById('breadcrumb-project');

  if (project) {
    separator?.classList.remove('hidden');
    projectName?.classList.remove('hidden');
    if (projectName) projectName.textContent = project.displayName;
  } else {
    separator?.classList.add('hidden');
    projectName?.classList.add('hidden');
  }
}

// Stats in header
function updateStats() {
  const stats = document.getElementById('stats');
  if (stats) {
    const totalFiles = projects.reduce((sum, p) => sum + (p.fileCount || 0), 0);
    stats.textContent = `${projects.length} projects · ${totalFiles.toLocaleString()} files`;
  }
}

// API calls
async function loadProjects() {
  try {
    projects = await fetch('/api/projects').then(r => r.json());
    updateStats();
    console.log(`Loaded ${projects.length} projects`);
  } catch (e) {
    console.error('Failed to load projects:', e);
    projects = [];
  }
}

async function checkOllamaStatus() {
  try {
    const status = await fetch('/api/ollama/status').then(r => r.json());
    ollamaAvailable = status.available;
    updateOllamaIndicator(status);
  } catch (e) {
    ollamaAvailable = false;
    updateOllamaIndicator({ available: false });
  }
}

function updateOllamaIndicator(status) {
  const indicator = document.getElementById('ollama-status');
  if (indicator) {
    indicator.classList.toggle('available', status.available);
    indicator.title = status.available ? `AI: ${status.model || 'Ready'}` : 'AI: Offline';
  }
}

// Chat / Ollama Modal
function showChat(projectId) {
  const modal = document.getElementById('chat-modal');
  const projectName = document.getElementById('chat-project-name');
  if (projectName) projectName.textContent = currentProject?.displayName || projectId || 'Dash AI';
  modal?.classList.remove('hidden');
  document.getElementById('chat-input')?.focus();
}

function closeChat() {
  document.getElementById('chat-modal')?.classList.add('hidden');
}

async function sendMessage() {
  const input = document.getElementById('chat-input');
  const messages = document.getElementById('chat-messages');
  const prompt = input?.value.trim();

  if (!prompt || !messages) return;

  messages.innerHTML += `<div class="chat-message user">${escapeHtml(prompt)}</div>`;
  input.value = '';

  const loadingId = Date.now();
  messages.innerHTML += `<div class="chat-message assistant loading" id="msg-${loadingId}">Thinking...</div>`;
  messages.scrollTop = messages.scrollHeight;

  try {
    const response = await fetch('/api/ollama/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt, project: currentProject?.id })
    }).then(r => r.json());

    const msgEl = document.getElementById(`msg-${loadingId}`);
    if (msgEl) {
      msgEl.classList.remove('loading');
      msgEl.textContent = response.response || response.error || 'No response';
    }
  } catch (e) {
    const msgEl = document.getElementById(`msg-${loadingId}`);
    if (msgEl) {
      msgEl.classList.remove('loading');
      msgEl.textContent = `Error: ${e.message}`;
    }
  }

  messages.scrollTop = messages.scrollHeight;
}

// Health scan
async function runHealthScan() {
  const scoreEl = document.getElementById('health-score');
  const timestampEl = document.getElementById('health-timestamp');
  const issuesEl = document.getElementById('health-issues');
  const runBtn = document.getElementById('run-scan');

  if (runBtn) runBtn.disabled = true;
  if (scoreEl) scoreEl.textContent = '...';
  if (timestampEl) timestampEl.textContent = 'Scanning...';
  if (issuesEl) issuesEl.innerHTML = '<div class="loading" style="padding: 20px;">Running health analysis...</div>';

  try {
    const response = await fetch(`/api/health/scan?project=${currentProject?.id}`, { method: 'POST' });
    const result = await response.json();

    if (result.error) {
      throw new Error(result.error);
    }

    // Re-render the full health tab with new data
    await renderHealth();
  } catch (e) {
    if (scoreEl) scoreEl.textContent = 'Error';
    if (timestampEl) timestampEl.textContent = e.message || 'Scan failed';
    if (issuesEl) issuesEl.innerHTML = `<div class="empty-state" style="color: var(--error);">Scan failed: ${escapeHtml(e.message)}</div>`;
    console.error('Health scan failed:', e);
  } finally {
    if (runBtn) runBtn.disabled = false;
  }
}

// Utilities
function escapeHtml(text) {
  if (!text) return '';
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

function formatSize(bytes) {
  if (!bytes || bytes === 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return `${(bytes / Math.pow(1024, i)).toFixed(i > 0 ? 1 : 0)} ${units[i]}`;
}

function formatDate(isoString) {
  if (!isoString) return 'Never';
  const date = new Date(isoString);
  if (isNaN(date.getTime())) return 'Never';

  const now = new Date();
  const diff = now - date;

  if (diff < 0) return 'Just now';
  if (diff < 60000) return 'Just now';
  if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
  if (diff < 604800000) return `${Math.floor(diff / 86400000)}d ago`;
  return date.toLocaleDateString();
}

// Features Tab
function renderFeatures() {
  const featuresGrid = document.getElementById('features-grid');
  if (!featuresGrid || !currentProjectData) return;

  const features = currentProjectData.features || {};
  const featureList = Object.entries(features);

  if (featureList.length === 0) {
    featuresGrid.innerHTML = '<div class="empty-state">No features documented yet</div>';
    return;
  }

  featuresGrid.innerHTML = featureList.map(([name, info]) => `
    <div class="feature-card">
      <h4>${escapeHtml(name)}</h4>
      <p>${escapeHtml(info.description || 'No description')}</p>
      ${info.files?.length ? `<div class="feature-files">${info.files.length} files</div>` : ''}
    </div>
  `).join('');
}

// ===== EFFICIENCY METRICS =====

let efficiencyData = null;
let projectionData = null;

async function loadEfficiencyData() {
  try {
    const [effRes, projRes] = await Promise.all([
      fetch('/api/efficiency'),
      fetch('/api/efficiency/projection?weeks=12')
    ]);

    efficiencyData = await effRes.json();
    projectionData = await projRes.json();

    renderEfficiencyMetrics();
  } catch (e) {
    console.error('Error loading efficiency data:', e);
  }
}

function renderEfficiencyMetrics() {
  if (!efficiencyData) return;

  // Update stat cards
  document.getElementById('eff-sessions').textContent = efficiencyData.sessions?.total || 0;
  document.getElementById('eff-corrections').textContent = efficiencyData.corrections?.total || 0;

  const rate = efficiencyData.corrections?.rate || 0;
  document.getElementById('eff-correction-rate').textContent = `${rate.toFixed(2)} per session`;

  const tokens = efficiencyData.tokenSavings?.estimated || 0;
  document.getElementById('eff-tokens').textContent = tokens > 1000
    ? `~${(tokens / 1000).toFixed(1)}k`
    : `~${tokens}`;

  const prefs = efficiencyData.preferences?.learned || 0;
  const highConf = efficiencyData.preferences?.highConfidence || 0;
  document.getElementById('eff-preferences').textContent = prefs;
  document.getElementById('eff-pref-confidence').textContent = `${highConf} high-confidence`;

  // Update progress bars
  renderProgressBars();

  // Render projections
  renderProjections();

  // Render domain confidence
  renderDomainConfidence();
}

function renderProgressBars() {
  // Correction rate improvement (compare to baseline of 1.0 corrections/session)
  const baselineCps = 1.0;
  const currentCps = efficiencyData.corrections?.rate || 0;
  const correctionImprovement = baselineCps > 0
    ? Math.max(0, Math.min(100, ((baselineCps - currentCps) / baselineCps) * 100))
    : 0;

  document.getElementById('eff-correction-bar').style.width = `${correctionImprovement}%`;
  document.getElementById('eff-correction-progress-val').textContent = `${correctionImprovement.toFixed(0)}%`;

  if (correctionImprovement > 50) {
    document.getElementById('eff-correction-hint').textContent = 'Excellent! Correction rate well below baseline.';
  } else if (correctionImprovement > 20) {
    document.getElementById('eff-correction-hint').textContent = 'Good progress. System is learning from corrections.';
  } else if (efficiencyData.sessions?.total >= 5) {
    document.getElementById('eff-correction-hint').textContent = 'Building baseline. More sessions needed for improvement.';
  } else {
    document.getElementById('eff-correction-hint').textContent = 'Baseline being established...';
  }

  // Memory utilization (estimate based on sessions)
  const sessions = efficiencyData.sessions?.total || 0;
  const memoryUtil = Math.min(100, sessions * 8); // ~8% per session up to 100%
  document.getElementById('eff-memory-bar').style.width = `${memoryUtil}%`;
  document.getElementById('eff-memory-progress-val').textContent = `${memoryUtil.toFixed(0)}%`;

  // Preference confidence
  const totalPrefs = efficiencyData.preferences?.learned || 0;
  const highConfPrefs = efficiencyData.preferences?.highConfidence || 0;
  const prefConfidence = totalPrefs > 0 ? (highConfPrefs / totalPrefs) * 100 : 0;
  document.getElementById('eff-pref-bar').style.width = `${prefConfidence}%`;
  document.getElementById('eff-pref-progress-val').textContent =
    totalPrefs > 0 ? `${prefConfidence.toFixed(0)}%` : 'No data';
}

function renderProjections() {
  const container = document.getElementById('eff-projection-content');
  if (!container) return;

  if (!projectionData || !projectionData.projected || projectionData.projected.length === 0) {
    container.innerHTML = `
      <div class="efficiency-projection-card">
        <div class="projection-period">Current</div>
        <div class="projection-stats">
          <div class="projection-stat">
            <span class="projection-stat-value">${(efficiencyData?.corrections?.rate || 0).toFixed(2)}</span>
            <span class="projection-stat-label">corrections/session</span>
          </div>
          <div class="projection-stat">
            <span class="projection-stat-value">${efficiencyData?.preferences?.learned || 0}</span>
            <span class="projection-stat-label">preferences learned</span>
          </div>
        </div>
      </div>
      <div class="efficiency-projection-note">
        Need more data to project. Keep using Claude to build learning history.
      </div>
    `;
    return;
  }

  const current = projectionData.current || {};
  const projected = projectionData.projected || [];

  let html = `
    <div class="efficiency-projection-card current">
      <div class="projection-period">Now</div>
      <div class="projection-stats">
        <div class="projection-stat">
          <span class="projection-stat-value">${(current.correctionsPerSession || 0).toFixed(2)}</span>
          <span class="projection-stat-label">corr/session</span>
        </div>
        <div class="projection-stat">
          <span class="projection-stat-value">${formatTokens(current.tokenSavings || 0)}</span>
          <span class="projection-stat-label">tokens saved</span>
        </div>
      </div>
    </div>
  `;

  projected.forEach(p => {
    const improvementClass = p.improvementPercent > 30 ? 'good' : p.improvementPercent > 10 ? 'moderate' : '';
    html += `
      <div class="efficiency-projection-card ${improvementClass}">
        <div class="projection-period">${p.weeksAhead} weeks</div>
        <div class="projection-stats">
          <div class="projection-stat">
            <span class="projection-stat-value">${p.correctionsPerSession.toFixed(2)}</span>
            <span class="projection-stat-label">corr/session</span>
          </div>
          <div class="projection-stat improvement">
            <span class="projection-stat-value">${p.improvementPercent > 0 ? '+' : ''}${p.improvementPercent.toFixed(0)}%</span>
            <span class="projection-stat-label">improvement</span>
          </div>
        </div>
      </div>
    `;
  });

  if (projectionData.weeksToTarget) {
    html += `
      <div class="efficiency-projection-target">
        Target (0.5 corr/session) in ~${projectionData.weeksToTarget} weeks
      </div>
    `;
  }

  container.innerHTML = html;
}

function renderDomainConfidence() {
  const container = document.getElementById('eff-domains-content');
  if (!container) return;

  const domains = efficiencyData?.confidence?.domains || {};
  const entries = Object.entries(domains).filter(([_, stats]) => stats.total >= 1);

  if (entries.length === 0) {
    container.innerHTML = `
      <div class="efficiency-domain-empty">
        No domain data yet. Use Claude more to build calibration.
      </div>
    `;
    return;
  }

  // Sort by total interactions
  entries.sort((a, b) => b[1].total - a[1].total);

  container.innerHTML = entries.map(([domain, stats]) => {
    const accuracy = (stats.accuracy * 100) || 0;
    const level = accuracy >= 85 ? 'high' : accuracy >= 65 ? 'medium' : 'low';

    return `
      <div class="efficiency-domain-card ${level}">
        <div class="domain-name">${escapeHtml(domain)}</div>
        <div class="domain-accuracy">
          <div class="domain-accuracy-bar">
            <div class="domain-accuracy-fill" style="width: ${accuracy}%"></div>
          </div>
          <span class="domain-accuracy-value">${accuracy.toFixed(0)}%</span>
        </div>
        <div class="domain-stats">${stats.total} interactions</div>
      </div>
    `;
  }).join('');
}

function formatTokens(num) {
  if (num >= 1000000) return `${(num / 1000000).toFixed(1)}M`;
  if (num >= 1000) return `${(num / 1000).toFixed(1)}k`;
  return num.toString();
}

function refreshEfficiency() {
  loadEfficiencyData();
}

// Load efficiency when reports tab is shown
function onReportsTabShown() {
  loadEfficiencyData();
}

// Global functions for onclick handlers in HTML
window.showPortalTab = showPortalTab;
window.refreshEfficiency = refreshEfficiency;
window.showOllamaChat = () => showChat(currentProject?.id);
window.hideOllamaChat = closeChat;
window.closeChat = closeChat;
window.sendMessage = sendMessage;
window.showSettingsModal = () => document.getElementById('settings-modal')?.classList.remove('hidden');
window.hideSettingsModal = () => document.getElementById('settings-modal')?.classList.add('hidden');
window.clearOllamaChat = () => {
  const m = document.getElementById('chat-messages');
  if (m) m.innerHTML = '';
};
window.addKnowledgeBaseSource = () => {
  const input = document.getElementById('kb-url-input');
  if (input?.value) {
    console.log('Adding KB source:', input.value);
    alert('Knowledge base feature coming soon');
    input.value = '';
  }
};
window.generateReport = () => {
  alert('Report generation coming soon');
};
window.saveKey = () => window.hideSettingsModal();
window.askOllama = sendMessage;
window.handleOllamaKeydown = (e) => { if (e.key === 'Enter' && !e.shiftKey) sendMessage(); };
window.executeQuickHandoff = () => console.log('Quick handoff not implemented');
window.hideQuickHandoff = () => document.getElementById('quick-handoff')?.classList.add('hidden');
window.handoffToClaude = () => console.log('Handoff to Claude not implemented');
window.handleContextModeChange = () => console.log('Context mode change not implemented');
window.handleFixDropdown = () => console.log('Fix dropdown not implemented');

// Event listeners
document.addEventListener('DOMContentLoaded', () => {
  // Health scan button
  const runScanBtn = document.getElementById('run-scan');
  if (runScanBtn) {
    runScanBtn.addEventListener('click', runHealthScan);
  }

  // Chat input enter key
  const chatInput = document.getElementById('chat-input');
  if (chatInput) {
    chatInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
      }
    });
  }
});

// Keyboard shortcuts
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    closeChat();
    window.hideSettingsModal();
    window.closeSyncModal();
  }
});
