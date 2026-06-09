"""GitHub contributions via the GraphQL API.

One query against ``contributionsCollection.contributionCalendar`` returns the
last year of daily contribution counts — enough to derive today's count, the
current streak and the 7-day history in a single round trip.

Requires a token with no particular scope (``read:user`` is plenty):
https://docs.github.com/en/graphql
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

import httpx

GRAPHQL_URL = "https://api.github.com/graphql"

_CONTRIBUTIONS_QUERY = """\
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        weeks {
          contributionDays {
            date
            contributionCount
          }
        }
      }
    }
  }
}
"""


@dataclass
class ContributionStats:
    today: int
    streak: int
    week: list[int] = field(default_factory=list)  # per day, oldest first


def fetch_contributions(
    username: str, token: str, *, today: date, timeout: float = 10.0
) -> ContributionStats:
    """Query the contributions calendar for ``username`` and reduce it to stats."""
    resp = httpx.post(
        GRAPHQL_URL,
        json={"query": _CONTRIBUTIONS_QUERY, "variables": {"login": username}},
        headers={
            "Authorization": f"Bearer {token}",
            "User-Agent": "lumen-py",
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("errors"):
        raise RuntimeError(f"GitHub GraphQL: {payload['errors'][0].get('message')}")
    user = payload.get("data", {}).get("user")
    if user is None:
        raise RuntimeError(f"GitHub GraphQL: unknown user {username!r}")
    days = parse_calendar(user["contributionsCollection"]["contributionCalendar"])
    return contribution_stats(days, today)


def parse_calendar(calendar: dict) -> dict[date, int]:
    """Flatten the weeks/contributionDays structure into ``{date: count}``."""
    days: dict[date, int] = {}
    for week in calendar.get("weeks", []):
        for day in week.get("contributionDays", []):
            days[date.fromisoformat(day["date"])] = int(day["contributionCount"])
    return days


def contribution_stats(days: dict[date, int], today: date) -> ContributionStats:
    week = [days.get(today - timedelta(days=6 - i), 0) for i in range(7)]
    return ContributionStats(today=days.get(today, 0), streak=_streak(days, today), week=week)


def _streak(days: dict[date, int], today: date) -> int:
    # Today doesn't break the streak while it's still in progress: a 0 today
    # just means "not yet", so counting starts from yesterday in that case.
    d = today if days.get(today, 0) > 0 else today - timedelta(days=1)
    n = 0
    while days.get(d, 0) > 0:
        n += 1
        d -= timedelta(days=1)
    return n
