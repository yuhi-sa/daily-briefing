"""Daily News Digest - Main entry point."""

from __future__ import annotations

import argparse
import json
import logging
import os
import pathlib
import sys
from datetime import datetime, timezone

from .dedup import Deduplicator, normalize_url
from .feeds import load_config
from .formatter import format_digest
from .parser import Article, fetch_all_articles, fetch_articles
from .slack_notifier import send_slack_message
from .summarizer import generate_briefing, get_summarizer

logger = logging.getLogger(__name__)

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
WEEKLY_BUFFER = PROJECT_ROOT / "data" / "weekly_articles.json"


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _article_to_dict(a: Article) -> dict:
    return {
        "id": a.id,
        "title": a.title,
        "link": a.link,
        "summary": a.summary,
        "published": a.published.isoformat(),
        "source_name": a.source_name,
        "category": a.category,
        "category_ja": a.category_ja,
    }


def _dict_to_article(d: dict) -> Article:
    return Article(
        id=d["id"],
        title=d["title"],
        link=d["link"],
        summary=d["summary"],
        published=datetime.fromisoformat(d["published"]),
        source_name=d["source_name"],
        category=d["category"],
        category_ja=d["category_ja"],
    )


def _load_weekly_buffer() -> list[dict]:
    if not WEEKLY_BUFFER.exists():
        return []
    try:
        with open(WEEKLY_BUFFER, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        logger.warning("Corrupted weekly buffer, starting fresh")
        return []


def _save_weekly_buffer(articles: list[dict]) -> None:
    WEEKLY_BUFFER.parent.mkdir(parents=True, exist_ok=True)
    with open(WEEKLY_BUFFER, "w", encoding="utf-8") as f:
        json.dump(articles, f, indent=2, ensure_ascii=False)


def run_collect(verbose: bool = False) -> None:
    """Daily collection: fetch, dedup, summarize, save to daily digest and weekly buffer."""
    setup_logging(verbose)
    logger.info("Starting daily article collection")

    # 1. Load config
    config = load_config()
    logger.info("Loaded %d feeds from config", len(config.feeds))

    # 2. Fetch articles (parallel, with freshness filter)
    all_articles, feed_stats = fetch_all_articles(
        config.feeds, max_articles=config.max_articles_per_feed,
        max_age_hours=48,
    )

    logger.info("Fetched %d total articles from %d feeds", len(all_articles), len(config.feeds))

    if not all_articles:
        logger.error("All feeds failed, no articles fetched")
        sys.exit(1)

    # 3. Deduplicate
    dedup = Deduplicator()
    dedup.prune(window_days=config.dedup_window_days)
    new_articles = dedup.filter_new(all_articles)

    if not new_articles:
        logger.info("No new articles after dedup")
        dedup.save()
        return

    # 4. Keep RSS descriptions as-is (no API calls during collect).
    #    API budget is reserved for the briefing stage where it matters most.
    summarized = new_articles

    # 5. Save daily digest file
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    digest_content = format_digest(summarized, date=now, feed_stats=feed_stats)

    digest_path = PROJECT_ROOT / "digests" / f"{date_str}.md"
    digest_path.parent.mkdir(parents=True, exist_ok=True)
    digest_path.write_text(digest_content, encoding="utf-8")
    logger.info("Digest written to %s", digest_path)

    # 6. Append to weekly buffer (with URL dedup to prevent duplicates)
    buffer = _load_weekly_buffer()
    existing_urls = {normalize_url(d.get("link", "")) for d in buffer}
    added = 0
    for a in summarized:
        norm = normalize_url(a.link)
        if norm not in existing_urls:
            buffer.append(_article_to_dict(a))
            existing_urls.add(norm)
            added += 1
    _save_weekly_buffer(buffer)
    logger.info("Weekly buffer: added %d new, %d total", added, len(buffer))

    # 7. Save dedup DB
    dedup.save()

    logger.info("Daily collection complete: %d new articles saved", len(summarized))


def run_digest(dry_run: bool = False, verbose: bool = False) -> None:
    """Daily digest: generate briefing from accumulated articles, send to Slack."""
    setup_logging(verbose)
    logger.info("Starting daily digest")

    # 1. Load article buffer
    buffer = _load_weekly_buffer()
    if not buffer:
        logger.info("No articles in buffer, skipping")
        return

    articles = [_dict_to_article(d) for d in buffer]
    logger.info("Loaded %d articles from buffer", len(articles))

    # 1.5. Deduplicate buffer (remove URL duplicates accumulated across days)
    seen_urls: set[str] = set()
    unique_articles: list[Article] = []
    for a in articles:
        norm = normalize_url(a.link)
        if norm not in seen_urls:
            seen_urls.add(norm)
            unique_articles.append(a)
    if len(unique_articles) < len(articles):
        logger.info(
            "Buffer dedup: %d → %d articles (removed %d URL duplicates)",
            len(articles), len(unique_articles), len(articles) - len(unique_articles),
        )
    articles = unique_articles

    # 2. Generate briefing
    api_key = os.environ.get("SUMMARIZER_API_KEY")
    briefing = generate_briefing(articles, api_key)
    if briefing:
        logger.info("Daily briefing generated (%d chars)", len(briefing))
    else:
        logger.info("No briefing generated (no API key or failure)")

    # 3. Date label
    now = datetime.now(timezone.utc)
    date_label = now.strftime("%Y-%m-%d")

    # 4. Write briefing file (this is the new content for the PR branch)
    briefing_path = PROJECT_ROOT / "digests" / f"briefing-{date_label}.md"
    briefing_path.write_text(briefing or "(No briefing generated)", encoding="utf-8")
    logger.info("Briefing file written to %s", briefing_path)

    if dry_run:
        logger.info("Dry run mode - skipping Slack notification")
        print(f"\n{'='*60}")
        print(f"DAILY BRIEFING ({date_label})")
        print(f"{'='*60}\n")
        print(briefing or "(no briefing)")
        return

    # 5. Send Slack notification
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL", "")
    title = f"Daily Digest: {date_label}"
    success = send_slack_message(
        webhook_url=webhook_url,
        title=title,
        body=briefing or "(No briefing generated)",
    )

    if success:
        # 6. Clear buffer
        _save_weekly_buffer([])
        logger.info("Article buffer cleared")
        logger.info("Daily digest sent to Slack")
    else:
        logger.warning("Slack notification failed")


def main() -> None:
    parser = argparse.ArgumentParser(description="Daily News Digest Generator")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # collect subcommand
    collect_parser = subparsers.add_parser("collect", help="Daily article collection")
    collect_parser.add_argument("--verbose", "-v", action="store_true")

    # digest subcommand
    digest_parser = subparsers.add_parser("digest", help="Send daily digest to Slack")
    digest_parser.add_argument("--dry-run", action="store_true")
    digest_parser.add_argument("--verbose", "-v", action="store_true")

    args = parser.parse_args()

    if args.command == "collect":
        run_collect(verbose=args.verbose)
    elif args.command == "digest":
        run_digest(dry_run=args.dry_run, verbose=args.verbose)


if __name__ == "__main__":
    main()
