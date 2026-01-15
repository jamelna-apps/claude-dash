/**
 * Cache Layer for Claude-Dash Gateway
 *
 * Provides TTL-based caching for command results, file reads, and queries.
 */

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const CACHE_DIR = path.join(process.env.HOME, '.claude-dash', 'cache');

// Default TTLs in seconds
const DEFAULT_TTLS = {
  gitStatus: 30,
  fileList: 300,      // 5 minutes
  npmList: 3600,      // 1 hour
  fileRead: 600,      // 10 minutes
  query: 300,         // 5 minutes
  default: 60
};

class Cache {
  constructor() {
    this.memory = new Map();
    this.hits = 0;
    this.misses = 0;
    this.ensureCacheDir();
  }

  ensureCacheDir() {
    if (!fs.existsSync(CACHE_DIR)) {
      fs.mkdirSync(CACHE_DIR, { recursive: true });
    }
  }

  /**
   * Generate cache key from type and parameters
   */
  generateKey(type, params) {
    const data = JSON.stringify({ type, params });
    return crypto.createHash('md5').update(data).digest('hex');
  }

  /**
   * Get TTL for a given cache type
   */
  getTTL(type, command = null) {
    // Special handling for known commands
    if (command) {
      if (command.includes('git status')) return DEFAULT_TTLS.gitStatus;
      if (command.includes('npm list') || command.includes('npm ls')) return DEFAULT_TTLS.npmList;
      if (command.match(/^ls\s/)) return DEFAULT_TTLS.fileList;
    }
    return DEFAULT_TTLS[type] || DEFAULT_TTLS.default;
  }

  /**
   * Get cached value
   */
  get(type, params) {
    const key = this.generateKey(type, params);

    // Check memory cache first
    const memEntry = this.memory.get(key);
    if (memEntry && Date.now() < memEntry.expires) {
      this.hits++;
      return { hit: true, value: memEntry.value, source: 'memory' };
    }

    // Check disk cache
    const filePath = path.join(CACHE_DIR, `${key}.json`);
    if (fs.existsSync(filePath)) {
      try {
        const data = JSON.parse(fs.readFileSync(filePath, 'utf8'));
        if (Date.now() < data.expires) {
          // FIXED: Restore to memory with original expiry (not refreshed)
          // This preserves the original TTL semantics
          this.memory.set(key, data);
          this.hits++;
          return { hit: true, value: data.value, source: 'disk' };
        }
        // Expired - delete from both memory and disk
        this.memory.delete(key);
        fs.unlinkSync(filePath);
      } catch (e) {
        // Corrupted cache file - delete it
        try { fs.unlinkSync(filePath); } catch (e2) {}
      }
    }

    this.misses++;
    return { hit: false };
  }

  /**
   * Set cached value
   */
  set(type, params, value, customTTL = null) {
    const key = this.generateKey(type, params);
    const ttl = customTTL || this.getTTL(type, params.command);
    const expires = Date.now() + (ttl * 1000);

    const entry = { value, expires, type, params, cachedAt: Date.now() };

    // Store in memory
    this.memory.set(key, entry);

    // Persist to disk for longer-lived entries
    if (ttl > 60) {
      const filePath = path.join(CACHE_DIR, `${key}.json`);
      try {
        fs.writeFileSync(filePath, JSON.stringify(entry));
      } catch (e) {
        // Non-critical if disk cache fails
      }
    }
  }

  /**
   * Invalidate cache entries matching a pattern
   */
  invalidate(pattern) {
    // Clear matching memory entries
    for (const [key, entry] of this.memory.entries()) {
      if (this.matchesPattern(entry, pattern)) {
        this.memory.delete(key);
      }
    }

    // Clear matching disk entries
    try {
      const files = fs.readdirSync(CACHE_DIR);
      for (const file of files) {
        if (file.endsWith('.json')) {
          const filePath = path.join(CACHE_DIR, file);
          try {
            const data = JSON.parse(fs.readFileSync(filePath, 'utf8'));
            if (this.matchesPattern(data, pattern)) {
              fs.unlinkSync(filePath);
            }
          } catch (e) {
            // Ignore corrupted files
          }
        }
      }
    } catch (e) {
      // Cache dir might not exist
    }
  }

  matchesPattern(entry, pattern) {
    if (pattern.type && entry.type !== pattern.type) return false;
    // FIXED: Use exact path match or startsWith for proper path comparison
    // Previously used .includes() which caused false positives
    if (pattern.path && entry.params?.path) {
      const entryPath = path.resolve(entry.params.path);
      const patternPath = path.resolve(pattern.path);
      // Match if exact same path, or entry path starts with pattern path (file in directory)
      if (entryPath !== patternPath && !entryPath.startsWith(patternPath + path.sep)) {
        return false;
      }
    }
    if (pattern.project && entry.params?.project !== pattern.project) return false;
    return true;
  }

  /**
   * Get cache statistics
   */
  getStats() {
    const total = this.hits + this.misses;
    return {
      hits: this.hits,
      misses: this.misses,
      hitRate: total > 0 ? ((this.hits / total) * 100).toFixed(1) + '%' : '0%',
      memoryEntries: this.memory.size,
      diskEntries: this.countDiskEntries()
    };
  }

  countDiskEntries() {
    try {
      return fs.readdirSync(CACHE_DIR).filter(f => f.endsWith('.json')).length;
    } catch (e) {
      return 0;
    }
  }

  /**
   * Clear all caches
   */
  clear() {
    this.memory.clear();
    try {
      const files = fs.readdirSync(CACHE_DIR);
      for (const file of files) {
        if (file.endsWith('.json')) {
          fs.unlinkSync(path.join(CACHE_DIR, file));
        }
      }
    } catch (e) {
      // Ignore
    }
    this.hits = 0;
    this.misses = 0;
  }

  /**
   * Clean up expired entries from disk cache
   * ADDED: Periodic cleanup to prevent disk cache from growing indefinitely
   */
  cleanupExpired() {
    const now = Date.now();
    let cleaned = 0;

    try {
      const files = fs.readdirSync(CACHE_DIR);
      for (const file of files) {
        if (file.endsWith('.json')) {
          const filePath = path.join(CACHE_DIR, file);
          try {
            const data = JSON.parse(fs.readFileSync(filePath, 'utf8'));
            if (now >= data.expires) {
              fs.unlinkSync(filePath);
              cleaned++;
            }
          } catch (e) {
            // Corrupted file - delete it
            try { fs.unlinkSync(filePath); } catch (e2) {}
            cleaned++;
          }
        }
      }
    } catch (e) {
      // Ignore
    }

    return cleaned;
  }
}

module.exports = { Cache, DEFAULT_TTLS };
