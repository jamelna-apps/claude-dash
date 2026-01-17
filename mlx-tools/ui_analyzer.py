#!/usr/bin/env python3
"""
UI Analyzer - Vision-powered screenshot analysis using qwen3-vl

Analyze app screenshots for:
- UI/UX issues
- Accessibility problems
- Design inconsistencies
- Layout problems
- Best practices violations

Usage:
  python ui_analyzer.py <image_path> [--mode <review|accessibility|design>]
  python ui_analyzer.py screenshot.png
  python ui_analyzer.py screenshot.png --mode accessibility
  python ui_analyzer.py screenshot.png --mode design --project gyst
"""

import sys
import json
import base64
import argparse
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))
from ollama_client import OllamaClient
from config import MEMORY_ROOT


def encode_image(image_path: str) -> str:
    """Encode image to base64"""
    with open(image_path, 'rb') as f:
        return base64.b64encode(f.read()).decode('utf-8')


def get_project_context(project_id: Optional[str]) -> str:
    """Get project preferences and design guidelines"""
    if not project_id:
        return ""

    prefs_path = MEMORY_ROOT / 'projects' / project_id / 'preferences.json'
    if not prefs_path.exists():
        return ""

    try:
        prefs = json.loads(prefs_path.read_text())
        context_parts = []

        # Design preferences
        if 'design' in prefs:
            context_parts.append("Design Guidelines:")
            for guideline in prefs['design']:
                context_parts.append(f"  - {guideline}")

        # Avoid patterns
        if 'avoid' in prefs:
            context_parts.append("\nAvoid:")
            for pattern in prefs['avoid']:
                context_parts.append(f"  - {pattern}")

        # Conventions
        if 'conventions' in prefs:
            context_parts.append("\nConventions:")
            for conv in prefs['conventions']:
                context_parts.append(f"  - {conv}")

        return "\n".join(context_parts) if context_parts else ""
    except:
        return ""


def analyze_ui(image_path: str, mode: str = 'review', project_id: Optional[str] = None) -> str:
    """
    Analyze UI screenshot using vision model

    Args:
        image_path: Path to screenshot
        mode: Analysis mode (review, accessibility, design)
        project_id: Optional project ID for context
    """
    # Initialize VLM client
    client = OllamaClient(task='ui_analysis')

    # Get project context
    project_context = get_project_context(project_id)

    # Encode image
    print(f"🔍 Analyzing screenshot: {Path(image_path).name}")
    print(f"📋 Mode: {mode}")
    print(f"🤖 Model: {client.model}")
    print(f"🖼️  Encoding image...")

    try:
        image_b64 = encode_image(image_path)
    except Exception as e:
        return f"Error encoding image: {e}"

    # Build prompt based on mode
    prompts = {
        'review': """Analyze this app screenshot and provide a comprehensive UI/UX review.

Focus on:
1. **Layout & Spacing** - Are elements properly aligned and spaced?
2. **Visual Hierarchy** - Is the content hierarchy clear?
3. **Typography** - Are fonts readable, sized appropriately?
4. **Color & Contrast** - Are colors harmonious, is contrast sufficient?
5. **Navigation** - Is navigation clear and intuitive?
6. **Interactive Elements** - Are buttons/links clearly identifiable?
7. **Consistency** - Are UI patterns consistent throughout?
8. **Mobile Responsiveness** - Does the layout work well on this screen size?

{project_context}

Format your response as:
## ✅ Strengths
(What's working well)

## ⚠️ Issues Found
(Problems with severity: HIGH/MEDIUM/LOW)

## 💡 Recommendations
(Specific, actionable suggestions)

If no major issues found, say "Overall good UI design!" and mention minor improvements.""",

        'accessibility': """Analyze this app screenshot for accessibility issues.

Check for:
1. **Color Contrast** - Sufficient contrast for text readability (WCAG 2.1 AA minimum 4.5:1)
2. **Text Size** - Readable font sizes (minimum 16px for body text)
3. **Touch Targets** - Large enough tap areas (minimum 44x44pt on mobile)
4. **Visual Indicators** - Don't rely solely on color to convey information
5. **Reading Order** - Logical content flow for screen readers
6. **Labels** - Proper labels for form inputs and buttons
7. **Focus States** - Clear visual feedback for interactive elements
8. **Alternative Text** - Icons should have text labels or be decorative only

{project_context}

Format your response as:
## ✅ Accessibility Strengths

## 🚨 Critical Issues (WCAG Violations)

## ⚠️ Potential Issues

## 💡 Accessibility Recommendations

Rate overall accessibility: [Excellent/Good/Fair/Poor/Critical]""",

        'design': """Analyze this app screenshot from a design perspective.

Evaluate:
1. **Visual Design** - Color palette, imagery, iconography
2. **Brand Consistency** - Does it match the brand/app style?
3. **White Space** - Effective use of negative space
4. **Typography Scale** - Proper type hierarchy and sizing
5. **Component Design** - Quality of UI components (buttons, cards, inputs)
6. **Layout Grid** - Proper use of grid/column system
7. **Visual Weight** - Appropriate emphasis on important elements
8. **Design Trends** - Modern vs dated design patterns

{project_context}

Format your response as:
## 🎨 Design Strengths

## 🔍 Design Issues

## ✨ Design Suggestions

## 📊 Design Quality Score: [Score/10]

Provide specific, actionable feedback."""
    }

    prompt = prompts.get(mode, prompts['review']).format(
        project_context=f"\nProject Context:\n{project_context}\n" if project_context else ""
    )

    print(f"💭 Generating analysis...\n")

    try:
        # Call vision model with image
        response = client.generate(prompt, images=[image_b64])
        return response if response else "Analysis failed - no response from model"
    except Exception as e:
        return f"Error during analysis: {e}"


def main():
    parser = argparse.ArgumentParser(description="Analyze app screenshots using vision AI")
    parser.add_argument('image', help='Path to screenshot image')
    parser.add_argument('--mode', '-m', choices=['review', 'accessibility', 'design'],
                       default='review', help='Analysis mode (default: review)')
    parser.add_argument('--project', '-p', help='Project ID for context')
    parser.add_argument('--output', '-o', help='Save analysis to file')
    args = parser.parse_args()

    # Validate image exists
    image_path = Path(args.image)
    if not image_path.exists():
        print(f"Error: Image not found: {args.image}")
        sys.exit(1)

    # Run analysis
    result = analyze_ui(str(image_path), args.mode, args.project)

    # Output
    print(result)

    # Save to file if requested
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(result)
        print(f"\n✅ Analysis saved to: {args.output}")


if __name__ == '__main__':
    main()
