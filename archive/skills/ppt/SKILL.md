---
name: ppt
description: Use for creating PowerPoint presentations, slide outlines, PPTX files, executive decks, report-to-deck conversion, and embedding chart/image assets into slides with PPTXGenJS.
---

# PowerPoint Skill

Use this skill when the user asks for a PPT, PowerPoint, presentation, slide deck, executive deck, board deck, training deck, or when a report should be converted into slides.

## Workflow

1. Confirm the source material: report markdown, scratch notes, document summary, Excel analysis, research notes, and chart/image assets.
2. Create `scratch/*-slide-outline.md` before generating a deck. Each `##` heading becomes a slide when using the script.
3. Keep slide content concise. A slide should normally have one message, one supporting visual or 3-5 bullets.
4. Use existing PNG assets from `assets/`. If charts are only in the visualization DB, save them to `assets/` before deck creation.
5. Generate the PPTX with:
   ```bash
   node skills/ppt/scripts/create_pptx.js --spec output/scratch/slide-outline.md --output output/decks/presentation.pptx
   ```
   Use the active output directory if it is not `output`.
6. Verify the command returns `status: success`, the `.pptx` exists, and the slide count is plausible.

## Slide Outline Format

The script accepts markdown or JSON. Markdown is usually enough:

```markdown
# Deck Title

## Executive Summary
- Point one
- Point two
- Point three

## Trend Analysis
- Key takeaway
- Implication
![Revenue Trend](../assets/revenue-trend.png)
```

Image paths are resolved relative to the markdown file. Put reusable images in `assets/`.

## JSON Spec Format

Use JSON when exact control is needed:

```json
{
  "title": "Deck Title",
  "subtitle": "Optional subtitle",
  "slides": [
    {
      "title": "Executive Summary",
      "bullets": ["Point one", "Point two"],
      "images": [{"path": "/absolute/path/to/chart.png"}]
    }
  ]
}
```

## Quality Rules

- Do not make the title a generic phrase if a specific business topic exists.
- Do not paste dense report paragraphs into slides; convert them into tight bullets.
- Prefer charts/images for data-heavy slides.
- Keep citations, source URLs, and detailed methodology in report markdown unless the user asks to include them in the deck.
- Always report the final `.pptx` path and any source files used.
