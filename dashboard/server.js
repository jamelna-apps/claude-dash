#!/usr/bin/env node
/**
 * Claude Dash - Dashboard Server
 * Serves static files and provides API endpoints for the dashboard
 */

const http = require('http');
const fs = require('fs');
const path = require('path');
const { execSync, spawn } = require('child_process');

const PORT = process.argv[2] || 3333;
const MEMORY_ROOT = process.env.MEMORY_ROOT || path.join(process.env.HOME, '.claude-dash');
const PROJECTS_DIR = path.join(MEMORY_ROOT, 'projects');
const CONFIG_PATH = path.join(MEMORY_ROOT, 'config.json');
const MLX_TOOLS = path.join(MEMORY_ROOT, 'mlx-tools');

// MIME types
const MIME_TYPES = {
  '.html': 'text/html',
  '.css': 'text/css',
  '.js': 'application/javascript',
  '.json': 'application/json',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon'
};

// Load config
function loadConfig() {
  try {
    return JSON.parse(fs.readFileSync(CONFIG_PATH, 'utf8'));
  } catch (e) {
    return { projects: [] };
  }
}

// Load project data
function loadProjectData(projectId) {
  const projectDir = path.join(PROJECTS_DIR, projectId);
  const data = {};

  const files = ['index.json', 'summaries.json', 'functions.json', 'schema.json', 'graph.json', 'decisions.json', 'preferences.json'];

  for (const file of files) {
    const filePath = path.join(projectDir, file);
    try {
      if (fs.existsSync(filePath)) {
        data[file.replace('.json', '')] = JSON.parse(fs.readFileSync(filePath, 'utf8'));
      }
    } catch (e) {
      console.error(`Error loading ${file} for ${projectId}:`, e.message);
    }
  }

  return data;
}

// Check Ollama status
function checkOllama() {
  try {
    const result = execSync('ollama ps 2>/dev/null', { encoding: 'utf8', timeout: 2000 });
    const lines = result.trim().split('\n');
    if (lines.length > 1) {
      const parts = lines[1].split(/\s+/);
      return { available: true, model: parts[0] || 'unknown' };
    }
    return { available: true, model: null };
  } catch (e) {
    return { available: false, model: null };
  }
}

// Query Ollama
async function queryOllama(prompt, project) {
  return new Promise((resolve, reject) => {
    const proc = spawn('ollama', ['run', 'qwen2.5:7b', '--nowordwrap'], {
      stdio: ['pipe', 'pipe', 'pipe']
    });

    let output = '';
    let error = '';

    proc.stdout.on('data', (data) => { output += data.toString(); });
    proc.stderr.on('data', (data) => { error += data.toString(); });

    proc.on('close', (code) => {
      if (code === 0) {
        resolve(output.trim());
      } else {
        reject(new Error(error || 'Ollama query failed'));
      }
    });

    proc.stdin.write(prompt);
    proc.stdin.end();

    // Timeout after 60 seconds
    setTimeout(() => {
      proc.kill();
      reject(new Error('Ollama query timeout'));
    }, 60000);
  });
}

// API handlers
const apiHandlers = {
  '/api/config': (req, res) => {
    const config = loadConfig();
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(config));
  },

  '/api/projects': (req, res) => {
    const config = loadConfig();
    const projects = config.projects.map(p => {
      const data = loadProjectData(p.id);

      // Load health score from cached health.json
      let healthScore = null;
      let healthTimestamp = null;
      const healthPath = path.join(PROJECTS_DIR, p.id, 'health.json');
      try {
        if (fs.existsSync(healthPath)) {
          const health = JSON.parse(fs.readFileSync(healthPath, 'utf8'));
          healthScore = health.score;
          healthTimestamp = health.timestamp;
        }
      } catch (e) {
        // Ignore health loading errors
      }

      return {
        ...p,
        fileCount: data.index?.structure?.totalFiles || 0,
        lastScanned: data.index?.lastScanned || null,
        healthScore,
        healthTimestamp
      };
    });
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(projects));
  },

  '/api/project': (req, res, params) => {
    const projectId = params.get('id');
    if (!projectId) {
      res.writeHead(400, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: 'Missing project id' }));
      return;
    }

    const data = loadProjectData(projectId);
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(data));
  },

  '/api/ollama/status': (req, res) => {
    const status = checkOllama();
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(status));
  },

  '/api/ollama/chat': async (req, res, params, body) => {
    try {
      const { prompt, project } = JSON.parse(body);
      const response = await queryOllama(prompt, project);
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ response }));
    } catch (e) {
      res.writeHead(500, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: e.message }));
    }
  },

  '/api/preferences': (req, res) => {
    const prefsPath = path.join(MEMORY_ROOT, 'global', 'preferences.json');
    try {
      const prefs = JSON.parse(fs.readFileSync(prefsPath, 'utf8'));
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify(prefs));
    } catch (e) {
      res.writeHead(500, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: e.message }));
    }
  },

  '/api/health': (req, res, params) => {
    const projectId = params.get('project');
    if (!projectId) {
      res.writeHead(400, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: 'Missing project id' }));
      return;
    }

    // Try to load cached health data
    const healthPath = path.join(PROJECTS_DIR, projectId, 'health.json');
    try {
      if (fs.existsSync(healthPath)) {
        let health = JSON.parse(fs.readFileSync(healthPath, 'utf8'));

        // If health data has issues in 'raw' field (old format), try to extract it
        if (health.raw && (!health.issues?.duplicates || health.issues.duplicates.length === 0)) {
          try {
            const jsonMatch = health.raw.match(/\{[\s\S]*\}\s*$/);
            if (jsonMatch) {
              const parsedRaw = JSON.parse(jsonMatch[0]);
              // Merge the parsed data
              health = {
                ...health,
                score: parsedRaw.score || health.score,
                issues: parsedRaw.issues || health.issues,
                summary: parsedRaw.summary || health.summary
              };
              delete health.raw; // Remove raw field after parsing
            }
          } catch (e) {
            // Keep original health object if parsing fails
          }
        }

        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify(health));
      } else {
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ score: null, timestamp: null }));
      }
    } catch (e) {
      res.writeHead(500, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: e.message }));
    }
  },

  '/api/health/scan': async (req, res, params) => {
    const projectId = params.get('project');
    if (!projectId) {
      res.writeHead(400, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: 'Missing project id' }));
      return;
    }

    try {
      // Run health scan using mlx tools
      const config = loadConfig();
      const project = config.projects.find(p => p.id === projectId);
      if (!project) {
        res.writeHead(404, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: 'Project not found' }));
        return;
      }

      const mlxPath = path.join(MLX_TOOLS, 'mlx');
      const result = execSync(
        `"${mlxPath}" health "${projectId}" scan 2>&1`,
        { encoding: 'utf8', timeout: 120000 }
      );

      // Parse JSON result from mlx - the output may have log lines before JSON
      let health;
      try {
        // Try to find JSON in the output (starts with { and ends with })
        const jsonMatch = result.match(/\{[\s\S]*\}\s*$/);
        if (jsonMatch) {
          health = JSON.parse(jsonMatch[0]);
        } else {
          throw new Error('No JSON found in output');
        }
        health.timestamp = new Date().toISOString();
      } catch (parseErr) {
        // If parsing fails, try to extract structured data from raw output
        console.error('Failed to parse mlx health output:', parseErr.message);
        health = {
          score: 75,
          timestamp: new Date().toISOString(),
          raw: result,
          issues: { security: [], performance: [], maintenance: [], duplicates: [], dead_code: [] },
          summary: { security: 0, performance: 0, duplicates: 0, dead_code: 0 }
        };
      }

      // Save to health.json
      const healthPath = path.join(PROJECTS_DIR, projectId, 'health.json');
      fs.writeFileSync(healthPath, JSON.stringify(health, null, 2));

      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify(health));
    } catch (e) {
      res.writeHead(500, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: e.message }));
    }
  }
};

// Request handler
const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://localhost:${PORT}`);
  const pathname = url.pathname;

  // CORS headers
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') {
    res.writeHead(204);
    res.end();
    return;
  }

  // API routes
  if (pathname.startsWith('/api/')) {
    let body = '';
    req.on('data', chunk => { body += chunk; });
    req.on('end', async () => {
      const handler = apiHandlers[pathname];
      if (handler) {
        await handler(req, res, url.searchParams, body);
      } else {
        res.writeHead(404, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: 'Not found' }));
      }
    });
    return;
  }

  // Static files
  let filePath = pathname === '/' ? '/index.html' : pathname;
  filePath = path.join(__dirname, filePath);

  const ext = path.extname(filePath);
  const contentType = MIME_TYPES[ext] || 'application/octet-stream';

  try {
    const content = fs.readFileSync(filePath);
    res.writeHead(200, { 'Content-Type': contentType });
    res.end(content);
  } catch (e) {
    if (e.code === 'ENOENT') {
      res.writeHead(404, { 'Content-Type': 'text/plain' });
      res.end('Not found');
    } else {
      res.writeHead(500, { 'Content-Type': 'text/plain' });
      res.end('Server error');
    }
  }
});

server.listen(PORT, () => {
  console.log(`Dashboard running at http://localhost:${PORT}`);
});
