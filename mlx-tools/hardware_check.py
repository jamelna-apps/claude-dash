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

    print("\n✅ WILL RUN WELL (Recommended):")
    recommendations = [
        ("qwen2.5:7b", "~5GB", "General tasks, good quality", "Already installed" if "qwen2.5:7b" in installed else "ollama pull qwen2.5:7b"),
        ("llava:7b", "~5GB", "UI/screenshot analysis", "Already installed" if "llava:7b" in installed else "ollama pull llava:7b"),
        ("deepseek-coder:6.7b", "~4GB", "Code-focused tasks", "Already installed" if "deepseek-coder:6.7b" in installed else "ollama pull deepseek-coder:6.7b"),
        ("qwen2.5:3b", "~2GB", "Fast, simple tasks", "Already installed" if "qwen2.5:3b" in installed else "ollama pull qwen2.5:3b"),
    ]

    for model, size, purpose, install_cmd in recommendations:
        status = "✓" if model in installed else " "
        print(f"   [{status}] {model:<25} {size:<8} - {purpose}")
        if model not in installed:
            print(f"       Install: {install_cmd}")

    print("\n⚠️  POSSIBLE BUT SLOWER:")
    slow_models = [
        ("llava:13b", "~8GB", "Better vision, but will slow system"),
        ("mixtral:8x7b", "~26GB", "High quality, but won't fit comfortably"),
    ]

    for model, size, note in slow_models:
        print(f"   [ ] {model:<25} {size:<8} - {note}")

    print("\n❌ DON'T INSTALL (Too Large):")
    avoid = [
        ("deepseek-coder:33b", "~20GB", "Won't run well"),
        ("llama3:70b", "~40GB", "Way too large"),
        ("llava:34b", "~20GB", "Won't run well"),
    ]

    for model, size, note in avoid:
        print(f"   [ ] {model:<25} {size:<8} - {note}")

    # Performance expectations
    print("\n" + "=" * 70)
    print("Expected Performance on M2 16GB")
    print("=" * 70)

    print("\n7B models (qwen2.5:7b, llava:7b):")
    print("  • Speed: 30-50 tokens/sec")
    print("  • RAM: 4-5GB while running")
    print("  • Quality: ⭐⭐⭐⭐ Very good")
    print("  • Verdict: ✅ Perfect for your hardware")

    print("\n13B models (llava:13b):")
    print("  • Speed: 15-25 tokens/sec")
    print("  • RAM: 8-9GB while running")
    print("  • Quality: ⭐⭐⭐⭐⭐ Excellent")
    print("  • Verdict: ⚠️  Possible but will slow down other apps")

    print("\n3B models (qwen2.5:3b, llama3.2:3b):")
    print("  • Speed: 50-80 tokens/sec")
    print("  • RAM: 2-3GB while running")
    print("  • Quality: ⭐⭐⭐ Good")
    print("  • Verdict: ✅ Great for quick/simple tasks")

    # Suggested setup
    print("\n" + "=" * 70)
    print("Suggested Setup for Your Use Case")
    print("=" * 70)

    print("\n🎯 Recommended (Start Here):")
    print("   • qwen2.5:7b → All text tasks")
    print("   • nomic-embed-text → Embeddings")
    print("   Total: ~5GB disk, ~5GB RAM when running")

    print("\n🎨 Add for UI Analysis:")
    print("   • llava:7b → Screenshot/UI analysis")
    print("   Total: +5GB disk")

    print("\n💻 Add for Better Code Review (Optional):")
    print("   • deepseek-coder:6.7b → Specialized code understanding")
    print("   Total: +4GB disk")

    print("\n⚡ Add for Speed (Optional):")
    print("   • qwen2.5:3b → Quick queries, simple tasks")
    print("   Total: +2GB disk")

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
    print("  mlx models status")
    print("  mlx models list")
    print("  time mlx ask gyst 'what is this app?'")

    print("\nAdd visual analysis:")
    print("  ollama pull llava:7b")
    print("  export OLLAMA_VLM_MODEL='llava:7b'")
    print("  mlx models test ui_analysis")

    print("\nCleanup unused models:")
    print("  ollama list")
    print("  ollama rm <model-name>")

    print("\n" + "=" * 70)


if __name__ == '__main__':
    main()
