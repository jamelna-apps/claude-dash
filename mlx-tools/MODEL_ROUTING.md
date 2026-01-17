# Task-Based Model Routing

Claude-dash now supports automatic model selection based on the task being performed. This allows you to use different Ollama models optimized for specific tasks.

## How It Works

When you run any MLX tool (ask, review, rag, etc.), the system automatically selects the appropriate model based on the task type:

- **Code Review** → Uses the model configured for `code_review` task
- **RAG Queries** → Uses the model configured for `rag` task
- **Commit Messages** → Uses the model configured for `commit_message` task
- **UI Analysis** → Uses the model configured for `ui_analysis` task (VLM when available)

## Quick Start

### Check Current Status

```bash
mlx models status
```

Shows:
- Ollama connection status
- Available models
- Task configuration summary
- Missing models (if any)

### View Task-to-Model Mappings

```bash
mlx models list
```

Shows all task categories and their assigned models with availability status.

### Test a Task

```bash
mlx models test code_review
mlx models test rag
```

Tests the routing for a specific task and verifies the model is working.

## Configuration

### Current Setup

All tasks currently use: **qwen2.5:7b**

Models are configured in `~/.claude-dash/mlx-tools/config.py`:

```python
TASK_MODEL_MAP = {
    # Code analysis tasks
    'code_review': OLLAMA_CHAT_MODEL,      # qwen2.5:7b
    'code_analysis': OLLAMA_CHAT_MODEL,

    # Documentation tasks
    'commit_message': OLLAMA_CHAT_MODEL,
    'pr_description': OLLAMA_CHAT_MODEL,

    # Reasoning tasks
    'rag': OLLAMA_CHAT_MODEL,
    'ask': OLLAMA_CHAT_MODEL,

    # Visual tasks (ready for VLM)
    'ui_analysis': OLLAMA_VLM_MODEL,
    'screenshot_review': OLLAMA_VLM_MODEL,
}
```

### Change Models

To use different models for specific tasks, edit `config.py`:

```python
TASK_MODEL_MAP = {
    'code_review': 'deepseek-coder:33b',   # Use DeepSeek for code review
    'rag': 'qwen2.5:7b',                   # Keep qwen for RAG
    'ui_analysis': 'llava:13b',            # Use LLaVA for UI analysis
}
```

Or temporarily override using environment variables:

```bash
OLLAMA_MODEL="deepseek-coder:33b" mlx review file.js
```

## Adding Visual Language Model (VLM) Support

When you're ready to add UI analysis capabilities:

### 1. Install a VLM Model

```bash
# LLaVA (recommended for UI/screenshots)
ollama pull llava:13b

# Or other vision models
ollama pull llava:7b
ollama pull bakllava
```

### 2. Configure VLM in Environment

```bash
# Add to ~/.zshrc or ~/.bashrc
export OLLAMA_VLM_MODEL="llava:13b"
```

Or edit `config.py`:

```python
OLLAMA_VLM_MODEL = os.environ.get('OLLAMA_VLM_MODEL', 'llava:13b')
```

### 3. Verify Setup

```bash
mlx models list
mlx models test ui_analysis
```

### 4. Use VLM Tasks

Once configured, these tasks will automatically use the VLM:
- `ui_analysis` - Analyze UI screenshots
- `screenshot_review` - Review app screenshots for issues
- `design_assessment` - Assess UI/UX design quality
- `wireframe_analysis` - Analyze wireframe designs

## Task Categories

### Code Analysis
- `code_review` - Review code for bugs, security, performance
- `code_analysis` - Analyze code structure and patterns
- `code_explanation` - Explain what code does
- `static_analysis` - Static code analysis

### Documentation
- `documentation` - Generate documentation
- `summarization` - Summarize files/code
- `commit_message` - Generate commit messages
- `pr_description` - Generate PR descriptions

### Reasoning
- `rag` - RAG-powered Q&A
- `query` - Hybrid search queries
- `ask` - General codebase questions
- `planning` - Architecture planning
- `architecture` - Architecture decisions

### Testing
- `test_generation` - Generate unit tests
- `error_analysis` - Analyze errors and stack traces

### Visual (VLM Required)
- `ui_analysis` - Analyze UI screenshots
- `screenshot_review` - Review screenshots
- `design_assessment` - Assess UI/UX design
- `wireframe_analysis` - Analyze wireframes

## Examples

### Use Different Model for Code Review

```bash
# Temporarily use a different model
OLLAMA_MODEL="deepseek-coder:33b" mlx review src/file.js

# Or update config.py permanently
update_task_model('code_review', 'deepseek-coder:33b')
```

### Test Multiple Tasks

```bash
mlx models test code_review
mlx models test rag
mlx models test commit_message
```

### Check Available Models

```bash
mlx models available
ollama list
```

## Advanced: Per-Tool Model Override

Tools that support the `--model` flag can override the automatic routing:

```bash
# Use specific model for this ask command
mlx ask gyst "question" --model claude-dash-assistant

# Normal ask uses task routing
mlx ask gyst "question"  # Uses model from TASK_MODEL_MAP['ask']
```

## Troubleshooting

### Model Not Found

If you see "⚠️ Not found" in `mlx models list`:

```bash
# Install the missing model
ollama pull <model-name>

# Verify
mlx models available
```

### VLM Tasks Falling Back to Chat Model

If VLM tasks show the chat model instead of a VLM:

1. Check if VLM is configured: `mlx models list`
2. Set VLM: `export OLLAMA_VLM_MODEL="llava:13b"`
3. Or set in `config.py`: `OLLAMA_VLM_MODEL = 'llava:13b'`

### Test Generation Fails

```bash
# Check Ollama is running
ollama list

# Test specific task
mlx models test <task-name>

# Check logs
mlx status
```

## Next Steps for VLM Integration

When you're ready to add visual analysis:

1. **Install VLM**: `ollama pull llava:13b`
2. **Configure**: Set `OLLAMA_VLM_MODEL` environment variable
3. **Test**: `mlx models test ui_analysis`
4. **Create VLM Tool**: Add new tool in `mlx-tools/` for screenshot analysis
5. **Update MLX Script**: Add VLM commands to `mlx` script

Example VLM tool structure:

```python
# ui_analyzer.py
from ollama_client import OllamaClient

def analyze_screenshot(image_path: str) -> str:
    client = OllamaClient(task='ui_analysis')
    # VLM-specific logic here
    # Can handle images when VLM is configured
    ...
```

## Benefits

- **Specialized Models**: Use the best model for each task type
- **Easy Switching**: Change models without modifying tool code
- **Future-Ready**: VLM support ready when you need it
- **Fallback Support**: Automatically falls back to chat model if VLM not configured
- **Per-Task Control**: Fine-tune model selection per task category
