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
const { routeRequest, TIERS, getRoutingStats, classifyQueryComplexity } = require(path.join(__dirname, 'router'));

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

  // --- LOCAL LLM (Ollama) - NON-CRITICAL ONLY ---
  {
    name: 'local_ask',
    description: 'NON-CRITICAL USE ONLY: commit messages, Enchanted API, personal queries. DO NOT use for code generation, debugging, or development work - use Claude (Sonnet) instead. Returns in 5-15s.',
    inputSchema: {
      type: 'object',
      properties: {
        question: { type: 'string', description: 'Question to ask the local LLM' },
        project: { type: 'string', description: 'Project ID for context (auto-detected if omitted)' },
        mode: {
          type: 'string',
          enum: ['rag', 'ask', 'explain', 'commit'],
          description: 'Mode: rag (with retrieval, default), ask (direct), explain (code), commit (message)'
        }
      },
      required: ['question']
    }
  },
  // local_review REMOVED - use Claude for code reviews

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
  {
    name: 'context_budget',
    description: 'Show HOT/WARM/COLD context tier breakdown with token counts and cost estimates.',
    inputSchema: {
      type: 'object',
      properties: {
        project: { type: 'string', description: 'Project ID (shows all projects if omitted)' },
        format: {
          type: 'string',
          enum: ['summary', 'detailed'],
          description: 'Output format (default: detailed)'
        }
      }
    }
  },
  {
    name: 'pattern_review',
    description: 'LLM-powered code validation against documented patterns (PATTERNS.md, decisions.json). Guardian-style semantic review.',
    inputSchema: {
      type: 'object',
      properties: {
        file: { type: 'string', description: 'File path to review (relative to project root)' },
        project: { type: 'string', description: 'Project ID (auto-detected if omitted)' },
        mode: {
          type: 'string',
          enum: ['normal', 'safe'],
          description: 'Mode: normal (all issues) or safe (high confidence >=70% only)'
        }
      },
      required: ['file']
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
        action: { type: 'string', enum: ['status', 'scan', 'repair'], description: 'Action type: status (current health), scan (run analysis), repair (auto-fix issues)' }
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
  },

  // --- ROADMAP TOOLS ---
  {
    name: 'memory_roadmap',
    description: 'Query or update project roadmap. Actions: status (view roadmap), next (get next tasks), complete (mark task done), add (add new task).',
    inputSchema: {
      type: 'object',
      properties: {
        project: { type: 'string', description: 'Project ID (auto-detected if omitted)' },
        action: {
          type: 'string',
          enum: ['status', 'next', 'complete', 'add'],
          description: 'Action to perform (default: status)'
        },
        id: { type: 'string', description: 'Task ID (for complete action)' },
        title: { type: 'string', description: 'Task title (for add action)' },
        priority: {
          type: 'string',
          enum: ['high', 'medium', 'low'],
          description: 'Task priority (for add action, default: medium)'
        }
      }
    }
  },

  // --- LEARNING TOOLS (new) ---
  {
    name: 'reasoning_query',
    description: 'Query ReasoningBank for past learning trajectories. Finds applicable solutions from similar problems solved before.',
    inputSchema: {
      type: 'object',
      properties: {
        context: { type: 'string', description: 'Current problem context' },
        domain: {
          type: 'string',
          enum: ['docker', 'auth', 'react', 'database', 'api', 'ui', 'performance', 'testing'],
          description: 'Optional domain filter'
        },
        limit: { type: 'number', description: 'Max results (default: 5)' }
      },
      required: ['context']
    }
  },
  {
    name: 'reasoning_capture',
    description: 'Capture a reasoning chain during conversation for future learning. Records the full cognitive journey: trigger → steps → conclusion.',
    inputSchema: {
      type: 'object',
      properties: {
        trigger: { type: 'string', description: 'What started this investigation' },
        steps: {
          type: 'array',
          description: 'The thinking process steps',
          items: {
            type: 'object',
            properties: {
              observation: { type: 'string', description: 'What was noticed/tried' },
              interpretation: { type: 'string', description: 'What it meant' },
              action: { type: 'string', description: 'What was done next (optional)' }
            },
            required: ['observation', 'interpretation']
          }
        },
        conclusion: { type: 'string', description: 'Final decision/solution' },
        outcome: { type: 'string', enum: ['success', 'partial', 'failure'], description: 'How it turned out' },
        domain: {
          type: 'string',
          enum: ['docker', 'auth', 'react', 'database', 'api', 'ui', 'performance', 'testing'],
          description: 'Problem domain (optional)'
        },
        project: { type: 'string', description: 'Project ID (optional, auto-detected)' },
        alternatives: {
          type: 'array',
          description: 'Options considered but rejected',
          items: {
            type: 'object',
            properties: {
              option: { type: 'string' },
              rejectedBecause: { type: 'string' }
            }
          }
        },
        constraints: { type: 'array', items: { type: 'string' }, description: 'What limited the choices' },
        revisitWhen: { type: 'array', items: { type: 'string' }, description: 'Conditions that would change this decision' },
        confidence: { type: 'number', minimum: 0, maximum: 1, description: 'Confidence level (0-1)' }
      },
      required: ['trigger', 'steps', 'conclusion', 'outcome']
    }
  },
  {
    name: 'reasoning_recall',
    description: 'Find past reasoning chains relevant to current problem. Returns the full cognitive journey with steps, alternatives, and revisit conditions.',
    inputSchema: {
      type: 'object',
      properties: {
        context: { type: 'string', description: 'Current problem description' },
        domain: {
          type: 'string',
          enum: ['docker', 'auth', 'react', 'database', 'api', 'ui', 'performance', 'testing'],
          description: 'Filter by domain'
        },
        project: { type: 'string', description: 'Filter by project' },
        limit: { type: 'number', description: 'Max results (default: 5)' }
      },
      required: ['context']
    }
  },
  {
    name: 'learning_status',
    description: 'Get learning system status: preferences, corrections, confidence calibration.',
    inputSchema: {
      type: 'object',
      properties: {
        component: {
          type: 'string',
          enum: ['all', 'preferences', 'corrections', 'confidence', 'reasoning'],
          description: 'Which component to check (default: all)'
        },
        project: { type: 'string', description: 'Project ID for project-specific learning' }
      }
    }
  },
  {
    name: 'workers_run',
    description: 'Run background workers manually: consolidation, freshness check, health check.',
    inputSchema: {
      type: 'object',
      properties: {
        worker: {
          type: 'string',
          enum: ['consolidate', 'freshness', 'health', 'all'],
          description: 'Which worker to run'
        },
        project: { type: 'string', description: 'Project ID (for freshness check)' }
      },
      required: ['worker']
    }
  },
  {
    name: 'hnsw_status',
    description: 'Get HNSW index status for all projects or rebuild indexes.',
    inputSchema: {
      type: 'object',
      properties: {
        action: {
          type: 'string',
          enum: ['status', 'rebuild', 'rebuild-all'],
          description: 'Action to perform (default: status)'
        },
        project: { type: 'string', description: 'Project ID (for single project rebuild)' }
      }
    }
  },

  // --- CROSS-PROJECT QUERY TOOL ---
  {
    name: 'project_query',
    description: 'Query another project\'s memory without switching contexts. Ask about auth patterns in GYST while working on CoachDesk, etc.',
    inputSchema: {
      type: 'object',
      properties: {
        project: {
          type: 'string',
          description: 'Target project ID to query (e.g., "gyst", "coachdesk")'
        },
        query: {
          type: 'string',
          description: 'Natural language question about the target project'
        },
        type: {
          type: 'string',
          enum: ['memory', 'functions', 'similar', 'decisions', 'patterns'],
          description: 'Query type: memory (hybrid search, default), functions (find functions), similar (find similar code), decisions (past decisions), patterns (code patterns)'
        }
      },
      required: ['project', 'query']
    }
  },

  // --- PM AGENT TOOLS ---
  {
    name: 'pm_portfolio',
    description: 'Get portfolio overview - project health, priorities, milestones across all projects.',
    inputSchema: {
      type: 'object',
      properties: {
        detail: {
          type: 'string',
          enum: ['summary', 'full'],
          description: 'Level of detail (default: full)'
        },
        project: { type: 'string', description: 'Optional: focus on specific project context' }
      }
    }
  },
  {
    name: 'pm_ask',
    description: 'Ask PM agent about priorities, what to work on, project status, or portfolio health.',
    inputSchema: {
      type: 'object',
      properties: {
        question: { type: 'string', description: 'Question about priorities, projects, or what to work on' },
        project: { type: 'string', description: 'Optional: current project context' }
      },
      required: ['question']
    }
  },

  // --- SELF-HEALING TOOLS ---
  {
    name: 'self_heal_check',
    description: 'Check system health for broken dependencies (missing models, broken imports, stale references). Run this after removing resources.',
    inputSchema: {
      type: 'object',
      properties: {
        verbose: { type: 'boolean', description: 'Show detailed output' }
      }
    }
  },
  {
    name: 'self_heal_analyze',
    description: 'Analyze impact of removing a resource. Shows what files would be affected and suggests fixes.',
    inputSchema: {
      type: 'object',
      properties: {
        resource_type: {
          type: 'string',
          enum: ['ollama_model', 'config_key', 'env_var', 'file'],
          description: 'Type of resource'
        },
        resource_id: { type: 'string', description: 'Resource identifier (e.g., "deepseek-coder:6.7b")' },
        replacement: { type: 'string', description: 'Optional replacement value' }
      },
      required: ['resource_id']
    }
  },
  {
    name: 'self_heal_fix',
    description: 'Apply fixes for broken dependencies. Creates backup before making changes.',
    inputSchema: {
      type: 'object',
      properties: {
        resource_id: { type: 'string', description: 'Resource to fix references for' },
        replacement: { type: 'string', description: 'What to replace it with' },
        dry_run: { type: 'boolean', description: 'Preview changes without applying (default: true)' },
        min_confidence: { type: 'number', description: 'Minimum confidence to apply fix (0-1, default: 0.5)' }
      },
      required: ['resource_id', 'replacement']
    }
  },
  {
    name: 'self_heal_rollback',
    description: 'Rollback self-healing changes from a backup.',
    inputSchema: {
      type: 'object',
      properties: {
        backup_id: { type: 'string', description: 'Backup timestamp to rollback (use self_heal_check to list backups)' }
      },
      required: ['backup_id']
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

      const summary = summaries.files?.[relativePath] || summaries.files?.[filePath];

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

// --- LOCAL LLM HANDLERS ---

async function handleLocalAsk(params, cwd) {
  const startTime = Date.now();
  const project = params.project || detectProject(cwd);
  const mode = params.mode || 'rag';
  const question = params.question;

  if (!question) {
    return { error: 'Question is required' };
  }

  try {
    let scriptPath;
    let args;

    switch (mode) {
      case 'rag':
        // Use RAG pipeline for context-aware answers
        scriptPath = path.join(MLX_TOOLS, 'rag_pipeline.py');
        args = project ? [project, question] : ['general', question];
        break;
      case 'ask':
        // Direct ask without RAG
        scriptPath = path.join(MLX_TOOLS, 'ask.py');
        args = project ? [project, question] : [question];
        break;
      case 'explain':
        // Code explanation mode
        scriptPath = path.join(MLX_TOOLS, 'code_analyzer.py');
        args = project ? [project, question, 'explain'] : [question, 'explain'];
        break;
      case 'commit':
        // Commit message generation
        scriptPath = path.join(MLX_TOOLS, 'commit_helper.py');
        args = [];
        break;
      default:
        scriptPath = path.join(MLX_TOOLS, 'rag_pipeline.py');
        args = project ? [project, question] : ['general', question];
    }

    const output = await runPythonScript(scriptPath, args, 60000); // 60s timeout for LLM

    const tokensUsed = metrics.estimateTokens(output);

    metrics.recordQuery({
      tool: 'local_ask',
      route: 'ollama',
      tokensUsed,
      tokensSaved: tokensUsed * 10, // Estimate: local is ~10x cheaper
      latencyMs: Date.now() - startTime,
      cacheHit: false
    });

    return { result: `[Local LLM - FREE]\n\n${output}` };
  } catch (error) {
    return { error: `Local LLM error: ${error.message}` };
  }
}

// handleLocalReview REMOVED - use Claude for code reviews

async function handlePatternReview(params, cwd) {
  const project = params?.project || detectProject(cwd);
  if (!project) {
    return { error: 'Could not detect project. Please specify project ID.' };
  }

  const file = params?.file;
  if (!file) {
    return { error: 'File path is required.' };
  }

  const mode = params?.mode || 'normal';

  try {
    const output = await runPythonScript(
      path.join(MLX_TOOLS, 'pattern_review.py'),
      [project, file, mode],
      60000  // 60s timeout for LLM
    );
    return { result: output };
  } catch (error) {
    return { error: `Pattern review error: ${error.message}` };
  }
}

async function handleContextBudget(params, cwd) {
  const project = params?.project || detectProject(cwd);
  const format = params?.format || 'detailed';

  try {
    const args = project ? [project] : [];
    const output = await runPythonScript(path.join(MLX_TOOLS, 'context_budget.py'), args);

    if (format === 'summary' && project) {
      // Parse and return compact summary
      const data = JSON.parse(output);
      const summary = data.summary || {};
      return {
        result: `Context Budget for ${project}:
  HOT:  ${summary.hotTokens || 0} tokens (always loaded)
  WARM: ${summary.warmTokens || 0} tokens (on-demand)
  COLD: ${summary.coldTokens || 0} tokens (full files)
  Savings: ${summary.savingsPercentage || '0%'}
  Est. cost: ${data.costs?.perSession || '$0'}/session`
      };
    }

    return { result: output };
  } catch (error) {
    return { error: `Context budget error: ${error.message}` };
  }
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
  const routingStats = getRoutingStats(metrics);

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

  // Handle repair action separately
  if (action === 'repair') {
    const output = await runPythonScript(path.join(MLX_TOOLS, 'memory_repair.py'), [project]);
    return { result: output };
  }

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

// --- Roadmap tool handler ---

async function handleMemoryRoadmap(params, cwd) {
  const project = params.project || detectProject(cwd);
  if (!project) {
    return { error: 'Could not detect project. Please specify project ID.' };
  }

  const action = params.action || 'status';
  const roadmapLoaderPath = path.join(MEMORY_ROOT, 'memory', 'roadmap_loader.py');

  if (!fs.existsSync(roadmapLoaderPath)) {
    return { error: 'Roadmap loader not installed.' };
  }

  const roadmapPath = path.join(MEMORY_ROOT, 'projects', project, 'roadmap.json');
  if (!fs.existsSync(roadmapPath) && action !== 'add') {
    return { error: `No roadmap found for project: ${project}. Create one at ${roadmapPath}` };
  }

  try {
    let args = [project, action];

    if (action === 'complete' && params.id) {
      args.push(params.id);
    } else if (action === 'add' && params.title) {
      args.push(params.title);
      if (params.priority) {
        args.push(params.priority);
      }
    }

    const output = await runPythonScript(roadmapLoaderPath, args);
    return { result: output };
  } catch (error) {
    return { error: `Roadmap error: ${error.message}` };
  }
}

// --- Learning tool handlers ---

async function handleReasoningQuery(params) {
  const startTime = Date.now();

  const args = [params.context];
  if (params.domain) {
    args.push('--domain', params.domain);
  }
  if (params.limit) {
    args.push('--limit', String(params.limit));
  }

  try {
    const reasoningBankPath = path.join(MEMORY_ROOT, 'learning', 'reasoning_bank.py');
    if (!fs.existsSync(reasoningBankPath)) {
      return { error: 'ReasoningBank not installed. Run learning system setup.' };
    }

    const output = await runPythonScript(reasoningBankPath, ['query', ...args]);

    metrics.recordQuery({
      tool: 'reasoning_query',
      route: 'learning',
      tokensUsed: metrics.estimateTokens(output),
      tokensSaved: 0,
      latencyMs: Date.now() - startTime,
      cacheHit: false
    });

    return { result: output || 'No relevant learning trajectories found.' };
  } catch (error) {
    return { error: `ReasoningBank error: ${error.message}` };
  }
}

async function handleReasoningCapture(params, cwd) {
  const startTime = Date.now();
  const project = params.project || detectProject(cwd);

  // Build the chain data
  const chainData = {
    trigger: params.trigger,
    steps: params.steps,
    conclusion: params.conclusion,
    outcome: params.outcome,
    domain: params.domain,
    project: project,
    alternatives: params.alternatives || [],
    constraints: params.constraints || [],
    revisitWhen: params.revisitWhen || [],
    confidence: params.confidence || 0.8
  };

  try {
    const chainsPath = path.join(MEMORY_ROOT, 'learning', 'reasoning_chains.py');
    if (!fs.existsSync(chainsPath)) {
      return { error: 'Reasoning chains module not installed.' };
    }

    const output = await runPythonScript(chainsPath, ['capture', JSON.stringify(chainData)]);

    metrics.recordQuery({
      tool: 'reasoning_capture',
      route: 'learning',
      tokensUsed: metrics.estimateTokens(output),
      tokensSaved: 0,
      latencyMs: Date.now() - startTime,
      cacheHit: false
    });

    return { result: output };
  } catch (error) {
    return { error: `Reasoning capture error: ${error.message}` };
  }
}

async function handleReasoningRecall(params, cwd) {
  const startTime = Date.now();
  const project = params.project || detectProject(cwd);

  const args = ['recall', params.context, '--json'];
  if (params.domain) {
    args.push('--domain', params.domain);
  }
  if (project) {
    args.push('--project', project);
  }
  if (params.limit) {
    args.push('--limit', String(params.limit));
  }

  try {
    const chainsPath = path.join(MEMORY_ROOT, 'learning', 'reasoning_chains.py');
    if (!fs.existsSync(chainsPath)) {
      return { error: 'Reasoning chains module not installed.' };
    }

    const output = await runPythonScript(chainsPath, args);

    // Parse JSON output and format for readability
    let chains;
    try {
      chains = JSON.parse(output);
    } catch {
      return { result: output };  // Return raw if not JSON
    }

    if (!chains || chains.length === 0) {
      return { result: 'No relevant reasoning chains found.' };
    }

    // Format for human readability
    const formatted = chains.map((chain, i) => {
      let text = `\n## ${i + 1}. ${chain.trigger}\n`;
      text += `**Conclusion:** ${chain.conclusion}\n`;
      text += `**Outcome:** ${chain.outcome}\n`;
      text += '**Journey:**\n';
      for (let j = 0; j < (chain.steps || []).length; j++) {
        const step = chain.steps[j];
        text += `  ${j + 1}. ${step.observation} → ${step.interpretation}\n`;
      }
      if (chain.alternatives && chain.alternatives.length > 0) {
        text += '**Alternatives considered:**\n';
        for (const alt of chain.alternatives) {
          text += `  - ${alt.option}: rejected because ${alt.rejectedBecause}\n`;
        }
      }
      if (chain.revisitWhen && chain.revisitWhen.length > 0) {
        text += `**Revisit if:** ${chain.revisitWhen.join(', ')}\n`;
      }
      return text;
    }).join('\n');

    metrics.recordQuery({
      tool: 'reasoning_recall',
      route: 'learning',
      tokensUsed: metrics.estimateTokens(formatted),
      tokensSaved: 0,
      latencyMs: Date.now() - startTime,
      cacheHit: false
    });

    return { result: `Found ${chains.length} relevant reasoning chain(s):\n${formatted}` };
  } catch (error) {
    return { error: `Reasoning recall error: ${error.message}` };
  }
}

async function handleLearningStatus(params, cwd) {
  const component = params.component || 'all';
  const project = params.project || detectProject(cwd);

  const results = [];

  try {
    // Preferences status
    if (component === 'all' || component === 'preferences') {
      const prefsPath = path.join(MEMORY_ROOT, 'learning', 'preference_learner.py');
      if (fs.existsSync(prefsPath)) {
        try {
          const output = await runPythonScript(prefsPath, ['--get-preferences']);
          results.push(`=== Learned Preferences ===\n${output || 'None yet'}`);
        } catch (e) {
          results.push(`=== Preferences ===\nError: ${e.message}`);
        }
      }
    }

    // Corrections status
    if (component === 'all' || component === 'corrections') {
      const correctionsPath = path.join(MEMORY_ROOT, 'learning', 'corrections.json');
      if (fs.existsSync(correctionsPath)) {
        const data = JSON.parse(fs.readFileSync(correctionsPath, 'utf8'));
        const count = data.corrections?.length || 0;
        const patterns = Object.keys(data.patterns || {}).length;
        results.push(`=== Corrections ===\nRecorded: ${count}\nPatterns: ${patterns}`);
      } else {
        results.push(`=== Corrections ===\nNo corrections recorded yet.`);
      }
    }

    // Confidence calibration
    if (component === 'all' || component === 'confidence') {
      const confPath = path.join(MEMORY_ROOT, 'learning', 'confidence_calibration.py');
      if (fs.existsSync(confPath)) {
        try {
          const output = await runPythonScript(confPath, ['--weak-areas']);
          results.push(`=== Confidence Calibration ===\n${output || 'No weak areas identified'}`);
        } catch (e) {
          results.push(`=== Confidence ===\nError: ${e.message}`);
        }
      }
    }

    // ReasoningBank status
    if (component === 'all' || component === 'reasoning') {
      const reasoningPath = path.join(MEMORY_ROOT, 'learning', 'reasoning_bank.json');
      if (fs.existsSync(reasoningPath)) {
        const data = JSON.parse(fs.readFileSync(reasoningPath, 'utf8'));
        const trajectories = data.trajectories?.length || 0;
        const patterns = data.patterns?.length || 0;
        results.push(`=== ReasoningBank ===\nTrajectories: ${trajectories}\nDistilled Patterns: ${patterns}`);
      } else {
        results.push(`=== ReasoningBank ===\nNo learning trajectories yet.`);
      }
    }

    return { result: results.join('\n\n') };
  } catch (error) {
    return { error: `Learning status error: ${error.message}` };
  }
}

async function handleWorkersRun(params, cwd) {
  const worker = params.worker;
  const project = params.project || detectProject(cwd);

  const workersPath = path.join(MEMORY_ROOT, 'workers', 'background_workers.py');
  if (!fs.existsSync(workersPath)) {
    return { error: 'Background workers not installed.' };
  }

  const results = [];

  try {
    if (worker === 'all' || worker === 'consolidate') {
      const output = await runPythonScript(workersPath, ['consolidate']);
      results.push(`=== Consolidation ===\n${output}`);
    }

    if (worker === 'all' || worker === 'freshness') {
      const args = ['freshness'];
      if (project) args.push('--project', project);
      const output = await runPythonScript(workersPath, args);
      results.push(`=== Freshness Check ===\n${output}`);
    }

    if (worker === 'all' || worker === 'health') {
      const output = await runPythonScript(workersPath, ['health']);
      results.push(`=== Health Check ===\n${output}`);
    }

    return { result: results.join('\n\n') };
  } catch (error) {
    return { error: `Worker error: ${error.message}` };
  }
}

async function handleHnswStatus(params) {
  const action = params.action || 'status';
  const hnswPath = path.join(MLX_TOOLS, 'hnsw_index.py');

  if (!fs.existsSync(hnswPath)) {
    return { error: 'HNSW index module not found.' };
  }

  try {
    if (action === 'status') {
      // Get status for all projects
      const config = loadConfig();
      const results = [];

      for (const project of config.projects || []) {
        const indexPath = path.join(MEMORY_ROOT, 'indexes', `${project.id}.hnsw`);
        const metaPath = path.join(MEMORY_ROOT, 'indexes', `${project.id}.meta`);

        if (fs.existsSync(indexPath) && fs.existsSync(metaPath)) {
          const stats = fs.statSync(indexPath);
          const age = Math.round((Date.now() - stats.mtimeMs) / 1000 / 60);
          results.push(`${project.id}: ✓ (${Math.round(stats.size / 1024)}KB, ${age}m old)`);
        } else {
          results.push(`${project.id}: ✗ (no index)`);
        }
      }

      return { result: `=== HNSW Index Status ===\n${results.join('\n')}` };
    } else if (action === 'rebuild') {
      if (!params.project) {
        return { error: 'Project ID required for single rebuild. Use rebuild-all for all projects.' };
      }
      const output = await runPythonScript(hnswPath, ['build', params.project]);
      return { result: output };
    } else if (action === 'rebuild-all') {
      const output = await runPythonScript(hnswPath, ['build-all']);
      return { result: output };
    }

    return { error: `Unknown action: ${action}` };
  } catch (error) {
    return { error: `HNSW error: ${error.message}` };
  }
}

// --- PM Agent tool handlers ---

async function handlePmPortfolio(params, cwd) {
  const detail = params?.detail || 'full';
  const project = params?.project || detectProject(cwd);
  const pmAgentPath = path.join(MEMORY_ROOT, 'pm', 'pm_agent.py');

  if (!fs.existsSync(pmAgentPath)) {
    return { error: 'PM Agent not installed.' };
  }

  try {
    const args = project ? [project, 'portfolio', detail] : ['_', 'portfolio', detail];
    const output = await runPythonScript(pmAgentPath, args);
    return { result: output || 'No portfolio data available.' };
  } catch (error) {
    return { error: `PM Agent error: ${error.message}` };
  }
}

async function handlePmAsk(params, cwd) {
  const question = params?.question;
  if (!question) {
    return { error: 'Question is required.' };
  }

  const project = params?.project || detectProject(cwd);
  const pmAgentPath = path.join(MEMORY_ROOT, 'pm', 'pm_agent.py');

  if (!fs.existsSync(pmAgentPath)) {
    return { error: 'PM Agent not installed.' };
  }

  try {
    const args = project ? [project, 'ask', question] : ['_', 'ask', question];
    const output = await runPythonScript(pmAgentPath, args);
    return { result: output || 'No answer available.' };
  } catch (error) {
    return { error: `PM Agent error: ${error.message}` };
  }
}

// =============================================================================
// SELF-HEALING HANDLERS
// =============================================================================

async function handleSelfHealCheck(params) {
  const analyzerPath = path.join(MEMORY_ROOT, 'memory', 'self_healing', 'analyzer.py');
  const registryPath = path.join(MEMORY_ROOT, 'memory', 'self_healing', 'registry.py');
  const fixerPath = path.join(MEMORY_ROOT, 'memory', 'self_healing', 'fixer.py');

  if (!fs.existsSync(analyzerPath)) {
    return { error: 'Self-healing system not installed.' };
  }

  try {
    // Run health scan
    const scanOutput = await runPythonScript(analyzerPath, ['scan']);

    // Also list backups
    let backupsOutput = '';
    if (fs.existsSync(fixerPath)) {
      try {
        backupsOutput = await runPythonScript(fixerPath, ['backups']);
        if (backupsOutput && !backupsOutput.includes('No backups')) {
          backupsOutput = '\n\nAvailable rollback points:\n' + backupsOutput;
        } else {
          backupsOutput = '';
        }
      } catch (e) {
        // Ignore backup listing errors
      }
    }

    return { result: scanOutput + backupsOutput };
  } catch (error) {
    return { error: `Health check failed: ${error.message}` };
  }
}

async function handleSelfHealAnalyze(params) {
  const resourceId = params?.resource_id;
  if (!resourceId) {
    return { error: 'resource_id is required.' };
  }

  const analyzerPath = path.join(MEMORY_ROOT, 'memory', 'self_healing', 'analyzer.py');
  if (!fs.existsSync(analyzerPath)) {
    return { error: 'Self-healing system not installed.' };
  }

  try {
    const args = ['analyze', resourceId];
    if (params.replacement) {
      args.push(params.replacement);
    }

    const output = await runPythonScript(analyzerPath, args);
    return { result: output || 'No impacts found.' };
  } catch (error) {
    return { error: `Analysis failed: ${error.message}` };
  }
}

async function handleSelfHealFix(params) {
  const resourceId = params?.resource_id;
  const replacement = params?.replacement;

  if (!resourceId || !replacement) {
    return { error: 'resource_id and replacement are required.' };
  }

  const fixerPath = path.join(MEMORY_ROOT, 'memory', 'self_healing', 'fixer.py');
  if (!fs.existsSync(fixerPath)) {
    return { error: 'Self-healing system not installed.' };
  }

  try {
    const args = ['fix', resourceId, replacement];

    // Default to dry_run unless explicitly set to false
    const dryRun = params.dry_run !== false;
    if (!dryRun) {
      args.push('--apply');
    }

    const output = await runPythonScript(fixerPath, args);
    return { result: output };
  } catch (error) {
    return { error: `Fix operation failed: ${error.message}` };
  }
}

async function handleSelfHealRollback(params) {
  const backupId = params?.backup_id;
  if (!backupId) {
    return { error: 'backup_id is required.' };
  }

  const fixerPath = path.join(MEMORY_ROOT, 'memory', 'self_healing', 'fixer.py');
  if (!fs.existsSync(fixerPath)) {
    return { error: 'Self-healing system not installed.' };
  }

  // Construct backup path
  const backupPath = path.join(MEMORY_ROOT, 'backups', 'self_heal', backupId);
  if (!fs.existsSync(backupPath)) {
    return { error: `Backup not found: ${backupId}` };
  }

  try {
    const output = await runPythonScript(fixerPath, ['rollback', backupPath]);
    return { result: output };
  } catch (error) {
    return { error: `Rollback failed: ${error.message}` };
  }
}

// --- Cross-Project Query Handler ---

async function handleProjectQuery(params, cwd) {
  const startTime = Date.now();
  const targetProject = params.project;
  const query = params.query;
  const queryType = params.type || 'memory';

  // Validate project ID
  const projectCheck = validateProjectId(targetProject);
  if (!projectCheck.valid) {
    return { error: projectCheck.error };
  }

  // Validate query
  const queryCheck = validateQuery(query);
  if (!queryCheck.valid) {
    return { error: queryCheck.error };
  }

  // Check if project exists in config
  const config = loadConfig();
  const projectConfig = config.projects.find(p => p.id === targetProject);
  if (!projectConfig) {
    const availableProjects = config.projects.map(p => p.id).join(', ');
    return { error: `Project not found: ${targetProject}. Available projects: ${availableProjects}` };
  }

  // Get current project for context prefix
  const currentProject = detectProject(cwd);
  const contextPrefix = currentProject && currentProject !== targetProject
    ? `[Cross-project query: ${currentProject} → ${targetProject}]\n\n`
    : `[Query: ${targetProject}]\n\n`;

  try {
    let result;

    switch (queryType) {
      case 'memory':
        // Use hybrid search (BM25 + semantic)
        const memoryOutput = await runPythonScript(
          path.join(MLX_TOOLS, 'query.py'),
          [targetProject, queryCheck.query]
        );
        result = contextPrefix + memoryOutput;
        break;

      case 'functions':
        // Search functions.json directly
        const functionsPath = path.join(MEMORY_ROOT, 'projects', targetProject, 'functions.json');
        if (!fs.existsSync(functionsPath)) {
          return { error: `Functions index not found for project: ${targetProject}` };
        }
        const functions = JSON.parse(fs.readFileSync(functionsPath, 'utf8'));
        const searchTerm = queryCheck.query.toLowerCase();
        const funcResults = [];

        for (const [funcName, locations] of Object.entries(functions.functions || {})) {
          if (funcName.toLowerCase().includes(searchTerm)) {
            for (const loc of locations) {
              funcResults.push({ name: funcName, file: loc.file, line: loc.line, type: loc.type || 'function' });
            }
          }
        }

        if (funcResults.length === 0) {
          result = contextPrefix + `No functions found matching: ${query}`;
        } else {
          const formatted = funcResults.slice(0, 20).map(r =>
            `${r.name}() [${r.type}] at ${r.file}:${r.line}`
          ).join('\n');
          result = contextPrefix + `Found ${funcResults.length} function(s) in ${targetProject}:\n${formatted}`;
        }
        break;

      case 'similar':
        // Find similar files using hybrid search
        const similarOutput = await runPythonScript(
          path.join(MLX_TOOLS, 'hybrid_search.py'),
          [targetProject, queryCheck.query, '--limit', '10']
        );
        result = contextPrefix + similarOutput;
        break;

      case 'decisions':
        // Search past decisions
        const decisionsPath = path.join(MEMORY_ROOT, 'projects', targetProject, 'decisions.json');
        if (!fs.existsSync(decisionsPath)) {
          return { error: `No decisions recorded for project: ${targetProject}` };
        }
        const decisions = JSON.parse(fs.readFileSync(decisionsPath, 'utf8'));
        const searchLower = queryCheck.query.toLowerCase();

        const matchingDecisions = (decisions.decisions || []).filter(d => {
          const searchText = `${d.summary || ''} ${d.reason || ''} ${d.context || ''}`.toLowerCase();
          return searchLower.split(' ').some(term => searchText.includes(term));
        });

        if (matchingDecisions.length === 0) {
          result = contextPrefix + `No decisions found matching: ${query}`;
        } else {
          const formatted = matchingDecisions.slice(0, 10).map(d =>
            `• ${d.summary}\n  Reason: ${d.reason || 'Not specified'}\n  Date: ${d.date || 'Unknown'}`
          ).join('\n\n');
          result = contextPrefix + `Found ${matchingDecisions.length} decision(s) in ${targetProject}:\n\n${formatted}`;
        }
        break;

      case 'patterns':
        // Search observations for patterns
        const observationsPath = path.join(MEMORY_ROOT, 'projects', targetProject, 'observations.json');
        if (!fs.existsSync(observationsPath)) {
          return { error: `No observations recorded for project: ${targetProject}` };
        }
        const observations = JSON.parse(fs.readFileSync(observationsPath, 'utf8'));
        const patternSearch = queryCheck.query.toLowerCase();

        const matchingPatterns = (observations.observations || []).filter(o => {
          if (o.type !== 'pattern' && o.type !== 'implementation') return false;
          const searchText = `${o.content || ''} ${o.summary || ''}`.toLowerCase();
          return patternSearch.split(' ').some(term => searchText.includes(term));
        });

        if (matchingPatterns.length === 0) {
          result = contextPrefix + `No patterns found matching: ${query}`;
        } else {
          const formatted = matchingPatterns.slice(0, 10).map(p =>
            `• ${p.summary || p.content?.substring(0, 100) || 'No summary'}`
          ).join('\n');
          result = contextPrefix + `Found ${matchingPatterns.length} pattern(s) in ${targetProject}:\n${formatted}`;
        }
        break;

      default:
        return { error: `Unknown query type: ${queryType}` };
    }

    const tokensUsed = metrics.estimateTokens(result);

    metrics.recordQuery({
      tool: 'project_query',
      route: 'memory',
      tokensUsed,
      tokensSaved: tokensUsed, // Would have been context switch + multiple queries
      latencyMs: Date.now() - startTime,
      cacheHit: false
    });

    return { result };
  } catch (error) {
    return { error: `Cross-project query error: ${error.message}` };
  }
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

        // Local LLM tools (Ollama - FREE, non-critical only)
        case 'local_ask':
          result = await handleLocalAsk(args, this.currentCwd);
          break;
        // local_review REMOVED - use Claude for code reviews

        case 'gateway_metrics':
          result = await handleGatewayMetrics(args);
          break;
        case 'context_budget':
          result = await handleContextBudget(args, this.currentCwd);
          break;
        case 'pattern_review':
          result = await handlePatternReview(args, this.currentCwd);
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

        // Roadmap tool
        case 'memory_roadmap':
          result = await handleMemoryRoadmap(args, this.currentCwd);
          break;

        // Learning tools
        case 'reasoning_query':
          result = await handleReasoningQuery(args);
          break;
        case 'reasoning_capture':
          result = await handleReasoningCapture(args, this.currentCwd);
          break;
        case 'reasoning_recall':
          result = await handleReasoningRecall(args, this.currentCwd);
          break;
        case 'learning_status':
          result = await handleLearningStatus(args, this.currentCwd);
          break;
        case 'workers_run':
          result = await handleWorkersRun(args, this.currentCwd);
          break;
        case 'hnsw_status':
          result = await handleHnswStatus(args);
          break;

        // PM Agent tools
        case 'pm_portfolio':
          result = await handlePmPortfolio(args, this.currentCwd);
          break;
        case 'pm_ask':
          result = await handlePmAsk(args, this.currentCwd);
          break;

        // Cross-project query tool
        case 'project_query':
          result = await handleProjectQuery(args, this.currentCwd);
          break;

        // Self-healing tools
        case 'self_heal_check':
          result = await handleSelfHealCheck(args);
          break;
        case 'self_heal_analyze':
          result = await handleSelfHealAnalyze(args);
          break;
        case 'self_heal_fix':
          result = await handleSelfHealFix(args);
          break;
        case 'self_heal_rollback':
          result = await handleSelfHealRollback(args);
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
