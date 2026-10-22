"""Service health via a Gatus status page's public API (no key needed).

One request against ``/api/v1/endpoints/statuses`` returns every monitored
endpoint with its recent check results — enough for the current state of each
service and a short history timeline.

Each check is reduced to one of four states, the same way the status page
itself classifies them:

- ``up``   — every condition passed
- ``deg``  — only "soft" conditions failed (response time, certificate expiry):
             the service still answers correctly, just slowly or with a
             certificate that needs renewing soon
- ``down`` — any other condition failed
- ``none`` — no result yet

https://github.com/TwiN/gatus#api
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

import httpx

#: Severity order; the worst state of a set wins.
RANK = {"none": 0, "up": 1, "deg": 2, "down": 3}

# Failing only these makes a check "degraded" instead of "down".
SOFT_CONDITIONS = ("[RESPONSE_TIME]", "[CERTIFICATE_EXPIRATION]")


@dataclass
class Check:
    when: datetime  # timezone-aware (UTC)
    state: str  # up / deg / down


@dataclass
class EndpointStatus:
    key: str  # Gatus endpoint key, "<group>_<name>" sanitised
    group: str
    name: str
    checks: list[Check] = field(default_factory=list)  # oldest first

    @property
    def state(self) -> str:
        return self.checks[-1].state if self.checks else "none"


def fetch_statuses(
    base_url: str, *, page_size: int = 64, timeout: float = 10.0
) -> list[EndpointStatus]:
    """All endpoints with up to ``page_size`` recent results each."""
    resp = httpx.get(
        f"{base_url.rstrip('/')}/api/v1/endpoints/statuses",
        params={"pageSize": page_size},
        headers={"User-Agent": "lumen-py"},
        timeout=timeout,
    )
    resp.raise_for_status()
    return parse_statuses(resp.json())


def parse_statuses(payload: list[dict]) -> list[EndpointStatus]:
    endpoints = []
    for ep in payload or []:
        checks = [
            Check(when=_parse_timestamp(r["timestamp"]), state=check_state(r))
            for r in ep.get("results") or []
        ]
        checks.sort(key=lambda c: c.when)
        endpoints.append(
            EndpointStatus(
                key=ep.get("key", ""),
                group=ep.get("group") or "",
                name=ep.get("name") or ep.get("key", ""),
                checks=checks,
            )
        )
    return endpoints


def check_state(result: dict) -> str:
    """Classify one check result as up / deg / down."""
    if result.get("success"):
        return "up"
    failed = [c for c in result.get("conditionResults") or [] if not c.get("success")]
    if failed and all(c.get("condition", "").startswith(SOFT_CONDITIONS) for c in failed):
        return "deg"
    return "down"


def worst(states) -> str:
    return max(states, key=RANK.__getitem__, default="none")


def _parse_timestamp(text: str) -> datetime:
    # Gatus emits nanoseconds ("...42.765430256Z"); datetime takes microseconds.
    text = re.sub(r"(\.\d{6})\d+", r"\1", text)
    return datetime.fromisoformat(text.replace("Z", "+00:00"))
