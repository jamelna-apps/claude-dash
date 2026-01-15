#!/usr/bin/env node
/**
 * Claude-Dash MCP Server (DEPRECATED)
 *
 * ⚠️  DEPRECATED: Use gateway/server.js instead!
 * The gateway provides all these tools plus:
 * - Caching (smart_read, smart_exec)
 * - Metrics tracking
 * - AnythingLLM integration (doc_query)
 *
 * This file is kept for backwards compatibility only.
 * Configure claude-dash-gateway in your MCP settings instead.
 *
 * Original description:
 * Exposes memory tools (query, search, similar, health) as native Claude tools
 * via the Model Context Protocol (MCP).
 *
 * Transport: stdio
 */

const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const readline = require('readline');

const MEMORY_ROOT = path.join(process.env.HOME, '.claude-dash');
const MLX_TOOLS = path.join(MEMORY_ROOT, 'mlx-tools');
const CONFIG_PATH = path.join(MEMORY_ROOT, 'config.json');

// Load config to get project list
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
  // Try to infer from directory name
  if (workingDir) {
    const dirName = path.basename(workingDir).toLowerCase().replace(/\s+/g, '-');
    const found = config.projects.find(p => p.id === dirName || p.path.endsWith(dirName));
    if (found) return found.id;
  }
  return null;
}

// Run a Python script and return output
function runPythonScript(scriptPath, args) {
  return new Promise((resolve, reject) => {
    const venvPython = path.join(MEMORY_ROOT, 'mlx-env', 'bin', 'python3');
    const pythonCmd = fs.existsSync(venvPython) ? venvPython : 'python3';

    const proc = spawn(pythonCmd, [scriptPath, ...args], {
      cwd: MLX_TOOLS,
      env: { ...process.env, PYTHONIOENCODING: 'utf-8' }
    });

    let stdout = '';
    let stderr = '';

    proc.stdout.on('data', (data) => { stdout += data.toString(); });
    proc.stderr.on('data', (data) => { stderr += data.toString(); });

    proc.on('close', (code) => {
      if (code === 0) {
        resolve(stdout.trim());
      } else {
        reject(new Error(stderr || `Process exited with code ${code}`));
      }
    });

    proc.on('error', reject);
  });
}

// Tool definitions
const TOOLS = [
  {
    name: 'memory_query',
    description: 'Query project memory to find files, functions, schema, or navigation info. Use this BEFORE using Glob/Grep to search the codebase - it often has the answer already indexed. Uses hybrid search (BM25 + semantic) for accurate results on both exact matches and conceptual queries.',
    inputSchema: {
      type: 'object',
      properties: {
        query: {
          type: 'string',
          description: 'Natural language question about the codebase (e.g., "where is the login screen?", "what collections store user data?")'
        },
        project: {
          type: 'string',
          description: 'Project ID (e.g., "gyst"). If not provided, auto-detected from working directory.'
        }
      },
      required: ['query']
    }
  },
  {
    name: 'memory_search',
    description: 'Semantic search across project files using embeddings. Finds files by meaning/concept, not keywords. Use memory_query for hybrid search (keywords + semantic).',
    inputSchema: {
      type: 'object',
      properties: {
        query: {
          type: 'string',
          description: 'Search query (e.g., "user authentication", "payment processing")'
        },
        project: {
          type: 'string',
          description: 'Project ID. If not provided, auto-detected.'
        },
        limit: {
          type: 'number',
          description: 'Max results to return (default: 10)'
        }
      },
      required: ['query']
    }
  },
  {
    name: 'memory_similar',
    description: 'Find files similar to a given file. Useful for finding related code, tests, or documentation.',
    inputSchema: {
      type: 'object',
      properties: {
        file: {
          type: 'string',
          description: 'Path to the file to find similar files for'
        },
        project: {
          type: 'string',
          description: 'Project ID. If not provided, auto-detected.'
        },
        limit: {
          type: 'number',
          description: 'Max results to return (default: 5)'
        }
      },
      required: ['file']
    }
  },
  {
    name: 'memory_health',
    description: 'Get code health status for a project - complexity issues, large files, etc.',
    inputSchema: {
      type: 'object',
      properties: {
        project: {
          type: 'string',
          description: 'Project ID. If not provided, auto-detected.'
        },
        action: {
          type: 'string',
          enum: ['status', 'scan'],
          description: 'Action: "status" for cached results, "scan" to run fresh analysis'
        }
      }
    }
  },
  {
    name: 'memory_functions',
    description: 'Look up function/method definitions by name. Returns file path and line number.',
    inputSchema: {
      type: 'object',
      properties: {
        name: {
          type: 'string',
          description: 'Function or method name to look up (partial match supported)'
        },
        project: {
          type: 'string',
          description: 'Project ID. If not provided, auto-detected.'
        }
      },
      required: ['name']
    }
  },
  {
    name: 'memory_wireframe',
    description: 'Get wireframe data for app design: screen inventory, navigation flow, data dependencies. Use before designing new screens or understanding app structure.',
    inputSchema: {
      type: 'object',
      properties: {
        project: {
          type: 'string',
          description: 'Project ID. If not provided, auto-detected.'
        },
        screen: {
          type: 'string',
          description: 'Optional: Get detailed info for a specific screen name'
        },
        format: {
          type: 'string',
          enum: ['summary', 'full', 'mermaid'],
          description: 'Output format: summary (screen list), full (all data), mermaid (navigation flowchart)'
        }
      }
    }
  },
  {
    name: 'memory_sessions',
    description: 'Search past session observations to find decisions made, bugs fixed, patterns learned. Use to recall "what did we decide about X?" or "how did we fix Y?"',
    inputSchema: {
      type: 'object',
      properties: {
        query: {
          type: 'string',
          description: 'Search query (e.g., "PID file", "authentication", "memory leak")'
        },
        project: {
          type: 'string',
          description: 'Filter by project ID. If not provided, searches all projects.'
        },
        category: {
          type: 'string',
          enum: ['decision', 'pattern', 'bugfix', 'gotcha', 'feature', 'implementation'],
          description: 'Filter by observation category'
        },
        list_sessions: {
          type: 'boolean',
          description: 'List recent sessions instead of searching'
        },
        session_id: {
          type: 'string',
          description: 'Get details for a specific session ID'
        },
        limit: {
          type: 'number',
          description: 'Max results to return (default: 10)'
        }
      }
    }
  }
];

// Tool handlers
async function handleMemoryQuery(params, cwd) {
  const project = params.project || detectProject(cwd);
  if (!project) {
    return { error: 'Could not detect project. Please specify project ID.' };
  }

  const output = await runPythonScript(
    path.join(MLX_TOOLS, 'query.py'),
    [project, params.query]
  );
  return { result: output };
}

async function handleMemorySearch(params, cwd) {
  const project = params.project || detectProject(cwd);
  if (!project) {
    return { error: 'Could not detect project. Please specify project ID.' };
  }

  const embeddingsPath = path.join(MEMORY_ROOT, 'projects', project, 'embeddings_v2.json');
  const scriptPath = fs.existsSync(embeddingsPath)
    ? path.join(MLX_TOOLS, 'embeddings_v2.py')
    : path.join(MLX_TOOLS, 'semantic_search.py');

  const args = [project, 'search', params.query];
  if (params.limit) args.push('--limit', String(params.limit));

  const output = await runPythonScript(scriptPath, args);
  return { result: output };
}

async function handleMemorySimilar(params, cwd) {
  const project = params.project || detectProject(cwd);
  if (!project) {
    return { error: 'Could not detect project. Please specify project ID.' };
  }

  const args = [project, 'similar', params.file];
  if (params.limit) args.push('--limit', String(params.limit));

  const output = await runPythonScript(
    path.join(MLX_TOOLS, 'semantic_search.py'),
    args
  );
  return { result: output };
}

async function handleMemoryHealth(params, cwd) {
  const project = params.project || detectProject(cwd);
  if (!project) {
    return { error: 'Could not detect project. Please specify project ID.' };
  }

  const config = loadConfig();
  const projectConfig = config.projects.find(p => p.id === project);
  if (!projectConfig) {
    return { error: `Project not found: ${project}` };
  }

  const action = params.action || 'status';
  const output = await runPythonScript(
    path.join(MLX_TOOLS, 'code_health.py'),
    [projectConfig.path, project, action]
  );
  return { result: output };
}

async function handleMemoryFunctions(params, cwd) {
  const project = params.project || detectProject(cwd);
  if (!project) {
    return { error: 'Could not detect project. Please specify project ID.' };
  }

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
        results.push({
          name: funcName,
          file: loc.file,
          line: loc.line,
          type: loc.type || 'function'
        });
      }
    }
  }

  if (results.length === 0) {
    return { result: `No functions found matching: ${params.name}` };
  }

  const formatted = results.slice(0, 20).map(r =>
    `${r.name}() [${r.type}] at ${r.file}:${r.line}`
  ).join('\n');

  return { result: `Found ${results.length} function(s):\n${formatted}` };
}

async function handleMemoryWireframe(params, cwd) {
  const project = params.project || detectProject(cwd);
  if (!project) {
    return { error: 'Could not detect project. Please specify project ID.' };
  }

  const format = params.format || 'summary';
  const screen = params.screen;

  let args;
  if (screen) {
    args = [project, 'screen', screen];
  } else if (format === 'mermaid') {
    args = [project, 'flow'];
  } else if (format === 'full') {
    args = [project, 'export'];
  } else {
    args = [project, 'inventory'];
  }

  const output = await runPythonScript(
    path.join(MLX_TOOLS, 'wireframe_analyzer.py'),
    args
  );
  return { result: output };
}

async function handleMemorySessions(params, cwd) {
  const args = [];

  // List sessions mode
  if (params.list_sessions) {
    args.push('--list-sessions');
    if (params.project) {
      args.push('--project', params.project);
    }
    if (params.limit) {
      args.push('--limit', String(params.limit));
    }
  }
  // Show specific session
  else if (params.session_id) {
    args.push('--session', params.session_id);
    if (params.project) {
      args.push('--project', params.project);
    }
  }
  // Search mode
  else if (params.query) {
    args.push(params.query);
    if (params.project) {
      args.push('--project', params.project);
    }
    if (params.category) {
      args.push('--category', params.category);
    }
    if (params.limit) {
      args.push('--limit', String(params.limit));
    }
    args.push('--verbose');
  }
  else {
    return { error: 'Please provide a query, list_sessions=true, or session_id' };
  }

  const output = await runPythonScript(
    path.join(MLX_TOOLS, 'session_search.py'),
    args
  );
  return { result: output };
}

// MCP Protocol handling
class MCPServer {
  constructor() {
    this.currentCwd = process.cwd();
  }

  handleRequest(request) {
    const { method, params, id } = request;

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
    // Track working directory if provided
    if (params?.workingDirectory) {
      this.currentCwd = params.workingDirectory;
    }

    return {
      jsonrpc: '2.0',
      id,
      result: {
        protocolVersion: '2024-11-05',
        capabilities: {
          tools: {}
        },
        serverInfo: {
          name: 'claude-dash',
          version: '1.0.0'
        }
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
        case 'memory_query':
          result = await handleMemoryQuery(args, this.currentCwd);
          break;
        case 'memory_search':
          result = await handleMemorySearch(args, this.currentCwd);
          break;
        case 'memory_similar':
          result = await handleMemorySimilar(args, this.currentCwd);
          break;
        case 'memory_health':
          result = await handleMemoryHealth(args, this.currentCwd);
          break;
        case 'memory_functions':
          result = await handleMemoryFunctions(args, this.currentCwd);
          break;
        case 'memory_wireframe':
          result = await handleMemoryWireframe(args, this.currentCwd);
          break;
        case 'memory_sessions':
          result = await handleMemorySessions(args, this.currentCwd);
          break;
        default:
          return this.errorResponse(id, -32602, `Unknown tool: ${name}`);
      }

      return {
        jsonrpc: '2.0',
        id,
        result: {
          content: [{
            type: 'text',
            text: result.error || result.result
          }],
          isError: !!result.error
        }
      };
    } catch (error) {
      return {
        jsonrpc: '2.0',
        id,
        result: {
          content: [{
            type: 'text',
            text: `Error: ${error.message}`
          }],
          isError: true
        }
      };
    }
  }

  errorResponse(id, code, message) {
    return {
      jsonrpc: '2.0',
      id,
      error: { code, message }
    };
  }
}

// Main: stdio transport
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
      console.log(JSON.stringify(response));
    } catch (error) {
      console.log(JSON.stringify({
        jsonrpc: '2.0',
        id: null,
        error: { code: -32700, message: 'Parse error' }
      }));
    }
  });

  // Handle stdin close
  rl.on('close', () => {
    process.exit(0);
  });
}

main();
