"""Slack notification via Incoming Webhook."""

from __future__ import annotations

import json
import logging
import re
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)

MAX_TEXT_LENGTH = 30000
# Slack section block text limit is 3000 chars
BLOCK_TEXT_LIMIT = 2900


def _md_to_slack(text: str) -> str:
    """Convert Markdown to Slack mrkdwn format."""
    # Convert Markdown links [text](url) → <url|text>
    text = re.sub(r"\[([^\]]+)\]\((https?://[^\s)]+)\)", r"<\2|\1>", text)

    # Convert **bold** → *bold* (Slack bold)
    text = re.sub(r"\*\*(.+?)\*\*", r"*\1*", text)

    # Convert ### heading → *heading* (bold)
    text = re.sub(r"^###\s+(.+)$", r"*\1*", text, flags=re.MULTILINE)

    # Convert Markdown bullets to Slack-friendly bullets
    text = re.sub(r"^\*\s+", "• ", text, flags=re.MULTILINE)
    text = re.sub(r"^-\s+", "• ", text, flags=re.MULTILINE)

    return text


def _split_topics(section_body: str) -> list[str]:
    """Split a section body into individual topics.

    Topics are separated by double newlines. Each topic typically
    ends with a 📎 link line.
    """
    # Split on double newlines (paragraph breaks)
    paragraphs = re.split(r"\n{2,}", section_body.strip())

    # Merge paragraphs that don't end with a link into the next one
    # (a topic = text paragraphs + 📎 link at the end)
    topics: list[str] = []
    current: list[str] = []
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        current.append(para)
        # If this paragraph contains a 📎 link, it's the end of a topic
        if "📎" in para:
            topics.append("\n\n".join(current))
            current = []

    # Any remaining paragraphs without a 📎 link
    if current:
        topics.append("\n\n".join(current))

    return topics


def _build_blocks(title: str, body: str) -> list[dict]:
    """Build Slack blocks from a title and Markdown body.

    Splits on ## headings so each section gets its own header block.
    Within each section, individual topics get their own blocks
    separated visually.
    """
    blocks: list[dict] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": title[:150], "emoji": True},
        },
    ]

    # Split body by ## headings
    parts = re.split(r"^(## .+)$", body, flags=re.MULTILINE)

    i = 0
    while i < len(parts):
        part = parts[i]

        if part.startswith("## "):
            heading = part.lstrip("# ").strip()
            section_body = parts[i + 1] if i + 1 < len(parts) else ""
            i += 2

            # Section header with divider
            blocks.append({"type": "divider"})
            blocks.append({
                "type": "header",
                "text": {"type": "plain_text", "text": heading[:150], "emoji": True},
            })

            # Split section into topics for better readability
            topics = _split_topics(section_body)
            for topic in topics:
                slack_text = _md_to_slack(topic)
                if slack_text:
                    for chunk in _split_text(slack_text):
                        blocks.append({
                            "type": "section",
                            "text": {"type": "mrkdwn", "text": chunk},
                        })
        else:
            preamble = _md_to_slack(part.strip())
            if preamble:
                for chunk in _split_text(preamble):
                    blocks.append({
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": chunk},
                    })
            i += 1

    return blocks


def _split_text(text: str) -> list[str]:
    """Split text into chunks that fit within Slack's block text limit."""
    if len(text) <= BLOCK_TEXT_LIMIT:
        return [text]

    chunks: list[str] = []
    while text:
        if len(text) <= BLOCK_TEXT_LIMIT:
            chunks.append(text)
            break
        split_at = text.rfind("\n", 0, BLOCK_TEXT_LIMIT)
        if split_at <= 0:
            split_at = BLOCK_TEXT_LIMIT
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    return chunks


def send_slack_message(
    webhook_url: str,
    title: str,
    body: str,
) -> bool:
    """Send a message to Slack via Incoming Webhook.

    Returns True on success, False on failure.
    """
    if not webhook_url:
        logger.error("No Slack webhook URL provided")
        return False

    if len(body) > MAX_TEXT_LENGTH:
        body = body[:MAX_TEXT_LENGTH] + "\n\n... (truncated)"

    blocks = _build_blocks(title, body)

    # Slack allows max 50 blocks per message
    if len(blocks) > 50:
        blocks = blocks[:49]
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": "_... (truncated)_"},
        })

    payload = {"blocks": blocks}

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            if resp.status == 200:
                logger.info("Slack notification sent: %s", title)
                return True
            logger.error("Slack API returned status %d", resp.status)
            return False
    except urllib.error.URLError as e:
        logger.error("Failed to send Slack notification: %s", e)
        return False
