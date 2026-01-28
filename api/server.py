#!/usr/bin/env python3
"""
Claude-Dash API Server with Tool Calling

OpenAI-compatible REST API with:
- RAG for codebase questions
- Tool calling (time, weather, web search)
- Smart model routing

Endpoints:
  GET  /v1/models              - List available models
  POST /v1/chat/completions    - Chat with RAG + tools
  GET  /health                 - Health check
  GET  /projects               - List indexed projects

Usage:
  python server.py [--port 5100] [--host 0.0.0.0]
"""

import json
import os
import sys
import time
import uuid
import argparse
import logging
import subprocess
import urllib.request
import urllib.error
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
from typing import Optional, Dict, Any, List
from datetime import datetime
import re

# Setup paths
MEMORY_ROOT = Path(os.environ.get('CLAUDE_DASH_ROOT', Path.home() / '.claude-dash'))
MLX_TOOLS = MEMORY_ROOT / 'mlx-tools'
PROJECTS_DIR = MEMORY_ROOT / 'projects'

# =============================================================================
# SECURITY: CORS and Rate Limiting
# =============================================================================

# SECURITY: Restrict CORS to localhost and Tailscale only
ALLOWED_ORIGINS = [
    'http://localhost:3000',
    'http://localhost:3333',  # Dashboard
    'http://127.0.0.1:3000',
    'http://127.0.0.1:3333',
]

def get_cors_origin(request_origin: str) -> str:
    """Return allowed origin or empty string if not allowed."""
    if request_origin in ALLOWED_ORIGINS:
        return request_origin
    # Allow localhost on any port for development
    if request_origin and (request_origin.startswith('http://localhost:') or
                           request_origin.startswith('http://127.0.0.1:')):
        return request_origin
    # Allow Tailscale IPs (100.x.x.x range) for remote access
    if request_origin and request_origin.startswith('http://100.'):
        return request_origin
    return ''

# SECURITY: Simple rate limiting
from collections import defaultdict
import threading

class RateLimiter:
    """Simple in-memory rate limiter."""
    def __init__(self, max_requests: int = 60, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = defaultdict(list)
        self.lock = threading.Lock()

    def is_allowed(self, client_ip: str) -> bool:
        """Check if request is allowed for this client."""
        now = time.time()
        with self.lock:
            # Clean old requests
            self.requests[client_ip] = [
                t for t in self.requests[client_ip]
                if now - t < self.window_seconds
            ]
            # Check limit
            if len(self.requests[client_ip]) >= self.max_requests:
                return False
            # Record this request
            self.requests[client_ip].append(now)
            return True

# Global rate limiter: 60 requests per minute per IP
rate_limiter = RateLimiter(max_requests=60, window_seconds=60)

# Add mlx-tools to path for imports
if str(MLX_TOOLS) not in sys.path:
    sys.path.insert(0, str(MLX_TOOLS))

# Import from mlx-tools
try:
    from config import (
        OLLAMA_URL, OLLAMA_CHAT_MODEL, OLLAMA_TIMEOUT,
        get_model_for_task, OLLAMA_TOOL_MODEL
    )
except ImportError:
    OLLAMA_URL = os.environ.get('OLLAMA_URL', 'http://localhost:11434')
    OLLAMA_CHAT_MODEL = os.environ.get('OLLAMA_MODEL', 'gemma3:4b-it-qat')
    OLLAMA_TOOL_MODEL = None  # Tool calling not supported locally - use Claude
    OLLAMA_TIMEOUT = 120
    def get_model_for_task(task): return OLLAMA_CHAT_MODEL

# Try to import hybrid search
try:
    from hybrid_search import hybrid_search
    HAS_HYBRID = True
except ImportError:
    HAS_HYBRID = False
    hybrid_search = None

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('claude-dash-api')


# =============================================================================
# TOOL DEFINITIONS
# =============================================================================

AVAILABLE_TOOLS = [
    {
        "name": "get_current_time",
        "description": "Get the current time in a specific timezone or location",
        "input_schema": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "City or timezone (e.g., 'Tokyo', 'New York', 'UTC', 'America/Los_Angeles')"
                }
            },
            "required": ["location"]
        }
    },
    {
        "name": "get_weather",
        "description": "Get current weather for a location",
        "input_schema": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "City name (e.g., 'Tokyo', 'New York', 'London')"
                }
            },
            "required": ["location"]
        }
    },
    {
        "name": "calculate",
        "description": "Perform mathematical calculations",
        "input_schema": {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "Mathematical expression to evaluate (e.g., '2 + 2', 'sqrt(16)', '100 * 1.15')"
                }
            },
            "required": ["expression"]
        }
    },
    # --- macOS Integration Tools ---
    {
        "name": "get_calendar_events",
        "description": "Get upcoming calendar events from macOS Calendar app",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Number of days to look ahead (default: 7, max: 30)"
                },
                "calendar": {
                    "type": "string",
                    "description": "Specific calendar name to filter (optional, searches all if not specified)"
                }
            }
        }
    },
    {
        "name": "get_reminders",
        "description": "Get pending reminders from macOS Reminders app",
        "input_schema": {
            "type": "object",
            "properties": {
                "list_name": {
                    "type": "string",
                    "description": "Specific reminder list to check (optional, checks all if not specified)"
                },
                "include_completed": {
                    "type": "boolean",
                    "description": "Include completed reminders (default: false)"
                }
            }
        }
    },
    {
        "name": "get_recent_emails",
        "description": "Get recent emails from macOS Mail app",
        "input_schema": {
            "type": "object",
            "properties": {
                "count": {
                    "type": "integer",
                    "description": "Number of recent emails to retrieve (default: 10, max: 50)"
                },
                "mailbox": {
                    "type": "string",
                    "description": "Mailbox to check (default: INBOX)"
                },
                "unread_only": {
                    "type": "boolean",
                    "description": "Only show unread emails (default: false)"
                }
            }
        }
    },
    {
        "name": "search_emails",
        "description": "Search emails by keyword in subject or sender",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search term to find in email subject or sender"
                },
                "count": {
                    "type": "integer",
                    "description": "Max results to return (default: 10)"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_notes",
        "description": "Search or list notes from macOS Notes app",
        "input_schema": {
            "type": "object",
            "properties": {
                "search": {
                    "type": "string",
                    "description": "Search term to find in notes (optional, lists recent if not specified)"
                },
                "folder": {
                    "type": "string",
                    "description": "Specific folder to search in (optional)"
                },
                "count": {
                    "type": "integer",
                    "description": "Max notes to return (default: 10)"
                }
            }
        }
    },
    {
        "name": "get_contacts",
        "description": "Search contacts from macOS Contacts app",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name to search for"
                }
            },
            "required": ["name"]
        }
    }
]

# Timezone mapping for common cities
TIMEZONE_MAP = {
    'tokyo': 'Asia/Tokyo',
    'beijing': 'Asia/Shanghai',
    'shanghai': 'Asia/Shanghai',
    'china': 'Asia/Shanghai',
    'new york': 'America/New_York',
    'nyc': 'America/New_York',
    'los angeles': 'America/Los_Angeles',
    'la': 'America/Los_Angeles',
    'london': 'Europe/London',
    'paris': 'Europe/Paris',
    'berlin': 'Europe/Berlin',
    'sydney': 'Australia/Sydney',
    'melbourne': 'Australia/Melbourne',
    'singapore': 'Asia/Singapore',
    'hong kong': 'Asia/Hong_Kong',
    'dubai': 'Asia/Dubai',
    'mumbai': 'Asia/Kolkata',
    'delhi': 'Asia/Kolkata',
    'chicago': 'America/Chicago',
    'seattle': 'America/Los_Angeles',
    'san francisco': 'America/Los_Angeles',
    'sf': 'America/Los_Angeles',
    'miami': 'America/New_York',
    'denver': 'America/Denver',
    'phoenix': 'America/Phoenix',
    'utc': 'UTC',
    'gmt': 'UTC',
}


# =============================================================================
# TOOL HANDLERS
# =============================================================================

def handle_get_current_time(location: str) -> str:
    """Get current time for a location."""
    try:
        from datetime import datetime, timezone
        import zoneinfo

        # Normalize location
        location_lower = location.lower().strip()

        # Try to find timezone
        tz_name = TIMEZONE_MAP.get(location_lower)

        if not tz_name:
            # Try direct timezone name
            try:
                tz = zoneinfo.ZoneInfo(location)
                tz_name = location
            except:
                # Default to UTC if unknown
                tz_name = 'UTC'

        tz = zoneinfo.ZoneInfo(tz_name)
        now = datetime.now(tz)

        return f"Current time in {location}: {now.strftime('%Y-%m-%d %H:%M:%S %Z')} ({now.strftime('%I:%M %p')})"
    except Exception as e:
        return f"Could not get time for {location}: {str(e)}"


def handle_get_weather(location: str) -> str:
    """Get weather for a location using wttr.in API."""
    try:
        # Use wttr.in for simple weather (no API key needed)
        url = f"https://wttr.in/{urllib.parse.quote(location)}?format=j1"
        req = urllib.request.Request(url, headers={'User-Agent': 'curl/7.68.0'})

        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))

            current = data.get('current_condition', [{}])[0]
            area = data.get('nearest_area', [{}])[0]

            temp_c = current.get('temp_C', 'N/A')
            temp_f = current.get('temp_F', 'N/A')
            desc = current.get('weatherDesc', [{}])[0].get('value', 'Unknown')
            humidity = current.get('humidity', 'N/A')
            wind_kmph = current.get('windspeedKmph', 'N/A')
            city = area.get('areaName', [{}])[0].get('value', location)
            country = area.get('country', [{}])[0].get('value', '')

            return f"""Weather in {city}, {country}:
- Temperature: {temp_c}°C ({temp_f}°F)
- Conditions: {desc}
- Humidity: {humidity}%
- Wind: {wind_kmph} km/h"""
    except Exception as e:
        return f"Could not get weather for {location}: {str(e)}"


def handle_calculate(expression: str) -> str:
    """Safely evaluate a mathematical expression using AST.
    SECURITY: Uses AST-based evaluation instead of eval() to prevent code injection.
    """
    import ast
    import math
    import operator

    # Allowed operations
    SAFE_OPERATORS = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
        ast.USub: operator.neg,
        ast.UAdd: operator.pos,
    }

    # Allowed functions
    SAFE_FUNCTIONS = {
        'abs': abs, 'round': round, 'min': min, 'max': max,
        'pow': pow, 'sqrt': math.sqrt,
        'sin': math.sin, 'cos': math.cos, 'tan': math.tan,
        'log': math.log, 'log10': math.log10, 'exp': math.exp,
    }

    # Allowed constants
    SAFE_CONSTANTS = {
        'pi': math.pi, 'e': math.e,
    }

    def safe_eval_node(node):
        """Recursively evaluate AST node safely."""
        if isinstance(node, ast.Constant):  # Python 3.8+
            if isinstance(node.value, (int, float)):
                return node.value
            raise ValueError(f"Unsafe constant: {node.value}")
        elif isinstance(node, ast.Num):  # Python 3.7 compatibility
            return node.n
        elif isinstance(node, ast.Name):
            name = node.id
            if name in SAFE_CONSTANTS:
                return SAFE_CONSTANTS[name]
            raise ValueError(f"Unknown variable: {name}")
        elif isinstance(node, ast.BinOp):
            op_type = type(node.op)
            if op_type not in SAFE_OPERATORS:
                raise ValueError(f"Unsafe operator: {op_type.__name__}")
            left = safe_eval_node(node.left)
            right = safe_eval_node(node.right)
            return SAFE_OPERATORS[op_type](left, right)
        elif isinstance(node, ast.UnaryOp):
            op_type = type(node.op)
            if op_type not in SAFE_OPERATORS:
                raise ValueError(f"Unsafe operator: {op_type.__name__}")
            operand = safe_eval_node(node.operand)
            return SAFE_OPERATORS[op_type](operand)
        elif isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise ValueError("Only simple function calls allowed")
            func_name = node.func.id
            if func_name not in SAFE_FUNCTIONS:
                raise ValueError(f"Unknown function: {func_name}")
            args = [safe_eval_node(arg) for arg in node.args]
            return SAFE_FUNCTIONS[func_name](*args)
        else:
            raise ValueError(f"Unsafe expression type: {type(node).__name__}")

    try:
        # Clean expression
        expr = expression.replace('^', '**')

        # Parse and evaluate safely using AST
        tree = ast.parse(expr, mode='eval')
        result = safe_eval_node(tree.body)

        return f"{expression} = {result}"
    except Exception as e:
        return f"Could not calculate '{expression}': {str(e)}"


# =============================================================================
# macOS INTEGRATION HANDLERS
# =============================================================================

def run_applescript(script: str, timeout: int = 30) -> str:
    """Run AppleScript and return result."""
    try:
        # Write script to temp file to handle multi-line scripts better
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.scpt', delete=False) as f:
            f.write(script)
            script_path = f.name

        try:
            result = subprocess.run(
                ['osascript', script_path],
                capture_output=True,
                text=True,
                timeout=timeout
            )
            if result.returncode == 0:
                return result.stdout.strip()
            else:
                return f"Error: {result.stderr.strip()}"
        finally:
            os.unlink(script_path)
    except subprocess.TimeoutExpired:
        return "Error: AppleScript timed out"
    except Exception as e:
        return f"Error: {str(e)}"


def handle_get_calendar_events(days: int = 7, calendar: str = None, period: str = None) -> str:
    """Get upcoming calendar events using icalBuddy (fast) or AppleScript fallback."""
    import shutil

    days = min(max(days, 0), 30)  # Clamp to 0-30 days

    # Try icalBuddy first (much faster)
    icalbuddy_path = shutil.which('icalBuddy') or '/opt/homebrew/bin/icalBuddy'
    if os.path.exists(icalbuddy_path):
        try:
            # Build the base command
            cmd = [icalbuddy_path, '-nc', '-nrd', '-npn', '-ea', '-eep', 'notes,url,attendees,location', '-po', 'datetime,title', '-iep', 'title,datetime', '-b', '• ', '-tf', '%H:%M', '-df', '%a %b %d']

            # Add the date range command
            if period == 'tomorrow':
                cmd.extend(['eventsFrom:tomorrow', 'to:tomorrow'])
            elif days == 0 or period == 'today':
                cmd.append('eventsToday')
            else:
                cmd.append(f'eventsToday+{days}')
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15, env={**os.environ, 'PATH': '/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin'})
            if result.returncode == 0 and result.stdout.strip():
                import re
                clean = re.sub(r'\x1b\[[0-9;]*m', '', result.stdout)
                lines = clean.strip().split('\n')
                events = []
                current_event = None
                for line in lines:
                    if line.startswith('• '):
                        # New event - datetime line
                        if current_event and current_event.get('title'):
                            events.append(current_event)
                        current_event = {'time': line[2:].strip(), 'title': ''}
                    elif current_event and line.strip():
                        # Indented title line
                        current_event['title'] = line.strip()
                if current_event and current_event.get('title'):
                    events.append(current_event)

                if events:
                    formatted = []
                    for evt in events[:15]:
                        formatted.append(f"- {evt['time']}: {evt['title']}")

                    display_period = period or ("today" if days == 0 else "tomorrow" if days == 1 else f"the next {days} days")
                    return f"Your events for {display_period}:\n" + "\n".join(formatted)
                else:
                    display_period = period or ("today" if days == 0 else "tomorrow" if days == 1 else f"the next {days} days")
                    return f"No events found for {display_period}."
        except Exception as e:
            logger.warning(f"icalBuddy failed: {e}, falling back to AppleScript")

    # Fallback to AppleScript (slower)
    script = '''
set output to ""
tell application "Calendar"
    set todayDate to current date
    set futureDate to todayDate + 7 * days
    repeat with cal in calendars
        try
            set calEvents to (every event of cal whose start date >= todayDate and start date <= futureDate)
            repeat with evt in calEvents
                set evtStart to start date of evt
                set evtSummary to summary of evt
                set output to output & evtSummary & " - " & (evtStart as string) & return
            end repeat
        end try
    end repeat
end tell
return output
'''
    result = run_applescript(script, timeout=30)
    if result.startswith("Error"):
        return result
    if not result.strip():
        return f"No events found in the next {days} day{'s' if days > 1 else ''}."
    lines = [f"- {line.strip()}" for line in result.strip().split('\n') if line.strip()][:15]
    return f"Your upcoming events:\n" + "\n".join(lines)


def handle_get_reminders(list_name: str = None, include_completed: bool = False) -> str:
    """Get reminders from Reminders app."""
    # Simplified script that's more reliable
    script = '''
tell application "Reminders"
    set output to ""
    repeat with reminderList in lists
        set listName to name of reminderList
        set rems to (every reminder of reminderList whose completed is false)
        if (count of rems) > 0 then
            set output to output & "[ " & listName & " ]" & return
            repeat with rem in rems
                set remName to name of rem
                set output to output & "  - " & remName & return
            end repeat
        end if
    end repeat
    return output
end tell
'''

    result = run_applescript(script, timeout=15)
    if result.startswith("Error"):
        return result

    if not result.strip():
        return "No pending reminders found."

    return "Your reminders:\n\n" + result


def handle_get_recent_emails(count: int = 10, mailbox: str = "INBOX", unread_only: bool = False) -> str:
    """Get recent emails from Mail app."""
    count = min(max(count, 1), 20)  # Clamp to 1-20 for speed

    if unread_only:
        # Query unread emails directly (much faster)
        script = f'''
tell application "Mail"
    set output to ""
    try
        set unreadMsgs to (messages of inbox whose read status is false)
        set msgCount to count of unreadMsgs
        if msgCount > {count} then set msgCount to {count}

        repeat with i from 1 to msgCount
            set msg to item i of unreadMsgs
            set msgSubject to subject of msg
            set msgSender to sender of msg
            set msgDate to date received of msg as string
            set output to output & msgDate & return
            set output to output & "  From: " & msgSender & return
            set output to output & "  Subject: " & msgSubject & return & return
        end repeat
    end try
    return output
end tell
'''
    else:
        # Get recent emails regardless of read status
        script = f'''
tell application "Mail"
    set output to ""
    try
        set acct to account 1
        set mbox to mailbox "{mailbox}" of acct
        set msgs to messages of mbox
        set msgCount to count of msgs
        if msgCount > {count} then set msgCount to {count}

        repeat with i from 1 to msgCount
            set msg to item i of msgs
            set msgSubject to subject of msg
            set msgSender to sender of msg
            set msgDate to date received of msg as string
            set msgRead to read status of msg
            set readMark to ""
            if msgRead is false then set readMark to "[UNREAD] "
            set output to output & readMark & msgDate & return
            set output to output & "  From: " & msgSender & return
            set output to output & "  Subject: " & msgSubject & return & return
        end repeat
    end try
    return output
end tell
'''

    result = run_applescript(script, timeout=15)
    if result.startswith("Error"):
        return result

    if not result.strip():
        if unread_only:
            return "No unread emails."
        return f"No emails found in {mailbox}."

    return result.strip()


def handle_search_emails(query: str, count: int = 10) -> str:
    """Search emails by subject or sender."""
    count = min(max(count, 1), 10)  # Limit for speed
    query_escaped = query.replace('"', '\\"').replace("'", "\\'")

    script = f'''
tell application "Mail"
    set output to ""
    set matchCount to 0
    try
        set acct to account 1
        set mbox to mailbox "INBOX" of acct
        set msgs to messages of mbox

        repeat with msg in msgs
            if matchCount >= {count} then exit repeat
            set msgSubject to subject of msg
            set msgSender to sender of msg

            if msgSubject contains "{query_escaped}" or msgSender contains "{query_escaped}" then
                set msgDate to date received of msg as string
                set output to output & msgDate & return
                set output to output & "  From: " & msgSender & return
                set output to output & "  Subject: " & msgSubject & return & return
                set matchCount to matchCount + 1
            end if
        end repeat
    end try
    return output
end tell
'''

    result = run_applescript(script, timeout=90)
    if result.startswith("Error"):
        return result

    if not result.strip():
        return f"No emails found matching '{query}'."

    return f"Emails matching '{query}':\n\n{result}"


def handle_get_notes(search: str = None, folder: str = None, count: int = 10) -> str:
    """Get or search notes from Notes app."""
    count = min(max(count, 1), 10)

    # Simple approach - just get note names directly
    script = f'tell application "Notes" to get name of (notes 1 thru {count})'

    result = run_applescript(script, timeout=30)
    if result.startswith("Error"):
        return result

    if not result.strip():
        return "No notes found."

    # Parse comma-separated names
    notes = [n.strip() for n in result.split(',')]
    formatted = '\n'.join([f"- {n}" for n in notes if n])

    return f"Recent notes:\n{formatted}"


def handle_get_contacts(name: str) -> str:
    """Search contacts by name."""
    name_escaped = name.replace('"', '\\"').replace("'", "\\'")

    # Simpler script - just get names first, then details for matches
    script = f'tell application "Contacts" to get name of (every person whose name contains "{name_escaped}")'

    result = run_applescript(script, timeout=60)

    if result.startswith("Error"):
        # Contacts search can be slow with large address books
        if "timed out" in result:
            return "Contact search timed out. Try a more specific name."
        return result

    if not result.strip():
        return f"No contacts found matching '{name}'."

    # Parse names and format
    names = [n.strip() for n in result.split(',')]
    if len(names) > 10:
        names = names[:10]
        formatted = '\n'.join([f"- {n}" for n in names])
        return f"Contacts matching '{name}' (showing 10 of {len(names)}):\n{formatted}"

    formatted = '\n'.join([f"- {n}" for n in names if n])
    return f"Contacts matching '{name}':\n{formatted}"


def execute_tool(tool_name: str, tool_input: dict) -> str:
    """Execute a tool and return the result."""
    if tool_name == "get_current_time":
        return handle_get_current_time(tool_input.get("location", "UTC"))
    elif tool_name == "get_weather":
        return handle_get_weather(tool_input.get("location", ""))
    elif tool_name == "calculate":
        return handle_calculate(tool_input.get("expression", ""))
    # macOS integration tools
    elif tool_name == "get_calendar_events":
        return handle_get_calendar_events(
            days=tool_input.get("days", 7),
            calendar=tool_input.get("calendar")
        )
    elif tool_name == "get_reminders":
        return handle_get_reminders(
            list_name=tool_input.get("list_name"),
            include_completed=tool_input.get("include_completed", False)
        )
    elif tool_name == "get_recent_emails":
        return handle_get_recent_emails(
            count=tool_input.get("count", 10),
            mailbox=tool_input.get("mailbox", "INBOX"),
            unread_only=tool_input.get("unread_only", False)
        )
    elif tool_name == "search_emails":
        return handle_search_emails(
            query=tool_input.get("query", ""),
            count=tool_input.get("count", 10)
        )
    elif tool_name == "get_notes":
        return handle_get_notes(
            search=tool_input.get("search"),
            folder=tool_input.get("folder"),
            count=tool_input.get("count", 10)
        )
    elif tool_name == "get_contacts":
        return handle_get_contacts(
            name=tool_input.get("name", "")
        )
    else:
        return f"Unknown tool: {tool_name}"


# =============================================================================
# QUERY CLASSIFICATION
# =============================================================================

def classify_query(query: str) -> Dict[str, Any]:
    """Classify a query to determine routing."""
    query_lower = query.lower()

    # Tool-requiring patterns
    time_patterns = ['what time', 'current time', 'time in', 'time is it', 'what\'s the time']
    weather_patterns = ['weather', 'temperature', 'forecast', 'how hot', 'how cold', 'raining']
    calc_patterns = ['calculate', 'compute', 'what is', 'how much is', '+', '-', '*', '/', '=']

    # macOS integration patterns
    calendar_patterns = ['calendar', 'schedule', 'events', 'appointments', 'meetings', 'what\'s on',
                         'do i have', 'my day', 'upcoming', 'next week', 'tomorrow', 'today\'s schedule']
    reminder_patterns = ['reminders', 'remind me', 'to do', 'todo', 'tasks', 'my reminders',
                         'what do i need', 'pending tasks']
    email_patterns = ['email', 'emails', 'mail', 'inbox', 'unread', 'messages', 'who emailed',
                      'recent emails', 'check my email', 'any emails']
    notes_patterns = ['notes', 'my notes', 'note about', 'find note', 'search notes']
    contacts_patterns = ['contact', 'phone number', 'email for', 'contact info', 'how to reach']

    # Code patterns
    code_patterns = ['function', 'method', 'class', 'implement', 'code', 'error', 'bug',
                     'how does', 'where is', 'find the', 'show me the', 'review']

    # Project patterns (check if mentions a project)
    projects = get_projects()
    project_mentioned = None
    for proj in projects:
        proj_id = proj.get('id', '').lower()
        proj_name = proj.get('displayName', proj.get('name', '')).lower()
        if proj_id in query_lower or proj_name in query_lower:
            project_mentioned = proj.get('id')
            break

    # Classify
    needs_tools = False
    tool_type = None
    needs_rag = False

    if any(p in query_lower for p in time_patterns):
        needs_tools = True
        tool_type = 'time'
    elif any(p in query_lower for p in weather_patterns):
        needs_tools = True
        tool_type = 'weather'
    elif any(p in query_lower for p in calc_patterns) and any(c.isdigit() for c in query):
        needs_tools = True
        tool_type = 'calculate'
    # macOS integration - check these before code patterns
    elif any(p in query_lower for p in calendar_patterns):
        needs_tools = True
        tool_type = 'calendar'
    elif any(p in query_lower for p in reminder_patterns):
        needs_tools = True
        tool_type = 'reminders'
    elif any(p in query_lower for p in email_patterns):
        needs_tools = True
        tool_type = 'email'
    elif any(p in query_lower for p in notes_patterns):
        needs_tools = True
        tool_type = 'notes'
    elif any(p in query_lower for p in contacts_patterns):
        needs_tools = True
        tool_type = 'contacts'
    elif project_mentioned or any(p in query_lower for p in code_patterns):
        needs_rag = True

    return {
        'needs_tools': needs_tools,
        'tool_type': tool_type,
        'needs_rag': needs_rag,
        'project': project_mentioned
    }


# =============================================================================
# RAG HELPERS (preserved from original)
# =============================================================================

def get_projects() -> list:
    """Get list of indexed projects."""
    config_path = MEMORY_ROOT / 'config.json'
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text())
            return config.get('projects', [])
        except Exception:
            pass

    projects = []
    if PROJECTS_DIR.exists():
        for p in PROJECTS_DIR.iterdir():
            if p.is_dir() and (p / 'index.json').exists():
                projects.append({'id': p.name, 'name': p.name})
    return projects


def detect_project_from_query(query: str) -> Optional[str]:
    """Try to detect which project the query is about."""
    query_lower = query.lower()
    projects = get_projects()

    for proj in projects:
        proj_id = proj.get('id', '')
        proj_name = proj.get('displayName', proj.get('name', '')).lower()
        if proj_id.lower() in query_lower or proj_name in query_lower:
            return proj_id

    if projects:
        return projects[0].get('id')
    return None


def retrieve_context(query: str, project_id: Optional[str] = None, top_k: int = 5) -> str:
    """Retrieve relevant context from claude-dash memory."""
    if not project_id:
        project_id = detect_project_from_query(query)

    if not project_id:
        return ""

    context_parts = []
    query_lower = query.lower()

    # Overview keywords
    overview_keywords = ['what is', 'what does', 'tell me about', 'describe', 'overview',
                         'purpose', 'about this', 'what kind of', 'explain the project']
    is_overview = any(kw in query_lower for kw in overview_keywords)

    # Add project overview
    if is_overview:
        index_path = PROJECTS_DIR / project_id / 'index.json'
        if index_path.exists():
            try:
                index = json.loads(index_path.read_text())
                context_parts.append("## Project Overview")
                context_parts.append(f"**Name:** {index.get('displayName', index.get('project', project_id))}")

                structure = index.get('structure', {})
                if structure.get('framework'):
                    context_parts.append(f"**Framework:** {structure.get('framework')}")
                if structure.get('languages'):
                    context_parts.append(f"**Languages:** {', '.join(structure.get('languages', []))}")

                features = index.get('featureModules', [])
                if features:
                    context_parts.append(f"**Features:** {', '.join(features[:15])}")
                context_parts.append("")
            except Exception:
                pass

    # Hybrid search
    if HAS_HYBRID and hybrid_search:
        try:
            results = hybrid_search(project_id, query, top_k=top_k)
            for r in results[:top_k]:
                file_path = r.get('file', '')
                summary = r.get('summary', '')
                purpose = r.get('purpose', '')

                if summary or purpose:
                    context_parts.append(f"**{file_path}**")
                    if purpose:
                        context_parts.append(f"Purpose: {purpose}")
                    if summary:
                        context_parts.append(f"Summary: {summary}")
                    context_parts.append("")
        except Exception:
            pass

    if context_parts:
        return "## Relevant Context from Codebase\n\n" + "\n".join(context_parts)
    return ""


# =============================================================================
# TOOL-CALLING WITH ANTHROPIC API
# =============================================================================

def call_with_tools(messages: list, tools: list = None) -> Dict:
    """Call local model with tool support. NOTE: Tool calling not supported locally - use Claude API."""
    url = f"{OLLAMA_URL}/v1/messages"

    payload = {
        "model": OLLAMA_TOOL_MODEL,
        "max_tokens": 1024,
        "messages": messages
    }

    if tools:
        payload["tools"] = tools

    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        url, data=data,
        headers={'Content-Type': 'application/json', 'x-api-key': 'ollama'}
    )

    try:
        with urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT) as response:
            return json.loads(response.read().decode('utf-8'))
    except Exception as e:
        logger.error(f"Tool calling failed: {e}")
        return {"error": str(e)}


def process_with_tools(query: str, conversation: list = None) -> str:
    """Process a query that may require tool calling."""

    # FAST PATH: Direct execution for obvious macOS queries (skip LLM entirely)
    query_lower = query.lower()

    # Calendar fast path
    if any(p in query_lower for p in ['calendar', 'schedule', 'my day', 'appointments', 'meetings']):
        logger.info(f"Fast path: calendar query")
        # Determine the specific day range
        if 'today' in query_lower:
            result = handle_get_calendar_events(days=0, period='today')
        elif 'tomorrow' in query_lower:
            result = handle_get_calendar_events(days=1, period='tomorrow')
        elif 'week' in query_lower:
            result = handle_get_calendar_events(days=7, period='this week')
        else:
            result = handle_get_calendar_events(days=3, period='the next few days')
        return result or "No upcoming events found."

    # Reminders fast path
    if any(p in query_lower for p in ['reminder', 'to do', 'todo', 'tasks']):
        logger.info(f"Fast path: reminders query")
        result = handle_get_reminders()
        if result and not result.startswith("Error"):
            return f"Here are your reminders:\n\n{result}"
        return result or "No reminders found."

    # Email fast path
    if any(p in query_lower for p in ['email', 'mail', 'inbox', 'unread']):
        logger.info(f"Fast path: email query")
        unread_only = 'unread' in query_lower
        if 'search' in query_lower or 'find' in query_lower or 'from' in query_lower:
            result = handle_get_recent_emails(count=10, unread_only=unread_only)
        else:
            result = handle_get_recent_emails(count=5, unread_only=unread_only)
        if result and not result.startswith("Error"):
            prefix = "Your unread emails" if unread_only else "Your recent emails"
            return f"{prefix}:\n{result}"
        return result or ("No unread emails." if unread_only else "No recent emails found.")

    # Notes fast path
    if any(p in query_lower for p in ['notes', 'my notes']):
        logger.info(f"Fast path: notes query")
        result = handle_get_notes(limit=10)
        if result and not result.startswith("Error"):
            return f"Here are your recent notes:\n\n{result}"
        return result or "No notes found."

    # Time fast path (no AppleScript needed)
    if any(p in query_lower for p in ['what time', 'current time', 'time is it']):
        logger.info(f"Fast path: time query")
        from datetime import datetime
        return f"The current time is {datetime.now().strftime('%I:%M %p on %A, %B %d, %Y')}."

    # END FAST PATH - Fall through to LLM tool calling for complex queries

    messages = conversation or []
    messages.append({"role": "user", "content": query})

    logger.info(f"Processing with tools: {query[:50]}...")

    # First call - may return tool_use
    response = call_with_tools(messages, AVAILABLE_TOOLS)

    if "error" in response:
        logger.error(f"Tool API error: {response['error']}")
        return f"Error: {response['error']}"

    # Check for tool calls
    content = response.get("content", [])
    stop_reason = response.get("stop_reason", "")
    logger.info(f"First response - stop_reason: {stop_reason}, content blocks: {len(content)}")

    tool_results = []
    final_text = ""

    for block in content:
        block_type = block.get("type")
        if block_type == "text":
            final_text += block.get("text", "")
        elif block_type == "thinking":
            # Skip thinking blocks from qwen3
            logger.debug(f"Thinking: {block.get('thinking', '')[:100]}...")
        elif block_type == "tool_use":
            tool_name = block.get("name")
            tool_input = block.get("input", {})
            tool_id = block.get("id")

            logger.info(f"Tool call: {tool_name}({tool_input})")

            # Execute tool
            result = execute_tool(tool_name, tool_input)
            logger.info(f"Tool result: {result[:100]}...")
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_id,
                "content": result
            })

    # If tools were called, continue conversation
    if tool_results:
        logger.info(f"Sending {len(tool_results)} tool results back to model")

        # Add assistant message with tool calls
        messages.append({"role": "assistant", "content": content})

        # Add tool results
        messages.append({"role": "user", "content": tool_results})

        # Get final response
        final_response = call_with_tools(messages)

        if "error" in final_response:
            logger.error(f"Final response error: {final_response['error']}")
            # Return the tool result directly if second call fails
            return tool_results[0].get("content", "Tool executed but couldn't get response.")

        logger.info(f"Final response received")
        for block in final_response.get("content", []):
            if block.get("type") == "text":
                final_text = block.get("text", "")

    return final_text or "I couldn't process that request."


# =============================================================================
# OLLAMA CHAT (for non-tool queries)
# =============================================================================

def call_ollama_chat(messages: list, model: str = None, stream: bool = False,
                     temperature: float = 0.7, max_tokens: int = 2048):
    """Call Ollama chat API."""
    model = model or OLLAMA_CHAT_MODEL

    data = json.dumps({
        'model': model,
        'messages': messages,
        'stream': stream,
        'options': {'temperature': temperature, 'num_predict': max_tokens}
    }).encode('utf-8')

    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat", data=data,
        headers={'Content-Type': 'application/json'}
    )

    try:
        with urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT) as response:
            if stream:
                for line in response:
                    if line:
                        yield json.loads(line.decode('utf-8'))
            else:
                yield json.loads(response.read().decode('utf-8'))
    except Exception as e:
        raise Exception(f"Ollama request failed: {e}")


def get_ollama_models() -> list:
    """Get list of models from Ollama."""
    try:
        req = urllib.request.Request(f"{OLLAMA_URL}/api/tags")
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
            return data.get('models', [])
    except Exception:
        return []


# =============================================================================
# HTTP HANDLER
# =============================================================================

class APIHandler(BaseHTTPRequestHandler):
    """Handle API requests with smart routing."""

    def log_message(self, format, *args):
        logger.info(f"{self.address_string()} - {format % args}")

    def get_client_ip(self) -> str:
        """Get client IP address."""
        return self.client_address[0]

    def get_cors_header(self) -> str:
        """Get appropriate CORS origin for this request."""
        origin = self.headers.get('Origin', '')
        return get_cors_origin(origin)

    def check_rate_limit(self) -> bool:
        """Check if request is within rate limits. Returns False if limited."""
        client_ip = self.get_client_ip()
        if not rate_limiter.is_allowed(client_ip):
            self.send_response(429)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Retry-After', '60')
            self.end_headers()
            self.wfile.write(json.dumps({
                'error': {'message': 'Rate limit exceeded. Try again later.', 'type': 'rate_limit_error'}
            }).encode('utf-8'))
            return False
        return True

    def send_json(self, data: dict, status: int = 200):
        body = json.dumps(data).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', len(body))
        cors_origin = self.get_cors_header()
        if cors_origin:
            self.send_header('Access-Control-Allow-Origin', cors_origin)
        self.end_headers()
        self.wfile.write(body)

    def send_error_json(self, message: str, status: int = 500):
        self.send_json({'error': {'message': message, 'type': 'api_error', 'code': status}}, status)

    def do_OPTIONS(self):
        self.send_response(200)
        cors_origin = self.get_cors_header()
        if cors_origin:
            self.send_header('Access-Control-Allow-Origin', cors_origin)
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, HEAD, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.end_headers()

    def do_HEAD(self):
        """Handle HEAD requests - return 200 for all valid API endpoints."""
        parsed = urlparse(self.path)
        valid_paths = [
            '/', '/v1', '/v1/', '/health',
            '/api/tags', '/v1/api/tags', '/api/version',
            '/api/ps', '/api/show',
            '/v1/models', '/models', '/projects',
            '/v1/chat/completions', '/chat/completions',
            '/api/chat', '/v1/api/chat'
        ]
        if parsed.path in valid_paths:
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            cors_origin = self.get_cors_header()
            if cors_origin:
                self.send_header('Access-Control-Allow-Origin', cors_origin)
            self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def send_text(self, text: str, status: int = 200):
        body = text.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'text/plain')
        self.send_header('Content-Length', len(body))
        cors_origin = self.get_cors_header()
        if cors_origin:
            self.send_header('Access-Control-Allow-Origin', cors_origin)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        # SECURITY: Rate limiting
        if not self.check_rate_limit():
            return

        parsed = urlparse(self.path)
        path = parsed.path

        if path == '/' or path == '':
            # Must return plain text for Ollama compatibility
            self.send_text('Ollama is running')
        elif path == '/api/version':
            self.send_json({'version': '0.14.2'})
        elif path == '/health':
            self.handle_health()
        elif path in ['/v1/models', '/models']:
            self.handle_models()
        elif path in ['/api/tags', '/v1/api/tags']:
            self.handle_ollama_tags()
        elif path == '/api/ps':
            self.handle_ollama_ps()
        elif path == '/projects':
            self.handle_projects()
        else:
            self.send_error_json('Not found', 404)

    def do_POST(self):
        # SECURITY: Rate limiting
        if not self.check_rate_limit():
            return

        parsed = urlparse(self.path)
        path = parsed.path

        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length) if content_length > 0 else b'{}'

        try:
            data = json.loads(body.decode('utf-8'))
        except json.JSONDecodeError:
            self.send_error_json('Invalid JSON', 400)
            return

        if path in ['/v1/chat/completions', '/chat/completions']:
            self.handle_chat_completions(data)
        elif path in ['/api/chat', '/v1/api/chat']:
            self.handle_ollama_chat(data)
        elif path == '/api/show':
            self.handle_ollama_show(data)
        else:
            self.send_error_json('Not found', 404)

    def handle_health(self):
        ollama_ok = False
        try:
            req = urllib.request.Request(f"{OLLAMA_URL}/api/tags")
            with urllib.request.urlopen(req, timeout=5) as response:
                ollama_ok = response.status == 200
        except Exception:
            pass

        self.send_json({
            'status': 'healthy' if ollama_ok else 'degraded',
            'ollama': 'connected' if ollama_ok else 'disconnected',
            'features': {
                'rag': HAS_HYBRID,
                'tools': True,
                'model_routing': True,
                'macos_integration': True
            },
            'tools': {
                'utility': ['time', 'weather', 'calculate'],
                'macos': ['calendar', 'reminders', 'email', 'notes', 'contacts']
            },
            'models': {
                'default': OLLAMA_CHAT_MODEL,
                'tools': OLLAMA_TOOL_MODEL,
                'code': get_model_for_task('code_review')
            },
            'projects': len(get_projects())
        })

    def handle_models(self):
        ollama_models = get_ollama_models()

        models = []
        for m in ollama_models:
            name = m.get('name', '')
            models.append({
                'id': name,
                'object': 'model',
                'created': int(time.time()),
                'owned_by': 'ollama'
            })

        # Add Terra (smart assistant)
        models.append({
            'id': 'Terra',
            'object': 'model',
            'created': int(time.time()),
            'owned_by': 'claude-dash',
            'description': 'Smart assistant with RAG + tools (auto-routes queries)'
        })

        self.send_json({'object': 'list', 'data': models})

    def handle_ollama_tags(self):
        ollama_models = get_ollama_models()

        # Terra model with full Ollama-compatible format
        terra_model = [{
            'name': 'Terra',
            'model': 'Terra',
            'modified_at': time.strftime('%Y-%m-%dT%H:%M:%S.000000000-05:00'),
            'size': 4000000000,  # Approximate size
            'digest': 'claudedashterrasmartassistant00000000000000000000000000000000',
            'details': {
                'parent_model': '',
                'format': 'gguf',
                'family': 'gemma3',
                'families': ['gemma3'],
                'parameter_size': '4.0B',
                'quantization_level': 'Q4_K_M'
            }
        }]

        self.send_json({'models': terra_model + ollama_models})

    def handle_ollama_ps(self):
        """Proxy /api/ps to real Ollama (shows running models)."""
        try:
            req = urllib.request.Request(f"{OLLAMA_URL}/api/ps")
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode('utf-8'))
                self.send_json(data)
        except Exception as e:
            # Return empty list if Ollama not available
            self.send_json({'models': []})

    def handle_ollama_show(self, data: dict):
        """Proxy /api/show to real Ollama (shows model details)."""
        model_name = data.get('name', '')

        # Handle Terra specially
        if model_name == 'Terra':
            self.send_json({
                'modelfile': '# Terra - Claude-Dash Smart Assistant\n# Routes queries to appropriate backends with RAG support',
                'parameters': 'temperature 0.7\ntop_k 64\ntop_p 0.95',
                'template': '{{.Prompt}}',
                'details': {
                    'parent_model': '',
                    'format': 'gguf',
                    'family': 'gemma3',
                    'families': ['gemma3'],
                    'parameter_size': '4.0B',
                    'quantization_level': 'Q4_K_M'
                },
                'model_info': {
                    'general.architecture': 'gemma3',
                    'general.parameter_count': 4000000000
                }
            })
            return

        try:
            req = urllib.request.Request(
                f"{OLLAMA_URL}/api/show",
                data=json.dumps({'name': model_name}).encode('utf-8'),
                headers={'Content-Type': 'application/json'},
                method='POST'
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode('utf-8'))
                self.send_json(data)
        except Exception as e:
            self.send_error_json(f'Model not found: {model_name}', 404)

    def handle_projects(self):
        projects = get_projects()
        self.send_json({'projects': projects, 'count': len(projects)})

    def handle_chat_completions(self, data: dict):
        """Handle chat with smart routing."""
        messages = data.get('messages', [])
        model = data.get('model', 'Terra')
        stream = data.get('stream', False)
        temperature = data.get('temperature', 0.7)
        max_tokens = data.get('max_tokens', 2048)

        if not messages:
            self.send_error_json('messages is required', 400)
            return

        # Get last user message for classification
        last_user = next((m.get('content', '') for m in reversed(messages) if m.get('role') == 'user'), '')

        # Use Terra (smart routing) or direct model
        use_terra = model.lower() in ['terra', 'rag'] or model.startswith('rag-')

        response_text = ""

        if use_terra:
            # Classify query
            classification = classify_query(last_user)
            logger.info(f"Query classification: {classification}")

            if classification['needs_tools']:
                # Use tool-calling model
                logger.info(f"Routing to tools ({OLLAMA_TOOL_MODEL})")
                response_text = process_with_tools(last_user)
            elif classification['needs_rag']:
                # Use RAG with default model
                logger.info(f"Routing to RAG ({OLLAMA_CHAT_MODEL})")
                project_id = classification.get('project') or detect_project_from_query(last_user)
                context = retrieve_context(last_user, project_id)

                rag_messages = messages.copy()
                if context:
                    rag_messages.insert(0, {
                        'role': 'system',
                        'content': f"You are a helpful assistant with knowledge of the codebase.\n\n{context}"
                    })

                for chunk in call_ollama_chat(rag_messages, OLLAMA_CHAT_MODEL, stream=False,
                                              temperature=temperature, max_tokens=max_tokens):
                    if 'message' in chunk:
                        response_text = chunk['message'].get('content', '')
            else:
                # General query - use default model
                logger.info(f"Routing to general ({OLLAMA_CHAT_MODEL})")
                for chunk in call_ollama_chat(messages, OLLAMA_CHAT_MODEL, stream=False,
                                              temperature=temperature, max_tokens=max_tokens):
                    if 'message' in chunk:
                        response_text = chunk['message'].get('content', '')
        else:
            # Direct model call
            ollama_model = model
            for chunk in call_ollama_chat(messages, ollama_model, stream=False,
                                          temperature=temperature, max_tokens=max_tokens):
                if 'message' in chunk:
                    response_text = chunk['message'].get('content', '')

        # Return OpenAI-compatible response
        self.send_json({
            'id': f'chatcmpl-{uuid.uuid4().hex[:8]}',
            'object': 'chat.completion',
            'created': int(time.time()),
            'model': model,
            'choices': [{
                'index': 0,
                'message': {'role': 'assistant', 'content': response_text},
                'finish_reason': 'stop'
            }],
            'usage': {
                'prompt_tokens': sum(len(m.get('content', '')) // 4 for m in messages),
                'completion_tokens': len(response_text) // 4,
                'total_tokens': sum(len(m.get('content', '')) // 4 for m in messages) + len(response_text) // 4
            }
        })

    def handle_ollama_chat(self, data: dict):
        """Ollama-native /api/chat endpoint with smart routing."""
        model = data.get('model', 'Terra')
        messages = data.get('messages', [])
        stream = data.get('stream', True)

        if not messages:
            self.send_error_json('messages is required', 400)
            return

        last_user = next((m.get('content', '') for m in reversed(messages) if m.get('role') == 'user'), '')
        use_terra = model.lower() in ['terra', 'rag']

        if use_terra:
            classification = classify_query(last_user)

            if classification['needs_tools']:
                # Tool response (non-streaming)
                response_text = process_with_tools(last_user)
                result = {
                    'model': OLLAMA_TOOL_MODEL,
                    'created_at': time.strftime('%Y-%m-%dT%H:%M:%S.000Z'),
                    'message': {'role': 'assistant', 'content': response_text},
                    'done': True
                }
                self.send_json(result)
                return

            # RAG or general
            if classification['needs_rag']:
                project_id = classification.get('project') or detect_project_from_query(last_user)
                context = retrieve_context(last_user, project_id)
                if context:
                    messages = [{'role': 'system', 'content': f"You are a helpful assistant.\n\n{context}"}] + messages

            ollama_model = OLLAMA_CHAT_MODEL
        else:
            ollama_model = model

        # Forward to Ollama
        ollama_data = json.dumps({
            'model': ollama_model,
            'messages': messages,
            'stream': stream,
            'options': data.get('options', {})
        }).encode('utf-8')

        req = urllib.request.Request(
            f"{OLLAMA_URL}/api/chat", data=ollama_data,
            headers={'Content-Type': 'application/json'}
        )

        try:
            with urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT) as response:
                if stream:
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/x-ndjson')
                    cors_origin = self.get_cors_header()
                    if cors_origin:
                        self.send_header('Access-Control-Allow-Origin', cors_origin)
                    self.end_headers()

                    for line in response:
                        if line:
                            self.wfile.write(line)
                            self.wfile.flush()
                else:
                    result = response.read()
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Content-Length', len(result))
                    cors_origin = self.get_cors_header()
                    if cors_origin:
                        self.send_header('Access-Control-Allow-Origin', cors_origin)
                    self.end_headers()
                    self.wfile.write(result)
        except Exception as e:
            logger.error(f"Ollama chat error: {e}")
            self.send_error_json(str(e), 500)


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description='Claude-Dash API Server with Tools')
    parser.add_argument('--port', type=int, default=5100, help='Port to listen on')
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind to')
    args = parser.parse_args()

    server_address = (args.host, args.port)
    httpd = HTTPServer(server_address, APIHandler)

    logger.info(f"Claude-Dash API Server starting on http://{args.host}:{args.port}")
    logger.info(f"  Ollama URL: {OLLAMA_URL}")
    logger.info(f"  Default Model: {OLLAMA_CHAT_MODEL}")
    logger.info(f"  Tool Model: {OLLAMA_TOOL_MODEL}")
    logger.info(f"  Code Model: {get_model_for_task('code_review')}")
    logger.info(f"  Hybrid Search: {'enabled' if HAS_HYBRID else 'disabled'}")
    logger.info(f"  Projects: {len(get_projects())}")
    logger.info("")
    logger.info("Features:")
    logger.info("  ✓ RAG (codebase context)")
    logger.info("  ✓ Tool calling (time, weather, calculate)")
    logger.info("  ✓ Smart model routing")
    logger.info("")
    logger.info("Select 'Terra' model in Enchanted for smart routing")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("\nShutting down...")
        httpd.shutdown()


if __name__ == '__main__':
    main()
