#!/usr/bin/env node

const fs = require('fs');
const path = require('path');
const chokidar = require('chokidar');
const os = require('os');
const { execSync, spawn } = require('child_process');
const net = require('net');

const MEMORY_ROOT = path.join(os.homedir(), '.claude-dash');
const MLX_TOOLS = path.join(MEMORY_ROOT, 'mlx-tools');
const PYTHON_PATH = path.join(MEMORY_ROOT, 'mlx-env', 'bin', 'python3');

// Sync file to SQLite database (runs detached, non-blocking)
function syncToDatabase(projectId, filePath) {
  const script = path.join(MLX_TOOLS, 'db_sync.py');

  // Check if Python and script exist
  if (!fs.existsSync(PYTHON_PATH) || !fs.existsSync(script)) {
    return; // Silently skip if not set up
  }

  try {
    const child = spawn(PYTHON_PATH, [script, projectId, filePath], {
      detached: true,
      stdio: 'ignore',
      cwd: MLX_TOOLS
    });
    child.unref(); // Don't wait for completion
  } catch (error) {
    // Silently fail - DB sync is best-effort
  }
}
const PID_FILE = path.join(MEMORY_ROOT, 'watcher', 'watcher.pid');

// Check if another instance is already running
function checkForExistingInstance() {
  try {
    if (fs.existsSync(PID_FILE)) {
      const existingPid = parseInt(fs.readFileSync(PID_FILE, 'utf8').trim(), 10);

      // Check if process is still running
      try {
        process.kill(existingPid, 0); // Signal 0 just checks if process exists
        console.error(`Another watcher instance is already running (PID: ${existingPid})`);
        console.error(`If this is incorrect, delete ${PID_FILE} and try again.`);
        process.exit(1);
      } catch (e) {
        // Process not running, stale PID file - remove it
        console.log(`Removing stale PID file (PID ${existingPid} not running)`);
        fs.unlinkSync(PID_FILE);
      }
    }
  } catch (error) {
    console.error('Error checking for existing instance:', error.message);
  }
}

// Write PID file
function writePidFile() {
  fs.writeFileSync(PID_FILE, process.pid.toString());
  console.log(`PID file written: ${PID_FILE} (PID: ${process.pid})`);
}

// Remove PID file on exit
function removePidFile() {
  try {
    if (fs.existsSync(PID_FILE)) {
      fs.unlinkSync(PID_FILE);
      console.log('PID file removed');
    }
  } catch (error) {
    console.error('Error removing PID file:', error.message);
  }
}

// Track which projects have Metro running
const metroRunningForProject = new Map();

// Queue of pending changes while Metro is running (batched updates)
const pendingChanges = new Map(); // projectId -> [{filePath, action}, ...]

// Check if Metro bundler is running (checks port 8081 and process list)
function isMetroRunning() {
  try {
    // Check if port 8081 is in use (Metro's default port) - any LISTEN connection
    const result = execSync('lsof -i :8081 -sTCP:LISTEN 2>/dev/null || true', { encoding: 'utf8' });
    if (result.trim().length > 0) {
      return true;
    }

    // Also check for expo/metro processes directly
    const processes = execSync('pgrep -fl "metro|expo start|react-native start" 2>/dev/null || true', { encoding: 'utf8' });
    if (processes.trim().length > 0) {
      return true;
    }

    // Check if expo is running via its default dev server
    const expoPort = execSync('lsof -i :19000 -sTCP:LISTEN 2>/dev/null || true', { encoding: 'utf8' });
    if (expoPort.trim().length > 0) {
      return true;
    }

    return false;
  } catch (error) {
    return false;
  }
}

// Check if Metro is running for a specific project
function isMetroRunningForProject(projectPath) {
  try {
    // Get expo/metro processes - their command line includes the project path
    const processes = execSync('pgrep -fl "expo|metro" 2>/dev/null || true', { encoding: 'utf8' });

    // Check if any process command line includes this project's directory name
    const projectDir = path.basename(projectPath);
    if (processes.includes(projectPath) || processes.includes(projectDir)) {
      return true;
    }

    // Also check if the process with port 8081 has this project as cwd
    try {
      const lsofResult = execSync('lsof -i :8081 -sTCP:LISTEN 2>/dev/null | tail -1 || true', { encoding: 'utf8' });
      const pidMatch = lsofResult.match(/\S+\s+(\d+)/);
      if (pidMatch) {
        const pid = pidMatch[1];
        const cwdResult = execSync(`lsof -p ${pid} 2>/dev/null | grep cwd || true`, { encoding: 'utf8' });
        if (cwdResult.includes(projectDir) || cwdResult.includes(projectPath)) {
          return true;
        }
      }
    } catch (e) {
      // Ignore errors in cwd detection
    }

    // If Metro is running and this is an Expo project, assume it's for this project
    // (Conservative - if we can't determine, assume yes to avoid conflicts)
    if (isMetroRunning() &&
        (fs.existsSync(path.join(projectPath, 'app.json')) ||
         fs.existsSync(path.join(projectPath, 'expo.json')))) {
      return true;
    }

    return false;
  } catch (error) {
    return false;
  }
}

// Process pending changes for a project (batch update)
function processPendingChanges(project) {
  const changes = pendingChanges.get(project.id) || [];
  if (changes.length === 0) return;

  console.log(`  📦 Processing ${changes.length} queued changes for ${project.displayName}`);

  for (const { filePath, action } of changes) {
    processFileChange(project, filePath, action);
  }

  // Update project index once after all changes
  updateProjectIndex(project);

  // Clear the queue
  pendingChanges.set(project.id, []);
}

// Queue a change for later processing
function queueChange(projectId, filePath, action) {
  if (!pendingChanges.has(projectId)) {
    pendingChanges.set(projectId, []);
  }
  const queue = pendingChanges.get(projectId);

  // Avoid duplicate entries for the same file
  const existingIndex = queue.findIndex(c => c.filePath === filePath);
  if (existingIndex >= 0) {
    // Update the action (latest action wins)
    queue[existingIndex].action = action;
  } else {
    queue.push({ filePath, action });
  }
}

// Cache for Metro status to reduce polling overhead
let cachedMetroStatus = null;
let lastMetroCheck = 0;
const METRO_CACHE_TTL = 60000; // Cache Metro status for 60 seconds (was 10s)

// Fast port check using net.connect (much faster than lsof)
function isPortInUse(port) {
  return new Promise((resolve) => {
    const socket = net.createConnection(port, '127.0.0.1');
    socket.setTimeout(500);
    socket.on('connect', () => { socket.destroy(); resolve(true); });
    socket.on('timeout', () => { socket.destroy(); resolve(false); });
    socket.on('error', () => { socket.destroy(); resolve(false); });
  });
}

// Quick Metro check using port probe (async, fast)
async function isMetroRunningFast() {
  // Check Metro ports first (fast, no shell commands)
  const [port8081, port19000] = await Promise.all([
    isPortInUse(8081),  // Metro default
    isPortInUse(19000)  // Expo default
  ]);
  return port8081 || port19000;
}

// Cached Metro check - only runs shell commands if cache expired
function getCachedMetroStatus() {
  const now = Date.now();
  if (cachedMetroStatus !== null && (now - lastMetroCheck) < METRO_CACHE_TTL) {
    return cachedMetroStatus;
  }
  cachedMetroStatus = isMetroRunning();
  lastMetroCheck = now;
  return cachedMetroStatus;
}

// Periodically check Metro status (optimized - less frequent, cached)
function startMetroDetection(projects) {
  let batchUpdateCounter = 0;

  setInterval(() => {
    // Only check Metro if there are pending changes or we need to update status
    const hasPendingChanges = projects.some(p => (pendingChanges.get(p.id) || []).length > 0);

    // Use cached status unless there are pending changes
    const metroActive = hasPendingChanges ? isMetroRunning() : getCachedMetroStatus();
    batchUpdateCounter++;

    for (const project of projects) {
      const wasRunning = metroRunningForProject.get(project.id) || false;

      // Only do expensive per-project check if Metro is active and we have pending changes
      const projectHasPending = (pendingChanges.get(project.id) || []).length > 0;
      const isRunning = metroActive && (wasRunning || projectHasPending) && isMetroRunningForProject(project.path);

      if (isRunning !== wasRunning) {
        metroRunningForProject.set(project.id, isRunning);
        if (isRunning) {
          console.log(`⏸️  Metro detected for ${project.displayName} - switching to batch mode`);
        } else {
          console.log(`▶️  Metro stopped for ${project.displayName} - processing queued changes`);
          processPendingChanges(project);
        }
      }

      // While Metro is running, do periodic batch updates every 60 seconds (2 intervals)
      if (isRunning && batchUpdateCounter % 2 === 0) {
        const queueSize = (pendingChanges.get(project.id) || []).length;
        if (queueSize > 0) {
          console.log(`  🔄 Batch updating ${project.displayName} (${queueSize} changes)`);
          processPendingChanges(project);
        }
      }
    }
  }, 60000); // Check every 60 seconds (was 30s) - reduced CPU overhead
}

// Check if we should process this project
function shouldProcessProject(projectId) {
  return !metroRunningForProject.get(projectId);
}

// Import extractors
const { parseFile } = require('./extractors/ast-parser');
const { scanFileForCollections } = require('./extractors/schema-extractor');
const CONFIG_PATH = path.join(MEMORY_ROOT, 'config.json');

// Config cache to avoid repeated disk reads
let configCache = null;
let configCacheTime = 0;
const CONFIG_CACHE_TTL = 30000; // 30 seconds

// Load configuration (with caching)
function loadConfig(forceReload = false) {
  const now = Date.now();
  if (!forceReload && configCache && (now - configCacheTime) < CONFIG_CACHE_TTL) {
    return configCache;
  }
  try {
    configCache = JSON.parse(fs.readFileSync(CONFIG_PATH, 'utf8'));
    configCacheTime = now;
    return configCache;
  } catch (error) {
    console.error('Error loading config:', error.message);
    return null;
  }
}

// Invalidate config cache (call when config changes)
function invalidateConfigCache() {
  configCache = null;
  configCacheTime = 0;
}

// Get file type from extension
function getFileType(filePath) {
  const ext = path.extname(filePath).toLowerCase();
  const typeMap = {
    '.js': 'javascript',
    '.jsx': 'javascript',
    '.ts': 'typescript',
    '.tsx': 'typescript',
    '.json': 'json',
    '.md': 'markdown',
    '.css': 'css',
    '.scss': 'scss',
    '.html': 'html',
    '.py': 'python',
    '.rb': 'ruby',
    '.go': 'go',
    '.rs': 'rust'
  };
  return typeMap[ext] || 'other';
}

// Categorize file by path
function categorizeFile(relativePath) {
  if (relativePath.includes('/screens/')) return 'screen';
  if (relativePath.includes('/components/')) return 'component';
  if (relativePath.includes('/services/')) return 'service';
  if (relativePath.includes('/hooks/')) return 'hook';
  if (relativePath.includes('/contexts/')) return 'context';
  if (relativePath.includes('/utils/')) return 'utility';
  if (relativePath.includes('/navigation/')) return 'navigation';
  if (relativePath.includes('/constants/')) return 'constant';
  if (relativePath.includes('/lib/')) return 'library';
  return 'other';
}

// Update functions.json for a single file change
function updateFunctionsIndex(project, filePath, action) {
  const memoryPath = path.join(MEMORY_ROOT, project.memoryPath);
  const functionsPath = path.join(memoryPath, 'functions.json');
  const relativePath = path.relative(project.path, filePath);

  // Only process JS/TS files
  if (!/\.(js|jsx|ts|tsx)$/.test(filePath)) return;

  let functionsIndex;
  try {
    functionsIndex = JSON.parse(fs.readFileSync(functionsPath, 'utf8'));
  } catch (error) {
    return; // No functions index yet
  }

  if (action === 'remove') {
    // Remove functions from this file
    for (const funcName of Object.keys(functionsIndex.functions)) {
      functionsIndex.functions[funcName] = functionsIndex.functions[funcName].filter(
        f => f.file !== relativePath
      );
      if (functionsIndex.functions[funcName].length === 0) {
        delete functionsIndex.functions[funcName];
      }
    }
    functionsIndex.totalFunctions = Object.values(functionsIndex.functions)
      .reduce((sum, arr) => sum + arr.length, 0);
  } else {
    // Parse the changed file
    const result = parseFile(filePath);

    // Remove old entries for this file
    for (const funcName of Object.keys(functionsIndex.functions)) {
      functionsIndex.functions[funcName] = functionsIndex.functions[funcName].filter(
        f => f.file !== relativePath
      );
      if (functionsIndex.functions[funcName].length === 0) {
        delete functionsIndex.functions[funcName];
      }
    }

    // Add new entries
    for (const func of result.functions) {
      functionsIndex.functions[func.name] = functionsIndex.functions[func.name] || [];
      functionsIndex.functions[func.name].push({
        file: relativePath,
        line: func.line,
        endLine: func.endLine,
        type: func.type,
        async: func.async
      });
    }

    functionsIndex.totalFunctions = Object.values(functionsIndex.functions)
      .reduce((sum, arr) => sum + arr.length, 0);
  }

  functionsIndex.lastUpdated = new Date().toISOString();
  fs.writeFileSync(functionsPath, JSON.stringify(functionsIndex, null, 2));
}

// Update summaries.json structural data for a file change
function updateSummariesStructure(project, filePath, action) {
  const memoryPath = path.join(MEMORY_ROOT, project.memoryPath);
  const summariesPath = path.join(memoryPath, 'summaries.json');
  const relativePath = path.relative(project.path, filePath);

  // Only process JS/TS files
  if (!/\.(js|jsx|ts|tsx)$/.test(filePath)) return;

  let summaries;
  try {
    summaries = JSON.parse(fs.readFileSync(summariesPath, 'utf8'));
  } catch (error) {
    return; // No summaries index yet
  }

  if (action === 'remove') {
    delete summaries.files[relativePath];
  } else {
    // Parse the file for structural data
    const result = parseFile(filePath);

    // Update or create entry
    summaries.files[relativePath] = {
      isComponent: result.isComponent,
      componentName: result.componentName,
      functions: result.functions.map(f => ({
        name: f.name,
        line: f.line,
        type: f.type
      })),
      exports: result.exports,
      imports: result.imports.map(i => i.source),
      hooks: result.hooks,
      stateVariables: result.stateVariables.map(s => s.variable),
      navigation: result.navigation,
      firestoreOperations: result.firestoreOperations,
      // Mark as needing re-summarization
      summary: summaries.files[relativePath]?.summary || null,
      purpose: summaries.files[relativePath]?.purpose || null,
      keyLogic: summaries.files[relativePath]?.keyLogic || null,
      needsResummarization: true,
      lastStructuralUpdate: new Date().toISOString()
    };
  }

  summaries.lastUpdated = new Date().toISOString();
  fs.writeFileSync(summariesPath, JSON.stringify(summaries, null, 2));
}

// Process a single file change
function processFileChange(project, filePath, action) {
  console.log(`  → Updating functions index`);
  updateFunctionsIndex(project, filePath, action);
  console.log(`  → Updating summaries structure`);
  updateSummariesStructure(project, filePath, action);

  // Sync to SQLite database (async, non-blocking)
  const relativePath = path.relative(project.path, filePath);
  syncToDatabase(project.id, relativePath);
}

// Scan project and update index.json
function updateProjectIndex(project) {
  const projectPath = project.path;
  const memoryPath = path.join(MEMORY_ROOT, project.memoryPath);
  const indexPath = path.join(memoryPath, 'index.json');

  // Read existing index
  let index;
  try {
    index = JSON.parse(fs.readFileSync(indexPath, 'utf8'));
  } catch (error) {
    console.error(`Error reading index for ${project.id}:`, error.message);
    return;
  }

  // Scan files
  const fileIndex = [];
  const languageCount = {};
  let totalFiles = 0;

  // Load config once at start of scan
  const config = loadConfig();
  const ignorePatterns = config?.watcher?.ignorePatterns || [];

  function scanDir(dir, relativePath = '') {
    try {
      const entries = fs.readdirSync(dir, { withFileTypes: true });

      for (const entry of entries) {
        const entryPath = path.join(dir, entry.name);
        const entryRelative = path.join(relativePath, entry.name);

        // Check ignore patterns (using cached ignorePatterns from outer scope)
        const shouldIgnore = ignorePatterns.some(pattern => {
          if (pattern.includes('*')) {
            const regex = new RegExp(pattern.replace('*', '.*'));
            return regex.test(entry.name);
          }
          return entry.name === pattern;
        });

        if (shouldIgnore) continue;

        if (entry.isDirectory()) {
          scanDir(entryPath, entryRelative);
        } else if (entry.isFile()) {
          const stats = fs.statSync(entryPath);
          const fileType = getFileType(entry.name);

          // Count languages
          if (fileType !== 'other') {
            languageCount[fileType] = (languageCount[fileType] || 0) + 1;
          }
          totalFiles++;

          // Only index source files
          if (['javascript', 'typescript', 'json'].includes(fileType)) {
            fileIndex.push({
              path: entryRelative,
              type: categorizeFile(entryRelative),
              lastModified: stats.mtime.toISOString(),
              size: stats.size
            });
          }
        }
      }
    } catch (error) {
      // Skip directories we can't read
    }
  }

  // Start scan from src directory if it exists
  const srcPath = path.join(projectPath, 'src');
  if (fs.existsSync(srcPath)) {
    scanDir(srcPath, 'src');
  } else {
    scanDir(projectPath);
  }

  // Update index
  index.lastScanned = new Date().toISOString();
  index.structure.totalFiles = totalFiles;
  index.structure.languages = languageCount;
  index.fileIndex = fileIndex.slice(0, 500); // Limit to 500 files

  // Write updated index
  fs.writeFileSync(indexPath, JSON.stringify(index, null, 2));
  console.log(`Updated index for ${project.displayName}: ${totalFiles} files`);
}

// Setup watcher for a project
function watchProject(project, config) {
  const ignorePatterns = config.watcher.ignorePatterns.map(p => {
    if (p.includes('*')) {
      return new RegExp(p.replace('*', '.*'));
    }
    return p;
  });

  // Only watch src directory if it exists, otherwise watch project root
  const watchPath = fs.existsSync(path.join(project.path, 'src'))
    ? path.join(project.path, 'src')
    : project.path;

  const watcher = chokidar.watch(watchPath, {
    ignored: [
      /(^|[\/\\])\../,  // dotfiles
      /node_modules/,
      /ios\//,
      /android\//,
      /Pods\//,
      /\.worktrees\//,
      ...ignorePatterns
    ],
    persistent: true,
    ignoreInitial: true,
    usePolling: false,  // Use native fsevents on macOS
    depth: 10,  // Limit directory depth
    awaitWriteFinish: {
      stabilityThreshold: 2000,
      pollInterval: 500
    }
  });

  let debounceTimer = null;

  function scheduleUpdate() {
    if (debounceTimer) {
      clearTimeout(debounceTimer);
    }
    debounceTimer = setTimeout(() => {
      updateProjectIndex(project);
    }, config.watcher.scanIntervalMs || 5000);
  }

  watcher
    .on('add', (filePath) => {
      const relativePath = path.relative(project.path, filePath);

      // If Metro is running, queue the change for batch processing
      if (!shouldProcessProject(project.id)) {
        queueChange(project.id, filePath, 'add');
        return;
      }

      console.log(`File added: ${relativePath}`);
      processFileChange(project, filePath, 'add');
      scheduleUpdate();
    })
    .on('unlink', (filePath) => {
      const relativePath = path.relative(project.path, filePath);

      // If Metro is running, queue the change for batch processing
      if (!shouldProcessProject(project.id)) {
        queueChange(project.id, filePath, 'remove');
        return;
      }

      console.log(`File removed: ${relativePath}`);
      processFileChange(project, filePath, 'remove');
      scheduleUpdate();
    })
    .on('change', (filePath) => {
      const ext = path.extname(filePath);
      if (['.js', '.jsx', '.ts', '.tsx'].includes(ext)) {
        const relativePath = path.relative(project.path, filePath);

        // If Metro is running, queue the change for batch processing
        if (!shouldProcessProject(project.id)) {
          queueChange(project.id, filePath, 'change');
          return;
        }

        console.log(`File changed: ${relativePath}`);
        processFileChange(project, filePath, 'change');
        scheduleUpdate();
      }
    })
    .on('error', (error) => {
      console.error(`Watcher error for ${project.id}:`, error);
    });

  console.log(`Watching: ${project.displayName} (${project.path})`);
  return watcher;
}

// Main function
function main() {
  console.log('Claude Memory Watcher starting...');
  console.log(`Memory root: ${MEMORY_ROOT}`);

  // Prevent multiple instances
  checkForExistingInstance();
  writePidFile();

  const config = loadConfig();
  if (!config) {
    console.error('Could not load config. Exiting.');
    process.exit(1);
  }

  if (!config.watcher.enabled) {
    console.log('Watcher is disabled in config. Exiting.');
    process.exit(0);
  }

  if (config.projects.length === 0) {
    console.log('No projects registered. Add projects to config.json.');
    process.exit(0);
  }

  // Initial scan of all projects
  console.log('Performing initial scan...');
  for (const project of config.projects) {
    if (fs.existsSync(project.path)) {
      updateProjectIndex(project);
    } else {
      console.warn(`Project path not found: ${project.path}`);
    }
  }

  // Setup watchers
  const watchers = [];
  for (const project of config.projects) {
    if (fs.existsSync(project.path)) {
      watchers.push(watchProject(project, config));
    }
  }

  console.log(`Watching ${watchers.length} project(s). Press Ctrl+C to stop.`);

  // Start Metro detection to pause watching during development
  startMetroDetection(config.projects);

  // Handle graceful shutdown
  process.on('SIGINT', () => {
    console.log('\nShutting down watchers...');
    watchers.forEach(w => w.close());
    removePidFile();
    process.exit(0);
  });

  process.on('SIGTERM', () => {
    console.log('\nShutting down watchers...');
    watchers.forEach(w => w.close());
    removePidFile();
    process.exit(0);
  });

  // Also clean up on uncaught exceptions
  process.on('uncaughtException', (error) => {
    console.error('Uncaught exception:', error);
    removePidFile();
    process.exit(1);
  });

  process.on('exit', () => {
    removePidFile();
  });
}

main();
