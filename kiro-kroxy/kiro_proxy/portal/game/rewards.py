"""Achievement → reward_usd mapping.

Kept separate from ``achievements.py`` so balancing passes don't drag the
rule-firing code along, and so the scorecard is easy to eyeball at review
time. Values are intentionally small ($0.05 – $1.50 range) — the pool is a
real expense on our side and we'd rather drip than dump.

How the lookup works:
    slug                                 → reward_usd
    pioneer:<genre>:<ending>             → PIONEER_USD            (global first)
    collector:cg:<genre>:5/15/30         → CG_TIER_USD[threshold]
    collector:endings:<genre>            → GENRE_ENDINGS_USD
    collector:multigenre:3               → MULTIGENRE_3_USD
    collector:total:50                   → TOTAL_50_USD
    collector:total:200                  → TOTAL_200_USD
    hidden:*                             → HIDDEN_USD

Anything that doesn't match returns 0.0 — unknown slug means "not yet
monetized", not "free money exploit". The redeem endpoint refuses 0.0
rewards so adding a new rule without touching this table is safe.
"""
from __future__ import annotations

import re

# Tier/value catalogue — balance via these constants only.
PIONEER_USD = 0.20
CG_TIER_USD: dict[int, float] = {5: 0.05, 15: 0.15, 30: 0.40}
GENRE_ENDINGS_USD = 0.30
MULTIGENRE_3_USD = 0.20
TOTAL_TIER_USD: dict[int, float] = {50: 0.30, 200: 1.50}
HIDDEN_USD = 0.50


_COLLECTOR_CG_RE = re.compile(r"^collector:cg:[^:]+:(\d+)$")
_COLLECTOR_TOTAL_RE = re.compile(r"^collector:total:(\d+)$")


def _base_reward(slug: str) -> float:
    """Hardcoded fallback rewards."""
    if not slug:
        return 0.0
    if slug.startswith("pioneer:"):
        return PIONEER_USD
    m = _COLLECTOR_CG_RE.match(slug)
    if m:
        return CG_TIER_USD.get(int(m.group(1)), 0.0)
    if slug.startswith("collector:endings:"):
        return GENRE_ENDINGS_USD
    if slug == "collector:multigenre:3":
        return MULTIGENRE_3_USD
    m = _COLLECTOR_TOTAL_RE.match(slug)
    if m:
        return TOTAL_TIER_USD.get(int(m.group(1)), 0.0)
    if slug.startswith("hidden:"):
        return HIDDEN_USD
    return 0.0


# Module-level override cache — populated at startup and when admin updates.
_overrides: dict[str, float] = {}


def set_overrides(overrides: dict[str, float]) -> None:
    """Replace the in-memory override map (called at startup / admin update)."""
    global _overrides
    _overrides = dict(overrides)


def reward_for(slug: str, kind: str | None = None) -> float:
    """Return the reward in USD for a given achievement slug.

    Checks admin overrides first, then falls back to hardcoded tiers.
    Returns ``0.0`` for unrecognized slugs so the caller should treat 0
    as "not redeemable".
    """
    if not slug:
        return 0.0
    if slug in _overrides:
        return _overrides[slug]
    return _base_reward(slug)
