# Continue.dev Setup with Local Ollama

Continue is an open-source AI code assistant that runs in VS Code and JetBrains IDEs. It can use your local Ollama instance for a free, private coding assistant.

## Installation

1. **Install Continue extension**
   - VS Code: Search "Continue" in extensions
   - Or: `code --install-extension continue.continue`

2. **Configure for Ollama**

   Open Continue settings (`~/.continue/config.json` or via Continue sidebar → gear icon):

   ```json
   {
     "models": [
       {
         "title": "Ollama Local",
         "provider": "ollama",
         "model": "llama3.2:3b",
         "apiBase": "http://localhost:11434"
       }
     ],
     "tabAutocompleteModel": {
       "title": "Ollama Autocomplete",
       "provider": "ollama",
       "model": "llama3.2:3b",
       "apiBase": "http://localhost:11434"
     }
   }
   ```

3. **For better code completion, use a code-specific model:**

   ```bash
   # Pull a code-focused model
   docker exec ollama ollama pull codellama:7b
   # Or smaller:
   docker exec ollama ollama pull deepseek-coder:1.3b
   ```

   Then update config:
   ```json
   {
     "tabAutocompleteModel": {
       "title": "DeepSeek Coder",
       "provider": "ollama",
       "model": "deepseek-coder:1.3b"
     }
   }
   ```

## Features

- **Tab Autocomplete**: Get AI suggestions as you type
- **Chat**: Ask questions about your code in the sidebar
- **Inline Edits**: Select code and ask to modify it
- **Context**: Add files, docs, or codebase to context

## Keyboard Shortcuts

| Action | Shortcut |
|--------|----------|
| Open Chat | `Cmd+L` |
| Inline Edit | `Cmd+I` |
| Accept Autocomplete | `Tab` |
| Add to Context | `Cmd+Shift+L` |

## Recommended Models

| Model | Size | Best For |
|-------|------|----------|
| `llama3.2:3b` | 2GB | General chat, explanations |
| `codellama:7b` | 4GB | Code generation |
| `deepseek-coder:1.3b` | 1GB | Fast autocomplete |
| `codellama:13b` | 8GB | Best code quality |

## Using with Claude Memory

You can add Claude Memory context to Continue:

1. Open Continue sidebar
2. Click `+` to add context
3. Add your project's memory files:
   - `~/.claude-memory/projects/gyst/summaries.json`
   - `~/.claude-memory/projects/gyst/schema.json`

## Troubleshooting

**"Model not found"**
```bash
# Make sure Ollama is running
docker ps | grep ollama

# Pull the model
docker exec ollama ollama pull llama3.2:3b
```

**Slow responses**
- Use a smaller model for autocomplete
- Check if other apps are using GPU memory

**Connection refused**
```bash
# Check Ollama is accessible
curl http://localhost:11434/api/tags
```
