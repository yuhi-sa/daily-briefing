"""Slack notification via Incoming Webhook."""

from __future__ import annotations

import json
import logging
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)

# Slack message limit is ~40,000 chars, but for readability keep it reasonable.
MAX_TEXT_LENGTH = 30000


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

    # Truncate if too long
    if len(body) > MAX_TEXT_LENGTH:
        body = body[:MAX_TEXT_LENGTH] + "\n\n... (truncated)"

    payload = {
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": title[:150]},
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": body},
            },
        ],
    }

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
