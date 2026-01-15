#!/usr/bin/env node
/**
 * DEPRECATED MCP Server - Redirects to Gateway
 *
 * This server is deprecated. Use gateway/server.js instead.
 * This stub exists for backwards compatibility only.
 *
 * The gateway provides all these tools plus:
 * - Caching (smart_read, smart_exec)
 * - Metrics tracking
 * - AnythingLLM integration (doc_query)
 *
 * To migrate:
 * 1. Update your MCP settings to use gateway/server.js
 * 2. Remove this server from your configuration
 */

const path = require('path');
const { spawn } = require('child_process');

const GATEWAY_PATH = path.join(__dirname, '..', 'gateway', 'server.js');

console.error('='.repeat(60));
console.error('DEPRECATED: mcp-server/server.js');
console.error('');
console.error('This MCP server is deprecated. Redirecting to gateway...');
console.error('');
console.error('Please update your MCP configuration to use:');
console.error(`  ${GATEWAY_PATH}`);
console.error('='.repeat(60));
console.error('');

// Forward to gateway server
const gateway = spawn('node', [GATEWAY_PATH], {
  stdio: 'inherit',
  env: process.env
});

gateway.on('close', (code) => {
  process.exit(code);
});

gateway.on('error', (err) => {
  console.error('Failed to start gateway:', err.message);
  process.exit(1);
});
