#!/usr/bin/env python3
"""
Model Router CLI - Manage task-based model routing

Usage:
  python model_router.py list                           # Show all task-model mappings
  python model_router.py test <task>                    # Test routing for a task
  python model_router.py set <task> <model>             # Set model for a task
  python model_router.py available                      # List available Ollama models
  python model_router.py status                         # Show routing system status
"""

import sys
import json
from pathlib import Path

# Add tools directory to path
sys.path.insert(0, str(Path(__file__).parent))

from config import (
    get_model_for_task,
    list_task_models,
    update_task_model,
    TASK_MODEL_MAP,
    OLLAMA_CHAT_MODEL,
    OLLAMA_EMBED_MODEL,
    OLLAMA_VLM_MODEL
)
from ollama_client import OllamaClient


def list_mappings():
    """List all task-to-model mappings"""
    print("Task-to-Model Routing Table")
    print("=" * 70)
    print(f"{'Task':<25} {'Model':<30} {'Status':<15}")
    print("-" * 70)

    client = OllamaClient()
    available_models = set(client.list_models())

    mappings = list_task_models()

    # Group by category
    categories = {
        'Code Analysis': ['code_review', 'code_analysis', 'code_explanation', 'static_analysis'],
        'Documentation': ['documentation', 'summarization', 'commit_message', 'pr_description'],
        'Reasoning': ['rag', 'query', 'ask', 'planning', 'architecture'],
        'Testing': ['test_generation', 'error_analysis'],
        'Visual': ['ui_analysis', 'screenshot_review', 'design_assessment', 'wireframe_analysis']
    }

    for category, tasks in categories.items():
        print(f"\n{category}:")
        for task in tasks:
            if task in mappings:
                model = mappings[task]
                if model is None:
                    status = "❌ Not set"
                    model = f"→ {OLLAMA_CHAT_MODEL}"
                elif model in available_models:
                    status = "✅ Ready"
                else:
                    status = "⚠️  Not found"
                print(f"  {task:<23} {model:<30} {status}")

    print("\n" + "=" * 70)
    print(f"\nDefault Models:")
    print(f"  Chat:       {OLLAMA_CHAT_MODEL}")
    print(f"  Embeddings: {OLLAMA_EMBED_MODEL}")
    print(f"  VLM:        {OLLAMA_VLM_MODEL or 'Not configured'}")


def test_routing(task: str):
    """Test routing for a specific task"""
    print(f"Testing routing for task: {task}")
    print("-" * 50)

    model = get_model_for_task(task)
    print(f"Selected model: {model}")

    # Check if model exists
    client = OllamaClient()
    available = client.list_models()

    if model in available:
        print(f"✅ Model '{model}' is available")

        # Test generation
        print("\nTesting generation...")
        test_client = OllamaClient(task=task)
        response = test_client.generate("Say 'Task routing is working!' in exactly those words.")

        if response:
            print(f"✅ Generation test passed")
            print(f"Response: {response[:100]}")
        else:
            print("❌ Generation test failed")
    else:
        print(f"❌ Model '{model}' not found in Ollama")
        print(f"Available models: {', '.join(available)}")


def set_task_model(task: str, model: str):
    """Set model for a task"""
    print(f"Setting task '{task}' to use model '{model}'")

    # Verify model exists
    client = OllamaClient()
    available = client.list_models()

    if model not in available:
        print(f"⚠️  Warning: Model '{model}' not found in Ollama")
        print(f"Available models: {', '.join(available)}")
        confirm = input("Continue anyway? [y/N]: ").strip().lower()
        if confirm != 'y':
            print("Cancelled")
            return

    update_task_model(task, model)
    print(f"✅ Updated: {task} → {model}")
    print("\nNote: This change is temporary (in-memory only).")
    print("To make it permanent, update TASK_MODEL_MAP in config.py")


def show_available():
    """List available Ollama models"""
    print("Available Ollama Models")
    print("=" * 50)

    client = OllamaClient()
    models = client.list_models()

    if models:
        for model in sorted(models):
            # Highlight currently used models
            markers = []
            if model == OLLAMA_CHAT_MODEL:
                markers.append("CHAT")
            if model == OLLAMA_EMBED_MODEL:
                markers.append("EMBED")
            if model == OLLAMA_VLM_MODEL:
                markers.append("VLM")

            marker_str = f" [{', '.join(markers)}]" if markers else ""
            print(f"  • {model}{marker_str}")
    else:
        print("No models found. Is Ollama running?")


def show_status():
    """Show routing system status"""
    print("Task-Based Model Routing Status")
    print("=" * 70)

    client = OllamaClient()
    health = client.health()

    print(f"\nOllama Status:")
    print(f"  URL:       {health['url']}")
    print(f"  Available: {'✅ Yes' if health['available'] else '❌ No'}")

    if health['available']:
        print(f"  Models:    {len(health['models'])} available")

        # Count configured tasks
        mappings = list_task_models()
        configured = sum(1 for m in mappings.values() if m is not None)
        total = len(mappings)

        print(f"\nTask Configuration:")
        print(f"  Total tasks:      {total}")
        print(f"  Configured:       {configured}")
        print(f"  Using fallback:   {total - configured}")

        # Check for missing models
        available_models = set(health['models'])
        missing = []
        for task, model in mappings.items():
            if model and model not in available_models:
                missing.append((task, model))

        if missing:
            print(f"\n⚠️  Missing Models:")
            for task, model in missing:
                print(f"    {task} → {model}")
            print(f"\nInstall with: ollama pull <model>")
    else:
        print("\n❌ Ollama is not running")
        print("Start with: ollama serve")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]

    if command == 'list':
        list_mappings()
    elif command == 'test':
        if len(sys.argv) < 3:
            print("Usage: model_router.py test <task>")
            sys.exit(1)
        test_routing(sys.argv[2])
    elif command == 'set':
        if len(sys.argv) < 4:
            print("Usage: model_router.py set <task> <model>")
            sys.exit(1)
        set_task_model(sys.argv[2], sys.argv[3])
    elif command == 'available':
        show_available()
    elif command == 'status':
        show_status()
    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == '__main__':
    main()
