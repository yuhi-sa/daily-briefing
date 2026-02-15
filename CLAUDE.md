# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Automated news aggregation system that fetches articles from 30+ RSS feeds, deduplicates them, summarizes in Japanese via Google Gemini API, and creates daily digest PRs on GitHub. Written in Python 3.12+, runs on GitHub Actions.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Collect articles (fetch → dedup → summarize → save)
python -m src.main collect --verbose

# Generate briefing and create PR (use --dry-run for local testing)
python -m src.main digest --dry-run
python -m src.main digest --verbose

# Run all tests
pytest tests/ -v

# Run a single test file
pytest tests/test_dedup.py -v
```

## Environment Variables

- `SUMMARIZER_API_KEY` — Google Gemini API key. Without it, the PassthroughSummarizer is used (no LLM summarization).

## Architecture

```
RSS Feeds → Parser → Dedup → Summarizer → Formatter → PR
```

**Two-stage daily pipeline** via GitHub Actions:

1. **Collect** (06:00 JST): Parallel-fetches RSS feeds → deduplicates → summarizes → writes `digests/YYYY-MM-DD.md` → appends to `data/weekly_articles.json` buffer → commits to main.
2. **Digest** (07:00 JST): Loads buffered articles → two-stage Gemini analysis (select top articles, then fetch full text for deeper briefing) → creates PR with briefing as body → clears buffer.

### Key modules (`src/`)

- **main.py** — Entry point with `collect` and `digest` subcommands
- **parser.py** — RSS fetching with ThreadPoolExecutor (8 workers), Article dataclass
- **dedup.py** — URL normalization (strips tracking params) + title similarity (difflib, 0.9 threshold), persists to `data/seen_articles.json`
- **summarizer.py** — Pluggable via ABC: `PassthroughSummarizer` and `GeminiSummarizer`. Batch summarization (size 5) with fallback. Two-stage briefing generation with page text fetching.
- **formatter.py** — Markdown output grouped by category with bilingual headers
- **pr_creator.py** — Git branch + PR creation via `gh` CLI
- **feeds.py** — Loads `config/feeds.yml`

### Data files

- `config/feeds.yml` — Feed sources and settings (add/remove feeds here)
- `data/seen_articles.json` — Dedup database (URL → metadata, 7-day window)
- `data/weekly_articles.json` — Article buffer for briefing generation
- `digests/` — Generated daily digests and briefing files

## Key Design Patterns

- **Pluggable summarizer**: Abstract base class allows swapping between Passthrough (no API key) and Gemini strategies via `get_summarizer()`
- **All output is Japanese**: Summaries, briefings, and category labels are in Japanese
- **Resilient fetching**: Individual feed/article failures don't crash the pipeline; errors are logged and skipped
