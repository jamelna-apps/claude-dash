# Local Hardware Architecture for Claude-Dash

## Overview

This document outlines hardware configurations for running larger local AI models with Claude-Dash. More powerful local compute enables:

- **Larger models** (70B+ parameters vs current 7B)
- **Real-time analysis** (streaming code analysis, live error detection)
- **Multi-model pipelines** (specialized models for different tasks)
- **Proactive intelligence** (background learning, pattern mining)

---

## What Local Compute Affects

| Component | Server-Side (Claude API) | Local (Ollama) |
|-----------|-------------------------|----------------|
| Main reasoning | Claude handles this | N/A |
| Code generation | Claude handles this | N/A |
| Memory queries | N/A | **Local** - faster with better hardware |
| Embeddings | N/A | **Local** - nomic-embed-text |
| Session synthesis | N/A | **Local** - qwen2.5:7b |
| Code review | N/A | **Local** - can use larger models |
| Error analysis | N/A | **Local** - can use larger models |
| Background indexing | N/A | **Local** - watcher + extractors |

**Key insight**: Local hardware improvements affect memory operations, not Claude's main reasoning. But better local models = smarter context injection = Claude makes better decisions.

---

## Model Tiers

| Tier | Model Size | VRAM Needed | Quality | Speed |
|------|-----------|-------------|---------|-------|
| Current | 7B (qwen2.5:7b) | 8GB | Good | Fast |
| Mid | 32B (qwen2.5:32b) | 24GB | Better | Medium |
| High | 70B (llama3.3:70b) | 48GB | Excellent | Slower |
| Ultra | 405B (llama3.1:405b) | 200GB+ | Best | Slow |

---

## Mac Configurations

### Tier 1: Current Setup (M1/M2/M3 Base)
**Cost: $0 (existing hardware)**

```
┌─────────────────────────────────────┐
│ MacBook Air/Pro M1-M3 (8-16GB)     │
│                                     │
│  ┌─────────────┐  ┌──────────────┐ │
│  │ qwen2.5:7b  │  │ nomic-embed  │ │
│  │ (sessions)  │  │ (search)     │ │
│  └─────────────┘  └──────────────┘ │
└─────────────────────────────────────┘
```

**Capabilities:**
- 7B models run well
- ~30 tokens/sec inference
- Good for current Claude-Dash features

**Limitations:**
- Can't run models larger than 13B efficiently
- No concurrent model loading

---

### Tier 2: M3 Pro/Max MacBook Pro
**Cost: $2,500-4,000**

```
Hardware:
- M3 Pro: 18GB unified memory ($2,499)
- M3 Max: 36-48GB unified memory ($3,499-4,499)

Performance:
- M3 Max 48GB can run 32B models
- ~25 tokens/sec on 32B
- Can keep 2 models loaded simultaneously
```

```
┌─────────────────────────────────────────────┐
│ MacBook Pro M3 Max (48GB)                   │
│                                             │
│  ┌──────────────┐  ┌──────────────────────┐│
│  │qwen2.5:32b   │  │ Concurrent:          ││
│  │(synthesis)   │  │ - nomic-embed        ││
│  │              │  │ - codellama:13b      ││
│  └──────────────┘  └──────────────────────┘│
└─────────────────────────────────────────────┘
```

**Capabilities:**
- Run 32B models for better reasoning
- Multi-model pipelines (embedding + reasoning)
- Background code analysis while working

**Best for:** Developers who want better local AI without a separate machine.

---

### Tier 3: Mac Studio M2/M3 Ultra
**Cost: $4,000-8,000**

```
Hardware:
- M2 Ultra: 64-192GB unified memory ($3,999-7,999)
- M3 Ultra: 64-192GB unified memory (expected ~$4,499-8,499)

Performance:
- 192GB can run 70B models fully in memory
- ~40 tokens/sec on 70B (M2 Ultra)
- Can run multiple large models concurrently
```

```
┌───────────────────────────────────────────────────────────┐
│ Mac Studio M2/M3 Ultra (192GB)                            │
│                                                           │
│  ┌────────────────┐  ┌────────────────┐  ┌─────────────┐ │
│  │ llama3.3:70b   │  │ qwen2.5:32b    │  │ deepseek-   │ │
│  │ (main reason)  │  │ (code review)  │  │ coder:33b   │ │
│  └────────────────┘  └────────────────┘  └─────────────┘ │
│                                                           │
│  ┌────────────────┐  ┌────────────────┐                  │
│  │ nomic-embed    │  │ Background     │                  │
│  │ (always loaded)│  │ indexing       │                  │
│  └────────────────┘  └────────────────┘                  │
└───────────────────────────────────────────────────────────┘
```

**Capabilities:**
- Run 70B models at good speed
- Multi-model routing (best model for each task)
- Real-time code analysis
- Proactive pattern learning

**Best for:** Power users who want near-Claude-level local reasoning for specific tasks.

---

### Tier 4: Mac Pro (Future M3 Ultra)
**Cost: $8,000-15,000+**

```
Hardware:
- Dual M3 Ultra (theoretical): 384GB unified memory
- Expected ~$10,000-15,000

Performance:
- Could run 405B models with offloading
- Multiple 70B models concurrently
- ~20-30 tokens/sec on 405B
```

**Capabilities:**
- State-of-the-art open models locally
- Full multi-agent pipelines
- Research-grade local AI

**Best for:** AI researchers, companies with security requirements, enthusiasts.

---

## Linux Configurations

### Tier 1: Single Consumer GPU
**Cost: $400-2,000**

```
Hardware Options:
- RTX 4070 (12GB) - $549
- RTX 4080 (16GB) - $1,199
- RTX 4090 (24GB) - $1,599

Performance:
- RTX 4090: ~60 tokens/sec on 7B
- RTX 4090: ~25 tokens/sec on 32B (quantized)
```

```
┌────────────────────────────────────────────┐
│ Linux Desktop + RTX 4090                   │
│                                            │
│  ┌───────────────────────────────────────┐│
│  │ GPU: RTX 4090 (24GB VRAM)             ││
│  │                                        ││
│  │  qwen2.5:32b-q4 (~18GB)               ││
│  │  + nomic-embed (~1GB)                 ││
│  └───────────────────────────────────────┘│
│                                            │
│  CPU: Any modern 8+ core                   │
│  RAM: 32GB+ (for model loading)           │
└────────────────────────────────────────────┘
```

**Capabilities:**
- Faster inference than M3 Max (CUDA optimization)
- Can run quantized 32B models
- Good for single-task workflows

**Limitations:**
- 24GB VRAM limits model size
- Single GPU = limited concurrency

**Best for:** Developers with existing gaming PCs, budget-conscious setups.

---

### Tier 2: Dual/Multi-GPU Workstation
**Cost: $3,000-10,000**

```
Hardware Options:
- 2x RTX 4090 (48GB total) - ~$3,500
- 2x RTX A6000 (96GB total) - ~$10,000
- 4x RTX 4090 (96GB total) - ~$7,000

Performance:
- 2x RTX 4090: ~30 tokens/sec on 70B (tensor parallel)
- 4x RTX 4090: ~50 tokens/sec on 70B
```

```
┌────────────────────────────────────────────────────────┐
│ Multi-GPU Workstation                                  │
│                                                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐│
│  │ GPU 1        │  │ GPU 2        │  │ GPU 3        ││
│  │ RTX 4090     │  │ RTX 4090     │  │ RTX 4090     ││
│  │ 24GB         │  │ 24GB         │  │ 24GB         ││
│  └──────────────┘  └──────────────┘  └──────────────┘│
│                                                        │
│  ┌──────────────────────────────────────────────────┐ │
│  │ llama3.3:70b (tensor parallel across 3 GPUs)    │ │
│  └──────────────────────────────────────────────────┘ │
│                                                        │
│  ┌──────────────┐                                     │
│  │ GPU 4 (opt)  │  Dedicated for:                    │
│  │ RTX 4090     │  - Embeddings                      │
│  │ 24GB         │  - Background tasks                │
│  └──────────────┘                                     │
└────────────────────────────────────────────────────────┘
```

**Capabilities:**
- Run 70B models at good speed
- Dedicated GPU for embeddings/background
- Multi-model concurrency

**Considerations:**
- Needs NVLink or high PCIe bandwidth for tensor parallel
- Power: 450W per 4090 = 1800W for 4 GPUs
- Cooling requirements significant

**Best for:** Serious local AI work, small teams, privacy-focused organizations.

---

### Tier 3: Cloud GPU Instances
**Cost: $1-10/hour**

```
Provider Options:

AWS:
- p4d.24xlarge: 8x A100 (320GB) - ~$32/hr
- g5.48xlarge: 8x A10G (192GB) - ~$16/hr

Lambda Labs:
- 1x A100 (80GB): ~$1.10/hr
- 8x A100 (640GB): ~$8.80/hr

RunPod:
- 1x A100 (80GB): ~$1.50/hr
- Community GPUs: ~$0.20-0.50/hr
```

```
┌─────────────────────────────────────────────────────────┐
│ Cloud Instance (8x A100)                                │
│                                                         │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐      │
│  │ A100    │ │ A100    │ │ A100    │ │ A100    │      │
│  │ 80GB    │ │ 80GB    │ │ 80GB    │ │ 80GB    │      │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘      │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐      │
│  │ A100    │ │ A100    │ │ A100    │ │ A100    │      │
│  │ 80GB    │ │ 80GB    │ │ 80GB    │ │ 80GB    │      │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘      │
│                                                         │
│  Can run: llama3.1:405b at ~20 tokens/sec              │
└─────────────────────────────────────────────────────────┘
```

**Capabilities:**
- Run ANY model including 405B
- Scale up/down as needed
- No hardware maintenance

**Considerations:**
- Ongoing cost (vs one-time hardware)
- Data leaves your machine
- Network latency for every inference

**Best for:** Occasional heavy workloads, experimentation, teams without capital.

---

### Tier 4: Homelab / Dedicated Server
**Cost: $5,000-30,000**

```
Build Options:

Budget Build (~$5,000):
- Used server chassis
- 2x used RTX 3090 (48GB total)
- 128GB RAM
- 2TB NVMe

Mid Build (~$12,000):
- Supermicro 4U chassis
- 4x RTX 4090 (96GB total)
- 256GB RAM
- 4TB NVMe RAID

High-End Build (~$25,000):
- 2x RTX A6000 (96GB) or 4x RTX 4090
- 512GB RAM
- 10GbE networking
- UPS + cooling solution
```

```
┌────────────────────────────────────────────────────────────┐
│ Homelab Server (4U Rack)                                   │
│                                                            │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ 4x RTX 4090 (96GB VRAM)                             │  │
│  │ - llama3.3:70b (primary reasoning)                  │  │
│  │ - deepseek-coder:33b (code-specific)               │  │
│  │ - qwen2.5:32b (general tasks)                      │  │
│  │ - embeddings + background                          │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                            │
│  ┌──────────────────┐  ┌─────────────────────────────┐   │
│  │ 512GB RAM        │  │ 4TB NVMe (model storage)    │   │
│  │ (model loading)  │  │ (instant model switching)   │   │
│  └──────────────────┘  └─────────────────────────────┘   │
│                                                            │
│  Network: 10GbE → Local workstation                       │
└────────────────────────────────────────────────────────────┘
```

**Capabilities:**
- 24/7 availability
- Multiple concurrent large models
- Network-accessible from any machine
- Can serve entire team

**Considerations:**
- Electricity: $50-200/month depending on usage
- Noise (server fans)
- Space and cooling requirements

**Best for:** Teams, heavy users, those who want true local AI infrastructure.

---

## Architecture Recommendations by Use Case

### Solo Developer (Current + Near-term)
```
Recommended: Mac Studio M2 Ultra 64GB ($3,999)

Why:
- Runs 32B models well
- Silent operation
- No maintenance
- macOS integration

Models:
- qwen2.5:32b (main reasoning)
- deepseek-coder:6.7b (code-specific, fast)
- nomic-embed-text (search)
```

### Power User / Consultant
```
Recommended: Mac Studio M2 Ultra 192GB ($7,999) OR RTX 4090 workstation

Mac path:
- Silent, integrated, runs 70B models
- Higher cost per compute

Linux path:
- 2x RTX 4090 ($3,500 GPUs + $1,500 system)
- Faster inference, more complexity
- Requires Linux expertise
```

### Team / Company
```
Recommended: Homelab server + Cloud burst

On-prem:
- 4x RTX 4090 server for daily use
- Handles 90% of workload locally

Cloud burst:
- Lambda Labs/RunPod for heavy tasks
- Spin up 8x A100 for $8/hr when needed
```

---

## Claude-Dash Configuration by Tier

### Tier 1 Config (7B - Current)
```json
{
  "localAI": {
    "provider": "ollama",
    "models": {
      "default": "qwen2.5:7b",
      "embedding": "nomic-embed-text"
    }
  }
}
```

### Tier 2 Config (32B)
```json
{
  "localAI": {
    "provider": "ollama",
    "models": {
      "default": "qwen2.5:32b",
      "fast": "qwen2.5:7b",
      "code": "deepseek-coder:33b",
      "embedding": "nomic-embed-text"
    },
    "routing": {
      "codeReview": "code",
      "quickQuery": "fast",
      "synthesis": "default"
    }
  }
}
```

### Tier 3 Config (70B + Multi-model)
```json
{
  "localAI": {
    "provider": "ollama",
    "endpoint": "http://homelab:11434",
    "models": {
      "default": "llama3.3:70b",
      "fast": "qwen2.5:7b",
      "code": "deepseek-coder:33b",
      "reasoning": "qwen2.5:32b",
      "embedding": "nomic-embed-text"
    },
    "routing": {
      "codeReview": "code",
      "quickQuery": "fast",
      "synthesis": "default",
      "errorAnalysis": "reasoning",
      "patternMining": "default"
    },
    "background": {
      "enabled": true,
      "tasks": ["reindex", "patternLearn", "confidenceUpdate"]
    }
  }
}
```

---

## Network Architecture (Multi-machine)

For setups where the AI server is separate from your development machine:

```
┌─────────────────────┐         ┌─────────────────────────┐
│ Development Mac     │         │ AI Server (Linux)       │
│                     │         │                         │
│  Claude Code        │◄───────►│  Ollama API             │
│  Claude-Dash        │  HTTP   │  :11434                 │
│  hooks              │         │                         │
│                     │         │  Models:                │
│  config:            │         │  - llama3.3:70b         │
│  endpoint:          │         │  - qwen2.5:32b          │
│  homelab:11434      │         │  - deepseek-coder       │
└─────────────────────┘         └─────────────────────────┘
```

**Setup steps:**
1. Install Ollama on Linux server
2. Configure Ollama to listen on network: `OLLAMA_HOST=0.0.0.0 ollama serve`
3. Update Claude-Dash config to point to server IP
4. Ensure firewall allows port 11434

---

## Summary Recommendations

| Budget | Mac Option | Linux Option | Models |
|--------|-----------|--------------|--------|
| $0 | Current setup | - | 7B |
| $2,500 | M3 Pro 18GB | RTX 4070 build | 7B-13B |
| $4,000 | M3 Max 48GB | RTX 4090 build | 32B |
| $8,000 | M2 Ultra 192GB | 2x RTX 4090 | 70B |
| $15,000 | M3 Ultra (future) | 4x RTX 4090 server | 70B concurrent |
| $30,000+ | - | 8x GPU server | 405B |

**My recommendation for your current setup:**

Given you're on macOS and value simplicity, the **Mac Studio M2 Ultra 64-128GB** offers the best balance:
- Runs 32B models smoothly
- Can run 70B with some offloading (128GB+)
- Zero maintenance
- Silent operation
- ~$4,000-6,000

If you want maximum performance per dollar and don't mind Linux complexity:
- **2x RTX 4090 workstation** (~$5,000 total build)
- Faster than Mac for inference
- Can run 70B models with tensor parallel
- Requires more setup and maintenance

---

## Next Steps

1. **Immediate (no cost):** Optimize current 7B usage with gateway routing
2. **Short-term:** Consider M3 Max MacBook Pro for portable 32B capability
3. **Medium-term:** Mac Studio or multi-GPU Linux for 70B access
4. **Long-term:** Homelab server for team/24-7 availability

Would you like me to detail the Claude-Dash modifications needed for any specific tier?
