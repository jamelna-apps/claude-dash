#!/usr/bin/env python3
"""
Wireframe Analyzer for Claude Memory System

Analyzes project screens and generates wireframe-friendly data:
- Screen inventory with purposes
- Navigation flow map
- Data dependencies per screen
- UI component usage
- Mermaid flowchart generation

Usage:
  python wireframe_analyzer.py <project_id> [command]

Commands:
  inventory    - List all screens with details
  flow         - Generate navigation flow (Mermaid)
  screen <name> - Get detailed info for one screen
  data-map     - Show screen-to-data relationships
  components   - Analyze UI component usage
  export       - Export full wireframe data as JSON
"""

import json
import sys
import re
import os
from pathlib import Path
from collections import defaultdict

MEMORY_ROOT = Path.home() / ".claude-dash"


def load_project_data(project_id):
    """Load all relevant project memory files."""
    project_path = MEMORY_ROOT / "projects" / project_id

    data = {
        "graph": {},
        "summaries": {},
        "schema": {},
        "functions": {},
        "index": {}
    }

    files = {
        "graph": "graph.json",
        "summaries": "summaries.json",
        "schema": "schema.json",
        "functions": "functions.json",
        "index": "index.json"
    }

    for key, filename in files.items():
        filepath = project_path / filename
        if filepath.exists():
            try:
                data[key] = json.loads(filepath.read_text())
            except:
                pass

    return data


def get_screen_inventory(data):
    """Get inventory of all screens with details."""
    screens = []

    # Get screens from graph
    screen_nav = data["graph"].get("screenNavigation", {})
    summaries = data["summaries"].get("files", {})

    for screen_name, nav_data in screen_nav.items():
        screen_path = nav_data.get("path", "")

        # Find summary for this screen
        summary_data = {}
        for file_path, file_summary in summaries.items():
            if screen_name in file_path or file_path == screen_path:
                summary_data = file_summary
                break

        screens.append({
            "name": screen_name,
            "path": screen_path,
            "purpose": summary_data.get("purpose", "Unknown"),
            "summary": summary_data.get("summary", ""),
            "navigatesTo": nav_data.get("navigatesTo", []),
            "reachableFrom": nav_data.get("reachableFrom", []),
            "component": summary_data.get("componentName", screen_name)
        })

    return sorted(screens, key=lambda x: x["name"])


def generate_navigation_flow(data, format="mermaid"):
    """Generate navigation flow diagram."""
    screen_nav = data["graph"].get("screenNavigation", {})

    if format == "mermaid":
        lines = ["flowchart TD"]

        # Track all screens and connections
        connections = set()
        all_screens = set()

        for screen_name, nav_data in screen_nav.items():
            all_screens.add(screen_name)
            for target in nav_data.get("navigatesTo", []):
                # Clean target name (remove 'Screen' suffix for cleaner display)
                target_clean = target.replace("Screen", "") if target.endswith("Screen") else target
                screen_clean = screen_name.replace("Screen", "") if screen_name.endswith("Screen") else screen_name
                connections.add((screen_clean, target_clean))
                all_screens.add(target)

        # Add node definitions with styling
        for screen in sorted(all_screens):
            screen_clean = screen.replace("Screen", "") if screen.endswith("Screen") else screen
            # Style based on screen type
            if "Home" in screen or "Main" in screen:
                lines.append(f"    {screen_clean}[/{screen_clean}/]")  # Trapezoid for main
            elif "Login" in screen or "Auth" in screen or "Signup" in screen:
                lines.append(f"    {screen_clean}([{screen_clean}])")  # Stadium for auth
            elif "Settings" in screen or "Profile" in screen:
                lines.append(f"    {screen_clean}[({screen_clean})]")  # Subroutine for settings
            else:
                lines.append(f"    {screen_clean}[{screen_clean}]")  # Rectangle default

        # Add connections
        for source, target in sorted(connections):
            lines.append(f"    {source} --> {target}")

        return "\n".join(lines)

    elif format == "ascii":
        # Simple ASCII representation
        lines = ["NAVIGATION FLOW", "=" * 50]
        for screen_name, nav_data in sorted(screen_nav.items()):
            targets = nav_data.get("navigatesTo", [])
            if targets:
                lines.append(f"\n{screen_name}")
                for target in targets:
                    lines.append(f"  └──> {target}")
        return "\n".join(lines)

    return ""


def get_screen_data_map(data):
    """Map screens to their data dependencies (Firestore collections, etc.)."""
    schema = data["schema"].get("collections", {})
    summaries = data["summaries"].get("files", {})
    screen_nav = data["graph"].get("screenNavigation", {})

    screen_data = {}

    for screen_name, nav_data in screen_nav.items():
        screen_path = nav_data.get("path", "")

        # Find which collections this screen uses
        collections_used = []
        for collection_name, collection_data in schema.items():
            referenced_in = collection_data.get("referencedIn", [])
            for ref in referenced_in:
                if screen_name.lower() in ref.lower() or screen_path in ref:
                    collections_used.append({
                        "collection": collection_name,
                        "fields": collection_data.get("fields", [])[:10]  # First 10 fields
                    })
                    break

        # Get screen summary for context
        summary = ""
        for file_path, file_summary in summaries.items():
            if screen_name in file_path:
                summary = file_summary.get("summary", "")
                break

        screen_data[screen_name] = {
            "path": screen_path,
            "collections": collections_used,
            "summary": summary
        }

    return screen_data


def analyze_ui_components(data):
    """Analyze UI component usage across screens."""
    summaries = data["summaries"].get("files", {})
    graph = data["graph"]

    # Common React Native / React components to look for
    common_components = [
        "Button", "Modal", "Card", "List", "Input", "Form",
        "Header", "Footer", "Tab", "Navigation", "Image",
        "Avatar", "Badge", "Chip", "Alert", "Toast", "Drawer",
        "Fab", "Icon", "Menu", "Picker", "Slider", "Switch",
        "TextInput", "ScrollView", "FlatList", "SectionList"
    ]

    component_usage = defaultdict(list)

    # Get components from graph if available
    components = graph.get("nodes", {}).get("components", {})
    for comp_path, comp_data in components.items():
        comp_name = comp_data.get("name", Path(comp_path).stem)
        component_usage[comp_name].append({
            "path": comp_path,
            "usedIn": comp_data.get("usedIn", [])
        })

    return dict(component_usage)


def get_screen_detail(data, screen_name):
    """Get detailed information for a specific screen."""
    screen_nav = data["graph"].get("screenNavigation", {})
    summaries = data["summaries"].get("files", {})
    functions = data["functions"].get("functions", {})
    schema = data["schema"].get("collections", {})

    # Find screen in navigation
    screen_data = None
    for name, nav_data in screen_nav.items():
        if name.lower() == screen_name.lower() or screen_name.lower() in name.lower():
            screen_data = {"name": name, **nav_data}
            break

    if not screen_data:
        return {"error": f"Screen not found: {screen_name}"}

    # Find summary
    screen_path = screen_data.get("path", "")
    summary_data = {}
    for file_path, file_summary in summaries.items():
        if screen_data["name"] in file_path or file_path == screen_path:
            summary_data = file_summary
            break

    # Find functions in this screen
    screen_functions = []
    for func_name, locations in functions.items():
        for loc in locations:
            if screen_data["name"] in loc.get("file", "") or screen_path in loc.get("file", ""):
                screen_functions.append({
                    "name": func_name,
                    "line": loc.get("line"),
                    "type": loc.get("type", "function")
                })

    # Find data dependencies
    collections_used = []
    for collection_name, collection_data in schema.items():
        for ref in collection_data.get("referencedIn", []):
            if screen_data["name"].lower() in ref.lower():
                collections_used.append({
                    "collection": collection_name,
                    "fields": collection_data.get("fields", [])[:15]
                })
                break

    return {
        "name": screen_data["name"],
        "path": screen_path,
        "purpose": summary_data.get("purpose", "Unknown"),
        "summary": summary_data.get("summary", ""),
        "navigation": {
            "navigatesTo": screen_data.get("navigatesTo", []),
            "reachableFrom": screen_data.get("reachableFrom", [])
        },
        "functions": screen_functions[:20],  # Limit to 20
        "dataCollections": collections_used,
        "component": summary_data.get("componentName")
    }


def export_wireframe_data(data, project_id):
    """Export complete wireframe data as JSON."""
    return {
        "projectId": project_id,
        "generatedAt": __import__("datetime").datetime.now().isoformat(),
        "screens": get_screen_inventory(data),
        "navigationFlow": generate_navigation_flow(data, "mermaid"),
        "dataMap": get_screen_data_map(data),
        "components": analyze_ui_components(data),
        "stats": {
            "totalScreens": len(data["graph"].get("screenNavigation", {})),
            "totalCollections": len(data["schema"].get("collections", {})),
            "totalFunctions": data["functions"].get("totalFunctions", 0)
        }
    }


def format_inventory(screens):
    """Format screen inventory for display."""
    lines = ["SCREEN INVENTORY", "=" * 60, ""]

    for screen in screens:
        lines.append(f"## {screen['name']}")
        lines.append(f"   Path: {screen['path']}")
        lines.append(f"   Purpose: {screen['purpose']}")
        if screen['navigatesTo']:
            lines.append(f"   Navigates to: {', '.join(screen['navigatesTo'][:5])}")
        if screen['reachableFrom']:
            lines.append(f"   Reachable from: {', '.join(screen['reachableFrom'][:5])}")
        lines.append("")

    return "\n".join(lines)


def format_data_map(data_map):
    """Format data map for display."""
    lines = ["SCREEN DATA DEPENDENCIES", "=" * 60, ""]

    for screen_name, screen_data in sorted(data_map.items()):
        if screen_data["collections"]:
            lines.append(f"## {screen_name}")
            for coll in screen_data["collections"]:
                lines.append(f"   Collection: {coll['collection']}")
                if coll['fields']:
                    fields_str = ", ".join(coll['fields'][:5])
                    lines.append(f"   Fields: {fields_str}...")
            lines.append("")

    return "\n".join(lines)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    project_id = sys.argv[1]
    command = sys.argv[2] if len(sys.argv) > 2 else "inventory"

    # Load project data
    data = load_project_data(project_id)

    if not data["graph"]:
        print(f"Error: No graph data found for project '{project_id}'")
        sys.exit(1)

    if command == "inventory":
        screens = get_screen_inventory(data)
        print(format_inventory(screens))

    elif command == "flow":
        format_type = sys.argv[3] if len(sys.argv) > 3 else "mermaid"
        print(generate_navigation_flow(data, format_type))

    elif command == "screen":
        if len(sys.argv) < 4:
            print("Usage: wireframe_analyzer.py <project> screen <screen_name>")
            sys.exit(1)
        screen_name = sys.argv[3]
        detail = get_screen_detail(data, screen_name)
        print(json.dumps(detail, indent=2))

    elif command == "data-map":
        data_map = get_screen_data_map(data)
        print(format_data_map(data_map))

    elif command == "components":
        components = analyze_ui_components(data)
        print(json.dumps(components, indent=2))

    elif command == "export":
        export_data = export_wireframe_data(data, project_id)
        print(json.dumps(export_data, indent=2))

    elif command == "--json":
        # Output everything as JSON (for API use)
        export_data = export_wireframe_data(data, project_id)
        print(json.dumps(export_data))

    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
