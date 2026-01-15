#!/usr/bin/env node

/**
 * AST Parser for Claude Memory System
 *
 * Extracts structural information from JavaScript/React files:
 * - Function declarations with line numbers
 * - Exports (named and default)
 * - Imports
 * - React components
 * - Hooks usage
 *
 * Uses regex-based parsing (no external dependencies)
 */

const fs = require('fs');
const path = require('path');

/**
 * Atomic JSON write - writes to temp file then renames
 */
function atomicWriteJSON(filePath, data) {
  const tmpPath = filePath + '.tmp.' + process.pid + '.' + Date.now();
  try {
    fs.writeFileSync(tmpPath, JSON.stringify(data, null, 2));
    fs.renameSync(tmpPath, filePath);
  } catch (e) {
    try { fs.unlinkSync(tmpPath); } catch (e2) {}
    throw e;
  }
}

// Patterns for extraction
const PATTERNS = {
  // Function declarations
  functionDeclaration: /^(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(/gm,

  // Arrow functions assigned to const/let
  arrowFunction: /^(?:export\s+)?(?:const|let)\s+(\w+)\s*=\s*(?:async\s+)?\([^)]*\)\s*=>/gm,

  // Arrow functions without params or single param
  arrowFunctionSimple: /^(?:export\s+)?(?:const|let)\s+(\w+)\s*=\s*(?:async\s+)?(?:\w+|\([^)]*\))\s*=>/gm,

  // React component (function returning JSX)
  reactComponent: /^(?:export\s+)?(?:const|function)\s+([A-Z]\w+)/gm,

  // Default export
  defaultExport: /^export\s+default\s+(?:function\s+)?(\w+)/gm,

  // Named exports
  namedExport: /^export\s+(?:const|let|function|async function)\s+(\w+)/gm,

  // Export statement at end
  exportStatement: /^export\s*\{\s*([^}]+)\s*\}/gm,

  // Imports
  importStatement: /^import\s+(?:(\w+)(?:\s*,\s*)?)?(?:\{([^}]+)\})?\s+from\s+['"]([^'"]+)['"]/gm,

  // Hooks usage
  hookUsage: /\b(use[A-Z]\w+)\s*\(/g,

  // useEffect/useCallback with dependencies
  effectHook: /(useEffect|useCallback|useMemo)\s*\(\s*(?:async\s*)?\([^)]*\)\s*=>\s*\{/g,

  // useState
  useState: /const\s+\[(\w+),\s*set(\w+)\]\s*=\s*useState/g,

  // Navigation
  navigation: /navigation\.navigate\s*\(\s*['"](\w+)['"]/g,

  // Firestore operations
  firestoreOp: /(getDocs|getDoc|setDoc|updateDoc|deleteDoc|addDoc|onSnapshot)\s*\(/g,
};

/**
 * Extract line number for a match position
 */
function getLineNumber(content, position) {
  const lines = content.substring(0, position).split('\n');
  return lines.length;
}

/**
 * Find the end line of a function (simplified - counts braces)
 */
function findFunctionEndLine(content, startLine) {
  const lines = content.split('\n');
  let braceCount = 0;
  let started = false;

  for (let i = startLine - 1; i < lines.length; i++) {
    const line = lines[i];

    for (const char of line) {
      if (char === '{') {
        braceCount++;
        started = true;
      } else if (char === '}') {
        braceCount--;
        if (started && braceCount === 0) {
          return i + 1;
        }
      }
    }
  }

  return startLine + 10; // Fallback
}

/**
 * Parse a single file
 */
function parseFile(filePath) {
  const result = {
    file: filePath,
    functions: [],
    exports: {
      default: null,
      named: []
    },
    imports: [],
    hooks: [],
    stateVariables: [],
    navigation: [],
    firestoreOperations: [],
    isComponent: false,
    componentName: null
  };

  try {
    const content = fs.readFileSync(filePath, 'utf8');
    const lines = content.split('\n');

    // Extract functions
    const functionPatterns = [
      { pattern: /(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(/g, type: 'function' },
      { pattern: /(?:export\s+)?(?:const|let)\s+(\w+)\s*=\s*(?:async\s+)?\(?[^)]*\)?\s*=>/g, type: 'arrow' }
    ];

    for (const { pattern, type } of functionPatterns) {
      let match;
      while ((match = pattern.exec(content)) !== null) {
        const name = match[1];
        const line = getLineNumber(content, match.index);
        const endLine = findFunctionEndLine(content, line);

        // Check if it's a React component (starts with capital, or returns JSX)
        const isComponent = /^[A-Z]/.test(name);

        result.functions.push({
          name,
          type: isComponent ? 'component' : type,
          line,
          endLine,
          async: match[0].includes('async')
        });

        if (isComponent && !result.componentName) {
          result.isComponent = true;
          result.componentName = name;
        }
      }
    }

    // Extract default export
    const defaultMatch = /export\s+default\s+(?:function\s+)?(\w+)/g.exec(content);
    if (defaultMatch) {
      result.exports.default = defaultMatch[1];
    }

    // Extract named exports
    let namedMatch;
    const namedPattern = /export\s+(?:const|let|function|async\s+function)\s+(\w+)/g;
    while ((namedMatch = namedPattern.exec(content)) !== null) {
      result.exports.named.push(namedMatch[1]);
    }

    // Export statement at end
    const exportStmtMatch = /export\s*\{\s*([^}]+)\s*\}/g.exec(content);
    if (exportStmtMatch) {
      const exports = exportStmtMatch[1].split(',').map(e => e.trim().split(/\s+as\s+/)[0]);
      result.exports.named.push(...exports);
    }

    // Extract imports
    const importPattern = /import\s+(?:(\w+)(?:\s*,\s*)?)?(?:\{([^}]+)\})?\s+from\s+['"]([^'"]+)['"]/g;
    let importMatch;
    while ((importMatch = importPattern.exec(content)) !== null) {
      const defaultImport = importMatch[1];
      const namedImports = importMatch[2] ? importMatch[2].split(',').map(i => i.trim().split(/\s+as\s+/)[0]) : [];
      const source = importMatch[3];

      result.imports.push({
        source,
        default: defaultImport || null,
        named: namedImports
      });
    }

    // Extract hooks usage
    const hookPattern = /\b(use[A-Z]\w+)\s*\(/g;
    let hookMatch;
    const hooksSet = new Set();
    while ((hookMatch = hookPattern.exec(content)) !== null) {
      hooksSet.add(hookMatch[1]);
    }
    result.hooks = Array.from(hooksSet);

    // Extract useState variables
    const statePattern = /const\s+\[(\w+),\s*set(\w+)\]\s*=\s*useState/g;
    let stateMatch;
    while ((stateMatch = statePattern.exec(content)) !== null) {
      result.stateVariables.push({
        variable: stateMatch[1],
        setter: `set${stateMatch[2]}`
      });
    }

    // Extract navigation calls - multiple patterns
    const navPatterns = [
      /navigation\.navigate\s*\(\s*['"`](\w+)['"`]/g,  // navigation.navigate('Screen')
      /navigation\.push\s*\(\s*['"`](\w+)['"`]/g,       // navigation.push('Screen')
      /navigation\.replace\s*\(\s*['"`](\w+)['"`]/g,    // navigation.replace('Screen')
      /\.navigate\s*\(\s*['"`](\w+)['"`]/g,             // .navigate('Screen') - destructured
      /navigate\s*\(\s*['"`](\w+)['"`]/g,               // navigate('Screen') - direct call
    ];

    const navTargets = new Set();
    for (const pattern of navPatterns) {
      let navMatch;
      while ((navMatch = pattern.exec(content)) !== null) {
        navTargets.add(navMatch[1]);
      }
    }
    result.navigation = Array.from(navTargets);

    // Extract Stack.Screen registrations (for navigation files)
    const stackScreenPattern = /<Stack\.Screen[^>]*name\s*=\s*['"`](\w+)['"`]/g;
    let stackMatch;
    while ((stackMatch = stackScreenPattern.exec(content)) !== null) {
      if (!result.stackScreens) result.stackScreens = [];
      result.stackScreens.push(stackMatch[1]);
    }

    // Extract Firestore operations
    const firestorePattern = /(getDocs|getDoc|setDoc|updateDoc|deleteDoc|addDoc|onSnapshot)\s*\(/g;
    let firestoreMatch;
    const firestoreOps = new Set();
    while ((firestoreMatch = firestorePattern.exec(content)) !== null) {
      firestoreOps.add(firestoreMatch[1]);
    }
    result.firestoreOperations = Array.from(firestoreOps);

  } catch (error) {
    result.error = error.message;
  }

  return result;
}

/**
 * Recursively scan directory
 */
function scanDirectory(dirPath, ignorePatterns = ['node_modules', '.git', 'dist', 'build', '.expo']) {
  const results = [];

  function walkDir(dir) {
    try {
      const entries = fs.readdirSync(dir, { withFileTypes: true });

      for (const entry of entries) {
        const fullPath = path.join(dir, entry.name);

        if (ignorePatterns.some(p => entry.name === p || entry.name.startsWith('.'))) {
          continue;
        }

        if (entry.isDirectory()) {
          walkDir(fullPath);
        } else if (entry.isFile() && /\.(js|jsx|ts|tsx)$/.test(entry.name)) {
          results.push(parseFile(fullPath));
        }
      }
    } catch (error) {
      // Skip directories that can't be read
    }
  }

  walkDir(dirPath);
  return results;
}

/**
 * Generate functions index
 */
function generateFunctionsIndex(projectPath, projectId) {
  console.log(`Parsing ${projectPath} for functions...`);

  const fileResults = scanDirectory(projectPath);

  const functionsIndex = {
    version: '1.0',
    project: projectId,
    lastUpdated: new Date().toISOString(),
    totalFiles: fileResults.length,
    totalFunctions: 0,
    functions: {}
  };

  for (const fileResult of fileResults) {
    const relativePath = path.relative(projectPath, fileResult.file);

    for (const func of fileResult.functions) {
      const key = `${relativePath}:${func.name}`;

      functionsIndex.functions[func.name] = functionsIndex.functions[func.name] || [];
      functionsIndex.functions[func.name].push({
        file: relativePath,
        line: func.line,
        endLine: func.endLine,
        type: func.type,
        async: func.async
      });

      functionsIndex.totalFunctions++;
    }
  }

  return { functionsIndex, fileResults };
}

/**
 * Generate file summaries (structural only - no semantic summary yet)
 */
function generateFileSummaries(projectPath, projectId, fileResults) {
  const summaries = {
    version: '1.0',
    project: projectId,
    lastUpdated: new Date().toISOString(),
    files: {}
  };

  for (const fileResult of fileResults) {
    const relativePath = path.relative(projectPath, fileResult.file);

    summaries.files[relativePath] = {
      isComponent: fileResult.isComponent,
      componentName: fileResult.componentName,
      functions: fileResult.functions.map(f => ({
        name: f.name,
        line: f.line,
        type: f.type
      })),
      exports: fileResult.exports,
      imports: fileResult.imports.map(i => i.source),
      hooks: fileResult.hooks,
      stateVariables: fileResult.stateVariables.map(s => s.variable),
      navigation: fileResult.navigation,
      firestoreOperations: fileResult.firestoreOperations,
      // Placeholder for semantic summary (will be filled by Claude)
      summary: null,
      purpose: null,
      keyLogic: null
    };
  }

  return summaries;
}

/**
 * Main function
 */
function main() {
  const args = process.argv.slice(2);

  if (args.length < 2) {
    console.log('Usage: node ast-parser.js <project-path> <project-id>');
    console.log('Example: node ast-parser.js /path/to/WardrobeApp gyst');
    process.exit(1);
  }

  const projectPath = args[0];
  const projectId = args[1];
  const memoryPath = path.join(process.env.HOME, '.claude-dash', 'projects', projectId);

  if (!fs.existsSync(projectPath)) {
    console.error(`Project path not found: ${projectPath}`);
    process.exit(1);
  }

  // Generate functions index
  const { functionsIndex, fileResults } = generateFunctionsIndex(projectPath, projectId);

  // Generate file summaries (structural)
  const summaries = generateFileSummaries(projectPath, projectId, fileResults);

  // Ensure output directory exists
  fs.mkdirSync(memoryPath, { recursive: true });

  // Write functions index (atomic)
  const functionsPath = path.join(memoryPath, 'functions.json');
  atomicWriteJSON(functionsPath, functionsIndex);
  console.log(`Functions index: ${functionsIndex.totalFunctions} functions in ${functionsIndex.totalFiles} files`);

  // Write summaries (atomic)
  const summariesPath = path.join(memoryPath, 'summaries.json');
  atomicWriteJSON(summariesPath, summaries);
  console.log(`Summaries: ${Object.keys(summaries.files).length} files`);

  // Stats
  let componentCount = 0;
  let hookUsageCount = 0;
  let firestoreFileCount = 0;

  for (const file of Object.values(summaries.files)) {
    if (file.isComponent) componentCount++;
    hookUsageCount += file.hooks.length;
    if (file.firestoreOperations.length > 0) firestoreFileCount++;
  }

  console.log(`\nStats:`);
  console.log(`  - React components: ${componentCount}`);
  console.log(`  - Files using Firestore: ${firestoreFileCount}`);
  console.log(`  - Total hooks usage: ${hookUsageCount}`);
}

// Run if called directly
if (require.main === module) {
  main();
}

module.exports = { parseFile, scanDirectory, generateFunctionsIndex, generateFileSummaries };
