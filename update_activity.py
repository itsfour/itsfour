"""Update the recent GitHub activity section in README.md."""

from __future__ import annotations

import html
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


GITHUB_USERNAME = os.getenv("GITHUB_USERNAME", "itsfour").strip()
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN", "").strip()
README_PATH = Path("README.md")
START_MARKER = "<!--START_SECTION:activity-->"
END_MARKER = "<!--END_SECTION:activity-->"


def get_recent_events(limit: int = 25) -> list[str]:
    """Return recent public GitHub events for the user."""
    if not GITHUB_USERNAME:
        raise RuntimeError("GITHUB_USERNAME must not be empty.")

    headers = {"Accept": "application/vnd.github+json"}
    if ACCESS_TOKEN:
        headers["Authorization"] = f"Bearer {ACCESS_TOKEN}"
    events: list[dict[str, Any]] = []
    seen_event_ids: set[str] = set()
    for page in range(1, 11):
        response = requests.get(
            f"https://api.github.com/users/{GITHUB_USERNAME}/events",
            headers=headers,
            params={"per_page": 100, "page": page},
            timeout=30,
        )
        response.raise_for_status()
        page_events = response.json()
        if not page_events:
            break
        for event in page_events:
            event_id = str(event.get("id") or "")
            if event_id and event_id in seen_event_ids:
                continue
            if event_id:
                seen_event_ids.add(event_id)
            events.append(event)

    activity_lines: list[str] = []
    for event in events:
        if len(activity_lines) >= limit:
            break
        repo_name = str((event.get("repo") or {}).get("name") or "")
        if not repo_name:
            continue
        event_type = str(event.get("type") or "")
        payload = event.get("payload") or {}
        repo_url = f"https://github.com/{repo_name}"
        icon, description, target_url = _describe_event(event_type, payload, repo_url)
        if not description:
            continue
        created_at = event.get("created_at")
        if not isinstance(created_at, str):
            raise ValueError("GitHub activity event is missing its creation time.")
        happened_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        time_label = _format_relative_time(happened_at)
        line = f"{len(activity_lines) + 1}. {icon} {description} in [{html.escape(repo_name)}]({repo_url})"
        if target_url:
            line += f" ([view]({html.escape(target_url)}))"
        line += f" <sub>· {time_label}</sub>"
        activity_lines.append(line)
    return activity_lines


def _format_relative_time(happened_at: datetime) -> str:
    """Format an event time as a short relative label, falling back to its date."""
    if happened_at.tzinfo is None:
        raise ValueError("GitHub activity event time must include a timezone.")

    elapsed = max(
        0,
        int((datetime.now(timezone.utc) - happened_at.astimezone(timezone.utc)).total_seconds()),
    )
    if elapsed < 60:
        return "just now"
    if elapsed < 3600:
        return f"{elapsed // 60}m ago"
    if elapsed < 86400:
        return f"{elapsed // 3600}h ago"
    if elapsed < 7 * 86400:
        return f"{elapsed // 86400}d ago"
    return happened_at.astimezone(timezone.utc).strftime("%b %d, %Y UTC")


def _describe_event(
    event_type: str, payload: dict[str, Any], repo_url: str
) -> tuple[str, str, str]:
    """Convert one GitHub event into an icon, description, and optional link."""
    if event_type == "PushEvent":
        ref = str(payload.get("ref") or "").removeprefix("refs/heads/")
        head = str(payload.get("head") or "")
        commits = payload.get("commits") or []
        message = ""
        if commits and isinstance(commits[0], dict):
            message = str(commits[0].get("message") or "").splitlines()[0][:100]
        description = f"Pushed [`{html.escape(head[:7])}`]({repo_url}/commit/{head}) to [`{html.escape(ref or 'main')}`]"
        if message:
            description += f" - {html.escape(message)}"
        return "📦", description, ""

    if event_type == "CreateEvent" and payload.get("ref_type") == "branch":
        branch = html.escape(str(payload.get("ref") or "main"))
        return "🌿", f"Created branch [`{branch}`]", f"{repo_url}/tree/{branch}"

    if event_type == "CreateEvent" and payload.get("ref_type") == "repository":
        return "📁", "Created repository", ""

    if event_type == "PullRequestEvent":
        pull = payload.get("pull_request") or {}
        number = pull.get("number") or payload.get("number") or "?"
        action = html.escape(str(payload.get("action") or "updated").title())
        title = html.escape(str(pull.get("title") or "pull request")[:100])
        return "🔀", f"{action} pull request #{number}: {title}", str(pull.get("html_url") or repo_url)

    if event_type == "IssuesEvent":
        issue = payload.get("issue") or {}
        number = issue.get("number") or payload.get("number") or "?"
        action = html.escape(str(payload.get("action") or "updated").title())
        title = html.escape(str(issue.get("title") or "issue")[:100])
        return "🐛", f"{action} issue #{number}: {title}", str(issue.get("html_url") or repo_url)

    if event_type == "IssueCommentEvent":
        issue = payload.get("issue") or {}
        number = issue.get("number") or "?"
        return "💬", f"Commented on issue #{number}", str(issue.get("html_url") or repo_url)

    if event_type == "WatchEvent":
        return "⭐", "Starred repository", ""

    if event_type == "ForkEvent":
        fork = payload.get("forkee") or {}
        return "🍴", "Forked repository", str(fork.get("html_url") or repo_url)

    if event_type == "ReleaseEvent":
        release = payload.get("release") or {}
        tag = html.escape(str(release.get("tag_name") or "release"))
        return "🚀", f"Published release `{tag}`", str(release.get("html_url") or repo_url)

    return "", "", ""


def update_readme(new_activities: list[str]) -> bool:
    """Replace the marked activity block and return whether it changed."""
    if not README_PATH.exists():
        raise FileNotFoundError(f"README not found: {README_PATH}")
    content = README_PATH.read_text(encoding="utf-8")
    start = content.find(START_MARKER)
    end = content.find(END_MARKER, start + len(START_MARKER))
    if start < 0 or end < 0:
        raise ValueError("README activity markers are missing or out of order.")

    activity_block = "\n".join(new_activities) if new_activities else "No recent public activity."
    new_content = content[: start + len(START_MARKER)] + "\n" + activity_block + "\n" + content[end:]
    if new_content == content:
        return False
    README_PATH.write_text(new_content, encoding="utf-8")
    return True


if __name__ == "__main__":
    activities = get_recent_events()
    print("README activity updated." if update_readme(activities) else "README activity is already current.")
