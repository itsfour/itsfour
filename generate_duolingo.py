"""Generate a Duolingo profile card from its public user endpoint."""

from __future__ import annotations

import os
from html import escape
from pathlib import Path
from typing import Any

import requests


API_URL = "https://www.duolingo.com/2017-06-30/users"
OUTPUT_PATH = Path("generated/duolingo.svg")


def fetch_profile(username: str) -> dict[str, Any]:
    """Fetch and validate the public profile data used by the card."""
    response = requests.get(
        API_URL,
        params={"username": username},
        headers={"Accept": "application/json", "User-Agent": "itsfour-profile-readme"},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()

    users = payload.get("users") if isinstance(payload, dict) else None
    if not isinstance(users, list) or len(users) != 1 or not isinstance(users[0], dict):
        raise RuntimeError(f"Duolingo returned no public profile for {username!r}.")

    profile = users[0]
    if str(profile.get("username", "")).casefold() != username.casefold():
        raise RuntimeError("Duolingo returned a profile with an unexpected username.")
    for field in ("streak", "totalXp"):
        value = profile.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise RuntimeError(f"Duolingo profile is missing a valid {field} value.")
    if not isinstance(profile.get("courses"), list):
        raise RuntimeError("Duolingo profile is missing its courses list.")

    return profile


def create_card(profile: dict[str, Any]) -> str:
    """Render a compact, dark-mode-friendly SVG profile card."""
    username = escape(str(profile["username"]))
    streak = f'{profile["streak"]:,}'
    total_xp = f'{profile["totalXp"]:,}'
    course_names = [
        str(course["title"])
        for course in profile["courses"]
        if isinstance(course, dict) and course.get("title")
    ]
    course_count = len(course_names)
    course_summary = " · ".join(course_names) if course_names else "No courses listed"
    if len(course_summary) > 58:
        course_summary = course_summary[:55].rstrip() + "..."
    course_summary = escape(course_summary)

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="760" height="248" viewBox="0 0 760 248" role="img" aria-labelledby="title description">
  <title id="title">Duolingo progress for {username}</title>
  <desc id="description">{streak} day streak, {total_xp} total XP, and {course_count} courses.</desc>
  <defs>
    <linearGradient id="background" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#10241c"/>
      <stop offset="1" stop-color="#101820"/>
    </linearGradient>
    <linearGradient id="accent" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#a5ed38"/>
      <stop offset="1" stop-color="#58cc02"/>
    </linearGradient>
  </defs>
  <rect x="1" y="1" width="758" height="246" rx="22" fill="url(#background)" stroke="#2d4438" stroke-width="2"/>
  <circle cx="76" cy="79" r="37" fill="url(#accent)"/>
  <path d="M66 98V60h22c13 0 20 7 20 19s-7 19-20 19H66zm12-10h9c6 0 9-3 9-9s-3-9-9-9h-9v18z" fill="#12351d"/>
  <text x="132" y="60" fill="#a5ed38" font-family="Segoe UI,Arial,sans-serif" font-size="13" font-weight="700" letter-spacing="2">DUOLINGO PROGRESS</text>
  <text x="132" y="88" fill="#f3f7f4" font-family="Segoe UI,Arial,sans-serif" font-size="23" font-weight="700">@{username}</text>
  <line x1="132" y1="108" x2="718" y2="108" stroke="#304238"/>
  <line x1="330" y1="126" x2="330" y2="195" stroke="#304238"/>
  <line x1="527" y1="126" x2="527" y2="195" stroke="#304238"/>
  <g font-family="Segoe UI,Arial,sans-serif">
    <text x="150" y="148" fill="#a5ed38" font-size="30" font-weight="700">{streak}</text>
    <text x="150" y="174" fill="#9aaca1" font-size="12" font-weight="700" letter-spacing="1.5">DAY STREAK</text>
    <text x="360" y="148" fill="#f3f7f4" font-size="30" font-weight="700">{total_xp}</text>
    <text x="360" y="174" fill="#9aaca1" font-size="12" font-weight="700" letter-spacing="1.5">TOTAL XP</text>
    <text x="557" y="148" fill="#f3f7f4" font-size="30" font-weight="700">{course_count}</text>
    <text x="557" y="174" fill="#9aaca1" font-size="12" font-weight="700" letter-spacing="1.5">COURSES</text>
  </g>
  <circle cx="43" cy="218" r="4" fill="#58cc02"/>
  <text x="56" y="223" fill="#c6d2ca" font-family="Segoe UI,Arial,sans-serif" font-size="13">{course_summary}</text>
</svg>
"""


def main() -> None:
    username = os.getenv("DUOLINGO_USERNAME", "").strip()
    if not username:
        raise RuntimeError("DUOLINGO_USERNAME must be set.")

    profile = fetch_profile(username)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(create_card(profile), encoding="utf-8")
    print(f"Generated {OUTPUT_PATH} for {username}.")


if __name__ == "__main__":
    main()
