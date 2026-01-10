# API Keys Management Design

## Overview

A secure API keys management section for the Claude Memory Dashboard that stores keys in macOS Keychain and syncs them to project `.env` files.

## Goals

- Centrally manage API keys across multiple projects
- Secure storage using macOS Keychain (no plaintext files)
- Manual sync to project `.env` files with smart merge
- Support for various services (Claude API, Stripe, Firebase, etc.)

## Architecture

### Storage Layer

Keys stored in macOS Keychain under service name `claude-memory-keys`. Each key stored as: `claude-memory:{KEY_NAME}`.

Metadata (no secrets) stored in `~/.claude-memory/global/keys-metadata.json`:

```json
{
  "CLAUDE_API_KEY": {
    "description": "Anthropic API key",
    "projects": ["gyst", "jamelna", "smartiegoals"],
    "createdAt": "2025-12-27T...",
    "lastSynced": { "gyst": "2025-12-27T..." }
  }
}
```

### Server Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/keys` | List all keys (metadata only) |
| GET | `/api/keys/:name` | Get key value from Keychain |
| POST | `/api/keys` | Add new key |
| PUT | `/api/keys/:name` | Update key |
| DELETE | `/api/keys/:name` | Remove key |
| POST | `/api/keys/:name/sync` | Sync to projects |

### Security

- Server uses `security` CLI for Keychain access
- Keys only retrieved when explicitly requested
- No caching of secret values in memory

## UI Design

### Keys Tab

New tab added after "Sessions" with key icon.

### Key Card Layout

```
CLAUDE_API_KEY
sk-ant-••••••••••••••••••••••abcd
Anthropic API key
Tags: gyst, jamelna, smartiegoals     [Reveal] [Copy] [Menu]
Last synced: gyst (2 hours ago)
```

### Actions

- Reveal: Shows full key for 5 seconds
- Copy: Copies to clipboard
- Menu: Edit, Sync, Delete

### Add/Edit Modal

- Key name (uppercase, underscores)
- Key value (password input)
- Description (optional)
- Project tags (multi-select)

## Sync Flow

### Process

1. User clicks Sync on a key
2. Modal shows tagged projects with checkboxes
3. User confirms selection
4. For each project:
   - Read existing `.env`
   - Create `.env.backup`
   - Update or append key
   - Update `.env.example` with placeholder
   - Record lastSynced timestamp

### Conflict Handling

- Existing key with different value: show diff, confirm overwrite
- Malformed `.env`: show error, skip

### Results Modal

Shows per-project status (Updated, Added, No change, Skipped).

## Error Handling

### Keychain Access

- First access prompts macOS permission dialog
- Denied access shows instructions for System Settings

### Validation

- Key names: uppercase and underscores only
- No duplicate names
- No empty values

### Edge Cases

- Missing project path: warning icon, skip on sync
- No `.env` file: create new
- No `.env.example`: create with placeholder
