#!/usr/bin/env node
/**
 * AST Transformer for Claude-Dash
 *
 * Performs simple code transformations WITHOUT needing an LLM:
 * - Add/remove imports
 * - Rename variables/functions
 * - Add/remove exports
 * - Simple refactors
 *
 * Inspired by claude-flow's "Agent Booster" concept:
 * Use fast, deterministic transforms for simple edits instead of LLM calls.
 *
 * This saves tokens and provides instant results for routine operations.
 */

const fs = require('fs');
const path = require('path');
const acorn = require('acorn');
const jsx = require('acorn-jsx');

const Parser = acorn.Parser.extend(jsx());

/**
 * Parse JavaScript/JSX file
 */
function parseCode(code) {
  try {
    const ast = Parser.parse(code, {
      ecmaVersion: 2022,
      sourceType: 'module',
      locations: true,
      ranges: true,
      allowHashBang: true,
      allowImportExportEverywhere: true,
      allowAwaitOutsideFunction: true,
    });
    return { success: true, ast };
  } catch (e) {
    return { success: false, error: e.message };
  }
}

/**
 * Add an import statement to code
 * @param {string} code - Source code
 * @param {string} importSpec - Import specifier (e.g., "useState" or "{ useState, useEffect }")
 * @param {string} from - Module path
 * @param {boolean} isDefault - Whether it's a default import
 */
function addImport(code, importSpec, from, isDefault = false) {
  const parsed = parseCode(code);
  if (!parsed.success) {
    return { success: false, error: parsed.error };
  }

  // Check if import already exists
  const existingImportRegex = new RegExp(`import\\s+.*?\\s+from\\s+['"]${from.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}['"]`);
  if (existingImportRegex.test(code)) {
    // Import from this module exists - try to merge
    const lines = code.split('\n');
    for (let i = 0; i < lines.length; i++) {
      if (lines[i].includes(`from '${from}'`) || lines[i].includes(`from "${from}"`)) {
        // Found the import line
        if (lines[i].includes(importSpec)) {
          // Already imported
          return { success: true, code, changed: false, message: `${importSpec} already imported` };
        }

        // Try to add to existing named imports
        if (!isDefault && lines[i].includes('{')) {
          const match = lines[i].match(/\{([^}]*)\}/);
          if (match) {
            const existingImports = match[1].split(',').map(s => s.trim());
            if (!existingImports.includes(importSpec)) {
              existingImports.push(importSpec);
              lines[i] = lines[i].replace(/\{[^}]*\}/, `{ ${existingImports.join(', ')} }`);
              return { success: true, code: lines.join('\n'), changed: true };
            }
          }
        }
      }
    }
  }

  // Find position to insert (after last import or at top)
  const lines = code.split('\n');
  let insertIndex = 0;

  for (let i = 0; i < lines.length; i++) {
    if (lines[i].match(/^import\s/)) {
      insertIndex = i + 1;
    }
  }

  // Build import statement
  let importStatement;
  if (isDefault) {
    importStatement = `import ${importSpec} from '${from}';`;
  } else if (importSpec.startsWith('{')) {
    importStatement = `import ${importSpec} from '${from}';`;
  } else {
    importStatement = `import { ${importSpec} } from '${from}';`;
  }

  lines.splice(insertIndex, 0, importStatement);
  return { success: true, code: lines.join('\n'), changed: true };
}

/**
 * Remove an import
 */
function removeImport(code, importSpec, from = null) {
  const lines = code.split('\n');
  let changed = false;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    // Skip if from specified and doesn't match
    if (from && !line.includes(`'${from}'`) && !line.includes(`"${from}"`)) {
      continue;
    }

    if (line.includes('import') && line.includes(importSpec)) {
      // Check if it's the only import from this module
      const match = line.match(/\{([^}]*)\}/);
      if (match) {
        const imports = match[1].split(',').map(s => s.trim());
        const filtered = imports.filter(s => s !== importSpec && !s.startsWith(`${importSpec} as`));

        if (filtered.length === 0) {
          // Remove entire line
          lines.splice(i, 1);
          i--;
        } else {
          // Update line with remaining imports
          lines[i] = line.replace(/\{[^}]*\}/, `{ ${filtered.join(', ')} }`);
        }
        changed = true;
      } else if (line.match(new RegExp(`import\\s+${importSpec}\\s+from`))) {
        // Default import - remove entire line
        lines.splice(i, 1);
        i--;
        changed = true;
      }
    }
  }

  return { success: true, code: lines.join('\n'), changed };
}

/**
 * Rename a variable or function throughout the code
 */
function rename(code, oldName, newName) {
  // Use word boundaries to avoid partial matches
  const regex = new RegExp(`\\b${oldName}\\b`, 'g');
  const newCode = code.replace(regex, newName);
  const changed = newCode !== code;

  return { success: true, code: newCode, changed };
}

/**
 * Add an export to a function or variable
 */
function addExport(code, name, isDefault = false) {
  const lines = code.split('\n');

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    // Find function declaration
    const funcMatch = line.match(new RegExp(`^(\\s*)(async\\s+)?function\\s+${name}\\s*\\(`));
    if (funcMatch) {
      const indent = funcMatch[1];
      if (isDefault) {
        lines[i] = `${indent}export default ${line.trim()}`;
      } else {
        lines[i] = `${indent}export ${line.trim()}`;
      }
      return { success: true, code: lines.join('\n'), changed: true };
    }

    // Find const/let/var declaration
    const varMatch = line.match(new RegExp(`^(\\s*)(const|let|var)\\s+${name}\\s*=`));
    if (varMatch) {
      const indent = varMatch[1];
      const keyword = varMatch[2];
      if (isDefault) {
        lines[i] = `${indent}export default ${line.trim()}`;
      } else {
        lines[i] = `${indent}export ${line.trim()}`;
      }
      return { success: true, code: lines.join('\n'), changed: true };
    }

    // Find arrow function
    const arrowMatch = line.match(new RegExp(`^(\\s*)(const|let)\\s+${name}\\s*=\\s*`));
    if (arrowMatch && (line.includes('=>') || lines[i + 1]?.includes('=>'))) {
      const indent = arrowMatch[1];
      if (isDefault) {
        lines[i] = `${indent}export default ${line.trim()}`;
      } else {
        lines[i] = `${indent}export ${line.trim()}`;
      }
      return { success: true, code: lines.join('\n'), changed: true };
    }
  }

  return { success: false, error: `Could not find ${name} to export` };
}

/**
 * Wrap code in a try-catch block
 */
function wrapInTryCatch(code, startLine, endLine, errorHandler = 'console.error(error)') {
  const lines = code.split('\n');
  const start = startLine - 1;
  const end = endLine - 1;

  if (start < 0 || end >= lines.length || start > end) {
    return { success: false, error: 'Invalid line range' };
  }

  // Detect indentation
  const indent = lines[start].match(/^(\s*)/)[1];
  const innerIndent = indent + '  ';

  // Extract lines to wrap
  const toWrap = lines.slice(start, end + 1).map(l => innerIndent + l.trim());

  // Build try-catch
  const tryCatch = [
    `${indent}try {`,
    ...toWrap,
    `${indent}} catch (error) {`,
    `${innerIndent}${errorHandler}`,
    `${indent}}`
  ];

  // Replace lines
  lines.splice(start, end - start + 1, ...tryCatch);

  return { success: true, code: lines.join('\n'), changed: true };
}

/**
 * Convert function to async
 */
function makeAsync(code, functionName) {
  // Match function declaration
  const funcRegex = new RegExp(`(^|\\n)(\\s*)(function\\s+${functionName}\\s*\\()`, 'g');
  let newCode = code.replace(funcRegex, '$1$2async $3');

  // Match arrow function
  const arrowRegex = new RegExp(`(const|let|var)\\s+(${functionName})\\s*=\\s*\\(`, 'g');
  newCode = newCode.replace(arrowRegex, `$1 ${functionName} = async (`);

  const changed = newCode !== code;
  return { success: true, code: newCode, changed };
}

/**
 * Convert var to const/let
 */
function convertVar(code, toKeyword = 'const') {
  const newCode = code.replace(/\bvar\s+/g, `${toKeyword} `);
  return { success: true, code: newCode, changed: newCode !== code };
}

/**
 * Main CLI interface
 */
function main() {
  const args = process.argv.slice(2);

  if (args.length < 2) {
    console.log(`AST Transformer - Fast code transforms without LLM

Usage:
  node ast_transformer.js <command> <file> [options]

Commands:
  add-import <file> --spec <spec> --from <module> [--default]
    Add an import statement

  remove-import <file> --spec <spec> [--from <module>]
    Remove an import

  rename <file> --old <name> --new <name>
    Rename a variable/function

  add-export <file> --name <name> [--default]
    Add export to a declaration

  make-async <file> --name <name>
    Convert function to async

  convert-var <file> [--to const|let]
    Convert var to const/let

  try-catch <file> --start <line> --end <line> [--handler <code>]
    Wrap lines in try-catch

Examples:
  node ast_transformer.js add-import app.js --spec "useState" --from "react"
  node ast_transformer.js rename utils.js --old "getData" --new "fetchData"
  node ast_transformer.js add-export helpers.js --name "formatDate"
`);
    process.exit(1);
  }

  const command = args[0];
  const file = args[1];

  // Parse options
  const options = {};
  for (let i = 2; i < args.length; i += 2) {
    if (args[i].startsWith('--')) {
      options[args[i].slice(2)] = args[i + 1] || true;
    }
  }

  // Read file
  if (!fs.existsSync(file)) {
    console.error(`File not found: ${file}`);
    process.exit(1);
  }
  const code = fs.readFileSync(file, 'utf8');

  let result;

  switch (command) {
    case 'add-import':
      result = addImport(code, options.spec, options.from, options.default === 'true' || options.default === true);
      break;

    case 'remove-import':
      result = removeImport(code, options.spec, options.from);
      break;

    case 'rename':
      result = rename(code, options.old, options.new);
      break;

    case 'add-export':
      result = addExport(code, options.name, options.default === 'true' || options.default === true);
      break;

    case 'make-async':
      result = makeAsync(code, options.name);
      break;

    case 'convert-var':
      result = convertVar(code, options.to || 'const');
      break;

    case 'try-catch':
      result = wrapInTryCatch(code, parseInt(options.start), parseInt(options.end), options.handler);
      break;

    default:
      console.error(`Unknown command: ${command}`);
      process.exit(1);
  }

  if (!result.success) {
    console.error(`Error: ${result.error}`);
    process.exit(1);
  }

  if (result.changed) {
    // Write back or output
    if (options.write || options.w) {
      fs.writeFileSync(file, result.code);
      console.log(`Updated ${file}`);
    } else {
      // Output to stdout (for preview/piping)
      console.log(result.code);
    }
  } else {
    console.error('No changes needed');
  }
}

if (require.main === module) {
  main();
}

module.exports = {
  addImport,
  removeImport,
  rename,
  addExport,
  makeAsync,
  convertVar,
  wrapInTryCatch
};
