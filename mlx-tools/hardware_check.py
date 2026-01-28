#!/usr/bin/env python3
"""
Hardware-aware model recommendations for M2 Mac

Shows what models will run well on your specific hardware.
"""

import sys
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ollama_client import OllamaClient


def get_system_ram():
    """Get total system RAM in GB"""
    try:
        result = subprocess.check_output(['sysctl', 'hw.memsize']).decode()
        bytes_ram = int(result.split(':')[1].strip())
        return bytes_ram / (1024**3)
    except:
        return None


def get_available_ram():
    """Get available RAM in GB"""
    try:
        result = subprocess.check_output(['vm_stat']).decode()
        lines = result.split('\n')

        page_size = 4096  # bytes
        free = 0
        inactive = 0

        for line in lines:
            if 'Pages free' in line:
                free = int(line.split(':')[1].strip().replace('.', ''))
            elif 'Pages inactive' in line:
                inactive = int(line.split(':')[1].strip().replace('.', ''))

        available_bytes = (free + inactive) * page_size
        return available_bytes / (1024**3)
    except:
        return None


def get_model_size(model_name: str) -> str:
    """Estimate model size from name"""
    sizes = {
        '3b': '~2GB',
        '6.7b': '~4GB',
        '7b': '~4-5GB',
        '13b': '~8GB',
        '33b': '~20GB',
        '70b': '~40GB',
    }

    for key, size in sizes.items():
        if key in model_name.lower():
            return size
    return 'Unknown'


def main():
    print("=" * 70)
    print("M2 Mac - Model Recommendations Based on Your Hardware")
    print("=" * 70)

    # System info
    total_ram = get_system_ram()
    available_ram = get_available_ram()

    if total_ram:
        print(f"\n📊 System RAM: {total_ram:.1f}GB total")
        if available_ram:
            print(f"   Available now: {available_ram:.1f}GB")

    # Ollama status
    client = OllamaClient()
    health = client.health()

    print(f"\n🤖 Ollama Status: {'✅ Running' if health['available'] else '❌ Not running'}")

    if not health['available']:
        print("\nStart Ollama with: ollama serve")
        return

    # Installed models
    installed = health['models']
    print(f"\n📦 Installed Models ({len(installed)}):")

    total_size = 0
    for model in installed:
        size = get_model_size(model)
        print(f"   • {model:<30} {size}")
        # Rough size calculation
        if '7b' in model.lower():
            total_size += 4.7
        elif '13b' in model.lower():
            total_size += 8
        elif '3b' in model.lower():
            total_size += 2

    print(f"\n   Estimated total: ~{total_size:.1f}GB on disk")

    # Recommendations based on 16GB M2
    print("\n" + "=" * 70)
    print("Recommendations for 16GB M2")
    print("=" * 70)

    print("\n✅ MINIMAL SETUP (Recommended):")
    print("   Use Claude for real code work, Ollama for embeddings + cheap tasks\n")
    recommendations = [
        ("gemma3:4b-it-qat", "~4GB", "All local generation tasks (128K context)", "Already installed" if "gemma3:4b-it-qat" in installed else "ollama pull gemma3:4b-it-qat"),
        ("nomic-embed-text", "~0.3GB", "Embeddings for semantic search", "Already installed" if "nomic-embed-text:latest" in installed else "ollama pull nomic-embed-text"),
    ]

    for model, size, purpose, install_cmd in recommendations:
        status = "✓" if model in installed else " "
        print(f"   [{status}] {model:<25} {size:<8} - {purpose}")
        if model not in installed:
            print(f"       Install: {install_cmd}")

    print("\n⚠️  OPTIONAL (If you want more local power):")
    optional_models = [
        ("gemma3:12b", "~8GB", "Higher quality but slower"),
    ]

    for model, size, note in optional_models:
        status = "✓" if model in installed else " "
        print(f"   [{status}] {model:<25} {size:<8} - {note}")

    print("\n❌ NOT NEEDED (Use Claude instead):")
    avoid = [
        ("deepseek-coder", "~4GB", "Use Claude for code review"),
        ("qwen3:*", "~2-20GB", "Use Claude for tool calling/agents"),
    ]

    for model, size, note in avoid:
        print(f"   [ ] {model:<25} {size:<8} - {note}")

    # Performance expectations
    print("\n" + "=" * 70)
    print("Expected Performance on M2 16GB")
    print("=" * 70)

    print("\n4B models (gemma3:4b-it-qat):")
    print("  • Speed: 30-50 tokens/sec")
    print("  • RAM: 3-4GB while running")
    print("  • Quality: ⭐⭐⭐⭐ Good for non-critical tasks")
    print("  • Verdict: ✅ Use for embeddings, commit msgs, cheap queries")

    print("\n12B models (gemma3:12b):")
    print("  • Speed: 15-25 tokens/sec")
    print("  • RAM: 8-9GB while running")
    print("  • Quality: ⭐⭐⭐⭐⭐ Excellent")
    print("  • Verdict: ⚠️  Possible but will slow down other apps")

    # Suggested setup
    print("\n" + "=" * 70)
    print("Suggested Setup for Your Use Case")
    print("=" * 70)

    print("\n🎯 Current Setup (Minimal - Claude for real work):")
    print("   • gemma3:4b-it-qat → Commit msgs, Enchanted queries, summarization")
    print("   • nomic-embed-text → Embeddings for semantic search")
    print("   • Claude (Sonnet/Opus) → All real code work")
    print("   Total: ~4.3GB disk, ~4GB RAM when running")

    print("\n🎨 For UI/Vision Analysis:")
    print("   • Use Claude API (no local VLM configured)")
    print("   • Better quality than local vision models")

    # Model management tips
    print("\n" + "=" * 70)
    print("💡 Tips for Managing Models on 16GB")
    print("=" * 70)

    print("\n• Ollama automatically unloads models after ~5 min of inactivity")
    print("• Only ONE model runs in RAM at a time (~5GB)")
    print("• You can install multiple models (disk space permitting)")
    print("• Task routing will auto-select the right model")
    print("• Stick to 7B models for best experience on M2 16GB")

    # Quick actions
    print("\n" + "=" * 70)
    print("Quick Actions")
    print("=" * 70)

    print("\nTest current setup:")
    print("  python hardware_check.py")
    print("  ollama list")
    print("  curl http://localhost:11434/api/tags | jq '.models[].name'")

    print("\nTest model routing:")
    print("  python -c \"from config import get_model_for_task; print(get_model_for_task('code_review'))\"")

    print("\nCleanup unused models:")
    print("  ollama list")
    print("  ollama rm <model-name>")

    print("\n" + "=" * 70)


if __name__ == '__main__':
    main()
