#!/usr/bin/env python3
"""
Consolidated Context Injector for Claude-Dash

Combines all context injection into a single Python process to reduce
hook latency from ~2-5s (7+ subprocess calls) to ~500ms (1 process).

Called by inject-context.sh as a single subprocess.
"""

import json
import os
import sys
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, List, Any

MEMORY_ROOT = Path.home() / ".claude-dash"

# Add paths for imports
sys.path.insert(0, str(MEMORY_ROOT / "hooks"))  # For injection_adapters
sys.path.insert(0, str(MEMORY_ROOT / "learning"))
sys.path.insert(0, str(MEMORY_ROOT / "memory"))
sys.path.insert(0, str(MEMORY_ROOT / "patterns"))
sys.path.insert(0, str(MEMORY_ROOT / "skills"))


class ContextInjector:
    """Orchestrates all context injection in a single process."""

    def __init__(self, prompt: str, project_id: str, is_first_message: bool = False):
        self.prompt = prompt
        self.prompt_lower = prompt.lower()
        self.project_id = project_id
        self.project_memory = MEMORY_ROOT / "projects" / project_id
        self.is_first_message = is_first_message
        self.output_parts: List[str] = []

    def inject_all(self) -> str:
        """Run all injections and return combined output."""
        # First message only injections
        if self.is_first_message:
            self._inject_session_health()
            self._inject_session_continuity()
            self._inject_git_awareness()
            self._inject_learned_preferences()
            self._inject_confidence_calibration()

        # Every message injections
        self._inject_memory_context()
        self._inject_corrections()
        self._inject_reasoning_bank()
        self._inject_reasoning_chains()
        self._inject_semantic_memory()
        self._inject_pattern_detection()
        self._inject_skills()

        return '\n'.join(self.output_parts)

    def _inject_session_health(self):
        """Check system health on first message."""
        try:
            from injection_adapters import check_health
            health = check_health()
            if health:
                self.output_parts.append("<system-health>")
                self.output_parts.append(health)
                self.output_parts.append("</system-health>")
        except Exception:
            pass  # Adapters handle errors internally

    def _inject_session_continuity(self):
        """Inject last session context."""
        try:
            from injection_adapters import get_session_context
            ctx = get_session_context(self.project_id)
            if ctx:
                self.output_parts.append("<session-continuity>")
                self.output_parts.append(ctx)
                self.output_parts.append("</session-continuity>")
        except Exception:
            pass

    def _inject_git_awareness(self):
        """Show what changed since last session."""
        try:
            # Only if project has git
            config = self._load_config()
            project_info = next((p for p in config.get('projects', [])
                               if p['id'] == self.project_id), None)
            if not project_info:
                return

            project_path = Path(project_info.get('path', ''))
            if not (project_path / '.git').exists():
                return

            from injection_adapters import get_changes_summary
            changes = get_changes_summary(str(project_path), self.project_id)
            if changes:
                self.output_parts.append("<git-changes>")
                self.output_parts.append(changes)
                self.output_parts.append("</git-changes>")
        except Exception:
            pass

    def _inject_learned_preferences(self):
        """Inject high-confidence learned preferences."""
        try:
            from injection_adapters import get_high_confidence_preferences
            prefs = get_high_confidence_preferences()
            if prefs:
                self.output_parts.append("<learned-preferences>")
                self.output_parts.append(prefs)
                self.output_parts.append("</learned-preferences>")
        except Exception:
            pass

    def _inject_confidence_calibration(self):
        """Inject weak areas for calibrated confidence."""
        try:
            from injection_adapters import get_weak_areas
            weak = get_weak_areas()
            if weak:
                self.output_parts.append("<confidence-calibration>")
                self.output_parts.append(weak)
                self.output_parts.append("</confidence-calibration>")
        except Exception:
            pass

    def _inject_memory_context(self):
        """Inject relevant memory based on prompt keywords."""
        # Schema context
        if self._has_keywords(['database', 'firestore', 'collection', 'schema', 'field', 'document']):
            schema_path = self.project_memory / "schema.json"
            if schema_path.exists():
                self.output_parts.append('<memory-context type="schema">')
                self.output_parts.append(self._read_truncated(schema_path, 5000))
                self.output_parts.append('</memory-context>')

        # Navigation context
        if self._has_keywords(['screen', 'navigate', 'tab', 'stack', 'route', 'page']):
            graph_path = self.project_memory / "graph.json"
            if graph_path.exists():
                self.output_parts.append('<memory-context type="navigation">')
                self.output_parts.append(self._read_truncated(graph_path, 3000))
                self.output_parts.append('</memory-context>')

        # Functions context
        if self._has_keywords(['function', 'method', 'implement', 'create', 'add', 'feature', 'component']):
            funcs_path = self.project_memory / "functions.json"
            if funcs_path.exists():
                self.output_parts.append('<memory-context type="functions">')
                self.output_parts.append(self._read_truncated(funcs_path, 5000))
                self.output_parts.append('</memory-context>')

        # Preferences (always if small)
        prefs_path = self.project_memory / "preferences.json"
        if prefs_path.exists() and prefs_path.stat().st_size < 2000:
            self.output_parts.append('<memory-context type="preferences">')
            self.output_parts.append(prefs_path.read_text())
            self.output_parts.append('</memory-context>')

    def _inject_corrections(self):
        """Detect corrections and inject relevant past corrections."""
        try:
            from correction_tracker import detect_correction, record_correction, find_relevant_corrections, format_corrections_for_injection

            result = detect_correction(self.prompt)
            if result.get('is_correction'):
                record_correction(self.prompt, project_id=self.project_id)
                past = find_relevant_corrections(self.prompt, limit=3)
                if past:
                    formatted = format_corrections_for_injection(past)
                    if formatted:
                        self.output_parts.append("<past-corrections>")
                        self.output_parts.append(formatted)
                        self.output_parts.append("</past-corrections>")
        except ImportError:
            pass
        except Exception:
            pass

        # Dynamic learned patterns from JSON
        self._inject_learned_patterns()

    def _inject_learned_patterns(self):
        """Inject learned patterns from JSON file based on keywords."""
        patterns_file = MEMORY_ROOT / "learning" / "learned_patterns.json"
        if not patterns_file.exists():
            return

        try:
            patterns_data = json.loads(patterns_file.read_text())

            # Check global patterns
            for pattern in patterns_data.get('patterns', []):
                triggers = pattern.get('triggers', [])
                if self._has_keywords(triggers):
                    source = pattern.get('source', 'learned')
                    priority = pattern.get('priority', 'medium')
                    tag = 'learned-warning' if priority == 'high' else 'learned-pattern'
                    self.output_parts.append(f'<{tag} source="{source}">')
                    self.output_parts.append(pattern.get('pattern', ''))
                    self.output_parts.append(f'</{tag}>')

            # Check project-specific patterns
            project_patterns = patterns_data.get('project_patterns', {}).get(self.project_id, [])
            for pattern in project_patterns:
                triggers = pattern.get('triggers', [])
                if self._has_keywords(triggers):
                    source = pattern.get('source', 'learned')
                    priority = pattern.get('priority', 'medium')
                    tag = 'learned-warning' if priority == 'high' else 'learned-pattern'
                    self.output_parts.append(f'<{tag} project="{self.project_id}" source="{source}">')
                    self.output_parts.append(pattern.get('pattern', ''))
                    self.output_parts.append(f'</{tag}>')
        except Exception:
            pass

    def _inject_reasoning_bank(self):
        """Query past learning trajectories."""
        if len(self.prompt) < 20:
            return

        try:
            from reasoning_bank import query_for_context, format_for_injection

            # Detect domain
            domain = self._detect_domain()

            result = query_for_context(self.prompt, domain)
            if result.get('applicable'):
                formatted = format_for_injection(self.prompt, domain)
                if formatted:
                    self.output_parts.append("<reasoning-bank>")
                    self.output_parts.append(formatted)
                    self.output_parts.append("</reasoning-bank>")
        except ImportError:
            pass
        except Exception:
            pass

    def _inject_reasoning_chains(self):
        """Inject relevant past reasoning chains for investigation/debugging prompts."""
        if len(self.prompt) < 20:
            return

        # Only inject for investigation/debugging type prompts
        investigation_keywords = ['why', 'debug', 'investigate', 'decide', 'choose', 'fix',
                                  'error', 'not working', 'broken', 'wrong', 'issue', 'problem']
        if not any(kw in self.prompt_lower for kw in investigation_keywords):
            return

        try:
            from reasoning_chains import recall_chains, format_for_injection
            formatted = format_for_injection(self.prompt, project=self.project_id, limit=3)
            if formatted:
                self.output_parts.append(formatted)
        except ImportError:
            pass
        except Exception:
            pass

    def _inject_semantic_memory(self):
        """Inject topic-relevant memory."""
        try:
            from injection_adapters import get_semantic_context
            ctx = get_semantic_context(self.prompt, self.project_id)
            if ctx:
                self.output_parts.append("<semantic-memory>")
                self.output_parts.append(ctx)
                self.output_parts.append("</semantic-memory>")
        except Exception:
            pass

    def _inject_pattern_detection(self):
        """Detect conversation mode and inject guidance."""
        if len(self.prompt) < 10 or self.prompt.startswith('/'):
            return

        try:
            from detector import detect_mode, get_mode_context, format_context_text, load_patterns

            result = detect_mode(self.prompt, use_ollama=False)
            mode = result.get('primary_mode')
            confidence = result.get('confidence', 0)

            if mode and confidence >= 0.5:
                patterns = load_patterns()
                context = get_mode_context(mode, patterns)
                context_text = format_context_text(context)
                if context_text:
                    self.output_parts.append(f'<pattern-context mode="{mode}" confidence="{confidence}">')
                    self.output_parts.append(context_text)
                    self.output_parts.append('</pattern-context>')
        except ImportError:
            pass
        except Exception:
            pass

    def _inject_skills(self):
        """Match prompt against skill triggers and inject relevant skills."""
        if len(self.prompt) < 10:
            return

        try:
            registry_path = MEMORY_ROOT / "skills" / "registry.json"
            if not registry_path.exists():
                return

            registry = json.loads(registry_path.read_text())

            matched_skills = []

            # Check global skills (core, marketing)
            for category, skills in registry.get("skills", {}).items():
                for skill in skills:
                    triggers = skill.get("triggers", [])
                    # Count how many triggers match
                    matches = sum(1 for t in triggers if t.lower() in self.prompt_lower)
                    if matches > 0:
                        matched_skills.append({
                            "skill": skill,
                            "matches": matches,
                            "category": category,
                            "type": "global"
                        })

            # Check project-specific skills
            project_skills = registry.get("project_skills", {}).get(self.project_id, [])
            for skill in project_skills:
                triggers = skill.get("triggers", [])
                matches = sum(1 for t in triggers if t.lower() in self.prompt_lower)
                if matches > 0:
                    matched_skills.append({
                        "skill": skill,
                        "matches": matches,
                        "category": "project",
                        "type": "project"
                    })

            if not matched_skills:
                return

            # Sort by match count (more matches = more relevant)
            matched_skills.sort(key=lambda x: x["matches"], reverse=True)

            # Limit to top 2 skills to avoid context bloat
            for match in matched_skills[:2]:
                skill = match["skill"]
                skill_name = skill.get("name", "unknown")
                skill_path = skill.get("path", "")

                if not skill_path:
                    continue

                # Resolve skill file path
                if match["type"] == "project":
                    full_path = MEMORY_ROOT / skill_path
                else:
                    full_path = MEMORY_ROOT / "skills" / skill_path

                if not full_path.exists():
                    continue

                content = self._read_truncated(full_path, 3000)
                if content:
                    triggers_matched = [t for t in skill.get("triggers", [])
                                       if t.lower() in self.prompt_lower]
                    self.output_parts.append(
                        f'<activated-skill name="{skill_name}" '
                        f'triggers="{", ".join(triggers_matched)}">'
                    )
                    self.output_parts.append(content)
                    self.output_parts.append('</activated-skill>')

        except Exception as e:
            pass  # Silently fail to not break context injection

    # Helper methods
    def _has_keywords(self, keywords: List[str]) -> bool:
        """Check if prompt contains any of the keywords."""
        return any(kw in self.prompt_lower for kw in keywords)

    def _detect_domain(self) -> Optional[str]:
        """Detect domain from prompt keywords."""
        domain_map = {
            'docker': ['docker', 'container', 'compose'],
            'auth': ['auth', 'login', 'token', 'session', 'firebase'],
            'react': ['react', 'component', 'hook', 'state', 'props'],
            'database': ['database', 'query', 'sql', 'firestore', 'collection'],
            'api': ['api', 'endpoint', 'fetch', 'request', 'response']
        }
        for domain, keywords in domain_map.items():
            if any(kw in self.prompt_lower for kw in keywords):
                return domain
        return None

    def _load_config(self) -> Dict:
        """Load main config."""
        config_path = MEMORY_ROOT / "config.json"
        if config_path.exists():
            try:
                return json.loads(config_path.read_text())
            except:
                pass
        return {'projects': []}

    def _read_truncated(self, path: Path, max_chars: int) -> str:
        """Read file with truncation."""
        try:
            content = path.read_text()
            if len(content) > max_chars:
                return content[:max_chars] + "\n... [truncated]"
            return content
        except:
            return ""


def main():
    """Entry point for hook invocation."""
    if len(sys.argv) < 3:
        print("Usage: inject_all_context.py <prompt> <project_id> [--first]", file=sys.stderr)
        sys.exit(1)

    prompt = sys.argv[1]
    project_id = sys.argv[2]
    is_first = "--first" in sys.argv

    injector = ContextInjector(prompt, project_id, is_first_message=is_first)
    output = injector.inject_all()

    if output:
        print(output)


if __name__ == "__main__":
    main()
