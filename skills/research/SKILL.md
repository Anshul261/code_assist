---
name: research
description: Use for online research with DuckDuckGo discovery, URL fetching, source notes, cited markdown reports, and research-to-document workflows.
---

# Research Skill

Use this workflow for research requests:

1. Call `think` with a concise public plan. Do not include private chain-of-thought.
2. Search with `duckduckgo_search` using 2-4 distinct queries.
3. Fetch the most relevant URLs with `fetch_url`; prefer primary sources, official docs, papers, company pages, or reputable publications.
4. Call `analyze` after the first source pass to record whether evidence is sufficient or another search round is needed.
5. If evidence is thin, run another targeted search/fetch pass.
6. Write a concise report with `write_markdown`, including source URLs.
7. If requested, convert the report into Word or PowerPoint.

Prefer direct source URLs over summaries from search snippets.

For substantial research, do not stop after one search result. Use the activity tools to show progress and continue until the answer has enough sourced evidence.
