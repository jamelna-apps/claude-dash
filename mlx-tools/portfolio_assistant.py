#!/usr/bin/env python3
"""
Portfolio Assistant - Cross-project intelligence for Ollama

Gives Ollama comprehensive understanding of ALL projects including:
- Project overview and tech stacks
- Health comparison across projects
- Feature catalog and overlap
- Session history and patterns learned
- Cross-project semantic search
- Architecture and code patterns

Usage:
    mlx portfolio overview              # Overview of all projects
    mlx portfolio health                # Health comparison
    mlx portfolio tech                  # Technology stacks
    mlx portfolio features              # Feature catalog
    mlx portfolio sessions              # Recent session activity
    mlx portfolio patterns              # Common patterns learned
    mlx portfolio search <query>        # Search across all projects
    mlx portfolio similar <file>        # Find similar code across projects
    mlx portfolio ask <question>        # Ask Ollama about your portfolio
"""

import json
import sys
import os
import urllib.request
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from collections import defaultdict

try:
    from config import OLLAMA_URL, OLLAMA_CHAT_MODEL as CHAT_MODEL, OLLAMA_EMBED_MODEL as EMBEDDING_MODEL, MEMORY_ROOT, cosine_similarity
except ImportError:
    import math
    MEMORY_ROOT = Path.home() / '.claude-dash'
    OLLAMA_URL = 'http://localhost:11434'
    CHAT_MODEL = 'gemma3:4b-it-qat'
    EMBEDDING_MODEL = 'nomic-embed-text'

    def cosine_similarity(vec1: list, vec2: list) -> float:
        """Fallback cosine similarity."""
        if not vec1 or not vec2 or len(vec1) != len(vec2):
            return 0.0
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = math.sqrt(sum(a * a for a in vec1))
        norm2 = math.sqrt(sum(b * b for b in vec2))
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return dot_product / (norm1 * norm2)

PORTFOLIO_SYSTEM_CONTEXT = """You are an AI assistant with complete knowledge of a developer's project portfolio.

You have access to:
- 8 tracked projects with code intelligence
- Health scores (0-100) measuring code quality
- Feature catalogs with dependencies
- Session history with patterns learned
- Cross-project semantic search
- Database schemas and function indexes

Health Score Guide:
- 90-100: Excellent (clean, well-maintained)
- 75-89: Good (minor issues)
- 60-74: Fair (needs attention)
- 40-59: Poor (significant tech debt)
- 0-39: Critical (major refactoring needed)

When answering questions:
1. Reference specific projects and files
2. Compare approaches across projects
3. Highlight patterns and best practices
4. Suggest improvements based on healthier projects
5. Reference past decisions and learnings
"""


class PortfolioAssistant:
    """Cross-project intelligence assistant."""

    def __init__(self):
        self.config = self._load_config()
        self.projects = {}
        self._load_all_projects()

    def _load_config(self) -> Dict:
        """Load main configuration."""
        config_path = MEMORY_ROOT / 'config.json'
        if config_path.exists():
            return json.loads(config_path.read_text())
        return {'projects': []}

    def _load_json(self, path: Path) -> Dict:
        """Safely load a JSON file."""
        if path.exists():
            try:
                return json.loads(path.read_text())
            except json.JSONDecodeError:
                return {}
        return {}

    def _load_all_projects(self):
        """Load data for all projects."""
        for proj in self.config.get('projects', []):
            project_id = proj['id']
            project_dir = MEMORY_ROOT / 'projects' / project_id

            self.projects[project_id] = {
                'config': proj,
                'health': self._load_json(project_dir / 'health.json'),
                'health_history': self._load_json(project_dir / 'health_history.json'),
                'features': self._load_json(project_dir / 'features.json'),
                'schema': self._load_json(project_dir / 'schema.json'),
                'functions': self._load_json(project_dir / 'functions.json'),
                'index': self._load_json(project_dir / 'index.json'),
                'preferences': self._load_json(project_dir / 'preferences.json'),
                'summaries': self._load_json(project_dir / 'summaries.json'),
                'observations': self._load_json(project_dir / 'observations.json'),
                'graph': self._load_json(project_dir / 'graph.json'),
            }

    def _load_sessions(self) -> Dict:
        """Load session data."""
        sessions_dir = MEMORY_ROOT / 'sessions'
        index = self._load_json(sessions_dir / 'index.json')
        observations = self._load_json(sessions_dir / 'observations.json')
        return {'index': index, 'observations': observations}

    def _load_global_preferences(self) -> Dict:
        """Load global preferences."""
        return self._load_json(MEMORY_ROOT / 'global' / 'preferences.json')

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
            'system': system or PORTFOLIO_SYSTEM_CONTEXT,
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

    def _get_embedding(self, text: str) -> List[float]:
        """Get embedding for text."""
        data = json.dumps({
            'model': EMBEDDING_MODEL,
            'prompt': text[:8000]
        }).encode()

        req = urllib.request.Request(
            f'{OLLAMA_URL}/api/embeddings',
            data=data,
            headers={'Content-Type': 'application/json'}
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode())
                return result.get('embedding', [])
        except:
            return []

    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        """Calculate cosine similarity using centralized implementation."""
        return cosine_similarity(a, b)

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

    # ==================== OVERVIEW COMMANDS ====================

    def get_overview(self) -> Dict[str, Any]:
        """Get comprehensive portfolio overview."""
        overview = {
            'total_projects': len(self.projects),
            'projects': [],
            'health_summary': {
                'average': 0,
                'best': None,
                'worst': None,
                'needs_attention': []
            },
            'total_functions': 0,
            'total_collections': 0,
            'total_features': 0
        }

        scores = []
        for project_id, data in self.projects.items():
            health = data['health']
            score = health.get('score', 0) if health else 0
            scores.append((project_id, score))

            # Count functions
            functions = data['functions'].get('functions', {})
            func_count = len(functions) if isinstance(functions, dict) else 0
            overview['total_functions'] += func_count

            # Count collections
            collections = data['schema'].get('collections', {})
            coll_count = len(collections)
            overview['total_collections'] += coll_count

            # Count features
            features = data['features'].get('features', [])
            feat_count = len(features) if isinstance(features, list) else 0
            overview['total_features'] += feat_count

            # Project summary
            proj_summary = {
                'id': project_id,
                'name': data['config'].get('displayName', project_id),
                'path': data['config'].get('path', ''),
                'health_score': score,
                'health_rating': self._get_rating(score) if score else 'Unknown',
                'functions': func_count,
                'collections': coll_count,
                'features': feat_count,
                'last_scan': health.get('timestamp', 'Never') if health else 'Never'
            }
            overview['projects'].append(proj_summary)

        # Calculate health stats
        valid_scores = [(p, s) for p, s in scores if s > 0]
        if valid_scores:
            overview['health_summary']['average'] = round(sum(s for _, s in valid_scores) / len(valid_scores))
            overview['health_summary']['best'] = max(valid_scores, key=lambda x: x[1])
            overview['health_summary']['worst'] = min(valid_scores, key=lambda x: x[1])
            overview['health_summary']['needs_attention'] = [p for p, s in valid_scores if s < 60]

        # Sort projects by health score
        overview['projects'].sort(key=lambda x: x['health_score'], reverse=True)

        return overview

    def get_health_comparison(self) -> Dict[str, Any]:
        """Compare health across all projects."""
        comparison = {
            'projects': [],
            'common_issues': defaultdict(int),
            'recommendations': []
        }

        for project_id, data in self.projects.items():
            health = data['health']
            if not health:
                continue

            proj_health = {
                'id': project_id,
                'name': data['config'].get('displayName', project_id),
                'score': health.get('score', 0),
                'rating': self._get_rating(health.get('score', 0)),
                'issues': health.get('summary', {}),
                'trend': self._calculate_trend(data['health_history'])
            }
            comparison['projects'].append(proj_health)

            # Aggregate common issues
            summary = health.get('summary', {})
            if summary.get('security', 0) > 0:
                comparison['common_issues']['security'] += summary['security']
            if summary.get('performance', 0) > 0:
                comparison['common_issues']['performance'] += summary['performance']
            if summary.get('duplicates', 0) > 0:
                comparison['common_issues']['duplicates'] += summary['duplicates']
            if summary.get('dead_code', 0) > 0:
                comparison['common_issues']['dead_code'] += summary['dead_code']

        # Sort by score
        comparison['projects'].sort(key=lambda x: x['score'], reverse=True)

        # Generate recommendations
        if comparison['common_issues'].get('security', 0) > 0:
            comparison['recommendations'].append(
                f"Security: {comparison['common_issues']['security']} issues across projects - prioritize fixing"
            )
        if comparison['common_issues'].get('dead_code', 0) > 100:
            comparison['recommendations'].append(
                f"Dead code: {comparison['common_issues']['dead_code']} items - consider cleanup sprint"
            )

        comparison['common_issues'] = dict(comparison['common_issues'])
        return comparison

    def _calculate_trend(self, history) -> str:
        """Calculate health trend from history."""
        if not history or not isinstance(history, list) or len(history) < 2:
            return 'stable'
        recent = history[-1].get('score', 0) if isinstance(history[-1], dict) else 0
        previous = history[-2].get('score', 0) if isinstance(history[-2], dict) else 0
        if recent > previous + 2:
            return 'improving'
        elif recent < previous - 2:
            return 'declining'
        return 'stable'

    def get_tech_stacks(self) -> Dict[str, Any]:
        """Analyze technology stacks across projects."""
        stacks = {
            'projects': [],
            'technologies': defaultdict(list),
            'frameworks': defaultdict(list),
            'databases': defaultdict(list)
        }

        for project_id, data in self.projects.items():
            index = data['index']
            schema = data['schema']
            summaries = data['summaries']

            # Detect technologies from file structure and imports
            tech_detected = set()
            frameworks_detected = set()

            # Check for common patterns
            files = summaries.get('files', {})
            for filepath, file_data in files.items():
                imports = file_data.get('imports', [])
                if isinstance(imports, list):
                    for imp in imports:
                        imp_lower = imp.lower() if isinstance(imp, str) else ''
                        if 'react' in imp_lower:
                            frameworks_detected.add('React')
                        if 'react-native' in imp_lower or 'expo' in imp_lower:
                            frameworks_detected.add('React Native')
                        if 'firebase' in imp_lower:
                            tech_detected.add('Firebase')
                        if 'express' in imp_lower:
                            frameworks_detected.add('Express.js')
                        if 'next' in imp_lower:
                            frameworks_detected.add('Next.js')

                # Check file extensions
                if filepath.endswith('.ts') or filepath.endswith('.tsx'):
                    tech_detected.add('TypeScript')
                elif filepath.endswith('.js') or filepath.endswith('.jsx'):
                    tech_detected.add('JavaScript')

            # Check schema for database
            if schema.get('collections'):
                tech_detected.add('Firestore')

            proj_stack = {
                'id': project_id,
                'name': data['config'].get('displayName', project_id),
                'technologies': list(tech_detected),
                'frameworks': list(frameworks_detected),
                'database': 'Firestore' if schema.get('collections') else 'Unknown'
            }
            stacks['projects'].append(proj_stack)

            # Aggregate
            for tech in tech_detected:
                stacks['technologies'][tech].append(project_id)
            for fw in frameworks_detected:
                stacks['frameworks'][fw].append(project_id)

        stacks['technologies'] = dict(stacks['technologies'])
        stacks['frameworks'] = dict(stacks['frameworks'])
        return stacks

    def get_features_catalog(self) -> Dict[str, Any]:
        """Get catalog of features across all projects."""
        catalog = {
            'total_features': 0,
            'by_project': {},
            'common_features': defaultdict(list),
            'feature_types': defaultdict(int)
        }

        for project_id, data in self.projects.items():
            features = data['features'].get('features', [])
            if not isinstance(features, list):
                continue

            catalog['by_project'][project_id] = {
                'name': data['config'].get('displayName', project_id),
                'features': []
            }

            for feat in features:
                if isinstance(feat, dict):
                    feat_name = feat.get('name', 'Unknown')
                    feat_type = feat.get('type', 'feature')

                    catalog['by_project'][project_id]['features'].append({
                        'name': feat_name,
                        'description': feat.get('description', ''),
                        'status': feat.get('status', 'unknown')
                    })

                    catalog['total_features'] += 1
                    catalog['feature_types'][feat_type] += 1

                    # Track common features
                    normalized_name = feat_name.lower().replace('-', ' ').replace('_', ' ')
                    catalog['common_features'][normalized_name].append(project_id)

        # Find features that appear in multiple projects
        catalog['shared_features'] = {
            k: v for k, v in catalog['common_features'].items()
            if len(v) > 1
        }

        catalog['common_features'] = dict(catalog['common_features'])
        catalog['feature_types'] = dict(catalog['feature_types'])
        return catalog

    def get_sessions_summary(self, days: int = 7) -> Dict[str, Any]:
        """Get recent session activity."""
        sessions_data = self._load_sessions()
        index = sessions_data.get('index', {})
        observations = sessions_data.get('observations', {})

        summary = {
            'total_sessions': 0,
            'recent_sessions': [],
            'by_project': defaultdict(int),
            'observation_categories': defaultdict(int),
            'recent_observations': []
        }

        # Process session index
        sessions = index.get('sessions', [])
        if isinstance(sessions, list):
            summary['total_sessions'] = len(sessions)

            # Get recent sessions
            cutoff = datetime.now() - timedelta(days=days)
            for session in sessions[-10:]:  # Last 10 sessions
                if isinstance(session, dict):
                    summary['recent_sessions'].append({
                        'id': session.get('sessionId', ''),
                        'project': session.get('projectId', 'unknown'),
                        'timestamp': session.get('timestamp', ''),
                        'observations': session.get('observationCount', 0)
                    })
                    summary['by_project'][session.get('projectId', 'unknown')] += 1

        # Process observations
        obs_list = observations.get('observations', [])
        if isinstance(obs_list, list):
            for obs in obs_list[-50:]:  # Last 50 observations
                if isinstance(obs, dict):
                    category = obs.get('category', 'other')
                    summary['observation_categories'][category] += 1
                    summary['recent_observations'].append({
                        'category': category,
                        'project': obs.get('project', 'unknown'),
                        'description': obs.get('description', '')[:100]
                    })

        summary['by_project'] = dict(summary['by_project'])
        summary['observation_categories'] = dict(summary['observation_categories'])
        return summary

    def get_patterns_learned(self) -> Dict[str, Any]:
        """Extract patterns and learnings from observations."""
        sessions_data = self._load_sessions()
        observations = sessions_data.get('observations', {})

        patterns = {
            'decisions': [],
            'bugfixes': [],
            'gotchas': [],
            'implementations': [],
            'by_project': defaultdict(list)
        }

        obs_list = observations.get('observations', [])
        if isinstance(obs_list, list):
            for obs in obs_list:
                if not isinstance(obs, dict):
                    continue

                category = obs.get('category', '')
                # Handle both 'project' and 'projectId' field names
                project = obs.get('projectId', obs.get('project', 'unknown'))
                # Handle both 'observation' and 'description' field names
                description = obs.get('observation', obs.get('description', ''))

                if not description:
                    continue

                entry = {
                    'project': project,
                    'description': description[:200],
                    'date': obs.get('timestamp', obs.get('date', ''))
                }

                if category == 'decision':
                    patterns['decisions'].append(entry)
                elif category == 'bugfix':
                    patterns['bugfixes'].append(entry)
                elif category == 'gotcha':
                    patterns['gotchas'].append(entry)
                elif category == 'implementation':
                    patterns['implementations'].append(entry)

                patterns['by_project'][project].append({
                    'category': category,
                    'description': description[:100]
                })

        # Limit to recent entries
        patterns['decisions'] = patterns['decisions'][-20:]
        patterns['bugfixes'] = patterns['bugfixes'][-20:]
        patterns['gotchas'] = patterns['gotchas'][-20:]
        patterns['implementations'] = patterns['implementations'][-20:]
        patterns['by_project'] = {k: v[-10:] for k, v in patterns['by_project'].items()}

        return patterns

    def search_all_projects(self, query: str, top_k: int = 10) -> List[Dict]:
        """Semantic search across all projects."""
        results = []

        # Get query embedding
        query_embedding = self._get_embedding(query)
        if not query_embedding:
            # Fall back to keyword search
            return self._keyword_search_all(query, top_k)

        # Search each project's embeddings
        for project_id, data in self.projects.items():
            # Try to load ollama embeddings
            embeddings_path = MEMORY_ROOT / 'projects' / project_id / 'ollama_embeddings.json'
            if not embeddings_path.exists():
                embeddings_path = MEMORY_ROOT / 'projects' / project_id / 'embeddings_v2.json'

            if not embeddings_path.exists():
                continue

            try:
                embeddings = json.loads(embeddings_path.read_text())
            except:
                continue

            for filepath, file_data in embeddings.items():
                if not isinstance(file_data, dict):
                    continue

                file_embedding = file_data.get('embedding', [])
                if not file_embedding:
                    continue

                similarity = self._cosine_similarity(query_embedding, file_embedding)
                results.append({
                    'project': project_id,
                    'project_name': data['config'].get('displayName', project_id),
                    'file': filepath,
                    'score': similarity,
                    'summary': file_data.get('summary', ''),
                    'purpose': file_data.get('purpose', '')
                })

        # Sort by score and return top results
        results.sort(key=lambda x: x['score'], reverse=True)
        return results[:top_k]

    def _keyword_search_all(self, query: str, top_k: int) -> List[Dict]:
        """Fallback keyword search across all projects."""
        results = []
        query_lower = query.lower()
        keywords = query_lower.split()

        for project_id, data in self.projects.items():
            summaries = data['summaries'].get('files', {})

            for filepath, file_data in summaries.items():
                text = f"{filepath} {file_data.get('summary', '')} {file_data.get('purpose', '')}".lower()
                score = sum(1 for kw in keywords if kw in text) / len(keywords)

                if score > 0:
                    results.append({
                        'project': project_id,
                        'project_name': data['config'].get('displayName', project_id),
                        'file': filepath,
                        'score': score,
                        'summary': file_data.get('summary', ''),
                        'purpose': file_data.get('purpose', '')
                    })

        results.sort(key=lambda x: x['score'], reverse=True)
        return results[:top_k]

    def ask_portfolio(self, question: str) -> str:
        """Ask Ollama anything about the portfolio."""
        # Build comprehensive context
        overview = self.get_overview()
        health = self.get_health_comparison()
        patterns = self.get_patterns_learned()

        context_parts = [
            "## Portfolio Overview",
            f"Total projects: {overview['total_projects']}",
            f"Average health: {overview['health_summary']['average']}/100",
            f"Total functions: {overview['total_functions']}",
            f"Total features: {overview['total_features']}",
            "",
            "## Projects"
        ]

        for proj in overview['projects']:
            context_parts.append(
                f"- {proj['name']}: {proj['health_score']}/100 ({proj['health_rating']}) - "
                f"{proj['functions']} functions, {proj['features']} features"
            )

        context_parts.append("")
        context_parts.append("## Health Issues")
        for issue, count in health.get('common_issues', {}).items():
            context_parts.append(f"- {issue}: {count} total across projects")

        context_parts.append("")
        context_parts.append("## Recent Decisions")
        for dec in patterns.get('decisions', [])[:5]:
            context_parts.append(f"- [{dec['project']}] {dec['description']}")

        context_parts.append("")
        context_parts.append("## Recent Bugfixes")
        for bug in patterns.get('bugfixes', [])[:5]:
            context_parts.append(f"- [{bug['project']}] {bug['description']}")

        context = '\n'.join(context_parts)

        prompt = f"""Using the portfolio data below, answer this question:

Question: {question}

---
PORTFOLIO DATA:
{context}
---

Provide specific, actionable insights. Reference project names and compare approaches when relevant."""

        return self._generate(prompt)


def main():
    if len(sys.argv) < 2:
        print("Portfolio Assistant - Cross-project intelligence")
        print("")
        print("Usage:")
        print("  mlx portfolio overview              # Overview of all projects")
        print("  mlx portfolio health                # Health comparison")
        print("  mlx portfolio tech                  # Technology stacks")
        print("  mlx portfolio features              # Feature catalog")
        print("  mlx portfolio sessions              # Recent session activity")
        print("  mlx portfolio patterns              # Patterns learned")
        print("  mlx portfolio search <query>        # Search across all projects")
        print("  mlx portfolio ask <question>        # Ask about your portfolio")
        print("")
        print("Examples:")
        print("  mlx portfolio overview")
        print("  mlx portfolio health")
        print("  mlx portfolio search 'authentication'")
        print("  mlx portfolio ask 'which project has the best code quality?'")
        sys.exit(1)

    assistant = PortfolioAssistant()
    command = sys.argv[1]

    if command == 'overview':
        print(json.dumps(assistant.get_overview(), indent=2))

    elif command == 'health':
        print(json.dumps(assistant.get_health_comparison(), indent=2))

    elif command == 'tech':
        print(json.dumps(assistant.get_tech_stacks(), indent=2))

    elif command == 'features':
        print(json.dumps(assistant.get_features_catalog(), indent=2))

    elif command == 'sessions':
        days = int(sys.argv[2]) if len(sys.argv) > 2 else 7
        print(json.dumps(assistant.get_sessions_summary(days), indent=2))

    elif command == 'patterns':
        print(json.dumps(assistant.get_patterns_learned(), indent=2))

    elif command == 'search':
        if len(sys.argv) < 3:
            print("Usage: mlx portfolio search <query>")
            sys.exit(1)
        query = ' '.join(sys.argv[2:])
        results = assistant.search_all_projects(query)
        print(f"Search results for: {query}")
        print("---")
        for r in results:
            print(f"[{r['project_name']}] {r['file']} (score: {r['score']:.2f})")
            if r['purpose']:
                print(f"  Purpose: {r['purpose']}")
            print()

    elif command == 'ask':
        if len(sys.argv) < 3:
            print("Usage: mlx portfolio ask <question>")
            sys.exit(1)
        question = ' '.join(sys.argv[2:])
        print(f"Question: {question}")
        print("---")
        print(assistant.ask_portfolio(question))

    else:
        print(f"Unknown command: {command}")
        print("Run 'mlx portfolio' for usage")
        sys.exit(1)


if __name__ == '__main__':
    main()
