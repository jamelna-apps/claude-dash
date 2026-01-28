#!/usr/bin/env python3
"""
Claude-Dash Webhook Listener

Listens for events and triggers project re-indexing.
Supports: git.push, file.change, build.complete, manual.reindex

Usage:
    python3 webhook-listener.py [--port PORT] [--log-level LEVEL]

Events:
    POST /webhook
    {
        "event": "git.push" | "file.change" | "build.complete" | "manual.reindex",
        "project": "project-id",
        "data": { ... optional event-specific data ... }
    }

    GET /health - Health check endpoint
    GET /status - Show recent events and stats
"""

import os
import sys
import json
import logging
import argparse
import subprocess
from datetime import datetime
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import threading
import time

# Configuration
MEMORY_ROOT = Path.home() / '.claude-dash'
CONFIG_PATH = MEMORY_ROOT / 'config.json'
LOG_PATH = MEMORY_ROOT / 'logs' / 'webhook-listener.log'
EVENTS_LOG = MEMORY_ROOT / 'logs' / 'webhook-events.json'
DEFAULT_PORT = 8765

# Event history (in-memory, last 100 events)
event_history = []
MAX_HISTORY = 100

# Stats
stats = {
    'started_at': None,
    'total_events': 0,
    'events_by_type': {},
    'events_by_project': {},
    'last_event': None,
    'reindex_count': 0,
    'errors': 0
}

def setup_logging(level='INFO'):
    """Configure logging to file and console."""
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[
            logging.FileHandler(LOG_PATH),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

def load_config():
    """Load claude-dash config."""
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Failed to load config: {e}")
        return {'projects': []}

def get_project_by_id(project_id):
    """Find project config by ID."""
    config = load_config()
    for project in config.get('projects', []):
        if project.get('id') == project_id:
            return project
    return None

def trigger_reindex(project_id, event_type='manual'):
    """Trigger re-indexing for a project."""
    logger = logging.getLogger(__name__)

    project = get_project_by_id(project_id)
    if not project:
        logger.warning(f"Project not found: {project_id}")
        return False, f"Project not found: {project_id}"

    project_path = project.get('path')
    if not project_path or not Path(project_path).exists():
        logger.warning(f"Project path not found: {project_path}")
        return False, f"Project path not found: {project_path}"

    # Write trigger file that watcher picks up
    trigger_path = MEMORY_ROOT / 'projects' / project_id / '.reindex-trigger'
    trigger_path.parent.mkdir(parents=True, exist_ok=True)

    trigger_data = {
        'triggered_at': datetime.now().isoformat(),
        'event_type': event_type,
        'project_path': project_path
    }

    with open(trigger_path, 'w') as f:
        json.dump(trigger_data, f)

    logger.info(f"Triggered reindex for {project_id} (event: {event_type})")
    stats['reindex_count'] += 1

    return True, f"Reindex triggered for {project_id}"

def run_watcher_incremental(project_id, changed_files=None):
    """Run incremental update via watcher."""
    logger = logging.getLogger(__name__)

    watcher_script = MEMORY_ROOT / 'watcher' / 'watcher.js'
    if not watcher_script.exists():
        logger.warning("Watcher script not found")
        return False

    try:
        cmd = ['node', str(watcher_script), '--project', project_id]
        if changed_files:
            cmd.extend(['--files', ','.join(changed_files)])

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(MEMORY_ROOT / 'watcher')
        )

        if result.returncode == 0:
            logger.info(f"Watcher update completed for {project_id}")
            return True
        else:
            logger.error(f"Watcher error: {result.stderr}")
            return False
    except subprocess.TimeoutExpired:
        logger.error(f"Watcher timeout for {project_id}")
        return False
    except Exception as e:
        logger.error(f"Watcher exception: {e}")
        return False

def record_event(event_data):
    """Record event to history and stats."""
    timestamp = datetime.now().isoformat()
    event_record = {
        'timestamp': timestamp,
        **event_data
    }

    # Update history
    event_history.append(event_record)
    if len(event_history) > MAX_HISTORY:
        event_history.pop(0)

    # Update stats
    stats['total_events'] += 1
    stats['last_event'] = timestamp

    event_type = event_data.get('event', 'unknown')
    stats['events_by_type'][event_type] = stats['events_by_type'].get(event_type, 0) + 1

    project = event_data.get('project', 'unknown')
    stats['events_by_project'][project] = stats['events_by_project'].get(project, 0) + 1

    # Persist to log file
    try:
        events_file = EVENTS_LOG
        events_file.parent.mkdir(parents=True, exist_ok=True)

        existing = []
        if events_file.exists():
            try:
                with open(events_file) as f:
                    existing = json.load(f)
            except:
                pass

        existing.append(event_record)
        # Keep last 1000 events on disk
        existing = existing[-1000:]

        with open(events_file, 'w') as f:
            json.dump(existing, f, indent=2)
    except Exception as e:
        logging.error(f"Failed to persist event: {e}")

class WebhookHandler(BaseHTTPRequestHandler):
    """HTTP request handler for webhooks."""

    def log_message(self, format, *args):
        """Override to use our logger."""
        logging.info(f"{self.address_string()} - {format % args}")

    def send_json_response(self, status_code, data):
        """Send JSON response."""
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', 'localhost')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def do_OPTIONS(self):
        """Handle CORS preflight."""
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', 'localhost')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        """Handle GET requests."""
        parsed = urlparse(self.path)
        path = parsed.path

        if path == '/health':
            self.send_json_response(200, {
                'status': 'healthy',
                'uptime_seconds': int(time.time() - stats['started_at']) if stats['started_at'] else 0,
                'total_events': stats['total_events']
            })

        elif path == '/status':
            self.send_json_response(200, {
                'stats': stats,
                'recent_events': event_history[-20:],
                'projects': [p['id'] for p in load_config().get('projects', [])]
            })

        elif path == '/events':
            # Get event history with optional filtering
            query = parse_qs(parsed.query)
            limit = int(query.get('limit', [50])[0])
            project = query.get('project', [None])[0]
            event_type = query.get('type', [None])[0]

            events = event_history[-limit:]
            if project:
                events = [e for e in events if e.get('project') == project]
            if event_type:
                events = [e for e in events if e.get('event') == event_type]

            self.send_json_response(200, {
                'events': events,
                'total': len(events)
            })

        else:
            self.send_json_response(404, {'error': 'Not found'})

    def do_POST(self):
        """Handle POST requests (webhooks)."""
        if self.path != '/webhook':
            self.send_json_response(404, {'error': 'Not found'})
            return

        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            self.send_json_response(400, {'error': 'Invalid JSON'})
            return

        event_type = data.get('event')
        project_id = data.get('project')
        event_data = data.get('data', {})

        if not event_type:
            self.send_json_response(400, {'error': 'Missing event type'})
            return

        if not project_id:
            self.send_json_response(400, {'error': 'Missing project ID'})
            return

        # Validate project exists
        project = get_project_by_id(project_id)
        if not project:
            self.send_json_response(404, {
                'error': f'Project not found: {project_id}',
                'available_projects': [p['id'] for p in load_config().get('projects', [])]
            })
            return

        logging.info(f"Received event: {event_type} for {project_id}")

        # Record the event
        record_event({
            'event': event_type,
            'project': project_id,
            'data': event_data
        })

        # Handle different event types
        result = {'event': event_type, 'project': project_id}

        if event_type == 'git.push':
            # Git push - full reindex
            success, message = trigger_reindex(project_id, 'git.push')
            result['reindex'] = success
            result['message'] = message

            # If commits provided, could do smarter incremental update
            commits = event_data.get('commits', [])
            if commits:
                changed_files = []
                for commit in commits:
                    changed_files.extend(commit.get('added', []))
                    changed_files.extend(commit.get('modified', []))
                result['changed_files'] = len(changed_files)

        elif event_type == 'file.change':
            # File change - incremental update
            changed_files = event_data.get('files', [])
            if changed_files:
                success = run_watcher_incremental(project_id, changed_files)
                result['incremental_update'] = success
                result['files_updated'] = len(changed_files)
            else:
                # No specific files, trigger full reindex
                success, message = trigger_reindex(project_id, 'file.change')
                result['reindex'] = success
                result['message'] = message

        elif event_type == 'build.complete':
            # Build complete - refresh function index
            success, message = trigger_reindex(project_id, 'build.complete')
            result['reindex'] = success
            result['message'] = message
            result['build_status'] = event_data.get('status', 'unknown')

        elif event_type == 'manual.reindex':
            # Manual reindex request
            success, message = trigger_reindex(project_id, 'manual')
            result['reindex'] = success
            result['message'] = message

        else:
            # Unknown event type - log but don't fail
            logging.warning(f"Unknown event type: {event_type}")
            result['warning'] = f"Unknown event type, no action taken"

        self.send_json_response(200, result)

def run_server(port=DEFAULT_PORT):
    """Run the webhook server."""
    logger = logging.getLogger(__name__)

    stats['started_at'] = time.time()

    server_address = ('127.0.0.1', port)
    httpd = HTTPServer(server_address, WebhookHandler)

    logger.info(f"Webhook listener started on http://127.0.0.1:{port}")
    logger.info(f"Endpoints: POST /webhook, GET /health, GET /status, GET /events")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down webhook listener")
        httpd.shutdown()

def main():
    parser = argparse.ArgumentParser(description='Claude-Dash Webhook Listener')
    parser.add_argument('--port', type=int, default=DEFAULT_PORT, help=f'Port to listen on (default: {DEFAULT_PORT})')
    parser.add_argument('--log-level', default='INFO', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'], help='Log level')
    args = parser.parse_args()

    setup_logging(args.log_level)
    run_server(args.port)

if __name__ == '__main__':
    main()
