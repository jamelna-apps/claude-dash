#!/usr/bin/env node

/**
 * Claude Summarizer for Claude Memory System
 *
 * Generates semantic summaries for files using Claude API:
 * - Reads structural data from summaries.json
 * - Sends file content + structure to Claude for summarization
 * - Updates summaries.json with semantic summaries
 * - Batches requests with rate limiting
 *
 * Usage: ANTHROPIC_API_KEY=xxx node summarizer.js <project-path> <project-id>
 */

const fs = require('fs');
const path = require('path');
const https = require('https');

// Configuration
const BATCH_SIZE = 2;  // Files per batch (reduced for rate limits)
const BATCH_DELAY_MS = 15000;  // 15 seconds between batches for rate limits
const MAX_FILE_SIZE = 50000;  // Skip files larger than 50KB for summarization
const PRIORITY_PATTERNS = [
  /Screen\.js$/,      // Screens first
  /Service\.js$/,     // Services
  /Hook\.js$/,        // Hooks
  /Context\.js$/,     // Contexts
];

/**
 * Call Claude API
 */
async function callClaude(prompt, maxTokens = 500) {
  const apiKey = process.env.ANTHROPIC_API_KEY;

  if (!apiKey) {
    throw new Error('ANTHROPIC_API_KEY environment variable not set');
  }

  return new Promise((resolve, reject) => {
    const data = JSON.stringify({
      model: 'claude-3-5-haiku-20241022',
      max_tokens: maxTokens,
      messages: [{ role: 'user', content: prompt }]
    });

    const options = {
      hostname: 'api.anthropic.com',
      port: 443,
      path: '/v1/messages',
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': apiKey,
        'anthropic-version': '2023-06-01',
        'Content-Length': Buffer.byteLength(data)
      }
    };

    const req = https.request(options, (res) => {
      let body = '';
      res.on('data', chunk => body += chunk);
      res.on('end', () => {
        try {
          const response = JSON.parse(body);
          if (response.error) {
            reject(new Error(response.error.message));
          } else {
            resolve(response.content[0].text);
          }
        } catch (e) {
          reject(new Error(`Failed to parse response: ${body}`));
        }
      });
    });

    req.on('error', reject);
    req.write(data);
    req.end();
  });
}

/**
 * Generate summary prompt for a file
 */
function generatePrompt(filePath, content, structuralData) {
  const truncatedContent = content.length > 15000
    ? content.substring(0, 15000) + '\n... [truncated]'
    : content;

  return `Analyze this React Native/JavaScript file and provide a concise summary.

FILE: ${filePath}

STRUCTURAL INFO:
- Component: ${structuralData.isComponent ? structuralData.componentName : 'No'}
- Functions: ${structuralData.functions?.map(f => f.name).join(', ') || 'None'}
- Hooks used: ${structuralData.hooks?.join(', ') || 'None'}
- State variables: ${structuralData.stateVariables?.join(', ') || 'None'}
- Firestore ops: ${structuralData.firestoreOperations?.join(', ') || 'None'}
- Navigation: ${structuralData.navigation?.join(', ') || 'None'}

CODE:
\`\`\`javascript
${truncatedContent}
\`\`\`

Respond ONLY with a JSON object (no markdown, no explanation):
{
  "summary": "1-2 sentence summary of what this file does",
  "purpose": "The main purpose (e.g., 'User authentication screen', 'Wardrobe data management hook')",
  "keyLogic": "Most important function or logic and what it does (e.g., 'handleLogin() at line 45 validates credentials')",
  "collections": ["list", "of", "firestore", "collections", "used"],
  "complexity": "low|medium|high"
}`;
}

/**
 * Process a single file
 */
async function processFile(projectPath, relativePath, structuralData) {
  const fullPath = path.join(projectPath, relativePath);

  try {
    const stats = fs.statSync(fullPath);
    if (stats.size > MAX_FILE_SIZE) {
      return {
        summary: 'Large file - manual review recommended',
        purpose: 'Unknown (file too large for auto-summarization)',
        keyLogic: null,
        collections: structuralData.firestoreOperations?.length > 0 ? ['unknown'] : [],
        complexity: 'high',
        skipped: true
      };
    }

    const content = fs.readFileSync(fullPath, 'utf8');
    const prompt = generatePrompt(relativePath, content, structuralData);

    const response = await callClaude(prompt);

    // Parse JSON response
    try {
      // Try to extract JSON from response
      const jsonMatch = response.match(/\{[\s\S]*\}/);
      if (jsonMatch) {
        return JSON.parse(jsonMatch[0]);
      }
      throw new Error('No JSON found in response');
    } catch (parseError) {
      console.error(`  Failed to parse response for ${relativePath}`);
      return {
        summary: 'Failed to generate summary',
        purpose: null,
        keyLogic: null,
        collections: [],
        complexity: 'unknown',
        error: parseError.message
      };
    }
  } catch (error) {
    console.error(`  Error processing ${relativePath}: ${error.message}`);
    return {
      summary: 'Error during summarization',
      purpose: null,
      keyLogic: null,
      collections: [],
      complexity: 'unknown',
      error: error.message
    };
  }
}

/**
 * Sort files by priority
 */
function sortByPriority(files) {
  return files.sort((a, b) => {
    // Priority files first
    const aIsPriority = PRIORITY_PATTERNS.some(p => p.test(a));
    const bIsPriority = PRIORITY_PATTERNS.some(p => p.test(b));

    if (aIsPriority && !bIsPriority) return -1;
    if (!aIsPriority && bIsPriority) return 1;

    // Then by path (screens before services, etc.)
    return a.localeCompare(b);
  });
}

/**
 * Sleep helper
 */
function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * Main function
 */
async function main() {
  const args = process.argv.slice(2);

  if (args.length < 2) {
    console.log('Usage: ANTHROPIC_API_KEY=xxx node summarizer.js <project-path> <project-id> [--limit N]');
    console.log('Example: ANTHROPIC_API_KEY=xxx node summarizer.js /path/to/WardrobeApp gyst --limit 10');
    process.exit(1);
  }

  const projectPath = args[0];
  const projectId = args[1];

  // Parse optional limit
  let limit = Infinity;
  const limitIdx = args.indexOf('--limit');
  if (limitIdx !== -1 && args[limitIdx + 1]) {
    limit = parseInt(args[limitIdx + 1], 10);
  }

  // Check for dry-run
  const dryRun = args.includes('--dry-run');

  const memoryPath = path.join(process.env.HOME, '.claude-dash', 'projects', projectId);
  const summariesPath = path.join(memoryPath, 'summaries.json');

  if (!fs.existsSync(summariesPath)) {
    console.error(`Summaries file not found: ${summariesPath}`);
    console.error('Run ast-parser.js first to generate structural summaries.');
    process.exit(1);
  }

  // Load existing summaries
  const summaries = JSON.parse(fs.readFileSync(summariesPath, 'utf8'));

  // Find files needing summarization
  const filesToProcess = sortByPriority(
    Object.entries(summaries.files)
      .filter(([_, data]) => !data.summary || data.summary === null)
      .map(([path, _]) => path)
  ).slice(0, limit);

  console.log(`Found ${filesToProcess.length} files to summarize`);

  if (dryRun) {
    console.log('\nDry run - files that would be processed:');
    filesToProcess.slice(0, 20).forEach(f => console.log(`  - ${f}`));
    if (filesToProcess.length > 20) {
      console.log(`  ... and ${filesToProcess.length - 20} more`);
    }
    process.exit(0);
  }

  if (!process.env.ANTHROPIC_API_KEY) {
    console.error('\nANTHROPIC_API_KEY environment variable not set');
    console.error('Usage: ANTHROPIC_API_KEY=xxx node summarizer.js ...');
    process.exit(1);
  }

  // Process in batches
  let processed = 0;
  let errors = 0;

  for (let i = 0; i < filesToProcess.length; i += BATCH_SIZE) {
    const batch = filesToProcess.slice(i, i + BATCH_SIZE);
    console.log(`\nBatch ${Math.floor(i / BATCH_SIZE) + 1}/${Math.ceil(filesToProcess.length / BATCH_SIZE)}`);

    const batchPromises = batch.map(async (filePath) => {
      console.log(`  Processing: ${filePath}`);
      const result = await processFile(projectPath, filePath, summaries.files[filePath]);

      // Update summaries
      Object.assign(summaries.files[filePath], result);

      if (result.error) {
        errors++;
      } else {
        processed++;
      }

      return result;
    });

    await Promise.all(batchPromises);

    // Save after each batch
    summaries.lastUpdated = new Date().toISOString();
    fs.writeFileSync(summariesPath, JSON.stringify(summaries, null, 2));

    // Rate limit delay
    if (i + BATCH_SIZE < filesToProcess.length) {
      console.log(`  Waiting ${BATCH_DELAY_MS}ms before next batch...`);
      await sleep(BATCH_DELAY_MS);
    }
  }

  console.log(`\nDone! Processed: ${processed}, Errors: ${errors}`);
  console.log(`Updated: ${summariesPath}`);
}

// Run if called directly
if (require.main === module) {
  main().catch(console.error);
}

module.exports = { callClaude, processFile, generatePrompt };
