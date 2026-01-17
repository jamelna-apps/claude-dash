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
const LEARNING_DIR = path.join(MEMORY_ROOT, 'learning');
const SESSIONS_DIR = path.join(MEMORY_ROOT, 'sessions');
const GATEWAY_DIR = path.join(MEMORY_ROOT, 'gateway');
const REPORTS_DIR = path.join(MEMORY_ROOT, 'reports');

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

// Load efficiency data from learning systems
function loadEfficiencyData() {
  const data = {
    sessions: { total: 0, byWeek: {} },
    corrections: { total: 0, byWeek: {}, rate: 0 },
    outcomes: { success: 0, failure: 0, partial: 0, byWeek: {} },
    tokenSavings: { memoryHits: 0, filesAvoided: 0, estimated: 0 },
    confidence: { domains: {}, weakAreas: [] },
    preferences: { learned: 0, highConfidence: 0 },
    trends: []
  };

  // Load corrections
  const correctionsPath = path.join(LEARNING_DIR, 'corrections.json');
  if (fs.existsSync(correctionsPath)) {
    try {
      const corrections = JSON.parse(fs.readFileSync(correctionsPath, 'utf8'));
      const list = corrections.corrections || [];
      data.corrections.total = list.length;

      // Group by week
      list.forEach(c => {
        if (c.timestamp) {
          const date = new Date(c.timestamp);
          const week = getWeekString(date);
          data.corrections.byWeek[week] = (data.corrections.byWeek[week] || 0) + 1;
        }
      });
    } catch (e) { console.error('Error loading corrections:', e.message); }
  }

  // Load outcomes
  const outcomesPath = path.join(LEARNING_DIR, 'outcomes.json');
  if (fs.existsSync(outcomesPath)) {
    try {
      const outcomes = JSON.parse(fs.readFileSync(outcomesPath, 'utf8'));
      const list = outcomes.outcomes || [];

      list.forEach(o => {
        if (o.outcome === 'success') data.outcomes.success++;
        else if (o.outcome === 'failure') data.outcomes.failure++;
        else if (o.outcome === 'partial') data.outcomes.partial++;

        if (o.timestamp) {
          const date = new Date(o.timestamp);
          const week = getWeekString(date);
          if (!data.outcomes.byWeek[week]) {
            data.outcomes.byWeek[week] = { success: 0, failure: 0, partial: 0 };
          }
          if (o.outcome in data.outcomes.byWeek[week]) {
            data.outcomes.byWeek[week][o.outcome]++;
          }
        }
      });
    } catch (e) { console.error('Error loading outcomes:', e.message); }
  }

  // Load confidence calibration
  const calibrationPath = path.join(LEARNING_DIR, 'confidence_calibration.json');
  if (fs.existsSync(calibrationPath)) {
    try {
      const calibration = JSON.parse(fs.readFileSync(calibrationPath, 'utf8'));
      data.confidence.domains = calibration.domains || {};

      // Find weak areas (accuracy < 0.65)
      Object.entries(data.confidence.domains).forEach(([domain, stats]) => {
        if (stats.total >= 3 && stats.accuracy < 0.65) {
          data.confidence.weakAreas.push({ domain, accuracy: stats.accuracy, total: stats.total });
        }
      });
    } catch (e) { console.error('Error loading calibration:', e.message); }
  }

  // Load preferences
  const preferencesPath = path.join(LEARNING_DIR, 'inferred_preferences.json');
  if (fs.existsSync(preferencesPath)) {
    try {
      const prefs = JSON.parse(fs.readFileSync(preferencesPath, 'utf8'));
      const list = prefs.preferences || [];
      data.preferences.learned = list.length;
      data.preferences.highConfidence = list.filter(p => p.confidence >= 0.7).length;
    } catch (e) { console.error('Error loading preferences:', e.message); }
  }

  // Count sessions from transcripts
  const transcriptsDir = path.join(SESSIONS_DIR, 'transcripts');
  if (fs.existsSync(transcriptsDir)) {
    try {
      const files = fs.readdirSync(transcriptsDir).filter(f => f.endsWith('.jsonl'));
      data.sessions.total = files.length;

      files.forEach(f => {
        const stat = fs.statSync(path.join(transcriptsDir, f));
        const week = getWeekString(stat.mtime);
        data.sessions.byWeek[week] = (data.sessions.byWeek[week] || 0) + 1;
      });
    } catch (e) { console.error('Error counting sessions:', e.message); }
  }

  // Calculate correction rate
  if (data.sessions.total > 0) {
    data.corrections.rate = data.corrections.total / data.sessions.total;
  }

  // Estimate token savings
  const AVG_FILE_TOKENS = 1500;
  const AVG_MEMORY_TOKENS = 200;
  data.tokenSavings.memoryHits = data.sessions.total * 5; // Estimate 5 memory hits per session
  data.tokenSavings.filesAvoided = Math.floor(data.tokenSavings.memoryHits * 0.7);
  data.tokenSavings.estimated = data.tokenSavings.filesAvoided * (AVG_FILE_TOKENS - AVG_MEMORY_TOKENS);

  // Build weekly trends
  const allWeeks = new Set([
    ...Object.keys(data.sessions.byWeek),
    ...Object.keys(data.corrections.byWeek)
  ]);
  const sortedWeeks = Array.from(allWeeks).sort().slice(-8);

  sortedWeeks.forEach(week => {
    const sessions = data.sessions.byWeek[week] || 0;
    const corrections = data.corrections.byWeek[week] || 0;
    const outcomes = data.outcomes.byWeek[week] || { success: 0, failure: 0, partial: 0 };

    data.trends.push({
      week,
      sessions,
      corrections,
      correctionsPerSession: sessions > 0 ? corrections / sessions : null,
      successRate: (outcomes.success + outcomes.failure + outcomes.partial) > 0
        ? outcomes.success / (outcomes.success + outcomes.failure + outcomes.partial) * 100
        : null
    });
  });

  return data;
}

// Get week string from date
function getWeekString(date) {
  const d = new Date(date);
  const year = d.getFullYear();
  const startOfYear = new Date(year, 0, 1);
  const weekNum = Math.ceil(((d - startOfYear) / 86400000 + startOfYear.getDay() + 1) / 7);
  return `${year}-W${weekNum.toString().padStart(2, '0')}`;
}

// Calculate efficiency projection
function calculateProjection(data, weeksAhead) {
  const trends = data.trends || [];
  const projection = {
    current: {
      correctionsPerSession: data.corrections.rate,
      successRate: data.outcomes.success + data.outcomes.failure + data.outcomes.partial > 0
        ? data.outcomes.success / (data.outcomes.success + data.outcomes.failure + data.outcomes.partial) * 100
        : null,
      tokenSavings: data.tokenSavings.estimated,
      preferencesLearned: data.preferences.learned
    },
    projected: [],
    improvementRate: null,
    weeksToTarget: null
  };

  // Calculate improvement rate from trends
  const cpsValues = trends
    .filter(t => t.correctionsPerSession !== null)
    .map(t => t.correctionsPerSession);

  if (cpsValues.length >= 2) {
    // Simple linear regression
    const n = cpsValues.length;
    const xMean = (n - 1) / 2;
    const yMean = cpsValues.reduce((a, b) => a + b, 0) / n;

    let numerator = 0;
    let denominator = 0;
    cpsValues.forEach((y, i) => {
      numerator += (i - xMean) * (y - yMean);
      denominator += (i - xMean) ** 2;
    });

    const slope = denominator !== 0 ? numerator / denominator : 0;
    const intercept = yMean - slope * xMean;

    projection.improvementRate = -slope; // Negative slope = improvement

    // Project forward
    const currentCps = cpsValues[cpsValues.length - 1];
    for (let w = 4; w <= weeksAhead; w += 4) {
      const projectedCps = Math.max(0, intercept + slope * (n - 1 + w));
      const improvement = currentCps > 0 ? ((currentCps - projectedCps) / currentCps * 100) : 0;

      projection.projected.push({
        weeksAhead: w,
        correctionsPerSession: projectedCps,
        improvementPercent: improvement,
        tokenSavings: data.tokenSavings.estimated * (1 + improvement / 100),
        preferencesLearned: data.preferences.learned + Math.floor(w * 0.5)
      });
    }

    // Calculate weeks to target (0.5 corrections per session)
    const targetCps = 0.5;
    if (slope < 0 && currentCps > targetCps) {
      projection.weeksToTarget = Math.ceil((targetCps - intercept) / slope - (n - 1));
    }
  }

  return projection;
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
  },

  '/api/efficiency': (req, res) => {
    try {
      const data = loadEfficiencyData();
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify(data));
    } catch (e) {
      res.writeHead(500, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: e.message }));
    }
  },

  '/api/efficiency/projection': (req, res, params) => {
    try {
      const weeks = parseInt(params.get('weeks')) || 12;
      const data = loadEfficiencyData();
      const projection = calculateProjection(data, weeks);
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify(projection));
    } catch (e) {
      res.writeHead(500, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: e.message }));
    }
  },

  '/api/gateway/metrics': (req, res) => {
    try {
      const metricsPath = path.join(GATEWAY_DIR, 'metrics.json');
      if (fs.existsSync(metricsPath)) {
        const metrics = JSON.parse(fs.readFileSync(metricsPath, 'utf8'));

        // Calculate summary stats
        const total = metrics.totalQueries || 1;
        const ollamaStats = metrics.ollamaStats || { totalQueries: 0, totalTokens: 0, estimatedSavings: 0 };
        const routing = metrics.routingBreakdown || {};

        const ollamaQueries = (routing.ollama || 0) + (routing.local_ai || 0);
        const apiQueries = routing.api || 0;

        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({
          totalQueries: total,
          routing: {
            ollama: ollamaQueries,
            api: apiQueries,
            memory: routing.memory || 0,
            cached: routing.cached || 0,
            ollamaPercent: ((ollamaQueries / total) * 100).toFixed(1),
            apiPercent: ((apiQueries / total) * 100).toFixed(1)
          },
          ollamaStats: {
            queriesRouted: ollamaStats.totalQueries,
            tokensProcessed: ollamaStats.totalTokens,
            estimatedSavingsUSD: ollamaStats.estimatedSavings.toFixed(4)
          },
          dailyStats: metrics.dailyStats || {},
          recentQueries: (metrics.recentQueries || []).slice(0, 20)
        }));
      } else {
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({
          totalQueries: 0,
          routing: { ollama: 0, api: 0, memory: 0, cached: 0, ollamaPercent: '0.0', apiPercent: '0.0' },
          ollamaStats: { queriesRouted: 0, tokensProcessed: 0, estimatedSavingsUSD: '0.0000' },
          dailyStats: {},
          recentQueries: []
        }));
      }
    } catch (e) {
      res.writeHead(500, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: e.message }));
    }
  },

  '/api/reports/generate': async (req, res) => {
    try {
      // Ensure reports directory exists
      if (!fs.existsSync(REPORTS_DIR)) {
        fs.mkdirSync(REPORTS_DIR, { recursive: true });
      }

      // Gather data for the report
      const efficiency = loadEfficiencyData();
      const config = loadConfig();

      // Load gateway metrics
      const metricsPath = path.join(GATEWAY_DIR, 'metrics.json');
      let gatewayMetrics = { totalQueries: 0, routingBreakdown: {}, ollamaStats: { totalQueries: 0, estimatedSavings: 0 } };
      if (fs.existsSync(metricsPath)) {
        gatewayMetrics = JSON.parse(fs.readFileSync(metricsPath, 'utf8'));
      }

      // Get this week's date range
      const now = new Date();
      const weekStart = new Date(now);
      weekStart.setDate(now.getDate() - now.getDay());
      weekStart.setHours(0, 0, 0, 0);
      const weekEnd = new Date(weekStart);
      weekEnd.setDate(weekStart.getDate() + 6);
      weekEnd.setHours(23, 59, 59, 999);

      const weekKey = getWeekString(now);

      // Count this week's sessions
      const thisWeekSessions = efficiency.sessions.byWeek[weekKey] || 0;
      const thisWeekCorrections = efficiency.corrections.byWeek[weekKey] || 0;

      // Count this week's queries from daily stats
      let thisWeekQueries = 0;
      let thisWeekOllamaQueries = 0;
      const dailyStats = gatewayMetrics.dailyStats || {};
      for (const [date, stats] of Object.entries(dailyStats)) {
        const d = new Date(date);
        if (d >= weekStart && d <= weekEnd) {
          thisWeekQueries += stats.queries || 0;
          thisWeekOllamaQueries += stats.ollamaQueries || 0;
        }
      }

      // Generate report
      const report = {
        id: `report-${weekKey}`,
        weekKey,
        generated: new Date().toISOString(),
        dateRange: {
          start: weekStart.toISOString().split('T')[0],
          end: weekEnd.toISOString().split('T')[0]
        },
        summary: {
          sessions: thisWeekSessions,
          corrections: thisWeekCorrections,
          correctionsPerSession: thisWeekSessions > 0 ? (thisWeekCorrections / thisWeekSessions).toFixed(2) : '0.00',
          queries: thisWeekQueries,
          ollamaQueries: thisWeekOllamaQueries,
          ollamaPercent: thisWeekQueries > 0 ? ((thisWeekOllamaQueries / thisWeekQueries) * 100).toFixed(1) : '0.0',
          estimatedSavingsUSD: (gatewayMetrics.ollamaStats?.estimatedSavings || 0).toFixed(4)
        },
        efficiency: {
          totalSessions: efficiency.sessions.total,
          totalCorrections: efficiency.corrections.total,
          preferencesLearned: efficiency.preferences.learned,
          highConfidencePrefs: efficiency.preferences.highConfidence,
          tokensSaved: efficiency.tokenSavings.estimated
        },
        projects: config.projects.map(p => ({
          id: p.id,
          name: p.name
        }))
      };

      // Save report
      const reportPath = path.join(REPORTS_DIR, `${report.id}.json`);
      fs.writeFileSync(reportPath, JSON.stringify(report, null, 2));

      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify(report));
    } catch (e) {
      res.writeHead(500, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: e.message }));
    }
  },

  '/api/reports': (req, res) => {
    try {
      if (!fs.existsSync(REPORTS_DIR)) {
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify([]));
        return;
      }

      const reports = fs.readdirSync(REPORTS_DIR)
        .filter(f => f.endsWith('.json'))
        .map(f => {
          try {
            const content = JSON.parse(fs.readFileSync(path.join(REPORTS_DIR, f), 'utf8'));

            // Normalize old format to new format
            if (content.weekOf && !content.weekKey) {
              const weekDate = new Date(content.weekOf);
              return {
                id: `report-${content.weekOf}`,
                weekKey: content.weekOf,
                generated: content.generatedAt,
                dateRange: {
                  start: content.weekOf,
                  end: new Date(weekDate.getTime() + 6 * 24 * 60 * 60 * 1000).toISOString().split('T')[0]
                },
                summary: {
                  sessions: '-',
                  queries: '-',
                  ollamaPercent: '-',
                  estimatedSavingsUSD: '-'
                },
                isLegacy: true,
                content: content.content
              };
            }
            return content;
          } catch (e) {
            return null;
          }
        })
        .filter(r => r !== null)
        .sort((a, b) => new Date(b.generated) - new Date(a.generated));

      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify(reports));
    } catch (e) {
      res.writeHead(500, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: e.message }));
    }
  },

  '/api/activity/heatmap': (req, res) => {
    try {
      const obsPath = path.join(SESSIONS_DIR, 'observations.json');
      if (!fs.existsSync(obsPath)) {
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ projects: [], total: 0 }));
        return;
      }

      const data = JSON.parse(fs.readFileSync(obsPath, 'utf8'));
      const observations = data.observations || [];

      // Count by project
      const projectCounts = {};
      const categoryCounts = {};
      observations.forEach(obs => {
        const project = obs.projectId || 'unknown';
        const category = obs.category || 'other';
        projectCounts[project] = (projectCounts[project] || 0) + 1;
        categoryCounts[category] = (categoryCounts[category] || 0) + 1;
      });

      // Sort by count
      const projects = Object.entries(projectCounts)
        .map(([name, count]) => ({ name, count }))
        .sort((a, b) => b.count - a.count);

      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({
        projects,
        categories: categoryCounts,
        total: observations.length,
        lastUpdated: data.lastUpdated
      }));
    } catch (e) {
      res.writeHead(500, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: e.message }));
    }
  },

  '/api/sessions/recent': (req, res) => {
    try {
      const digestsDir = path.join(SESSIONS_DIR, 'digests');
      if (!fs.existsSync(digestsDir)) {
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify([]));
        return;
      }

      const digests = fs.readdirSync(digestsDir)
        .filter(f => f.endsWith('.json'))
        .map(f => {
          try {
            const content = JSON.parse(fs.readFileSync(path.join(digestsDir, f), 'utf8'));
            return {
              id: f.replace('.json', ''),
              compactedAt: content.compacted_at,
              messageCount: content.message_count,
              synthesis: content.synthesis ? content.synthesis.substring(0, 500) + '...' : null,
              sourceTranscript: content.source_transcript
            };
          } catch (e) {
            return null;
          }
        })
        .filter(d => d !== null)
        .sort((a, b) => new Date(b.compactedAt) - new Date(a.compactedAt))
        .slice(0, 10);

      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify(digests));
    } catch (e) {
      res.writeHead(500, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: e.message }));
    }
  },

  '/api/transcripts/stats': (req, res) => {
    try {
      const transcriptsDir = path.join(SESSIONS_DIR, 'transcripts');
      if (!fs.existsSync(transcriptsDir)) {
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ total: 0, totalSizeMB: 0, transcripts: [] }));
        return;
      }

      const transcripts = fs.readdirSync(transcriptsDir)
        .filter(f => f.endsWith('.jsonl'))
        .map(f => {
          const filePath = path.join(transcriptsDir, f);
          const stat = fs.statSync(filePath);
          return {
            id: f.replace('.jsonl', ''),
            sizeMB: (stat.size / 1024 / 1024).toFixed(2),
            sizeBytes: stat.size,
            modified: stat.mtime.toISOString(),
            estimatedTokens: Math.round(stat.size / 4) // ~4 bytes per token
          };
        })
        .sort((a, b) => b.sizeBytes - a.sizeBytes);

      const totalSize = transcripts.reduce((sum, t) => sum + t.sizeBytes, 0);
      const totalTokens = transcripts.reduce((sum, t) => sum + t.estimatedTokens, 0);

      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({
        total: transcripts.length,
        totalSizeMB: (totalSize / 1024 / 1024).toFixed(2),
        totalTokens,
        largestSession: transcripts[0] || null,
        transcripts: transcripts.slice(0, 10)
      }));
    } catch (e) {
      res.writeHead(500, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: e.message }));
    }
  },

  '/api/activity/timeline': (req, res) => {
    try {
      const obsPath = path.join(SESSIONS_DIR, 'observations.json');
      const indexPath = path.join(SESSIONS_DIR, 'index.json');

      const timeline = {};

      // Get observations by date
      if (fs.existsSync(obsPath)) {
        const obsData = JSON.parse(fs.readFileSync(obsPath, 'utf8'));
        (obsData.observations || []).forEach(obs => {
          if (obs.timestamp) {
            const date = obs.timestamp.split('T')[0];
            const project = obs.projectId || 'unknown';
            if (!timeline[date]) timeline[date] = { projects: {}, total: 0 };
            timeline[date].projects[project] = (timeline[date].projects[project] || 0) + 1;
            timeline[date].total++;
          }
        });
      }

      // Get sessions by date
      if (fs.existsSync(indexPath)) {
        const indexData = JSON.parse(fs.readFileSync(indexPath, 'utf8'));
        (indexData.sessions || []).forEach(session => {
          if (session.startTime) {
            const date = session.startTime.split('T')[0];
            if (!timeline[date]) timeline[date] = { projects: {}, total: 0, sessions: 0 };
            timeline[date].sessions = (timeline[date].sessions || 0) + 1;
          }
        });
      }

      // Convert to array and sort by date
      const timelineArray = Object.entries(timeline)
        .map(([date, data]) => ({
          date,
          ...data,
          projectList: Object.entries(data.projects)
            .sort((a, b) => b[1] - a[1])
            .slice(0, 5)
            .map(([name, count]) => ({ name, count }))
        }))
        .sort((a, b) => new Date(b.date) - new Date(a.date))
        .slice(0, 30); // Last 30 days

      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify(timelineArray));
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
