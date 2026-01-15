#!/usr/bin/env node
/**
 * Claude-Dash Gateway - Unified MCP Server
 *
 * Combines memory, filesystem, and commander tools with smart routing.
 * Checks pre-indexed memory BEFORE disk access for token efficiency.
 *
 * Transport: stdio (MCP protocol)
 */

const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const readline = require('readline');
const { Cache } = require(path.join(__dirname, 'cache'));
const { Metrics } = require(path.join(__dirname, 'metrics'));

const MEMORY_ROOT = path.join(process.env.HOME, '.claude-dash');
const MLX_TOOLS = path.join(MEMORY_ROOT, 'mlx-tools');
const CONFIG_PATH = path.join(MEMORY_ROOT, 'config.json');

// =============================================================================
// SECURITY: Path Validation
// =============================================================================

// Allowed base directories for file operations
function getAllowedBasePaths() {
  const config = loadConfigUncached();
  const allowed = [
    process.env.HOME,
    '/tmp',
    MEMORY_ROOT
  ];
  // Add all registered project paths
  for (const project of config.projects || []) {
    if (project.path) {
      allowed.push(project.path);
    }
  }
  return allowed;
}

// Load config without caching (for security checks)
function loadConfigUncached() {
  try {
    return JSON.parse(fs.readFileSync(CONFIG_PATH, 'utf8'));
  } catch (e) {
    return { projects: [] };
  }
}

// Validate path is within allowed directories (prevents path traversal)
function isPathAllowed(filePath) {
  if (!filePath || typeof filePath !== 'string') {
    return false;
  }

  // Resolve to absolute, normalized path (this neutralizes .. traversal)
  const resolved = path.resolve(filePath);

  // Check against allowed base paths using strict prefix matching
  // Uses path.sep to prevent /home/user matching /home/username
  const allowed = getAllowedBasePaths();
  return allowed.some(base => {
    const resolvedBase = path.resolve(base);
    // Exact match or proper directory prefix (with separator)
    return resolved === resolvedBase ||
           resolved.startsWith(resolvedBase + path.sep);
  });
}

// Validate and sanitize file path
function validateFilePath(filePath, operation = 'read') {
  if (!filePath || typeof filePath !== 'string') {
    return { valid: false, error: 'Invalid file path' };
  }

  const resolved = path.resolve(filePath);

  // Block obvious dangerous paths
  const dangerousPaths = ['/etc/passwd', '/etc/shadow', '/.ssh/', '/id_rsa', '/.env'];
  for (const dangerous of dangerousPaths) {
    if (resolved.includes(dangerous)) {
      return { valid: false, error: `Access to ${dangerous} is not allowed` };
    }
  }

  if (!isPathAllowed(resolved)) {
    return { valid: false, error: `Path outside allowed directories: ${filePath}` };
  }

  // For write operations, additional checks
  if (operation === 'write') {
    // Don't allow writing to system directories
    const systemDirs = ['/bin', '/sbin', '/usr', '/System', '/Library'];
    for (const sysDir of systemDirs) {
      if (resolved.startsWith(sysDir)) {
        return { valid: false, error: `Cannot write to system directory: ${sysDir}` };
      }
    }
  }

  return { valid: true, path: resolved };
}

// =============================================================================
// SECURITY: Command Validation
// =============================================================================

// Commands that are never allowed
const BLOCKED_COMMANDS = [
  /\brm\s+(-rf?|--recursive)?\s*\//, // rm -rf /
  /\bmkfs\b/,
  /\bdd\s+.*of=\/dev/,
  /\b(curl|wget).*\|\s*(ba)?sh/,     // curl | sh patterns
  />\s*\/dev\/sd[a-z]/,
  /\bchmod\s+777\s+\//,
  /\bsudo\s+rm/,
  /\bformat\b.*c:/i,
  /\b:(){ :|:& };:/,                 // fork bomb
];

// Commands that require extra scrutiny
const SENSITIVE_PATTERNS = [
  /\bsudo\b/,
  /\bsu\s+-?\s*$/,
  />\s*\/etc\//,
  /\beval\b/,
  /\bexec\b/,
];

function validateCommand(command) {
  if (!command || typeof command !== 'string') {
    return { valid: false, error: 'Invalid command' };
  }

  // Check for blocked dangerous patterns
  for (const pattern of BLOCKED_COMMANDS) {
    if (pattern.test(command)) {
      return { valid: false, error: 'Command contains blocked dangerous pattern' };
    }
  }

  // Warn about sensitive commands but allow them
  let warning = null;
  for (const pattern of SENSITIVE_PATTERNS) {
    if (pattern.test(command)) {
      warning = 'Command contains sensitive operations';
      break;
    }
  }

  return { valid: true, command, warning };
}

// =============================================================================
// SECURITY: Input Validation
// =============================================================================

// Validate project ID format (alphanumeric, dashes, underscores only)
function validateProjectId(projectId) {
  if (!projectId || typeof projectId !== 'string') {
    return { valid: false, error: 'Invalid project ID' };
  }
  // Only allow safe characters in project IDs
  if (!/^[a-zA-Z0-9_-]+$/.test(projectId)) {
    return { valid: false, error: 'Project ID contains invalid characters' };
  }
  if (projectId.length > 100) {
    return { valid: false, error: 'Project ID too long' };
  }
  return { valid: true, id: projectId };
}

// Validate numeric parameters
function validateLimit(limit, defaultValue = 10, maxValue = 100) {
  if (limit === undefined || limit === null) {
    return defaultValue;
  }
  const num = parseInt(limit, 10);
  if (isNaN(num) || num < 1) {
    return defaultValue;
  }
  return Math.min(num, maxValue);
}

// Validate query string
function validateQuery(query) {
  if (!query || typeof query !== 'string') {
    return { valid: false, error: 'Invalid query' };
  }
  if (query.length > 10000) {
    return { valid: false, error: 'Query too long' };
  }
  return { valid: true, query: query.trim() };
}

// AnythingLLM Configuration
const ANYTHINGLLM_URL = process.env.ANYTHINGLLM_URL || 'http://localhost:3001';
const ANYTHINGLLM_API_KEY = process.env.ANYTHINGLLM_API_KEY || '';

// Initialize cache and metrics
const cache = new Cache();
const metrics = new Metrics();

// Periodic cache cleanup (every 5 minutes)
const CACHE_CLEANUP_INTERVAL = 5 * 60 * 1000; // 5 minutes
setInterval(() => {
  const cleaned = cache.cleanupExpired();
  if (cleaned > 0) {
    console.error(`[cache] Cleaned ${cleaned} expired entries`);
  }
}, CACHE_CLEANUP_INTERVAL);

// Load config
function loadConfig() {
  try {
    return JSON.parse(fs.readFileSync(CONFIG_PATH, 'utf8'));
  } catch (e) {
    return { projects: [] };
  }
}

// Detect project from path
function detectProject(workingDir) {
  const config = loadConfig();
  for (const project of config.projects) {
    if (workingDir && workingDir.startsWith(project.path)) {
      return project.id;
    }
  }
  if (workingDir) {
    const dirName = path.basename(workingDir).toLowerCase().replace(/\s+/g, '-');
    const found = config.projects.find(p => p.id === dirName || p.path.endsWith(dirName));
    if (found) return found.id;
  }
  return null;
}

// Run Python script (for memory tools) with timeout
const PYTHON_SCRIPT_TIMEOUT_MS = 30000;  // 30 second timeout

function runPythonScript(scriptPath, args, timeoutMs = PYTHON_SCRIPT_TIMEOUT_MS) {
  return new Promise((resolve, reject) => {
    const venvPython = path.join(MEMORY_ROOT, 'mlx-env', 'bin', 'python3');
    const pythonCmd = fs.existsSync(venvPython) ? venvPython : 'python3';

    const proc = spawn(pythonCmd, [scriptPath, ...args], {
      cwd: MLX_TOOLS,
      env: { ...process.env, PYTHONIOENCODING: 'utf-8' }
    });

    let stdout = '';
    let stderr = '';
    let killed = false;

    // Timeout handler - kill process if it takes too long
    const timeoutHandle = setTimeout(() => {
      killed = true;
      try {
        proc.kill('SIGTERM');
        setTimeout(() => {
          try { proc.kill('SIGKILL'); } catch (e) {}
        }, 1000);
      } catch (e) {}
      reject(new Error(`Script timeout after ${timeoutMs}ms: ${path.basename(scriptPath)}`));
    }, timeoutMs);

    proc.stdout.on('data', (data) => { stdout += data.toString(); });
    proc.stderr.on('data', (data) => { stderr += data.toString(); });

    proc.on('close', (code) => {
      clearTimeout(timeoutHandle);
      if (killed) return;  // Already rejected via timeout
      if (code === 0) {
        resolve(stdout.trim());
      } else {
        reject(new Error(stderr || `Process exited with code ${code}`));
      }
    });

    proc.on('error', (err) => {
      clearTimeout(timeoutHandle);
      if (!killed) reject(err);
    });
  });
}

// Run shell command (for commander functionality)
function runCommand(command, cwd = process.cwd()) {
  return new Promise((resolve, reject) => {
    const proc = spawn('sh', ['-c', command], {
      cwd,
      env: process.env
    });

    let stdout = '';
    let stderr = '';

    proc.stdout.on('data', (data) => { stdout += data.toString(); });
    proc.stderr.on('data', (data) => { stderr += data.toString(); });

    proc.on('close', (code) => {
      resolve({ stdout: stdout.trim(), stderr: stderr.trim(), code });
    });

    proc.on('error', reject);
  });
}

// =============================================================================
// TOOL DEFINITIONS
// =============================================================================

const TOOLS = [
  // --- SMART TOOLS (Memory-First) ---
  {
    name: 'smart_read',
    description: 'Memory-first file reading. Returns cached summary by default; fetches full content only if needed. Saves 60-95% tokens on typical reads.',
    inputSchema: {
      type: 'object',
      properties: {
        path: { type: 'string', description: 'File path to read' },
        detail: {
          type: 'string',
          enum: ['summary', 'functions', 'full'],
          description: 'Level of detail: summary (default, ~200 tokens), functions (list defs), full (entire file)'
        },
        project: { type: 'string', description: 'Project ID (auto-detected if omitted)' }
      },
      required: ['path']
    }
  },
  {
    name: 'smart_search',
    description: 'Memory-first code search. Checks indexed memory before grep. Returns file matches with summaries.',
    inputSchema: {
      type: 'object',
      properties: {
        query: { type: 'string', description: 'Search query (natural language or code pattern)' },
        project: { type: 'string', description: 'Project ID (auto-detected if omitted)' },
        limit: { type: 'number', description: 'Max results (default: 10)' }
      },
      required: ['query']
    }
  },
  {
    name: 'smart_exec',
    description: 'Cached command execution. Returns cached result for repeated commands within TTL.',
    inputSchema: {
      type: 'object',
      properties: {
        command: { type: 'string', description: 'Shell command to execute' },
        cwd: { type: 'string', description: 'Working directory (optional)' },
        skipCache: { type: 'boolean', description: 'Force fresh execution' }
      },
      required: ['command']
    }
  },
  {
    name: 'smart_edit',
    description: 'Edit file and trigger memory re-index. Keeps indexes fresh after modifications.',
    inputSchema: {
      type: 'object',
      properties: {
        path: { type: 'string', description: 'File path to edit' },
        content: { type: 'string', description: 'New file content' },
        project: { type: 'string', description: 'Project ID for re-indexing' }
      },
      required: ['path', 'content']
    }
  },

  // --- GATEWAY INFO ---
  {
    name: 'gateway_metrics',
    description: 'Get gateway performance metrics: cache hits, token savings, routing breakdown.',
    inputSchema: {
      type: 'object',
      properties: {
        format: {
          type: 'string',
          enum: ['summary', 'detailed', 'recent'],
          description: 'Output format'
        }
      }
    }
  },

  // --- DOCUMENT RAG (AnythingLLM) ---
  {
    name: 'doc_query',
    description: 'Query your personal documents (PDFs, research, guides) using RAG. Uses AnythingLLM to search and answer from indexed documents.',
    inputSchema: {
      type: 'object',
      properties: {
        query: { type: 'string', description: 'Question to ask about your documents' },
        workspace: { type: 'string', description: 'AnythingLLM workspace name (default: TERRA)' },
        mode: {
          type: 'string',
          enum: ['query', 'chat'],
          description: 'query = RAG only, chat = conversational with RAG context'
        }
      },
      required: ['query']
    }
  },
  {
    name: 'doc_list_workspaces',
    description: 'List available AnythingLLM workspaces (document collections).',
    inputSchema: {
      type: 'object',
      properties: {}
    }
  },

  // --- MEMORY TOOLS (passthrough to existing) ---
  {
    name: 'memory_query',
    description: 'Query project memory using hybrid search (BM25 + semantic). Use BEFORE Glob/Grep.',
    inputSchema: {
      type: 'object',
      properties: {
        query: { type: 'string', description: 'Natural language question about the codebase' },
        project: { type: 'string', description: 'Project ID (auto-detected if omitted)' }
      },
      required: ['query']
    }
  },
  {
    name: 'memory_search',
    description: 'Semantic search across project files using embeddings.',
    inputSchema: {
      type: 'object',
      properties: {
        query: { type: 'string', description: 'Search query' },
        project: { type: 'string', description: 'Project ID' },
        limit: { type: 'number', description: 'Max results (default: 10)' }
      },
      required: ['query']
    }
  },
  {
    name: 'memory_similar',
    description: 'Find files similar to a given file.',
    inputSchema: {
      type: 'object',
      properties: {
        file: { type: 'string', description: 'Path to the file' },
        project: { type: 'string', description: 'Project ID' },
        limit: { type: 'number', description: 'Max results (default: 5)' }
      },
      required: ['file']
    }
  },
  {
    name: 'memory_functions',
    description: 'Look up function/method definitions by name.',
    inputSchema: {
      type: 'object',
      properties: {
        name: { type: 'string', description: 'Function name (partial match supported)' },
        project: { type: 'string', description: 'Project ID' }
      },
      required: ['name']
    }
  },
  {
    name: 'memory_health',
    description: 'Get code health status for a project.',
    inputSchema: {
      type: 'object',
      properties: {
        project: { type: 'string', description: 'Project ID' },
        action: { type: 'string', enum: ['status', 'scan'], description: 'Action type' }
      }
    }
  },
  {
    name: 'memory_wireframe',
    description: 'Get app wireframe data: screens, navigation, data flow.',
    inputSchema: {
      type: 'object',
      properties: {
        project: { type: 'string', description: 'Project ID' },
        screen: { type: 'string', description: 'Specific screen name (optional)' },
        format: { type: 'string', enum: ['summary', 'full', 'mermaid'] }
      }
    }
  },
  {
    name: 'memory_sessions',
    description: 'Search past session decisions, patterns, and bug fixes.',
    inputSchema: {
      type: 'object',
      properties: {
        query: { type: 'string', description: 'Search query' },
        project: { type: 'string', description: 'Project ID' },
        category: { type: 'string', enum: ['decision', 'pattern', 'bugfix', 'gotcha', 'feature', 'implementation'] },
        list_sessions: { type: 'boolean' },
        session_id: { type: 'string' },
        limit: { type: 'number' }
      }
    }
  },
  {
    name: 'memory_search_all',
    description: 'Search across ALL projects for files, functions, or observations. Cross-project search.',
    inputSchema: {
      type: 'object',
      properties: {
        query: { type: 'string', description: 'Search query' },
        type: {
          type: 'string',
          enum: ['files', 'functions', 'observations'],
          description: 'What to search (default: files)'
        },
        limit: { type: 'number', description: 'Max results (default: 20)' }
      },
      required: ['query']
    }
  }
];

// =============================================================================
// TOOL HANDLERS
// =============================================================================

async function handleSmartRead(params, cwd) {
  const startTime = Date.now();
  const detail = params.detail || 'summary';
  const project = params.project || detectProject(cwd);

  // SECURITY: Validate file path
  const pathCheck = validateFilePath(params.path, 'read');
  if (!pathCheck.valid) {
    return { error: pathCheck.error };
  }
  const filePath = pathCheck.path;

  // Check cache first
  const cached = cache.get('fileRead', { path: filePath, detail });
  if (cached.hit) {
    metrics.recordQuery({
      tool: 'smart_read',
      route: 'cached',
      tokensUsed: metrics.estimateTokens(cached.value),
      tokensSaved: 0,
      latencyMs: Date.now() - startTime,
      cacheHit: true
    });
    return { result: cached.value };
  }

  // For summary/functions, check memory first
  if (detail !== 'full' && project) {
    const summariesPath = path.join(MEMORY_ROOT, 'projects', project, 'summaries.json');
    if (fs.existsSync(summariesPath)) {
      const summaries = JSON.parse(fs.readFileSync(summariesPath, 'utf8'));

      // Find matching file (try relative and absolute paths)
      const config = loadConfig();
      const projectConfig = config.projects.find(p => p.id === project);
      const relativePath = projectConfig
        ? filePath.replace(projectConfig.path + '/', '')
        : filePath;

      const summary = summaries[relativePath] || summaries[filePath];

      if (summary) {
        let result;
        if (detail === 'summary') {
          result = `File: ${filePath}\n\nSummary: ${summary.summary || 'No summary available'}\n\nPurpose: ${summary.purpose || 'Unknown'}`;
          if (summary.componentName) result += `\nComponent: ${summary.componentName}`;
        } else if (detail === 'functions') {
          // Get functions from functions.json
          const functionsPath = path.join(MEMORY_ROOT, 'projects', project, 'functions.json');
          if (fs.existsSync(functionsPath)) {
            const functions = JSON.parse(fs.readFileSync(functionsPath, 'utf8'));
            const fileFuncs = [];
            for (const [name, locs] of Object.entries(functions.functions || {})) {
              for (const loc of locs) {
                if (loc.file === relativePath || loc.file === filePath) {
                  fileFuncs.push(`${name}() at line ${loc.line}`);
                }
              }
            }
            result = `File: ${filePath}\n\nFunctions:\n${fileFuncs.join('\n') || 'No functions indexed'}`;
          } else {
            result = `File: ${filePath}\n\nFunctions: Index not available`;
          }
        }

        // Estimate savings
        const actualTokens = metrics.estimateTokens(result);
        const wouldBeTokens = fs.existsSync(filePath) ? metrics.estimateTokens(fs.readFileSync(filePath, 'utf8')) : 2000;
        const tokensSaved = Math.max(0, wouldBeTokens - actualTokens);

        cache.set('fileRead', { path: filePath, detail }, result);

        metrics.recordQuery({
          tool: 'smart_read',
          route: 'memory',
          tokensUsed: actualTokens,
          tokensSaved,
          latencyMs: Date.now() - startTime,
          cacheHit: false
        });

        return { result };
      }
    }
  }

  // Fallback to full file read
  if (!fs.existsSync(filePath)) {
    return { error: `File not found: ${filePath}` };
  }

  const content = fs.readFileSync(filePath, 'utf8');
  const result = `File: ${filePath}\n\n${content}`;

  cache.set('fileRead', { path: filePath, detail: 'full' }, result);

  metrics.recordQuery({
    tool: 'smart_read',
    route: 'filesystem',
    tokensUsed: metrics.estimateTokens(result),
    tokensSaved: 0,
    latencyMs: Date.now() - startTime,
    cacheHit: false
  });

  return { result };
}

async function handleSmartSearch(params, cwd) {
  const startTime = Date.now();
  const project = params.project || detectProject(cwd);
  const limit = params.limit || 10;

  if (!project) {
    return { error: 'Could not detect project. Please specify project ID.' };
  }

  // Route to memory_query (hybrid search)
  const output = await runPythonScript(
    path.join(MLX_TOOLS, 'query.py'),
    [project, params.query]
  );

  const tokensUsed = metrics.estimateTokens(output);

  metrics.recordQuery({
    tool: 'smart_search',
    route: 'memory',
    tokensUsed,
    tokensSaved: tokensUsed, // Would have been grep + file reads
    latencyMs: Date.now() - startTime,
    cacheHit: false
  });

  return { result: output };
}

async function handleSmartExec(params, cwd) {
  const startTime = Date.now();
  const workingDir = params.cwd || cwd;

  // SECURITY: Validate command
  const cmdCheck = validateCommand(params.command);
  if (!cmdCheck.valid) {
    return { error: cmdCheck.error };
  }
  const command = cmdCheck.command;

  // Check cache unless explicitly skipped
  if (!params.skipCache) {
    const cached = cache.get('command', { command, cwd: workingDir });
    if (cached.hit) {
      metrics.recordQuery({
        tool: 'smart_exec',
        route: 'cached',
        tokensUsed: metrics.estimateTokens(cached.value),
        tokensSaved: 0,
        latencyMs: Date.now() - startTime,
        cacheHit: true
      });
      return { result: `[Cached result]\n${cached.value}` };
    }
  }

  // Execute command
  const { stdout, stderr, code } = await runCommand(command, workingDir);

  const result = code === 0
    ? stdout || '(no output)'
    : `Error (exit ${code}):\n${stderr || stdout || 'Unknown error'}`;

  // Cache successful results
  if (code === 0) {
    cache.set('command', { command, cwd: workingDir }, result);
  }

  metrics.recordQuery({
    tool: 'smart_exec',
    route: 'commander',
    tokensUsed: metrics.estimateTokens(result),
    tokensSaved: 0,
    latencyMs: Date.now() - startTime,
    cacheHit: false
  });

  return { result };
}

async function handleSmartEdit(params, cwd) {
  const content = params.content;
  const project = params.project || detectProject(cwd);

  // SECURITY: Validate file path for write operation
  const pathCheck = validateFilePath(params.path, 'write');
  if (!pathCheck.valid) {
    return { error: pathCheck.error };
  }
  const filePath = pathCheck.path;

  // Write file
  try {
    fs.writeFileSync(filePath, content, 'utf8');
  } catch (e) {
    return { error: `Failed to write file: ${e.message}` };
  }

  // Invalidate caches for this file
  cache.invalidate({ path: filePath });

  // Trigger re-index if project detected
  if (project) {
    // Touch a trigger file that watcher can pick up
    const triggerPath = path.join(MEMORY_ROOT, 'projects', project, '.reindex-trigger');
    try {
      fs.writeFileSync(triggerPath, filePath);
    } catch (e) {
      // Non-critical
    }
  }

  return { result: `File written: ${filePath}\nCache invalidated. Re-index triggered.` };
}

async function handleGatewayMetrics(params) {
  const format = params?.format || 'summary';

  if (format === 'recent') {
    const recent = metrics.getRecentActivity(20);
    const lines = recent.map(q =>
      `${q.timeAgo}: ${q.tool} → ${q.route} (${q.tokensUsed || 0} tokens, ${q.latencyMs || 0}ms${q.cacheHit ? ' CACHED' : ''})`
    );
    return { result: `Recent Activity:\n${lines.join('\n')}` };
  }

  const summary = metrics.getSummary();
  const cacheStats = cache.getStats();

  if (format === 'detailed') {
    const trends = metrics.getDailyTrends(7);
    return {
      result: `Gateway Metrics (Detailed)

Total Queries: ${summary.totalQueries}
Session Duration: ${summary.sessionDuration}

Routing Breakdown:
  Memory:     ${summary.routing.counts.memory || 0} (${summary.routing.percentages.memory || '0%'})
  Filesystem: ${summary.routing.counts.filesystem || 0} (${summary.routing.percentages.filesystem || '0%'})
  Commander:  ${summary.routing.counts.commander || 0} (${summary.routing.percentages.commander || '0%'})
  Cached:     ${summary.routing.counts.cached || 0} (${summary.routing.percentages.cached || '0%'})

Token Efficiency:
  Actual Used:  ${summary.tokens.actualUsed}
  Saved:        ${summary.tokens.saved}
  Savings Rate: ${summary.tokens.savingsRate}

Cache Performance:
  Hit Rate:       ${cacheStats.hitRate}
  Memory Entries: ${cacheStats.memoryEntries}
  Disk Entries:   ${cacheStats.diskEntries}

Performance:
  Avg Latency: ${summary.performance.avgLatencyMs}ms

7-Day Trends:
${trends.map(d => `  ${d.date}: ${d.queries} queries, ${d.tokensSaved} tokens saved, ${d.cacheHits} cache hits`).join('\n')}`
    };
  }

  // Summary format
  return {
    result: `Gateway: ${summary.totalQueries} queries | Cache ${cacheStats.hitRate} hit | ${summary.tokens.savingsRate} tokens saved | ${summary.performance.avgLatencyMs}ms avg`
  };
}

// --- AnythingLLM Document RAG handlers ---

async function handleDocQuery(params) {
  const startTime = Date.now();
  const workspace = params.workspace || 'TERRA';
  const mode = params.mode || 'query';

  try {
    // First, get the workspace slug
    const workspacesRes = await fetch(`${ANYTHINGLLM_URL}/api/v1/workspaces`, {
      headers: { 'Authorization': `Bearer ${ANYTHINGLLM_API_KEY}` }
    });

    if (!workspacesRes.ok) {
      return { error: `AnythingLLM API error: ${workspacesRes.status} ${workspacesRes.statusText}` };
    }

    const workspacesData = await workspacesRes.json();
    const workspaceObj = workspacesData.workspaces?.find(
      w => w.name.toLowerCase() === workspace.toLowerCase() || w.slug === workspace
    );

    if (!workspaceObj) {
      const available = workspacesData.workspaces?.map(w => w.name).join(', ') || 'none';
      return { error: `Workspace '${workspace}' not found. Available: ${available}` };
    }

    // Query the workspace
    const chatRes = await fetch(`${ANYTHINGLLM_URL}/api/v1/workspace/${workspaceObj.slug}/chat`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${ANYTHINGLLM_API_KEY}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        message: params.query,
        mode: mode
      })
    });

    if (!chatRes.ok) {
      const errText = await chatRes.text();
      return { error: `AnythingLLM chat error: ${chatRes.status} - ${errText}` };
    }

    const chatData = await chatRes.json();

    // Format response with sources
    let result = chatData.textResponse || chatData.response || 'No response';

    if (chatData.sources && chatData.sources.length > 0) {
      result += '\n\n---\nSources:\n';
      for (const source of chatData.sources) {
        result += `- ${source.title || source.name || 'Document'}\n`;
      }
    }

    metrics.recordQuery({
      tool: 'doc_query',
      route: 'anythingllm',
      tokensUsed: metrics.estimateTokens(result),
      tokensSaved: 0,
      latencyMs: Date.now() - startTime,
      cacheHit: false
    });

    return { result };
  } catch (error) {
    return { error: `AnythingLLM error: ${error.message}` };
  }
}

async function handleDocListWorkspaces() {
  try {
    const res = await fetch(`${ANYTHINGLLM_URL}/api/v1/workspaces`, {
      headers: { 'Authorization': `Bearer ${ANYTHINGLLM_API_KEY}` }
    });

    if (!res.ok) {
      return { error: `AnythingLLM API error: ${res.status}` };
    }

    const data = await res.json();
    const workspaces = data.workspaces || [];

    if (workspaces.length === 0) {
      return { result: 'No workspaces found. Create one in AnythingLLM first.' };
    }

    const formatted = workspaces.map(w =>
      `- ${w.name} (slug: ${w.slug})${w.documentCount ? ` - ${w.documentCount} docs` : ''}`
    ).join('\n');

    return { result: `AnythingLLM Workspaces:\n${formatted}` };
  } catch (error) {
    return { error: `AnythingLLM error: ${error.message}` };
  }
}

// --- Memory tool handlers (passthrough) ---

async function handleMemoryQuery(params, cwd) {
  // Validate query
  const queryCheck = validateQuery(params.query);
  if (!queryCheck.valid) {
    return { error: queryCheck.error };
  }

  const project = params.project || detectProject(cwd);
  if (!project) return { error: 'Could not detect project.' };

  // Validate project ID
  const projectCheck = validateProjectId(project);
  if (!projectCheck.valid) {
    return { error: projectCheck.error };
  }

  const output = await runPythonScript(path.join(MLX_TOOLS, 'query.py'), [project, queryCheck.query]);
  return { result: output };
}

async function handleMemorySearch(params, cwd) {
  const project = params.project || detectProject(cwd);
  if (!project) return { error: 'Could not detect project.' };

  // Use hybrid_search.py for semantic + BM25 search
  const args = [project, params.query];
  if (params.limit) args.push('--limit', String(params.limit));

  const output = await runPythonScript(path.join(MLX_TOOLS, 'hybrid_search.py'), args);
  return { result: output };
}

async function handleMemorySimilar(params, cwd) {
  const project = params.project || detectProject(cwd);
  if (!project) return { error: 'Could not detect project.' };

  // Use hybrid_search.py with "similar" mode
  const args = [project, 'similar', params.file];
  if (params.limit) args.push('--limit', String(params.limit));

  const output = await runPythonScript(path.join(MLX_TOOLS, 'hybrid_search.py'), args);
  return { result: output };
}

async function handleMemoryFunctions(params, cwd) {
  const project = params.project || detectProject(cwd);
  if (!project) return { error: 'Could not detect project.' };

  const functionsPath = path.join(MEMORY_ROOT, 'projects', project, 'functions.json');
  if (!fs.existsSync(functionsPath)) {
    return { error: `Functions index not found for project: ${project}` };
  }

  const functions = JSON.parse(fs.readFileSync(functionsPath, 'utf8'));
  const searchName = params.name.toLowerCase();
  const results = [];

  for (const [funcName, locations] of Object.entries(functions.functions || {})) {
    if (funcName.toLowerCase().includes(searchName)) {
      for (const loc of locations) {
        results.push({ name: funcName, file: loc.file, line: loc.line, type: loc.type || 'function' });
      }
    }
  }

  if (results.length === 0) return { result: `No functions found matching: ${params.name}` };

  const formatted = results.slice(0, 20).map(r => `${r.name}() [${r.type}] at ${r.file}:${r.line}`).join('\n');
  return { result: `Found ${results.length} function(s):\n${formatted}` };
}

async function handleMemoryHealth(params, cwd) {
  const project = params.project || detectProject(cwd);
  if (!project) return { error: 'Could not detect project.' };

  const config = loadConfig();
  const projectConfig = config.projects.find(p => p.id === project);
  if (!projectConfig) return { error: `Project not found: ${project}` };

  const action = params.action || 'status';
  const output = await runPythonScript(path.join(MLX_TOOLS, 'code_health.py'), [projectConfig.path, project, action]);
  return { result: output };
}

async function handleMemoryWireframe(params, cwd) {
  const project = params.project || detectProject(cwd);
  if (!project) return { error: 'Could not detect project.' };

  const format = params.format || 'summary';
  let args;
  if (params.screen) {
    args = [project, 'screen', params.screen];
  } else if (format === 'mermaid') {
    args = [project, 'flow'];
  } else if (format === 'full') {
    args = [project, 'export'];
  } else {
    args = [project, 'inventory'];
  }

  const output = await runPythonScript(path.join(MLX_TOOLS, 'wireframe_analyzer.py'), args);
  return { result: output };
}

async function handleMemorySessions(params, cwd) {
  const args = [];

  if (params.list_sessions) {
    args.push('--list-sessions');
    if (params.project) args.push('--project', params.project);
    if (params.limit) args.push('--limit', String(params.limit));
  } else if (params.session_id) {
    args.push('--session', params.session_id);
    if (params.project) args.push('--project', params.project);
  } else if (params.query) {
    args.push(params.query);
    if (params.project) args.push('--project', params.project);
    if (params.category) args.push('--category', params.category);
    if (params.limit) args.push('--limit', String(params.limit));
    args.push('--verbose');
  } else {
    return { error: 'Please provide a query, list_sessions=true, or session_id' };
  }

  const output = await runPythonScript(path.join(MLX_TOOLS, 'session_search.py'), args);
  return { result: output };
}

async function handleMemorySearchAll(params) {
  const args = [params.query];

  if (params.type) {
    args.push('--type', params.type);
  }
  if (params.limit) {
    args.push('--limit', String(params.limit));
  }

  const output = await runPythonScript(path.join(MLX_TOOLS, 'cross_search.py'), args);
  return { result: output };
}

// =============================================================================
// MCP SERVER
// =============================================================================

class MCPServer {
  constructor() {
    this.currentCwd = process.cwd();
  }

  handleRequest(request) {
    const { method, params, id } = request;

    // Notifications don't have an id and don't expect a response
    if (id === undefined) {
      // Handle known notifications silently
      if (method === 'notifications/initialized' || method === 'notifications/cancelled') {
        return null; // No response for notifications
      }
      // Unknown notification - log but don't respond
      return null;
    }

    switch (method) {
      case 'initialize':
        return this.handleInitialize(params, id);
      case 'tools/list':
        return this.handleToolsList(id);
      case 'tools/call':
        return this.handleToolCall(params, id);
      default:
        return this.errorResponse(id, -32601, `Method not found: ${method}`);
    }
  }

  handleInitialize(params, id) {
    if (params?.workingDirectory) {
      this.currentCwd = params.workingDirectory;
    }

    return {
      jsonrpc: '2.0',
      id,
      result: {
        protocolVersion: '2024-11-05',
        capabilities: { tools: {} },
        serverInfo: { name: 'claude-dash-gateway', version: '1.0.0' }
      }
    };
  }

  handleToolsList(id) {
    return {
      jsonrpc: '2.0',
      id,
      result: { tools: TOOLS }
    };
  }

  async handleToolCall(params, id) {
    const { name, arguments: args } = params;

    try {
      let result;
      switch (name) {
        // Smart tools
        case 'smart_read':
          result = await handleSmartRead(args, this.currentCwd);
          break;
        case 'smart_search':
          result = await handleSmartSearch(args, this.currentCwd);
          break;
        case 'smart_exec':
          result = await handleSmartExec(args, this.currentCwd);
          break;
        case 'smart_edit':
          result = await handleSmartEdit(args, this.currentCwd);
          break;
        case 'gateway_metrics':
          result = await handleGatewayMetrics(args);
          break;

        // Document RAG tools (AnythingLLM)
        case 'doc_query':
          result = await handleDocQuery(args);
          break;
        case 'doc_list_workspaces':
          result = await handleDocListWorkspaces();
          break;

        // Memory tools
        case 'memory_query':
          result = await handleMemoryQuery(args, this.currentCwd);
          break;
        case 'memory_search':
          result = await handleMemorySearch(args, this.currentCwd);
          break;
        case 'memory_similar':
          result = await handleMemorySimilar(args, this.currentCwd);
          break;
        case 'memory_functions':
          result = await handleMemoryFunctions(args, this.currentCwd);
          break;
        case 'memory_health':
          result = await handleMemoryHealth(args, this.currentCwd);
          break;
        case 'memory_wireframe':
          result = await handleMemoryWireframe(args, this.currentCwd);
          break;
        case 'memory_sessions':
          result = await handleMemorySessions(args, this.currentCwd);
          break;
        case 'memory_search_all':
          result = await handleMemorySearchAll(args);
          break;

        default:
          return this.errorResponse(id, -32602, `Unknown tool: ${name}`);
      }

      return {
        jsonrpc: '2.0',
        id,
        result: {
          content: [{ type: 'text', text: result.error || result.result }],
          isError: !!result.error
        }
      };
    } catch (error) {
      return {
        jsonrpc: '2.0',
        id,
        result: {
          content: [{ type: 'text', text: `Error: ${error.message}` }],
          isError: true
        }
      };
    }
  }

  errorResponse(id, code, message) {
    return { jsonrpc: '2.0', id, error: { code, message } };
  }
}

// =============================================================================
// MAIN
// =============================================================================

async function main() {
  const server = new MCPServer();

  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
    terminal: false
  });

  rl.on('line', async (line) => {
    try {
      const request = JSON.parse(line);
      const response = await server.handleRequest(request);
      // Only send response if not null (notifications return null)
      if (response !== null) {
        console.log(JSON.stringify(response));
      }
    } catch (error) {
      // Only send error response if we can extract an id
      const id = (() => { try { return JSON.parse(line).id; } catch { return null; } })();
      if (id !== undefined) {
        console.log(JSON.stringify({
          jsonrpc: '2.0',
          id,
          error: { code: -32700, message: 'Parse error' }
        }));
      }
    }
  });

  rl.on('close', () => {
    metrics.save();
    process.exit(0);
  });

  // Save metrics on exit
  process.on('SIGINT', () => {
    metrics.save();
    process.exit(0);
  });
}

main();
