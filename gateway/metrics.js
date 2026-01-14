/**
 * Metrics Tracking for Claude-Dash Gateway
 *
 * Tracks token savings, routing decisions, and cache performance.
 */

const fs = require('fs');
const path = require('path');

const METRICS_FILE = path.join(process.env.HOME, '.claude-dash', 'gateway', 'metrics.json');

class Metrics {
  constructor() {
    this.data = this.load();
    this.sessionStart = Date.now();
  }

  load() {
    try {
      if (fs.existsSync(METRICS_FILE)) {
        return JSON.parse(fs.readFileSync(METRICS_FILE, 'utf8'));
      }
    } catch (e) {
      // Ignore
    }
    return this.getDefaultMetrics();
  }

  getDefaultMetrics() {
    return {
      totalQueries: 0,
      routingBreakdown: {
        memory: 0,
        filesystem: 0,
        commander: 0,
        cached: 0,
        anythingllm: 0
      },
      tokenEstimates: {
        saved: 0,
        actual: 0,
        wouldHaveBeen: 0
      },
      recentQueries: [],
      dailyStats: {},
      lastUpdated: Date.now()
    };
  }

  save() {
    this.data.lastUpdated = Date.now();
    try {
      fs.writeFileSync(METRICS_FILE, JSON.stringify(this.data, null, 2));
    } catch (e) {
      // Non-critical
    }
  }

  /**
   * Record a query and its routing decision
   */
  recordQuery(query) {
    const {
      tool,
      route,       // 'memory' | 'filesystem' | 'commander' | 'cached'
      tokensUsed,  // Actual tokens returned
      tokensSaved, // Estimated tokens saved vs full read
      latencyMs,
      cacheHit
    } = query;

    this.data.totalQueries++;
    this.data.routingBreakdown[route] = (this.data.routingBreakdown[route] || 0) + 1;

    if (tokensUsed) this.data.tokenEstimates.actual += tokensUsed;
    if (tokensSaved) this.data.tokenEstimates.saved += tokensSaved;

    // Track recent queries (keep last 100)
    this.data.recentQueries.unshift({
      tool,
      route,
      tokensUsed,
      tokensSaved,
      latencyMs,
      cacheHit,
      timestamp: Date.now()
    });
    if (this.data.recentQueries.length > 100) {
      this.data.recentQueries = this.data.recentQueries.slice(0, 100);
    }

    // Daily stats
    const today = new Date().toISOString().split('T')[0];
    if (!this.data.dailyStats[today]) {
      this.data.dailyStats[today] = { queries: 0, tokensSaved: 0, cacheHits: 0 };
    }
    this.data.dailyStats[today].queries++;
    if (tokensSaved) this.data.dailyStats[today].tokensSaved += tokensSaved;
    if (cacheHit) this.data.dailyStats[today].cacheHits++;

    // Periodic save
    if (this.data.totalQueries % 10 === 0) {
      this.save();
    }
  }

  /**
   * Estimate tokens for a piece of content
   * Rough approximation: 1 token ~ 4 characters
   */
  estimateTokens(content) {
    if (!content) return 0;
    return Math.ceil(String(content).length / 4);
  }

  /**
   * Get summary statistics
   */
  getSummary() {
    const { routingBreakdown, tokenEstimates, totalQueries, recentQueries } = this.data;

    // Calculate percentages
    const total = totalQueries || 1;
    const routingPercentages = {};
    for (const [route, count] of Object.entries(routingBreakdown)) {
      routingPercentages[route] = ((count / total) * 100).toFixed(1) + '%';
    }

    // Recent latency stats
    const recentLatencies = recentQueries.slice(0, 20).map(q => q.latencyMs).filter(Boolean);
    const avgLatency = recentLatencies.length > 0
      ? Math.round(recentLatencies.reduce((a, b) => a + b, 0) / recentLatencies.length)
      : 0;

    // Token savings rate
    const potentialTokens = tokenEstimates.actual + tokenEstimates.saved;
    const savingsRate = potentialTokens > 0
      ? ((tokenEstimates.saved / potentialTokens) * 100).toFixed(1) + '%'
      : '0%';

    return {
      totalQueries,
      sessionDuration: this.formatDuration(Date.now() - this.sessionStart),
      routing: {
        counts: routingBreakdown,
        percentages: routingPercentages
      },
      tokens: {
        actualUsed: tokenEstimates.actual,
        saved: tokenEstimates.saved,
        savingsRate
      },
      performance: {
        avgLatencyMs: avgLatency
      }
    };
  }

  /**
   * Get recent activity for dashboard
   */
  getRecentActivity(limit = 20) {
    return this.data.recentQueries.slice(0, limit).map(q => ({
      ...q,
      timeAgo: this.formatTimeAgo(q.timestamp)
    }));
  }

  /**
   * Get daily trends
   */
  getDailyTrends(days = 7) {
    const trends = [];
    const stats = this.data.dailyStats;

    for (let i = 0; i < days; i++) {
      const date = new Date();
      date.setDate(date.getDate() - i);
      const key = date.toISOString().split('T')[0];
      trends.push({
        date: key,
        ...stats[key] || { queries: 0, tokensSaved: 0, cacheHits: 0 }
      });
    }

    return trends.reverse();
  }

  formatDuration(ms) {
    const seconds = Math.floor(ms / 1000);
    if (seconds < 60) return `${seconds}s`;
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}m`;
    const hours = Math.floor(minutes / 60);
    return `${hours}h ${minutes % 60}m`;
  }

  formatTimeAgo(timestamp) {
    const seconds = Math.floor((Date.now() - timestamp) / 1000);
    if (seconds < 60) return `${seconds}s ago`;
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    return `${days}d ago`;
  }

  /**
   * Reset metrics
   */
  reset() {
    this.data = this.getDefaultMetrics();
    this.sessionStart = Date.now();
    this.save();
  }
}

module.exports = { Metrics };
