# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Automated news aggregation system that fetches articles from 30+ RSS feeds, deduplicates them, summarizes in Japanese via Google Gemini API, and sends daily digests to Slack. Written in Python 3.12+, runs on GitHub Actions.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Collect articles (fetch → dedup → summarize → save)
python -m src.main collect --verbose

# Generate briefing and send to Slack (use --dry-run for local testing)
python -m src.main digest --dry-run
python -m src.main digest --verbose

# Generate paper digest and send to Slack (use --dry-run for local testing)
python -m src.main paper --dry-run
python -m src.main paper --verbose

# Run all tests
pytest tests/ -v

# Run a single test file
pytest tests/test_dedup.py -v
```

## Environment Variables

- `SUMMARIZER_API_KEY` — Google Gemini API key. Without it, the PassthroughSummarizer is used (no LLM summarization).
- `SLACK_WEBHOOK_URL` — Slack Incoming Webhook URL for sending digest notifications.

## Architecture

```
RSS Feeds → Parser → Dedup → Summarizer → Formatter → Slack
Semantic Scholar → Paper Fetcher → Paper Dedup → Paper Summarizer → Paper Formatter → Slack
```

**Two-stage daily pipeline** via GitHub Actions:

1. **Collect** (06:00 JST): Parallel-fetches RSS feeds → deduplicates → summarizes → writes `digests/YYYY-MM-DD.md` → appends to `data/weekly_articles.json` buffer → commits to main.
2. **Digest** (07:00 JST): Loads buffered articles → two-stage Gemini analysis (select top articles, then fetch full text for deeper briefing) → sends briefing to Slack → clears buffer.
3. **Paper** (07:30 JST): Selects a classic CS paper from 4 rotating categories (distributed systems, security, AI, cloud) via Semantic Scholar API → Gemini structured summary → sends to Slack.

### Key modules (`src/`)

- **main.py** — Entry point with `collect`, `digest`, and `paper` subcommands
- **parser.py** — RSS fetching with ThreadPoolExecutor (8 workers), Article dataclass
- **dedup.py** — URL normalization (strips tracking params) + title similarity (difflib, 0.9 threshold), persists to `data/seen_articles.json`
- **summarizer.py** — Pluggable via ABC: `PassthroughSummarizer` and `GeminiSummarizer`. Batch summarization (size 5) with fallback. Two-stage briefing generation with page text fetching.
- **formatter.py** — Markdown output grouped by category with bilingual headers
- **slack_notifier.py** — Slack notification via Incoming Webhook
- **paper_fetcher.py** — Semantic Scholar API client, Paper dataclass, 4-category rotation (day_of_year % 4)
- **paper_dedup.py** — Tracks featured papers in `data/seen_papers.json` (90-day window)
- **paper_summarizer.py** — Structured paper summary via Gemini (background, method, contributions, impact)
- **paper_formatter.py** — Markdown PR body with metadata table and summary
- **feeds.py** — Loads `config/feeds.yml`

### Data files

- `config/feeds.yml` — Feed sources and settings (add/remove feeds here)
- `data/seen_articles.json` — Dedup database (URL → metadata, 7-day window)
- `data/seen_papers.json` — Paper dedup database (paperId → metadata, 90-day window)
- `data/weekly_articles.json` — Article buffer for briefing generation
- `digests/` — Generated daily digests, briefings, and paper digest files

## Key Design Patterns

- **Pluggable summarizer**: Abstract base class allows swapping between Passthrough (no API key) and Gemini strategies via `get_summarizer()`
- **All output is Japanese**: Summaries, briefings, and category labels are in Japanese
- **Resilient fetching**: Individual feed/article failures don't crash the pipeline; errors are logged and skipped
