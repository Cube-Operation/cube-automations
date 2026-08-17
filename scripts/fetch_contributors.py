#!/usr/bin/env python3
"""Fetch CubeSandbox contributors from the GitHub API and write data/contributors.json."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

GITHUB_OWNER = "tencentcloud"
GITHUB_REPO = "CubeSandbox"
GITHUB_API_BASE = "https://api.github.com"
OUTPUT_PATH = Path("data/contributors.json")
ACTIVE_CONFIG_PATH = Path("config/active-contributors.yml")
DEFAULT_ACTIVE_THRESHOLD = 10
USER_AGENT = "cube-automations-contributors"

BOT_LOGINS = {
    "dependabot",
    "dependabot[bot]",
    "github-actions",
    "github-actions[bot]",
    "copilot",
    "copilot[bot]",
    "web-flow",
    "renovate",
    "renovate[bot]",
    "imgbot",
    "imgbot[bot]",
}


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def github_headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": USER_AGENT,
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def parse_next_link(link_header: str | None) -> str | None:
    if not link_header:
        return None
    for part in link_header.split(","):
        section = part.strip()
        if 'rel="next"' not in section:
            continue
        start = section.find("<")
        end = section.find(">", start)
        if start != -1 and end != -1:
            return section[start + 1 : end]
    return None


def github_get(url: str) -> tuple[Any, str | None]:
    request = urllib.request.Request(url, headers=github_headers(), method="GET")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            body = json.loads(response.read().decode("utf-8"))
            return body, response.headers.get("Link")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"GitHub API error {exc.code} for {url}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"GitHub API request failed for {url}: {exc}") from exc


def fetch_repo() -> dict[str, Any]:
    url = f"{GITHUB_API_BASE}/repos/{GITHUB_OWNER}/{GITHUB_REPO}"
    body, _ = github_get(url)
    if not isinstance(body, dict):
        raise SystemExit(f"Unexpected repo payload from {url}")
    return body


def fetch_contributors() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    url: str | None = (
        f"{GITHUB_API_BASE}/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contributors"
        f"?{urllib.parse.urlencode({'per_page': 100})}"
    )
    while url:
        body, link = github_get(url)
        if not isinstance(body, list):
            raise SystemExit(f"Unexpected contributors payload from {url}")
        items.extend(item for item in body if isinstance(item, dict))
        url = parse_next_link(link)
    return items


def is_bot(item: dict[str, Any]) -> bool:
    if item.get("type") == "Bot":
        return True
    login = str(item.get("login") or "").strip()
    if not login:
        return True
    lowered = login.lower()
    return lowered.endswith("[bot]") or lowered in BOT_LOGINS


def fetch_user(login: str) -> dict[str, Any] | None:
    url = f"{GITHUB_API_BASE}/users/{urllib.parse.quote(login)}"
    try:
        body, _ = github_get(url)
    except SystemExit:
        print(f"warning: failed to fetch forced active contributor {login}, skipped")
        return None
    return body if isinstance(body, dict) else None


def load_active_config(root: Path) -> tuple[int, list[str]]:
    """Read config/active-contributors.yml -> (threshold, forced logins)."""
    path = root / ACTIVE_CONFIG_PATH
    if not path.is_file():
        return DEFAULT_ACTIVE_THRESHOLD, []
    try:
        import yaml
    except ImportError:
        raise SystemExit(
            "PyYAML is required to read config/active-contributors.yml: "
            "pip install -r requirements.txt"
        )
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise SystemExit(f"{ACTIVE_CONFIG_PATH}: top level must be a mapping")

    threshold = data.get("threshold", DEFAULT_ACTIVE_THRESHOLD)
    if not isinstance(threshold, int) or isinstance(threshold, bool) or threshold < 1:
        print(f"warning: invalid threshold {threshold!r}, using {DEFAULT_ACTIVE_THRESHOLD}")
        threshold = DEFAULT_ACTIVE_THRESHOLD

    force = data.get("force") or []
    if not isinstance(force, list):
        raise SystemExit(f"{ACTIVE_CONFIG_PATH}: 'force' must be a list of logins")
    forced = []
    for item in force:
        login = str(item or "").strip()
        if login and login.lower() not in {x.lower() for x in forced}:
            forced.append(login)
    return threshold, forced


def split_active_contributors(
    contributors: list[dict[str, Any]], threshold: int, forced: list[str]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split into (active, rest). Forced logins are always active; anyone
    active never appears in the rest list."""
    forced_lower = {login.lower() for login in forced}
    active: list[dict[str, Any]] = []
    rest: list[dict[str, Any]] = []
    for row in contributors:
        if row["contributions"] >= threshold or row["login"].lower() in forced_lower:
            active.append(row)
        else:
            rest.append(row)

    # forced logins missing from the contributor list count as 1 contribution
    known = {row["login"].lower() for row in contributors}
    for login in forced:
        if login.lower() in known:
            continue
        profile = fetch_user(login)
        if profile is None:
            continue
        html_url = str(profile.get("html_url") or "").strip()
        if not html_url:
            continue
        active.append(
            {
                "login": str(profile.get("login") or login),
                "htmlUrl": html_url,
                "avatarUrl": str(profile.get("avatar_url") or "").strip(),
                "contributions": 1,
            }
        )

    by_rank = lambda row: (-row["contributions"], row["login"].lower())  # noqa: E731
    active.sort(key=by_rank)
    rest.sort(key=by_rank)
    return active, rest


def semantic_payload(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "repo": data.get("repo"),
        "htmlUrl": data.get("htmlUrl"),
        "stats": data.get("stats"),
        "activeContributors": data.get("activeContributors"),
        "contributors": data.get("contributors"),
    }


def load_existing(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def main() -> int:
    root = repo_root()
    output = root / OUTPUT_PATH

    repo = fetch_repo()
    raw_contributors = fetch_contributors()

    contributors = []
    for item in raw_contributors:
        if is_bot(item):
            continue
        login = str(item.get("login") or "").strip()
        html_url = str(item.get("html_url") or "").strip()
        avatar_url = str(item.get("avatar_url") or "").strip()
        contributions = item.get("contributions")
        if not login or not html_url:
            continue
        if not isinstance(contributions, int):
            continue
        contributors.append(
            {
                "login": login,
                "htmlUrl": html_url,
                "avatarUrl": avatar_url,
                "contributions": contributions,
            }
        )

    contributors.sort(key=lambda row: (-row["contributions"], row["login"].lower()))
    commits = sum(row["contributions"] for row in contributors)
    stars = repo.get("stargazers_count")
    if not isinstance(stars, int):
        stars = 0

    threshold, forced = load_active_config(root)
    active, rest = split_active_contributors(contributors, threshold, forced)

    payload = {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repo": f"{GITHUB_OWNER}/{GITHUB_REPO}",
        "htmlUrl": str(repo.get("html_url") or f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}"),
        "stats": {
            # 墙上实际展示的总人数（活跃 + 其他），含 force 进来的编外成员
            "contributors": len(active) + len(rest),
            "commits": commits,
            "stars": stars,
        },
        "activeContributors": active,
        "contributors": rest,
    }

    existing = load_existing(output)
    if existing is not None and semantic_payload(existing) == semantic_payload(payload):
        print(f"{output.relative_to(root)} unchanged, skip write")
        return 0

    output.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    output.write_text(text, encoding="utf-8")
    print(
        f"wrote {output.relative_to(root)}: "
        f"{len(active)} active, "
        f"{len(rest)} other contributors, "
        f"{payload['stats']['commits']} commits, "
        f"{payload['stats']['stars']} stars"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
