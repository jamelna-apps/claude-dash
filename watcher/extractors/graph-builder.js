#!/usr/bin/env node

/**
 * Navigation Graph Builder for Claude Memory System
 *
 * Creates a graph of relationships between files, functions, and data:
 * - File imports/dependencies
 * - Function call relationships
 * - Navigation flows (screens)
 * - Data flow (which files access which collections)
 *
 * Usage: node graph-builder.js <project-path> <project-id>
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

/**
 * Build navigation graph from existing summaries and functions
 */
function buildGraph(projectPath, projectId) {
  const memoryPath = path.join(process.env.HOME, '.claude-dash', 'projects', projectId);

  const summariesPath = path.join(memoryPath, 'summaries.json');
  const functionsPath = path.join(memoryPath, 'functions.json');
  const schemaPath = path.join(memoryPath, 'schema.json');

  // Load existing data
  let summaries = {};
  let functions = {};
  let schema = {};

  try {
    summaries = JSON.parse(fs.readFileSync(summariesPath, 'utf8'));
  } catch (e) {
    console.error('Summaries not found. Run ast-parser.js first.');
    process.exit(1);
  }

  try {
    functions = JSON.parse(fs.readFileSync(functionsPath, 'utf8'));
  } catch (e) {
    console.log('Functions index not found, skipping function relationships.');
  }

  try {
    schema = JSON.parse(fs.readFileSync(schemaPath, 'utf8'));
  } catch (e) {
    console.log('Schema not found, skipping data relationships.');
  }

  // Build graph
  const graph = {
    version: '1.0',
    project: projectId,
    lastUpdated: new Date().toISOString(),
    nodes: {
      files: {},
      screens: {},
      components: {},
      services: {},
      hooks: {},
      collections: {}
    },
    edges: {
      imports: [],      // File A imports File B
      navigates: [],    // Screen A navigates to Screen B
      uses: [],         // File A uses Collection B
      calls: []         // Function A calls Function B
    },
    statistics: {}
  };

  // Process files
  const files = Object.entries(summaries.files);

  for (const [filePath, data] of files) {
    // Determine node type
    let nodeType = 'files';
    if (filePath.includes('/screens/')) nodeType = 'screens';
    else if (filePath.includes('/components/')) nodeType = 'components';
    else if (filePath.includes('/services/')) nodeType = 'services';
    else if (filePath.includes('/hooks/') || filePath.includes('Hook')) nodeType = 'hooks';

    // Create node
    const nodeId = filePath.replace(/\//g, '_').replace(/\./g, '_');
    graph.nodes[nodeType][nodeId] = {
      path: filePath,
      name: path.basename(filePath, path.extname(filePath)),
      type: nodeType,
      component: data.componentName,
      functions: data.functions?.map(f => f.name) || [],
      hooks: data.hooks || [],
      summary: data.summary,
      purpose: data.purpose
    };

    // Add import edges
    if (data.imports) {
      for (const importPath of data.imports) {
        // Resolve relative imports
        if (importPath.startsWith('.')) {
          const resolvedPath = resolveImportPath(filePath, importPath);
          if (resolvedPath) {
            graph.edges.imports.push({
              from: filePath,
              to: resolvedPath,
              type: 'import'
            });
          }
        }
      }
    }

    // Add navigation edges
    if (data.navigation) {
      for (const targetScreen of data.navigation) {
        graph.edges.navigates.push({
          from: filePath,
          to: targetScreen,
          type: 'navigation'
        });
      }
    }

    // Add Stack.Screen registrations as navigation structure
    if (data.stackScreens && data.stackScreens.length > 0) {
      // Store stack info for later
      if (!graph.stacks) graph.stacks = {};
      const stackName = path.basename(filePath, path.extname(filePath));
      graph.stacks[stackName] = {
        path: filePath,
        screens: data.stackScreens
      };

      // Add edges from stack to each registered screen
      for (const screenName of data.stackScreens) {
        graph.edges.navigates.push({
          from: filePath,
          to: screenName,
          type: 'stack-registration'
        });
      }
    }

    // Add collection usage edges
    if (data.firestoreOperations && data.firestoreOperations.length > 0) {
      // Try to find which collections this file uses from schema
      if (schema.collections) {
        for (const [collectionName, collectionData] of Object.entries(schema.collections)) {
          if (collectionData.referencedIn) {
            for (const ref of collectionData.referencedIn) {
              if (ref.startsWith(filePath.split(':')[0])) {
                graph.edges.uses.push({
                  from: filePath,
                  to: collectionName,
                  operations: data.firestoreOperations,
                  type: 'data'
                });
              }
            }
          }
        }
      }
    }
  }

  // Add collection nodes
  if (schema.collections) {
    for (const [name, data] of Object.entries(schema.collections)) {
      if (data.referencedIn && data.referencedIn.length > 0) {
        graph.nodes.collections[name] = {
          name,
          fields: data.fields || [],
          relationships: data.relationships || {},
          usedIn: data.referencedIn.length
        };
      }
    }
  }

  // Parse navigation stack files directly for stack registrations
  graph.stacks = {};
  const stackFiles = Object.keys(summaries.files).filter(f => f.includes('/stacks/') && f.endsWith('Stack.js'));
  for (const stackFile of stackFiles) {
    try {
      const fullPath = path.join(projectPath, stackFile);
      const content = fs.readFileSync(fullPath, 'utf8');
      const stackScreenPattern = /<Stack\.Screen[^>]*name\s*=\s*['"`](\w+)['"`]/g;
      const screens = [];
      let match;
      while ((match = stackScreenPattern.exec(content)) !== null) {
        screens.push(match[1]);
      }
      if (screens.length > 0) {
        const stackName = path.basename(stackFile, '.js');
        graph.stacks[stackName] = {
          path: stackFile,
          screens: screens
        };
        // Add edges from stack to each screen
        for (const screenName of screens) {
          graph.edges.navigates.push({
            from: stackFile,
            to: screenName,
            type: 'stack-registration'
          });
        }
      }
    } catch (e) {
      // Skip if file can't be read
    }
  }

  // Build screen navigation map
  const screenNavMap = buildScreenNavigationMap(graph);

  // Calculate statistics
  graph.statistics = {
    totalFiles: files.length,
    screens: Object.keys(graph.nodes.screens).length,
    components: Object.keys(graph.nodes.components).length,
    services: Object.keys(graph.nodes.services).length,
    hooks: Object.keys(graph.nodes.hooks).length,
    collections: Object.keys(graph.nodes.collections).length,
    importEdges: graph.edges.imports.length,
    navigationEdges: graph.edges.navigates.length,
    dataEdges: graph.edges.uses.length
  };

  // Add screen navigation summary
  graph.screenNavigation = screenNavMap;

  return graph;
}

/**
 * Resolve a relative import path to an actual file path
 */
function resolveImportPath(fromFile, importPath) {
  const fromDir = path.dirname(fromFile);

  // Handle different import styles
  let resolved = path.join(fromDir, importPath);

  // Try common extensions
  const extensions = ['', '.js', '.jsx', '.ts', '.tsx', '/index.js', '/index.ts'];

  for (const ext of extensions) {
    const tryPath = resolved + ext;
    // Return normalized path without leading ./
    if (tryPath.startsWith('./')) {
      return tryPath.substring(2);
    }
    return tryPath;
  }

  return resolved;
}

/**
 * Build a map of screen-to-screen navigation
 */
function buildScreenNavigationMap(graph) {
  const navMap = {};

  // Get all screens
  for (const [nodeId, node] of Object.entries(graph.nodes.screens)) {
    navMap[node.name] = {
      path: node.path,
      navigatesTo: [],
      reachableFrom: []
    };
  }

  // Add navigation relationships
  for (const edge of graph.edges.navigates) {
    const fromNode = Object.values(graph.nodes.screens).find(n => n.path === edge.from);
    const fromName = fromNode ? fromNode.name : path.basename(edge.from, path.extname(edge.from));

    if (navMap[fromName]) {
      navMap[fromName].navigatesTo.push(edge.to);
    }

    if (navMap[edge.to]) {
      navMap[edge.to].reachableFrom.push(fromName);
    }
  }

  return navMap;
}

/**
 * Main function
 */
function main() {
  const args = process.argv.slice(2);

  if (args.length < 2) {
    console.log('Usage: node graph-builder.js <project-path> <project-id>');
    console.log('Example: node graph-builder.js /path/to/WardrobeApp gyst');
    process.exit(1);
  }

  const projectPath = args[0];
  const projectId = args[1];
  const memoryPath = path.join(process.env.HOME, '.claude-dash', 'projects', projectId);

  if (!fs.existsSync(projectPath)) {
    console.error(`Project path not found: ${projectPath}`);
    process.exit(1);
  }

  console.log(`Building navigation graph for ${projectId}...`);

  const graph = buildGraph(projectPath, projectId);

  // Write graph (atomic)
  const graphPath = path.join(memoryPath, 'graph.json');
  atomicWriteJSON(graphPath, graph);

  console.log(`\nGraph Statistics:`);
  console.log(`  Files: ${graph.statistics.totalFiles}`);
  console.log(`  Screens: ${graph.statistics.screens}`);
  console.log(`  Components: ${graph.statistics.components}`);
  console.log(`  Services: ${graph.statistics.services}`);
  console.log(`  Hooks: ${graph.statistics.hooks}`);
  console.log(`  Collections: ${graph.statistics.collections}`);
  console.log(`\nRelationships:`);
  console.log(`  Import edges: ${graph.statistics.importEdges}`);
  console.log(`  Navigation edges: ${graph.statistics.navigationEdges}`);
  console.log(`  Data usage edges: ${graph.statistics.dataEdges}`);

  console.log(`\nOutput: ${graphPath}`);
}

// Run if called directly
if (require.main === module) {
  main();
}

module.exports = { buildGraph, buildScreenNavigationMap };
