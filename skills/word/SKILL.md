---
name: word
description: Use for creating Word documents, polished analyst reports, investment briefs, memos, and structured DOCX files.
---

# Word Document Skill

Use `create_analyst_word_report` when a user asks for a polished report, investment brief, market note, executive analysis, research memo, or document that should look presentation-ready.

Use `create_word_doc` for simple documents where basic headings and paragraphs are enough.

## Analyst Report Style

The visual target is a clean English analyst brief:

- compact title block with a left blue accent rule
- large company/report title and ticker or short label
- right-aligned headline price/status/date when relevant
- four-metric strip under the header
- strong section headings
- concise paragraphs with blue emphasis reserved for key figures
- callout boxes for thesis or decision notes
- clean comparison and financial tables
- two-column risk cards
- small disclaimer/footer

Keep all visible document text in English unless the user explicitly asks for another language.

## Analyst Report Schema

`report_json` must be a JSON object:

```json
{
  "kicker": "Q1 2026 Earnings Review",
  "title": "Tesla",
  "ticker": "TSLA",
  "subtitle": "Automobiles & Energy · NASDAQ · Margin recovery, but capex is the story",
  "price": "$373.72",
  "price_note": "Post-earnings -3.56%",
  "date": "2026-04-23 close",
  "metrics": [
    {"value": "$1.2T", "label": "Market Cap"},
    {"value": "~220x", "label": "Forward P/E"},
    {"value": "$22.4B", "label": "Q1 Revenue"},
    {"value": "21.1%", "label": "Gross Margin"}
  ],
  "thesis_title": "Investment Thesis",
  "thesis_paragraphs": [
    "Tesla delivered stronger margin recovery than expected, but the stock reaction suggests investors are focused on the capex and free-cash-flow path."
  ],
  "callout": "Hold. Margin recovery supports the base case, but AI/Robotaxi optionality still needs evidence.",
  "sections": [
    {
      "heading": "Segment Performance",
      "subsections": [
        {
          "heading": "Automotive",
          "paragraphs": ["Deliveries remained below market expectations, while production exceeded deliveries and inventory built."]
        }
      ]
    }
  ],
  "tables": [
    {
      "title": "Financial Overview",
      "columns": ["Metric", "FY2024", "FY2025", "Q1 2026"],
      "rows": [
        {"Metric": "Revenue", "FY2024": "$97.7B", "FY2025": "$97.0B", "Q1 2026": "$22.39B"}
      ]
    }
  ],
  "risk_cards": [
    {"title": "Capex", "body": "$25B+ capex guidance pressures near-term free cash flow."}
  ],
  "conclusion": "The quarter supports the margin recovery story, but valuation still depends on autonomy execution.",
  "disclaimer": "For informational use only. Not investment advice.",
  "footer": "Code Assist · 2026-04-24"
}
```

The tool writes the `.docx` under sandbox outputs and returns the downloadable path.

## Basic Document Schema

The `sections_json` argument must be a JSON list:

```json
[
  {
    "heading": "Executive Summary",
    "paragraphs": ["Paragraph one.", "Paragraph two."]
  }
]
```
