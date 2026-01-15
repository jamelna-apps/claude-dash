#!/usr/bin/env python3
"""
Memory Assistant - Ollama-powered assistant for Claude Memory system.

This tool gives Ollama complete visibility into the Claude Memory system,
including health scores, project data, and all stored metadata.

Usage:
    mlx memory-assist <project> <question>
    mlx memory-assist <project> --health
    mlx memory-assist <project> --explain-health
    mlx memory-assist <project> --summary
"""

import json
import sys
import urllib.request
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime

try:
    from config import OLLAMA_URL, OLLAMA_CHAT_MODEL as CHAT_MODEL, MEMORY_ROOT
except ImportError:
    MEMORY_ROOT = Path.home() / '.claude-dash'
    OLLAMA_URL = 'http://localhost:11434'
    CHAT_MODEL = 'llama3.2:3b'

# System context explaining the memory system to Ollama
SYSTEM_CONTEXT = """You are an AI assistant with complete access to the Claude Memory system.

## Health Score System (0-100)
The health score measures code quality. Higher is better.

Score Calculation:
- Base score: 100 (from static analysis)
- Deductions for:
  * Security issues (hardcoded secrets, injection risks, XSS)
  * Performance issues (slow queries, memory leaks, missing async)
  * Maintenance issues (complex functions, large files, deep nesting)
  * Duplicate code (logarithmic penalty, max -10 pts)
  * Dead code (unused exports, orphan files, max -10 pts)

Score Interpretation:
- 90-100: Excellent - clean, well-maintained
- 75-89: Good - minor issues
- 60-74: Fair - needs attention
- 40-59: Poor - significant tech debt
- 0-39: Critical - major refactoring needed

## Data Files in Each Project
- health.json: Current health metrics and issues
- health_history.json: Score history (last 100 entries)
- summaries.json: File summaries with purpose, exports, imports
- schema.json: Database collections and relationships
- functions.json: Function index with file paths and lines
- decisions.json: Architectural decisions
- observations.json: Session patterns and bugfixes
- preferences.json: Project-specific rules

When answering questions:
1. Reference specific files and line numbers when available
2. Explain health score components clearly
3. Provide actionable recommendations
4. Use data from the context provided
"""


class MemoryAssistant:
    """Ollama-powered assistant for Claude Memory system."""

    def __init__(self, project_id: str):
        self.project_id = project_id
        self.project_dir = MEMORY_ROOT / 'projects' / project_id
        self.data = self._load_all_data()

    def _load_json(self, filename: str) -> Dict:
        """Load a JSON file from the project directory."""
        path = self.project_dir / filename
        if path.exists():
            try:
                return json.loads(path.read_text())
            except json.JSONDecodeError:
                return {}
        return {}

    def _load_all_data(self) -> Dict[str, Any]:
        """Load all project data."""
        return {
            'health': self._load_json('health.json'),
            'health_history': self._load_json('health_history.json'),
            'summaries': self._load_json('summaries.json'),
            'schema': self._load_json('schema.json'),
            'functions': self._load_json('functions.json'),
            'decisions': self._load_json('decisions.json'),
            'observations': self._load_json('observations.json'),
            'preferences': self._load_json('preferences.json'),
            'features': self._load_json('features.json'),
            'graph': self._load_json('graph.json')
        }

    def _ollama_available(self) -> bool:
        """Check if Ollama is available."""
        try:
            req = urllib.request.Request(f'{OLLAMA_URL}/api/tags')
            with urllib.request.urlopen(req, timeout=2) as resp:
                return resp.status == 200
        except:
            return False

    def _generate(self, prompt: str, system: str = None) -> str:
        """Generate response using Ollama."""
        if not self._ollama_available():
            return "Error: Ollama is not available. Start it with: ollama serve"

        data = json.dumps({
            'model': CHAT_MODEL,
            'prompt': prompt,
            'system': system or SYSTEM_CONTEXT,
            'stream': False
        }).encode()

        req = urllib.request.Request(
            f'{OLLAMA_URL}/api/generate',
            data=data,
            headers={'Content-Type': 'application/json'}
        )

        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read().decode())
                return result.get('response', 'No response generated')
        except Exception as e:
            return f"Error: {e}"

    def get_health_summary(self) -> Dict[str, Any]:
        """Get structured health summary."""
        health = self.data['health']
        history = self.data['health_history']

        if not health:
            return {'error': 'No health data available. Run: mlx health scan'}

        # Calculate trend
        trend = 'stable'
        if len(history) >= 2:
            recent = history[-1]['score']
            previous = history[-2]['score']
            if recent > previous + 2:
                trend = 'improving'
            elif recent < previous - 2:
                trend = 'declining'

        return {
            'project': self.project_id,
            'score': health.get('score', 0),
            'rating': self._get_rating(health.get('score', 0)),
            'trend': trend,
            'last_scan': health.get('timestamp', 'unknown'),
            'scan_type': health.get('scan_type', 'unknown'),
            'issues': health.get('summary', {}),
            'issue_details': {
                'security': health.get('issues', {}).get('security', []),
                'performance': health.get('issues', {}).get('performance', []),
                'maintenance': health.get('issues', {}).get('maintenance', []),
                'duplicates': len(health.get('issues', {}).get('duplicates', [])),
                'dead_code': len(health.get('issues', {}).get('dead_code', []))
            },
            'history_length': len(history)
        }

    def _get_rating(self, score: int) -> str:
        """Convert score to rating."""
        if score >= 90:
            return 'Excellent'
        elif score >= 75:
            return 'Good'
        elif score >= 60:
            return 'Fair'
        elif score >= 40:
            return 'Poor'
        else:
            return 'Critical'

    def explain_health(self) -> str:
        """Get Ollama's explanation of the current health status."""
        summary = self.get_health_summary()

        if 'error' in summary:
            return summary['error']

        prompt = f"""Analyze this project's code health and provide a clear explanation:

Project: {summary['project']}
Current Score: {summary['score']}/100 ({summary['rating']})
Trend: {summary['trend']}
Last Scan: {summary['last_scan']}

Issue Summary:
- Security issues: {summary['issues'].get('security', 0)}
- Performance issues: {summary['issues'].get('performance', 0)}
- Duplicate code pairs: {summary['issues'].get('duplicates', 0)}
- Dead code items: {summary['issues'].get('dead_code', 0)}

Security Issues Found:
{json.dumps(summary['issue_details']['security'][:5], indent=2) if summary['issue_details']['security'] else 'None'}

Performance Issues Found:
{json.dumps(summary['issue_details']['performance'][:5], indent=2) if summary['issue_details']['performance'] else 'None'}

Please provide:
1. A summary of what this health score means
2. The most important issues to address
3. Specific recommendations for improvement
4. Expected score impact if issues are fixed"""

        return self._generate(prompt)

    def get_project_summary(self) -> str:
        """Get a summary of the entire project from memory data."""
        summaries = self.data['summaries']
        schema = self.data['schema']
        functions = self.data['functions']
        decisions = self.data['decisions']
        features = self.data['features']

        file_count = len(summaries.get('files', {}))
        collection_count = len(schema.get('collections', {}))
        function_count = len(functions.get('functions', []))
        decision_count = len(decisions.get('decisions', []))

        # Get key files
        key_files = []
        for filepath, data in list(summaries.get('files', {}).items())[:10]:
            key_files.append(f"- {filepath}: {data.get('purpose', 'No description')}")

        prompt = f"""Based on the Claude Memory data, provide a comprehensive project overview:

Project: {self.project_id}

Stats:
- Files indexed: {file_count}
- Database collections: {collection_count}
- Functions indexed: {function_count}
- Architectural decisions: {decision_count}

Key Files:
{chr(10).join(key_files)}

Database Collections:
{json.dumps(list(schema.get('collections', {}).keys())[:10], indent=2)}

Recent Decisions:
{json.dumps(decisions.get('decisions', [])[:3], indent=2)}

Provide:
1. Project type and purpose (based on file structure)
2. Key technologies used
3. Main features
4. Architecture overview
5. Database structure summary"""

        return self._generate(prompt)

    def query(self, question: str) -> str:
        """Answer any question about the project using memory data."""
        # Build comprehensive context
        context_parts = []

        # Add health context
        health = self.data['health']
        if health:
            context_parts.append(f"## Current Health\nScore: {health.get('score', 'N/A')}/100")
            context_parts.append(f"Issues: {json.dumps(health.get('summary', {}))}")

        # Add relevant file summaries
        summaries = self.data['summaries'].get('files', {})
        if summaries:
            context_parts.append("\n## File Summaries (sample)")
            for filepath, data in list(summaries.items())[:15]:
                context_parts.append(f"- {filepath}: {data.get('purpose', 'No description')}")

        # Add schema
        schema = self.data['schema']
        if schema.get('collections'):
            context_parts.append("\n## Database Schema")
            for name, info in list(schema['collections'].items())[:10]:
                fields = info.get('fields', [])
                # Handle both list and dict formats
                if isinstance(fields, dict):
                    field_names = list(fields.keys())[:8]
                else:
                    field_names = fields[:8] if isinstance(fields, list) else []
                context_parts.append(f"- {name}: {', '.join(field_names)}")

        # Add functions
        functions = self.data['functions'].get('functions', {})
        if functions:
            context_parts.append("\n## Functions Index (sample)")
            # Handle both dict and list formats
            if isinstance(functions, dict):
                for func_name, occurrences in list(functions.items())[:20]:
                    if occurrences and isinstance(occurrences, list):
                        first = occurrences[0]
                        context_parts.append(f"- {func_name} in {first.get('file', 'unknown')}:{first.get('line', '?')}")
                    else:
                        context_parts.append(f"- {func_name}")
            elif isinstance(functions, list):
                for func in functions[:20]:
                    context_parts.append(f"- {func.get('name')} in {func.get('file', 'unknown')}:{func.get('line', '?')}")

        # Add decisions
        decisions = self.data['decisions'].get('decisions', [])
        if decisions:
            context_parts.append("\n## Architectural Decisions")
            for dec in decisions[:5]:
                context_parts.append(f"- {dec.get('title', 'Untitled')}: {dec.get('decision', 'No details')}")

        # Add observations
        observations = self.data['observations'].get('observations', [])
        if observations:
            context_parts.append("\n## Past Observations")
            for obs in observations[:5]:
                context_parts.append(f"- [{obs.get('category', 'note')}] {obs.get('description', 'No description')}")

        context = '\n'.join(context_parts)

        prompt = f"""Using the Claude Memory data below, answer this question:

Question: {question}

---
PROJECT DATA:
{context}
---

Provide a clear, specific answer. Reference file paths and line numbers when available.
If the information isn't in the context, say so and suggest how to find it."""

        return self._generate(prompt)

    def get_all_data(self) -> Dict[str, Any]:
        """Return all project data as structured JSON."""
        return {
            'project_id': self.project_id,
            'project_path': str(self.project_dir),
            'data_available': {
                'health': bool(self.data['health']),
                'summaries': bool(self.data['summaries'].get('files')),
                'schema': bool(self.data['schema'].get('collections')),
                'functions': bool(self.data['functions'].get('functions')),
                'decisions': bool(self.data['decisions'].get('decisions')),
                'observations': bool(self.data['observations'].get('observations'))
            },
            'health': self.data['health'],
            'health_history': self.data['health_history'][-10:] if self.data['health_history'] else [],
            'file_count': len(self.data['summaries'].get('files', {})),
            'function_count': len(self.data['functions'].get('functions', [])),
            'collection_count': len(self.data['schema'].get('collections', {})),
            'decision_count': len(self.data['decisions'].get('decisions', [])),
            'observation_count': len(self.data['observations'].get('observations', []))
        }


def list_projects() -> List[str]:
    """List available projects."""
    projects_dir = MEMORY_ROOT / 'projects'
    if projects_dir.exists():
        return [p.name for p in projects_dir.iterdir() if p.is_dir()]
    return []


def main():
    if len(sys.argv) < 2:
        print("Memory Assistant - Ollama-powered Claude Memory explorer")
        print("")
        print("Usage:")
        print("  mlx memory-assist <project> <question>      # Ask anything about the project")
        print("  mlx memory-assist <project> --health        # Get structured health data")
        print("  mlx memory-assist <project> --explain-health # Get AI explanation of health")
        print("  mlx memory-assist <project> --summary       # Get project overview")
        print("  mlx memory-assist <project> --all           # Get all data as JSON")
        print("  mlx memory-assist --list                    # List available projects")
        print("")
        print("Examples:")
        print("  mlx memory-assist gyst 'what is the health score and what does it mean?'")
        print("  mlx memory-assist gyst --explain-health")
        print("  mlx memory-assist gyst 'where is authentication handled?'")
        sys.exit(1)

    # Handle --list
    if sys.argv[1] == '--list':
        projects = list_projects()
        print("Available projects:")
        for p in projects:
            print(f"  - {p}")
        sys.exit(0)

    project = sys.argv[1]
    assistant = MemoryAssistant(project)

    # Handle flags
    if len(sys.argv) == 3:
        flag = sys.argv[2]

        if flag == '--health':
            print(json.dumps(assistant.get_health_summary(), indent=2))
            sys.exit(0)

        if flag == '--explain-health':
            print(assistant.explain_health())
            sys.exit(0)

        if flag == '--summary':
            print(assistant.get_project_summary())
            sys.exit(0)

        if flag == '--all':
            print(json.dumps(assistant.get_all_data(), indent=2))
            sys.exit(0)

    # Handle question
    question = ' '.join(sys.argv[2:])
    if not question:
        print("Error: Please provide a question or use a flag (--health, --explain-health, --summary, --all)")
        sys.exit(1)

    print(f"Project: {project}")
    print(f"Question: {question}")
    print("---")
    print(assistant.query(question))


if __name__ == '__main__':
    main()
