"""Git operations and PR creation using gh CLI."""

from __future__ import annotations

import logging
import pathlib
import subprocess
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def _run(cmd: list[str], cwd: str | pathlib.Path | None = None) -> subprocess.CompletedProcess:
    """Run a shell command and return the result."""
    logger.debug("Running: %s", " ".join(cmd))
    return subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)


def create_pr(
    digest_path: pathlib.Path,
    seen_db_path: pathlib.Path,
    date: datetime | None = None,
    article_count: int = 0,
    feed_stats: dict[str, bool] | None = None,
    repo_root: str | pathlib.Path | None = None,
    digest_content: str = "",
) -> str | None:
    """Create a branch, commit the digest, and open a PR.

    Returns the PR URL on success, None on failure.
    """
    if date is None:
        date = datetime.now(timezone.utc)

    date_str = date.strftime("%Y-%m-%d")
    branch_name = f"digest/{date_str}"
    cwd = str(repo_root) if repo_root else None

    # Check if branch already exists on remote
    result = _run(["git", "ls-remote", "--heads", "origin", branch_name], cwd=cwd)
    if result.stdout.strip():
        logger.warning("Branch %s already exists on remote, skipping", branch_name)
        return None

    # Create and switch to new branch
    result = _run(["git", "checkout", "-b", branch_name], cwd=cwd)
    if result.returncode != 0:
        logger.error("Failed to create branch: %s", result.stderr)
        return None

    try:
        # Stage files
        _run(["git", "add", str(digest_path)], cwd=cwd)
        _run(["git", "add", str(seen_db_path)], cwd=cwd)

        # Commit
        commit_msg = f"Add daily digest for {date_str}"
        result = _run(["git", "commit", "-m", commit_msg], cwd=cwd)
        if result.returncode != 0:
            logger.error("Failed to commit: %s", result.stderr)
            return None

        # Push
        result = _run(["git", "push", "-u", "origin", branch_name], cwd=cwd)
        if result.returncode != 0:
            logger.error("Failed to push: %s", result.stderr)
            return None

        # Build PR body
        pr_body = _build_pr_body(date_str, article_count, feed_stats, digest_content)

        # Create PR
        result = _run(
            [
                "gh", "pr", "create",
                "--title", f"デイリーダイジェスト: {date_str}",
                "--body", pr_body,
                "--base", "main",
            ],
            cwd=cwd,
        )
        if result.returncode != 0:
            logger.error("Failed to create PR: %s", result.stderr)
            return None

        pr_url = result.stdout.strip()
        logger.info("PR created: %s", pr_url)
        return pr_url

    finally:
        # Switch back to main branch
        _run(["git", "checkout", "main"], cwd=cwd)


def _build_pr_body(
    date_str: str,
    article_count: int,
    feed_stats: dict[str, bool] | None,
    digest_content: str = "",
) -> str:
    """Build the PR description body."""
    lines = [
        f"## デイリーニュースダイジェスト - {date_str}",
        "",
        f"- **記事数**: {article_count}件",
    ]

    if feed_stats:
        ok = sum(1 for v in feed_stats.values() if v)
        fail = sum(1 for v in feed_stats.values() if not v)
        lines.append(f"- **フィード**: {ok}件 成功、{fail}件 失敗")
        if fail > 0:
            lines.append("")
            lines.append("### 失敗したフィード")
            for name, success in feed_stats.items():
                if not success:
                    lines.append(f"- {name}")

    if digest_content:
        lines.extend(["", "---", ""])
        lines.append(digest_content)

    lines.extend([
        "",
        "---",
        "*Daily News Digest ワークフローにより自動生成*",
    ])
    return "\n".join(lines)
