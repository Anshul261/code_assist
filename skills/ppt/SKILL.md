---
name: ppt
description: Use for creating warm editorial PowerPoint presentations, keynote-style decks, slide outlines, PPTX files, executive decks, report-to-deck conversion, and research-to-deck conversion.
---

# PowerPoint Skill

Use `run_ppt_skill` when a user asks for a presentation from notes, research, or a report and markdown is enough.

Use `create_powerpoint` when the deck needs richer control over slide type, subtitle, stats, diagram, chart, code block, quote, or footer text.

## Visual Style

The default PPT style should match a warm editorial keynote:

- off-white / warm paper background
- large serif titles, usually left-aligned
- muted gray body text
- deep navy accents for key terms, rules, numbers, and charts
- generous whitespace
- small uppercase monospace section labels such as `01 · AGENT LOOP`
- small footer label at bottom-left and slide number at bottom-right
- minimal diagrams using rings, thin lines, rounded rectangles, and sparse labels
- no heavy gradients, decorative blobs, dense cards, or default PowerPoint theme look
- keep each slide focused on one idea

## Rich JSON Schema

`slides_json` is a JSON list. Useful fields:

```json
[
  {
    "cover_kicker": "KEYNOTE · 2026",
    "subtitle": "Loops, harness, context, memory: what actually matters in production.",
    "meta": "code assist demo · A4 landscape · 7 slides",
    "deck_label": "AGENT ENGINEERING"
  },
  {
    "section": "01 · AGENT LOOP",
    "title": "Simple core, complex surroundings",
    "subtitle": "The loop is small. The infrastructure around it is what keeps it stable.",
    "bullets": [
      "A working Agent loop fits in about 20 lines of code.",
      "Control flow lives in the tools, not in branchy internal state."
    ],
    "quote": "If your loop keeps growing every sprint, you are fixing the wrong layer.",
    "diagram": {"type": "loop", "labels": ["PLAN", "ACT", "OBSERVE", "REFLECT"]}
  },
  {
    "section": "02 · HARNESS",
    "title": "Harness wins over hardware",
    "subtitle": "Verification, boundaries, feedback, and fallbacks matter more than model capability.",
    "bullets": ["Upgrade the harness first.", "Evaluation is the only honest signal."],
    "stats": [
      {"value": "20", "label": "lines of code in a working Agent core loop"},
      {"value": "4", "label": "harness layers that matter"},
      {"value": "10×", "label": "velocity gains trace to execution discipline"}
    ]
  },
  {
    "section": "03 · CONTEXT",
    "title": "Density beats length",
    "subtitle": "Long context windows do not fix weak context design.",
    "bullets": ["Layer the load.", "Index first, full content on demand."],
    "chart": {
      "title": "Loading strategy vs accuracy",
      "labels": ["Flat loading", "Layered loading"],
      "values": [53, 85],
      "target": 85
    }
  },
  {
    "section": "05 · CODE STYLE",
    "title": "Pseudocode over syntax",
    "subtitle": "The reader sees logic, not a language tutorial.",
    "bullets": ["Write the intent first.", "One concept per block."],
    "code": "# resolve tool call or decide to stop\nfunction agent_step(context, tools):\n    action = model.think(context)\n    if action.type == \"stop\":\n        return action.result"
  },
  {
    "section": "END OF DECK",
    "title": "Protocol first.\nThen parallelism.",
    "subtitle": "Fix your evals before you tweak the Agent.",
    "quote": "Protocol first.\nThen parallelism."
  }
]
```

## Outline Format

```markdown
# Deck Title

## First Slide
- Short point
- Short point

## Second Slide
- Short point
```

The tool stores the markdown outline in sandbox scratch space and writes the `.pptx` under sandbox outputs.
