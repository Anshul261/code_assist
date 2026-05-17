---
name: excel
description: Use for Excel or CSV analysis, workbook profiling, data summaries, chart generation, persistent scratch markdown, report creation, and preparing analysis outputs for PowerPoint decks.
---

# Excel Analysis Skill

Use this skill when the user asks to inspect, analyze, summarize, chart, explain, clean, compare, or report on spreadsheet data.

## Workflow

1. Locate the workbook in the assigned workspace with `ls`, `glob`, or `grep`.
2. Create or use the output structure: `scratch/`, `reports/`, `assets/`, and optionally `decks/`.
3. Run `scripts/profile_excel.py` before drawing conclusions:
   ```bash
   .venv/bin/python skills/excel/scripts/profile_excel.py "<workbook.xlsx>" --output-dir output
   ```
   Use the active output directory if it is not `output`.
4. Read the generated `scratch/*-data-profile.md` and `reports/*-analysis-report.md`.
5. Add analysis notes to a scratch markdown file before creating a final report.
6. For charts, prefer generated PNG files in `assets/`. Use visualization tools for quick ad-hoc charts that should also be available by URL.
7. If the user wants a deck, finish the report first, then use the PPT skill with the report and assets.

## Output Standards

- `scratch/*-data-profile.md`: workbook structure, sheets, columns, preview rows, chart inventory.
- `scratch/*-analysis-notes.md`: assumptions, checks, user instructions, analysis decisions.
- `reports/*-analysis-report.md`: final user-facing narrative with findings and chart references.
- `assets/*.png`: charts that can be embedded in reports and PPTs.

## Analysis Rules

- Do not infer business meaning from column names alone when the data is ambiguous; state the assumption in scratch notes.
- Check row counts, missing values, datatypes, and obvious outliers before summarizing.
- Prefer simple, explainable metrics over complex transformations unless the user asks for deeper analysis.
- Keep charts purposeful: distribution for numeric columns, top-values bar charts for categories, trends when a date and numeric metric exist.
- For large workbooks, profile first and then target the most relevant sheets/columns instead of trying to inspect everything manually.

## Hand-off To PPT

When a presentation is requested:

1. Ensure the report exists in `reports/`.
2. Ensure useful chart PNGs exist in `assets/`.
3. Create a slide outline in `scratch/*-slide-outline.md` or a JSON spec in `scratch/*-deck-spec.json`.
4. Use the PPT skill to build `decks/*.pptx`.
