# Qwen3-VL Vision Model Setup

You've successfully installed **qwen3-vl:8b** - a vision language model for analyzing screenshots and UI designs!

## Quick Status

```bash
mlx models status
mlx models list
```

Your setup:
- **Text tasks**: qwen2.5:7b (4.7GB)
- **Visual tasks**: qwen3-vl:8b (6.1GB)
- **Embeddings**: nomic-embed-text (274MB)

## What qwen3-vl:8b Can Do

✅ **Analyze app screenshots** - UI/UX review, layout analysis
✅ **Accessibility audits** - WCAG compliance, contrast checking
✅ **Design assessment** - Visual design quality, consistency
✅ **Component identification** - Recognize UI elements and patterns
✅ **OCR capabilities** - Read text in images
✅ **Multi-modal reasoning** - Combine visual and text understanding

## Performance on M2 16GB

- **Model size**: 6.1GB
- **RAM usage**: ~6-7GB while running
- **Speed**: ~20-30 tokens/sec with images
- **Quality**: ⭐⭐⭐⭐ Excellent for UI analysis
- **Verdict**: ✅ Works great on M2 16GB

## Usage

### Basic UI Analysis

```bash
# Comprehensive UI/UX review
mlx ui path/to/screenshot.png

# Accessibility audit
mlx ui screenshot.png --mode accessibility

# Design quality assessment
mlx ui screenshot.png --mode design
```

### With Project Context

```bash
# Include project preferences and guidelines
mlx ui screenshot.png --project gyst

# Accessibility check for specific project
mlx ui screenshot.png --mode accessibility --project gyst
```

### Save Analysis to File

```bash
# Save review to markdown file
mlx ui screenshot.png --output review.md

# Save accessibility audit
mlx ui screenshot.png --mode accessibility --output accessibility-report.md
```

## Analysis Modes

### 1. Review Mode (Default)

**What it checks:**
- Layout & spacing
- Visual hierarchy
- Typography
- Color & contrast
- Navigation clarity
- Interactive elements
- UI consistency
- Mobile responsiveness

**Output format:**
```markdown
## ✅ Strengths
(What's working well)

## ⚠️ Issues Found
(HIGH/MEDIUM/LOW severity)

## 💡 Recommendations
(Actionable suggestions)
```

**Example:**
```bash
mlx ui app-home-screen.png
```

### 2. Accessibility Mode

**What it checks:**
- Color contrast (WCAG 2.1 AA)
- Text size (minimum 16px)
- Touch targets (minimum 44x44pt)
- Visual indicators
- Reading order
- Form labels
- Focus states
- Alternative text

**Output format:**
```markdown
## ✅ Accessibility Strengths

## 🚨 Critical Issues (WCAG Violations)

## ⚠️ Potential Issues

## 💡 Accessibility Recommendations

Overall accessibility: [Excellent/Good/Fair/Poor/Critical]
```

**Example:**
```bash
mlx ui login-screen.png --mode accessibility
```

### 3. Design Mode

**What it checks:**
- Visual design quality
- Brand consistency
- White space usage
- Typography scale
- Component design
- Layout grid
- Visual weight
- Design trends

**Output format:**
```markdown
## 🎨 Design Strengths

## 🔍 Design Issues

## ✨ Design Suggestions

## 📊 Design Quality Score: [Score/10]
```

**Example:**
```bash
mlx ui product-page.png --mode design
```

## Real-World Examples

### Review App Home Screen

```bash
# Take screenshot of your app
# Save as home-screen.png

mlx ui home-screen.png --project gyst --output reports/home-screen-review.md
```

### Accessibility Audit Before Release

```bash
# Audit all key screens
mlx ui login.png --mode accessibility > reports/login-a11y.md
mlx ui signup.png --mode accessibility > reports/signup-a11y.md
mlx ui dashboard.png --mode accessibility > reports/dashboard-a11y.md
mlx ui profile.png --mode accessibility > reports/profile-a11y.md
```

### Design Quality Check

```bash
# Get design feedback
mlx ui new-feature.png --mode design --project gyst
```

### Batch Analysis

```bash
# Analyze all screenshots in a folder
for img in screenshots/*.png; do
  mlx ui "$img" --output "reports/$(basename $img .png)-review.md"
done
```

## Project Context Integration

If you add design preferences to your project, they'll be included in analysis:

```json
// ~/.claude-dash/projects/gyst/preferences.json
{
  "design": [
    "Use rounded corners (8px radius)",
    "Primary color: #007AFF",
    "Maintain 16px minimum spacing",
    "Use SF Pro font family"
  ],
  "avoid": [
    "Don't use pure black (#000000)",
    "Avoid center-aligned body text",
    "No all-caps for long text"
  ],
  "conventions": [
    "Buttons should be 44pt minimum height",
    "Use system icons where possible",
    "Maintain consistent card elevation"
  ]
}
```

Then:
```bash
mlx ui screenshot.png --project gyst
```

Will analyze against your project's specific guidelines!

## Tips for Best Results

### 1. High-Quality Screenshots
- Use original screenshots (not photos of screens)
- Full resolution (no compression)
- PNG or JPG format
- Capture complete screens (not partial crops)

### 2. Specific Analysis
- Use `--mode accessibility` for WCAG compliance
- Use `--mode design` for visual feedback
- Default `review` mode for comprehensive analysis

### 3. Iterative Improvement
```bash
# Before changes
mlx ui before.png --output before-analysis.md

# After changes
mlx ui after.png --output after-analysis.md

# Compare improvements
diff before-analysis.md after-analysis.md
```

### 4. Team Reviews
```bash
# Generate report for team review
mlx ui new-feature.png --project gyst > review.md

# Share review.md with team
```

## Common Use Cases

### Pre-Release Checklist

```bash
# 1. UI/UX review
mlx ui app-screens/*.png

# 2. Accessibility audit
mlx ui app-screens/*.png --mode accessibility

# 3. Design consistency check
mlx ui app-screens/*.png --mode design --project <project-id>
```

### Design Iterations

```bash
# Review design mockups before coding
mlx ui figma-export/*.png --mode design

# Check for accessibility early
mlx ui figma-export/*.png --mode accessibility
```

### Bug Reports

```bash
# Analyze problematic screens
mlx ui bug-screenshot.png > bug-analysis.md

# Include in bug report
```

## Performance Notes

**First run with images:**
- Model loads into RAM (~6-7GB)
- First analysis: ~30-45 seconds
- Subsequent analyses: ~10-20 seconds (model cached)

**Model auto-unloads** after ~5 minutes of inactivity to free RAM.

**Optimal workflow:**
```bash
# Batch multiple screenshots together
mlx ui screen1.png > analysis1.md
mlx ui screen2.png > analysis2.md  # Faster - model still loaded
mlx ui screen3.png > analysis3.md  # Faster - model still loaded
```

## Troubleshooting

### Model Not Found
```bash
# Verify installation
ollama list | grep qwen3-vl

# Should show: qwen3-vl:8b
```

### Slow Performance
```bash
# Check available RAM
mlx hardware

# Close other applications to free RAM
# qwen3-vl needs ~7GB while running
```

### Image Encoding Errors
```bash
# Verify image exists and is readable
file screenshot.png

# Should show: PNG image data or JPEG image data
```

### Wrong Model Used
```bash
# Check routing
mlx models list | grep ui_analysis

# Should show: ui_analysis → qwen3-vl:8b
```

## Next Steps

1. **Take screenshots of your app** - Home, login, key features
2. **Run comprehensive reviews** - `mlx ui <screenshot>`
3. **Check accessibility** - `mlx ui <screenshot> --mode accessibility`
4. **Add project preferences** - Customize analysis for your design system
5. **Integrate into workflow** - Pre-release checks, design iterations

## Advanced: Python API

```python
from ui_analyzer import analyze_ui

# Programmatic analysis
result = analyze_ui(
    image_path='screenshot.png',
    mode='accessibility',
    project_id='gyst'
)

print(result)
```

## Model Comparison

| Model | Size | Use Case | Speed | Quality |
|-------|------|----------|-------|---------|
| qwen3-vl:8b | 6.1GB | UI analysis, screenshots | ⚡⚡ Good | ⭐⭐⭐⭐ Excellent |
| llava:7b | 4.7GB | General vision tasks | ⚡⚡⚡ Fast | ⭐⭐⭐ Very good |
| llava:13b | 8GB | Higher quality (tight on 16GB) | ⚡ Slow | ⭐⭐⭐⭐⭐ Excellent |

qwen3-vl:8b is optimized for UI/text understanding - perfect for your use case!

## Resources

- Model info: https://ollama.com/library/qwen3-vl:8b
- Check status: `mlx models status`
- Hardware check: `mlx hardware`
- Task routing: `mlx models list`

Happy analyzing! 🎨📱
