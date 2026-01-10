#!/usr/bin/env node
/**
 * AST Analyzer for Claude Memory System
 * Uses acorn to parse JS/JSX and extract detailed import/export/call info.
 */

const fs = require('fs');
const path = require('path');
const acorn = require('acorn');
const jsx = require('acorn-jsx');

const Parser = acorn.Parser.extend(jsx());

function parseFile(filePath) {
  try {
    const content = fs.readFileSync(filePath, 'utf8');
    const ast = Parser.parse(content, {
      ecmaVersion: 2022,
      sourceType: 'module',
      locations: true,
      allowHashBang: true,
      allowImportExportEverywhere: true,
      allowAwaitOutsideFunction: true,
    });
    return { success: true, ast, content };
  } catch (e) {
    return { success: false, error: e.message };
  }
}

function extractImports(ast) {
  const imports = [];

  function walk(node) {
    if (!node || typeof node !== 'object') return;

    // Static imports: import X from 'Y'
    if (node.type === 'ImportDeclaration') {
      imports.push({
        type: 'static',
        source: node.source.value,
        line: node.loc?.start?.line,
        specifiers: node.specifiers?.map(s => ({
          type: s.type,
          imported: s.imported?.name || 'default',
          local: s.local?.name
        })) || []
      });
    }

    // Dynamic imports: import('X')
    if (node.type === 'ImportExpression') {
      imports.push({
        type: 'dynamic',
        source: node.source?.value || node.source?.quasis?.[0]?.value?.raw,
        line: node.loc?.start?.line
      });
    }

    // Require: require('X')
    if (node.type === 'CallExpression' &&
        node.callee?.name === 'require' &&
        node.arguments?.[0]?.value) {
      imports.push({
        type: 'require',
        source: node.arguments[0].value,
        line: node.loc?.start?.line
      });
    }

    // Walk children
    for (const key in node) {
      if (key === 'loc' || key === 'range') continue;
      const child = node[key];
      if (Array.isArray(child)) {
        child.forEach(walk);
      } else if (child && typeof child === 'object') {
        walk(child);
      }
    }
  }

  walk(ast);
  return imports;
}

function extractExports(ast) {
  const exports = [];

  function walk(node) {
    if (!node || typeof node !== 'object') return;

    // Named exports: export const X, export function Y
    if (node.type === 'ExportNamedDeclaration') {
      if (node.declaration) {
        const decl = node.declaration;
        if (decl.type === 'VariableDeclaration') {
          decl.declarations.forEach(d => {
            exports.push({
              type: 'named',
              name: d.id?.name,
              line: node.loc?.start?.line
            });
          });
        } else if (decl.id?.name) {
          exports.push({
            type: 'named',
            name: decl.id.name,
            line: node.loc?.start?.line
          });
        }
      }
      // export { X, Y }
      if (node.specifiers) {
        node.specifiers.forEach(s => {
          exports.push({
            type: 'named',
            name: s.exported?.name,
            local: s.local?.name,
            line: node.loc?.start?.line
          });
        });
      }
    }

    // Default export
    if (node.type === 'ExportDefaultDeclaration') {
      exports.push({
        type: 'default',
        name: node.declaration?.id?.name || node.declaration?.name || 'default',
        line: node.loc?.start?.line
      });
    }

    // Re-exports: export * from 'X'
    if (node.type === 'ExportAllDeclaration') {
      exports.push({
        type: 'reexport_all',
        source: node.source?.value,
        line: node.loc?.start?.line
      });
    }

    for (const key in node) {
      if (key === 'loc' || key === 'range') continue;
      const child = node[key];
      if (Array.isArray(child)) {
        child.forEach(walk);
      } else if (child && typeof child === 'object') {
        walk(child);
      }
    }
  }

  walk(ast);
  return exports;
}

function extractFunctionCalls(ast) {
  const calls = [];

  function walk(node, parentFunc = null) {
    if (!node || typeof node !== 'object') return;

    // Track current function context
    let currentFunc = parentFunc;
    if (node.type === 'FunctionDeclaration' ||
        node.type === 'FunctionExpression' ||
        node.type === 'ArrowFunctionExpression') {
      currentFunc = node.id?.name || parentFunc;
    }

    // Function calls
    if (node.type === 'CallExpression') {
      let name = null;
      if (node.callee?.name) {
        name = node.callee.name;
      } else if (node.callee?.property?.name) {
        name = node.callee.property.name;
      }

      if (name) {
        calls.push({
          name,
          line: node.loc?.start?.line,
          caller: currentFunc
        });
      }
    }

    for (const key in node) {
      if (key === 'loc' || key === 'range') continue;
      const child = node[key];
      if (Array.isArray(child)) {
        child.forEach(c => walk(c, currentFunc));
      } else if (child && typeof child === 'object') {
        walk(child, currentFunc);
      }
    }
  }

  walk(ast);
  return calls;
}

function extractNavigationRefs(ast, content) {
  const navRefs = [];

  // Pattern: navigation.navigate('ScreenName') or navigate('ScreenName')
  const navPattern = /(?:navigation\.)?navigate\s*\(\s*['"]([^'"]+)['"]/g;
  let match;
  while ((match = navPattern.exec(content)) !== null) {
    navRefs.push({
      screen: match[1],
      position: match.index
    });
  }

  return navRefs;
}

function analyzeFile(filePath) {
  const result = parseFile(filePath);

  if (!result.success) {
    return { error: result.error, file: filePath };
  }

  return {
    file: filePath,
    imports: extractImports(result.ast),
    exports: extractExports(result.ast),
    function_calls: extractFunctionCalls(result.ast),
    navigation_refs: extractNavigationRefs(result.ast, result.content)
  };
}

// CLI interface
if (require.main === module) {
  const args = process.argv.slice(2);

  if (args.length === 0) {
    console.error('Usage: node ast_analyzer.js <file.js> [file2.js ...]');
    console.error('       node ast_analyzer.js --dir <directory>');
    process.exit(1);
  }

  if (args[0] === '--dir') {
    // Analyze entire directory
    const dir = args[1];
    const results = {};

    function scanDir(d) {
      for (const item of fs.readdirSync(d)) {
        const full = path.join(d, item);
        const stat = fs.statSync(full);

        if (stat.isDirectory()) {
          if (!['node_modules', '.git', 'dist', 'build'].includes(item)) {
            scanDir(full);
          }
        } else if (/\.(js|jsx|ts|tsx)$/.test(item)) {
          const rel = path.relative(dir, full);
          results[rel] = analyzeFile(full);
        }
      }
    }

    scanDir(dir);
    console.log(JSON.stringify(results, null, 2));
  } else {
    // Analyze specific files
    const results = {};
    for (const file of args) {
      results[file] = analyzeFile(file);
    }
    console.log(JSON.stringify(results, null, 2));
  }
}

module.exports = { analyzeFile, parseFile, extractImports, extractExports };
