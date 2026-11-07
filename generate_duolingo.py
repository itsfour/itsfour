"""Generate the Duolingo profile card by filling its SVG template."""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any

import requests

API_URL = "https://www.duolingo.com/2017-06-30/users"
TEMPLATE_PATH = Path("templates/duolingo.svg")
OUTPUT_PATH = Path("generated/duolingo.svg")
COURSE_CHIPS_PATTERN = re.compile(
    r"<!-- COURSE_CHIPS_START -->.*?<!-- COURSE_CHIPS_END -->", re.DOTALL
)
SIGNED_METADATA_PATTERN = re.compile(
    r"<metadata(?:\s[^>]*)?>.*?</metadata>\s*", re.DOTALL
)


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
    for field in ("streak", "totalXp", "creationDate"):
        value = profile.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise RuntimeError(f"Duolingo profile is missing a valid {field} value.")
    if not isinstance(profile.get("courses"), list):
        raise RuntimeError("Duolingo profile is missing its courses list.")

    return profile


def compact_xp(value: int) -> str:
    """Format large XP values to fit the narrow stat card."""
    if value < 1_000:
        return f"{value:,}"
    compact = f"{value / 1_000:.1f}".rstrip("0").rstrip(".")
    return f"{compact}k"


def create_course_chips(courses: list[dict[str, Any]]) -> str:
    """Fill the three course-chip slots in the SVG design."""
    slots = (
        (215, 86, 258, "#58cc02"),
        (309, 92, 355, "#1cb0f6"),
        (409, 80, 449, "#ce82ff"),
    )
    chips = []
    for course, (x, width, center, color) in zip(courses[:3], slots):
        title = str(course["title"])
        label = title if len(title) <= 12 else f"{title[:9].rstrip()}…"
        chips.append(
            f'<rect x="{x}" y="112" width="{width}" height="28" rx="14" fill="{color}"/>'
            f'<text class="chip" x="{center}" y="131" text-anchor="middle" '
            f'textLength="{width - 12}" lengthAdjust="spacingAndGlyphs">'
            f"<title>{escape(title)}</title>{escape(label)}</text>"
        )
    return "\n    ".join(chips)


def create_card(profile: dict[str, Any]) -> str:
    """Fill the template with live values without changing its visual design."""
    if not TEMPLATE_PATH.is_file():
        raise FileNotFoundError(f"Duolingo SVG template not found: {TEMPLATE_PATH}")

    username = str(profile["username"])
    name = str(profile.get("name") or username)
    courses = [
        course
        for course in profile["courses"]
        if isinstance(course, dict) and isinstance(course.get("title"), str)
    ]
    english_course = next(
        (
            course
            for course in courses
            if str(course.get("learningLanguage", "")).casefold() == "en"
            or str(course["title"]).casefold() == "english"
        ),
        None,
    )
    english_xp_value = english_course.get("xp", 0) if english_course else 0
    if (
        not isinstance(english_xp_value, int)
        or isinstance(english_xp_value, bool)
        or english_xp_value < 0
    ):
        raise RuntimeError("Duolingo profile has an invalid English course XP value.")

    total_xp = profile["totalXp"]
    english_share = round(english_xp_value / total_xp * 100) if total_xp else 0
    english_bar_width = (
        min(561, max(0, english_xp_value / total_xp * 561)) if total_xp else 0
    )
    joined = datetime.fromtimestamp(profile["creationDate"], timezone.utc).strftime(
        "%b %Y"
    )

    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    chips_match = COURSE_CHIPS_PATTERN.search(template)
    if not chips_match:
        raise ValueError("Duolingo SVG template is missing its course-chip markers.")
    template = COURSE_CHIPS_PATTERN.sub(
        lambda _: create_course_chips(courses), template, count=1
    )

    replacements = {
        "__NAME__": escape(name),
        "__USERNAME__": escape(username),
        "__JOINED__": joined,
        "__ENGLISH_XP__": f"{english_xp_value:,}",
        "__ENGLISH_SHARE__": str(english_share),
        "__ENGLISH_BAR_WIDTH__": f"{english_bar_width:.1f}",
        "__STREAK__": f'{profile["streak"]:,}',
        "__TOTAL_XP_SHORT__": compact_xp(total_xp),
    }
    for placeholder, value in replacements.items():
        template = template.replace(placeholder, value)

    if re.search(r"__[A-Z0-9_]+__", template):
        raise ValueError("Duolingo SVG template contains an unfilled placeholder.")

    template, metadata_count = SIGNED_METADATA_PATTERN.subn("", template, count=1)
    if metadata_count:
        template = re.sub(r'\s+xmlns:c2pa="[^"]+"', "", template, count=1)

    return template


def main() -> None:
    username = os.getenv("DUOLINGO_USERNAME", "").strip()
    if not username:
        raise RuntimeError("DUOLINGO_USERNAME must be set.")

    profile = fetch_profile(username)
    card = create_card(profile)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(card, encoding="utf-8")
    print(f"Generated {OUTPUT_PATH} for {username} from {TEMPLATE_PATH}.")


if __name__ == "__main__":
    main()
