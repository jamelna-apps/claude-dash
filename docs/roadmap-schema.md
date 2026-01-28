# Roadmap Schema Documentation

## Overview

Every project in claude-dash can have a `roadmap.json` file that tracks planned work, current priorities, and progress. This file is automatically loaded at the start of each session to provide context continuity.

## File Location

```
~/.claude-dash/projects/{project-id}/roadmap.json
```

## Schema

```json
{
  "version": "1.0",
  "project": "project-id",
  "displayName": "Project Display Name",
  "lastUpdated": "2026-01-19T00:00:00Z",
  "currentVersion": "1.0.0",
  "currentBuild": 1,

  "summary": {
    "status": "active|paused|maintenance|completed",
    "phase": "planning|development|testing|launch|post-launch",
    "description": "Brief description of current project state"
  },

  "recentlyCompleted": [
    {
      "item": "Feature or task description",
      "completedDate": "2026-01-15",
      "version": "1.0.0"
    }
  ],

  "currentSprint": {
    "name": "Sprint Name",
    "startDate": "2026-01-15",
    "endDate": "2026-01-29",
    "goals": ["Goal 1", "Goal 2"],
    "items": [
      {
        "id": "unique-id",
        "title": "Task title",
        "priority": "high|medium|low",
        "status": "pending|in_progress|blocked|completed",
        "description": "Detailed description",
        "assignee": "optional",
        "blockedBy": "optional - what's blocking this"
      }
    ]
  },

  "backlog": {
    "shortTerm": {
      "timeframe": "1-2 months",
      "items": [
        {
          "id": "unique-id",
          "title": "Feature/task title",
          "priority": "high|medium|low",
          "status": "not_started|planning|in_progress",
          "description": "What needs to be done",
          "relatedProject": "optional - for cross-project work",
          "estimatedEffort": "small|medium|large|extra-large",
          "dependencies": ["optional", "list", "of", "dependency", "ids"]
        }
      ]
    },
    "mediumTerm": {
      "timeframe": "3-6 months",
      "items": []
    },
    "longTerm": {
      "timeframe": "6+ months",
      "items": []
    }
  },

  "technicalDebt": [
    {
      "id": "unique-id",
      "title": "Debt item title",
      "priority": "high|medium|low",
      "description": "What needs to be addressed"
    }
  ],

  "blockers": [
    {
      "id": "unique-id",
      "title": "Blocker description",
      "severity": "critical|major|minor",
      "affects": ["list", "of", "affected", "item", "ids"],
      "resolution": "How to resolve (if known)"
    }
  ],

  "milestones": [
    {
      "id": "unique-id",
      "title": "Milestone name",
      "targetDate": "2026-03-01",
      "status": "upcoming|in_progress|completed|missed",
      "criteria": ["What defines completion"]
    }
  ],

  "notes": [
    "Important notes about the project",
    "Context that should be remembered"
  ]
}
```

## Status Values

### Project Status
- `active` - Actively being developed
- `paused` - Development temporarily on hold
- `maintenance` - Only bug fixes and maintenance
- `completed` - Project is feature-complete

### Project Phase
- `planning` - Still in design/planning phase
- `development` - Active feature development
- `testing` - In QA/testing phase
- `launch` - Preparing for or actively launching
- `post-launch` - Post-release polish and monitoring

### Item Priority
- `high` - Should be done ASAP
- `medium` - Important but not urgent
- `low` - Nice to have, do when time allows

### Item Status
- `not_started` - Haven't begun work
- `pending` - Ready to start
- `planning` - In design/planning
- `in_progress` - Actively working on
- `blocked` - Waiting on something
- `completed` - Done

### Effort Estimates
- `small` - A few hours
- `medium` - A day or two
- `large` - A week
- `extra-large` - Multiple weeks

## Auto-Injection

The roadmap is automatically injected at session start via the `inject-context.sh` hook. The injection includes:

1. **Summary** - Current status and phase
2. **Current Sprint** - Active tasks with status
3. **Next Up** - Top 3-5 items from short-term backlog
4. **Blockers** - Any active blockers

## MCP Tool

Use `memory_roadmap` to query or update the roadmap:

```
memory_roadmap project=gyst action=status
memory_roadmap project=gyst action=next
memory_roadmap project=gyst action=complete id=task-id
memory_roadmap project=gyst action=add title="New task" priority=high
```

## Best Practices

1. **Keep it current** - Update after completing tasks
2. **Be specific** - Use clear, actionable titles
3. **Link related items** - Use `relatedProject` and `dependencies`
4. **Review weekly** - Reprioritize and update estimates
5. **Record context** - Use `notes` for important decisions
