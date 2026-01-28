/**
 * Tiered Router for Claude-Dash Gateway
 *
 * Implements multi-tier routing inspired by claude-flow:
 * - Tier 0: Cache (instant, 0 tokens)
 * - Tier 1: Pre-indexed memory (SQLite FTS5, HNSW - instant, 0 API tokens)
 * - Tier 2: Local AI (Ollama - ~1-2s, 0 API tokens)
 * - Tier 3: Claude API (when needed for complex reasoning)
 *
 * Cost optimization: Routes to cheapest tier that can handle the request.
 */

const path = require('path');
const fs = require('fs');

const MEMORY_ROOT = path.join(process.env.HOME, '.claude-dash');

/**
 * Routing Tiers
 */
const TIERS = {
  CACHE: { name: 'cached', cost: 0, latency: '<1ms', description: 'Cache hit' },
  MEMORY: { name: 'memory', cost: 0, latency: '1-5ms', description: 'Pre-indexed SQLite/HNSW' },
  LOCAL_AI: { name: 'local_ai', cost: 0, latency: '500-2000ms', description: 'Local Ollama' },
  FILESYSTEM: { name: 'filesystem', cost: 0, latency: '10-100ms', description: 'Direct file access' },
  API: { name: 'api', cost: 1, latency: '500-5000ms', description: 'Claude API call' }
};

/**
 * Read-only patterns - ALWAYS route to Ollama (free)
 * These queries don't modify anything and can be handled locally
 */
const READ_ONLY_PATTERNS = [
  /\b(where|find|search|look\s?up|locate)\b/i,
  /\b(what|explain|describe|summarize|tell\s+me\s+about)\b/i,
  /\b(how\s+does|how\s+do|how\s+is|how\s+are)\b/i,
  /\b(list|show|display|get)\b/i,
  /\b(which\s+file|what\s+file)\b/i,
  /\b(why\s+(is|does|did|are|do))\b/i,
  /\b(compare|difference\s+between)\b/i,
  /\b(overview|architecture|structure)\b/i,
];

/**
 * Ollama-specific enhancement patterns
 * Tasks that don't require Claude's full capabilities
 */
const OLLAMA_ENHANCEMENT_PATTERNS = [
  // Language translation
  /\b(translate|translation|convert\s+to|in\s+(spanish|french|german|italian|portuguese|chinese|japanese|korean))\b/i,

  // Code comments and documentation
  /\b(add\s+comment|comment\s+this|explain\s+this\s+(function|code|snippet)|what\s+does\s+this\s+code)\b/i,

  // Commit message generation
  /\b(generate\s+commit\s+message|commit\s+message\s+for|suggest\s+commit|draft\s+commit)\b/i,

  // Error explanations
  /\b(explain\s+(this\s+)?error|what\s+does.*error\s+mean|why.*error|interpret\s+error)\b/i,

  // Naming suggestions
  /\b(name\s+for|suggest\s+(a\s+)?name|rename|what\s+should\s+i\s+call|naming\s+convention)\b/i,

  // Documentation summarization
  /\b(summarize|tldr|tl;dr|key\s+points|brief\s+overview).*\b(documentation|readme|docs|guide)\b/i,

  // Test descriptions
  /\b(test\s+description|describe\s+(this\s+)?test|test\s+for|test\s+case)\b/i,

  // Simple code quality checks
  /\b(lint|code\s+quality|best\s+practices\s+for|improve\s+this\s+code|code\s+style)\b/i,

  // Log message formatting
  /\b(format\s+log|log\s+message|logging\s+format|standardize\s+log)\b/i,

  // Simple code explanations
  /\b(what\s+is\s+this\s+doing|walk\s+me\s+through|step\s+by\s+step|explain\s+line\s+by\s+line)\b/i,
];

/**
 * Write patterns - ALWAYS route to Claude API
 * These need Claude's full capabilities for safe code modification
 */
const WRITE_PATTERNS = [
  /\b(change|edit|modify|update|fix|create|add|remove|delete|refactor)\b/i,
  /\b(implement|write|build|make|generate)\b/i,
  /\b(commit|push|deploy|release)\b/i,
  /\b(rename|move|migrate)\b/i,
  /\b(install|upgrade|downgrade)\b/i,
];

/**
 * Query complexity classifier
 * Determines which tier can handle a query
 *
 * Priority:
 * 1. Write patterns → Claude API (always)
 * 2. Read-only patterns → Ollama (free)
 * 3. Default heuristics based on length
 */
function classifyQueryComplexity(query, tool) {
  const queryLower = query?.toLowerCase() || '';
  const queryLen = query?.length || 0;

  // FIRST: Check for write operations - these MUST go to Claude API
  for (const pattern of WRITE_PATTERNS) {
    if (pattern.test(queryLower)) {
      return {
        complexity: 'complex',
        minTier: 'API',
        reason: 'write operation',
        isWriteOperation: true
      };
    }
  }

  // SECOND: Check for Ollama enhancement patterns - specific tasks best suited for local AI
  for (const pattern of OLLAMA_ENHANCEMENT_PATTERNS) {
    if (pattern.test(queryLower)) {
      return {
        complexity: 'moderate',
        minTier: 'LOCAL_AI',
        reason: 'ollama enhancement task',
        isOllamaEnhancement: true
      };
    }
  }

  // THIRD: Check for read-only queries - route to Ollama (free)
  for (const pattern of READ_ONLY_PATTERNS) {
    if (pattern.test(queryLower)) {
      return {
        complexity: 'moderate',
        minTier: 'LOCAL_AI',
        reason: 'read-only query',
        isReadOnly: true
      };
    }
  }

  // Simple lookups - Tier 1 (Memory/Index)
  const simpleLookupPatterns = [
    /^where\s+is\s+/i,
    /^find\s+(the\s+)?file/i,
    /^what\s+function/i,
    /^show\s+me\s+(the\s+)?/i,
    /^list\s+(all\s+)?/i,
    /^get\s+(the\s+)?/i
  ];

  // Reasoning required - may need Tier 2 (Local AI) or Tier 3 (API)
  const reasoningPatterns = [
    /^how\s+(do(es)?|can|should)/i,
    /^why\s+(is|does|did)/i,
    /^explain\s+/i,
    /^what\s+is\s+the\s+(best|difference)/i,
    /^compare\s+/i,
    /^suggest\s+/i,
    /^refactor\s+/i,
    /^review\s+/i
  ];

  // Check patterns
  for (const pattern of simpleLookupPatterns) {
    if (pattern.test(queryLower)) {
      return { complexity: 'simple', minTier: 'MEMORY', reason: 'lookup query' };
    }
  }

  for (const pattern of reasoningPatterns) {
    if (pattern.test(queryLower)) {
      // Route to local AI by default for reasoning
      return { complexity: 'moderate', minTier: 'LOCAL_AI', reason: 'reasoning query' };
    }
  }

  // Default: shorter queries go to Ollama, longer to Claude
  if (queryLen < 300) {
    return { complexity: 'moderate', minTier: 'LOCAL_AI', reason: 'short/medium query' };
  } else {
    return { complexity: 'complex', minTier: 'API', reason: 'long query' };
  }
}

/**
 * Check if memory tier can handle the query
 */
function canMemoryHandle(tool, params, project) {
  // Tools that memory can handle
  const memoryTools = [
    'memory_query',
    'memory_search',
    'memory_functions',
    'memory_similar',
    'memory_sessions',
    'memory_search_all',
    'smart_read',
    'smart_search'
  ];

  if (!memoryTools.includes(tool)) {
    return false;
  }

  // Check if project has indexed data
  if (project) {
    const indexPath = path.join(MEMORY_ROOT, 'projects', project, 'summaries.json');
    return fs.existsSync(indexPath);
  }

  return true;
}

/**
 * Check if local AI (Ollama) is available
 */
let ollamaAvailable = null;
let ollamaLastCheck = 0;
const OLLAMA_CHECK_INTERVAL = 60000; // Check every minute

async function isOllamaAvailable() {
  const now = Date.now();

  if (ollamaAvailable !== null && (now - ollamaLastCheck) < OLLAMA_CHECK_INTERVAL) {
    return ollamaAvailable;
  }

  try {
    const http = require('http');
    return new Promise((resolve) => {
      const req = http.request({
        hostname: 'localhost',
        port: 11434,
        path: '/api/tags',
        method: 'GET',
        timeout: 2000
      }, (res) => {
        ollamaAvailable = res.statusCode === 200;
        ollamaLastCheck = now;
        resolve(ollamaAvailable);
      });

      req.on('error', () => {
        ollamaAvailable = false;
        ollamaLastCheck = now;
        resolve(false);
      });

      req.on('timeout', () => {
        req.destroy();
        ollamaAvailable = false;
        ollamaLastCheck = now;
        resolve(false);
      });

      req.end();
    });
  } catch (e) {
    ollamaAvailable = false;
    ollamaLastCheck = now;
    return false;
  }
}

/**
 * Main routing decision
 */
async function routeRequest(tool, params, cache, project) {
  const query = params.query || params.path || '';
  const classification = classifyQueryComplexity(query, tool);

  // Tier 0: Check cache first
  if (cache) {
    const cached = cache.get(tool, params);
    if (cached.hit) {
      return {
        tier: TIERS.CACHE,
        result: cached.value,
        classification
      };
    }
  }

  // Tier 1: Check if memory/index can handle
  if (canMemoryHandle(tool, params, project)) {
    return {
      tier: TIERS.MEMORY,
      handler: 'memory',
      classification
    };
  }

  // Tier 2: Check if local AI is available for reasoning queries
  if (classification.minTier === 'LOCAL_AI' || classification.complexity === 'moderate') {
    const ollamaReady = await isOllamaAvailable();
    if (ollamaReady) {
      return {
        tier: TIERS.LOCAL_AI,
        handler: 'ollama',
        classification
      };
    }
  }

  // Tier 3: Filesystem access for file operations
  if (['smart_read', 'smart_edit'].includes(tool)) {
    return {
      tier: TIERS.FILESYSTEM,
      handler: 'filesystem',
      classification
    };
  }

  // Default: Let the tool handle it directly
  return {
    tier: TIERS.MEMORY,
    handler: 'default',
    classification
  };
}

/**
 * Get routing statistics
 */
function getRoutingStats(metrics) {
  const breakdown = metrics?.data?.routingBreakdown || {};
  const total = Object.values(breakdown).reduce((a, b) => a + b, 0) || 1;

  return {
    tiers: Object.entries(breakdown).map(([tier, count]) => ({
      tier,
      count,
      percentage: ((count / total) * 100).toFixed(1) + '%'
    })),
    efficiency: {
      cacheHitRate: breakdown.cached ? ((breakdown.cached / total) * 100).toFixed(1) + '%' : '0%',
      memoryRate: breakdown.memory ? ((breakdown.memory / total) * 100).toFixed(1) + '%' : '0%',
      localAIRate: breakdown.local_ai ? ((breakdown.local_ai / total) * 100).toFixed(1) + '%' : '0%',
      apiRate: breakdown.api ? ((breakdown.api / total) * 100).toFixed(1) + '%' : '0%'
    }
  };
}

module.exports = {
  TIERS,
  READ_ONLY_PATTERNS,
  WRITE_PATTERNS,
  OLLAMA_ENHANCEMENT_PATTERNS,
  classifyQueryComplexity,
  canMemoryHandle,
  isOllamaAvailable,
  routeRequest,
  getRoutingStats
};
